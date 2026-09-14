"""``vs2.store`` -- a small JSON document per game, saved when the game says so.

See "``vs2.store``" in ``docs/vs2-behaviors-proposal.md`` for the design this
implements. In short::

    vs2.store["hiscore"] = max(vs2.store.get("hiscore", 0), self.score)
    vs2.store["song"] = self.sonidito.to_dict()
    vs2.store.save()

This module is standalone: it does not import from ``vs2/__init__.py``. A
later task wires the module-level :data:`store` singleton in as the
``vs2.store`` attribute, not the other way around.

Design notes
------------

**Lazy, per-app, never a game-chosen filename.** A :class:`Store` does not
touch the filesystem until its first dict-style access. At that point it asks
``ventilastation.api_guard.current_app()`` for the running app's slug (its
dotted ``"<group>.<name>"`` form, e.g. ``"alecu.vixeous"`` for a game, or
``"system.<name>"`` for a system app -- see ``app_loader.slug_to_parts``) and
loads ``<saves-root>/<slug>.json``. Nothing about the path is game-supplied.
If the current app changes (the launcher swaps games), the next access
re-binds to the new app's own document -- any unsaved change under the old
slug is simply dropped, the same way any other explicit-save API drops
unsaved edits when you navigate away without saving.

**It is a file, deliberately not NVS.** See the proposal for why: NVS is a
shared 16 kB partition also holding POV calibration and OTA state, and a full
NVS should never be a possible side effect of a game's high-score table. The
``saves`` directory sits next to ``games`` and ``system`` (not inside any
game's own directory, which installers and updaters delete and replace
wholesale), resolved the same way ``ventilastation.app_loader`` resolves
``GAMES_ROOT``/``SYSTEM_ROOT``: relative to whichever directory the running
process already treats as the project root, so the identical relative path
resolves correctly on-device (root of the on-device filesystem), under the
desktop unix-port emulator (repo checkout as cwd) and inside the browser's
MicroPython-in-WASM runtime (which virtualizes the same relative filesystem
and persists it to IndexedDB on its own -- nothing store-specific needed
there).

**Never raises, except the size-cap tripwire in save().** A missing
directory, a corrupt file, a full or read-only filesystem: every filesystem
failure is caught and silently leaves an in-memory dict in place so the game
keeps running. ``save()`` is the sole exception, and only for its own size
cap -- a guard against a game accidentally writing every tick, not a
filesystem condition, so it is allowed to be loud.

**Shallow dirty tracking.** Only the top-level mapping operations
(``store[k] = v``, ``del store[k]``, ``update``, ``pop``, ``setdefault``,
``clear``) mark the document dirty. Mutating a nested value in place (e.g.
``store["song"]["tempo"] = 4``) is invisible to the store -- replace the
whole value instead, as the module docstring's own example does.
"""

try:
    import ujson as json
except ImportError:
    import json

try:
    import uos as os
except ImportError:
    import os

from ventilastation import api_guard

# Tripwire only: catches a game writing something unbounded (or per-tick) by
# mistake. Not a partition limit -- the vfs partition is 8.75 MB, this is just
# meant to be generous for a hiscore table or a few settings and stingy for
# anything that grows on its own. Approximate (character count of the encoded
# JSON, not a strict UTF-8 byte count) -- good enough for a tripwire.
MAX_BYTES = 4096

# Sentinel distinct from any real slug (including the legitimate "no app is
# current" state, which is None) so a freshly constructed Store always rebinds
# on its first access.
_UNBOUND = object()


def _saves_root():
    """Directory that holds every app's saved document, resolved the same
    way ``ventilastation.app_loader`` resolves ``GAMES_ROOT``: relative to
    wherever "games" already lives from the current process's point of view.
    Re-implemented locally (rather than imported from app_loader) so that
    importing this module -- and constructing a Store -- never pulls in
    app_loader's own imports of the hardware-touching director/native_apps
    modules.
    """
    try:
        os.stat("games")
        project_root = ""
    except OSError:
        project_root = "../.."
    return (project_root + "/saves") if project_root else "saves"


def _path_for_slug(slug):
    if not slug:
        return None
    return _saves_root() + "/" + slug + ".json"


def _makedirs(path):
    """Best-effort recursive mkdir for every directory component of ``path``
    but the last (the file itself). Mirrors ``updater.py``'s ``_makedirs``:
    MicroPython's ``os.mkdir`` isn't recursive, and an OSError -- "already
    exists" just as much as "permission denied" on a read-only filesystem --
    is swallowed per segment. The caller's subsequent ``open()`` is what
    actually decides whether the write can proceed.
    """
    prefix = "/" if path.startswith("/") else ""
    parts = path.strip("/").split("/")[:-1]
    current = ""
    for part in parts:
        current = current + "/" + part if current else part
        try:
            os.mkdir(prefix + current)
        except OSError:
            pass


class Store:
    """A JSON document scoped to the current app. See the module docstring."""

    def __init__(self):
        self._slug = _UNBOUND
        self._data = {}
        self._path = None
        self._dirty = False

    # -- binding ----------------------------------------------------------

    def _ensure_loaded(self):
        slug = api_guard.current_app()
        if slug != self._slug:
            self._rebind(slug)

    def _rebind(self, slug):
        self._slug = slug
        self._path = _path_for_slug(slug)
        self._data = self._read(self._path) if self._path else {}
        self._dirty = False

    @staticmethod
    def _read(path):
        # Best-effort like the LFS hash cache in updater.py: a missing
        # directory, a missing file, corrupt JSON, or anything else wrong
        # with it just means "no saved document yet" -- never worth failing
        # the game over.
        try:
            with open(path) as handle:
                data = json.load(handle)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    # -- persistence --------------------------------------------------------

    def save(self):
        """Write the document if it changed since the last successful save.
        No-ops when clean, and when there is no current app to save against
        (nothing safe to name the file after). Raises only for the
        :data:`MAX_BYTES` tripwire -- every filesystem failure is caught,
        logged, and left for a later save() to retry; the in-memory document
        and its dirty flag are untouched either way.
        """
        self._ensure_loaded()
        if not self._dirty or self._path is None:
            return
        encoded = json.dumps(self._data)
        if len(encoded) > MAX_BYTES:
            raise ValueError(
                "vs2.store: document is %d bytes, over the %d-byte cap "
                "(likely a per-tick write)" % (len(encoded), MAX_BYTES)
            )
        try:
            _makedirs(self._path)
            tmp_path = self._path + ".tmp"
            with open(tmp_path, "w") as handle:
                handle.write(encoded)
            os.rename(tmp_path, self._path)
        except OSError as error:
            print("vs2.store: save failed for", self._path, "-", error)
            return
        self._dirty = False

    # -- mapping protocol -----------------------------------------------------

    def __getitem__(self, key):
        self._ensure_loaded()
        return self._data[key]

    def __setitem__(self, key, value):
        self._ensure_loaded()
        self._data[key] = value
        self._dirty = True

    def __delitem__(self, key):
        self._ensure_loaded()
        del self._data[key]
        self._dirty = True

    def __contains__(self, key):
        self._ensure_loaded()
        return key in self._data

    def __len__(self):
        self._ensure_loaded()
        return len(self._data)

    def __iter__(self):
        self._ensure_loaded()
        return iter(self._data)

    def get(self, key, default=None):
        self._ensure_loaded()
        return self._data.get(key, default)

    def setdefault(self, key, default=None):
        self._ensure_loaded()
        if key not in self._data:
            self._dirty = True
        return self._data.setdefault(key, default)

    def pop(self, key, *args):
        self._ensure_loaded()
        if key in self._data:
            self._dirty = True
        return self._data.pop(key, *args)

    def update(self, *args, **kwargs):
        self._ensure_loaded()
        self._data.update(*args, **kwargs)
        self._dirty = True

    def clear(self):
        self._ensure_loaded()
        if self._data:
            self._dirty = True
        self._data.clear()

    def keys(self):
        self._ensure_loaded()
        return self._data.keys()

    def values(self):
        self._ensure_loaded()
        return self._data.values()

    def items(self):
        self._ensure_loaded()
        return self._data.items()


# The ready-made singleton a later task exposes as ``vs2.store``.
store = Store()
