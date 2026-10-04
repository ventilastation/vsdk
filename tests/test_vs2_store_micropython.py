"""Smoke ``vs2/store.py`` on the MicroPython unix runtime itself.

Imports the module directly (not through the ``vs2`` package) since store.py
is a standalone module with no dependency on ``vs2/__init__.py`` -- this
keeps the smoke test fast and confirms that independence rather than
incidentally exercising the whole package's import side effects.

Runs against a scratch directory under /tmp containing only a "games" marker,
never the real repo checkout, so nothing here writes into the working tree.
"""

import sys

sys.path.insert(0, "apps/micropython")
sys.path.insert(0, "apps/micropython/vs2")

import uos as os

from ventilastation import api_guard
import store as vs2_store


def main():
    old_cwd = os.getcwd()
    scratch = "/tmp/vs2_store_micropython_test"
    try:
        os.stat(scratch)
        _rmtree(scratch)
    except OSError:
        pass
    os.mkdir(scratch)
    os.mkdir(scratch + "/games")
    os.chdir(scratch)

    try:
        api_guard.reset()

        # A game that never touches the store performs no filesystem access.
        api_guard.begin_app("games.probe", "vs2")
        vs2_store.Store()
        assert not _exists("saves")

        # Round-trips a nested document.
        api_guard.begin_app("alecu.smoketest", "vs2")
        store = vs2_store.Store()
        store["hiscore"] = 5
        store["song"] = {"tempo": 120, "notes": [1, 2, 3]}
        store.save()
        assert _exists("saves/alecu.smoketest.json")

        reloaded = vs2_store.Store()
        assert reloaded["hiscore"] == 5
        assert reloaded["song"] == {"tempo": 120, "notes": [1, 2, 3]}

        # save() twice with no change writes once. MicroPython's built-in
        # uos doesn't allow monkeypatching (its attribute table is fixed),
        # so prove the no-op directly: remove the file save() just wrote,
        # then call save() again on the still-clean store -- if it were
        # writing unconditionally the file would reappear.
        os.remove("saves/alecu.smoketest.json")
        reloaded.save()
        assert not _exists("saves/alecu.smoketest.json"), "clean save() must not write"

        # Corrupt file falls back to in-memory and keeps going.
        api_guard.begin_app("games.corrupt", "vs2")
        with open("saves/games.corrupt.json", "w") as handle:
            handle.write("{not valid json")
        broken = vs2_store.Store()
        assert dict(broken.items()) == {}
        broken["ok"] = True
        broken.save()

        # Missing directory falls back to in-memory and keeps going.
        api_guard.begin_app("games.missingdir", "vs2")
        _rmtree("saves")
        missing = vs2_store.Store()
        assert len(missing) == 0
        missing["x"] = 1  # does not raise

        # Never writes inside games/.
        assert _list_files(scratch + "/games") == []

        api_guard.reset()
        print("vs2.store micropython smoke: passed")
    finally:
        os.chdir(old_cwd)
        _rmtree(scratch)


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _list_files(path):
    found = []
    for name, kind, *_rest in os.ilistdir(path):
        full = path + "/" + name
        if kind & 0x4000:  # stat.S_IFDIR
            found.extend(_list_files(full))
        else:
            found.append(full)
    return found


def _rmtree(path):
    try:
        entries = list(os.ilistdir(path))
    except OSError:
        return
    for name, kind, *_rest in entries:
        full = path + "/" + name
        if kind & 0x4000:
            _rmtree(full)
        else:
            os.remove(full)
    os.rmdir(path)


if __name__ == "__main__":
    main()
