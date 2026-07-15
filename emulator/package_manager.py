"""Base-side storage of installed game packages (.vs2).

Packages stay zipped in installed_packages/ and are decompressed only when
needed: audio.py extracts their sounds into a cache to play them, and
get_board_file() derives the stripped .no-sound.vs2 the board installs.
installed_packages/ sits outside every OTA manifest root on purpose --
packages are not part of the system OTA (see docs/internals/ota.md); they
reach the board only through the targeted install_start flow.

Layout of a .vs2 (built by tools/package_game.py or the web editor):
    meta.json, menu.png, code/**.py, roms/<slug>.rom, menu-icon.rom,
    sounds/*.mp3
Stripped .no-sound.vs2 members are device paths (minus the leading "/"),
except menu-icon.rom which the board merges into its menu rom instead of
extracting:
    games/<group>/<name>/meta.json, games/<group>/<name>/code/**.py,
    roms/<slug>.rom.gz (STORE, pre-gzipped), menu-icon.rom

Everything here is import-light (stdlib only) so the standalone
upgrade_server keeps working without the emulator's dependencies.
"""

import gzip
import hashlib
import io
import json
import pathlib
import re
import threading
import zipfile

_VSDK_ROOT = pathlib.Path(__file__).resolve().parent.parent

PACKAGES_DIR = _VSDK_ROOT / "installed_packages"
BOARD_FILES_DIR = _VSDK_ROOT / "build" / "base" / "board_files"

PACKAGE_SUFFIX = ".vs2"
BOARD_SUFFIX = ".no-sound.vs2"

_SLUG_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)

_lock = threading.Lock()

# One record per slug: {"state": uploaded|triggered|serving|installing|
# done|error, "stage", "detail", "pct", "message"}. comms.py feeds it from
# the board's install_* lines; the editor polls it via the status endpoint.
install_status = {}


class PackageError(Exception):
    pass


def set_install_status(slug, state, **fields):
    with _lock:
        record = dict(install_status.get(slug) or {})
        record["state"] = state
        record.update(fields)
        install_status[slug] = record


def get_install_status(slug):
    with _lock:
        return dict(install_status.get(slug) or {"state": "unknown"})


# The board's install_progress/install_error lines don't carry a slug, so
# track which install is in flight (only one can be: the board reboots into
# install mode). comms.py feeds these from the serial link.
_active_slug = None


def note_install_triggered(slug):
    global _active_slug
    _active_slug = slug
    set_install_status(slug, "triggered")


def note_install_progress(stage, detail, pct):
    if _active_slug:
        set_install_status(_active_slug, "installing",
                           stage=stage, detail=detail, pct=pct)


def note_install_done(slug):
    global _active_slug
    set_install_status(slug, "done")
    if _active_slug == slug:
        _active_slug = None


def note_install_error(message):
    global _active_slug
    if _active_slug:
        set_install_status(_active_slug, "error", message=message)
        _active_slug = None


def split_slug(slug):
    if not _SLUG_RE.match(slug):
        raise PackageError("bad slug: %r" % slug)
    return slug.split(".", 1)


def package_path(slug):
    return PACKAGES_DIR / (slug + PACKAGE_SUFFIX)


def validate_package(slug, data):
    """Check the member layout at upload time, so both the audio/menu
    consumers here and the board-side installer can trust it later."""
    split_slug(slug)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise PackageError("not a zip: %s" % error)
    with archive:
        names = archive.namelist()
        has_code = False
        for name in names:
            if name.endswith("/"):
                continue
            if name.startswith("/") or ".." in name.split("/"):
                raise PackageError("unsafe member path: %s" % name)
            if name.startswith("code/") and name.endswith(".py"):
                has_code = True
            elif name in ("meta.json", "menu.png", "menu-icon.rom"):
                pass
            elif name.startswith("sounds/"):
                pass
            elif name.startswith("roms/"):
                if name != "roms/%s.rom" % slug:
                    raise PackageError(
                        "rom member %s doesn't match slug %s" % (name, slug))
            else:
                raise PackageError("unexpected member: %s" % name)
        if "meta.json" not in names:
            raise PackageError("missing meta.json")
        if not has_code:
            raise PackageError("missing code/*.py")
        try:
            meta = json.loads(archive.read("meta.json"))
        except ValueError as error:
            raise PackageError("bad meta.json: %s" % error)
        if not isinstance(meta, dict):
            raise PackageError("meta.json must hold an object")
    return meta


def save_package(slug, data):
    """Validate and store an uploaded package; returns its meta.json dict."""
    meta = validate_package(slug, data)
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    final = package_path(slug)
    tmp = final.with_suffix(final.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(final)
    # The cached stripped file is keyed on mtimes; drop it eagerly anyway so
    # a same-second re-upload can't serve the previous build.
    board_file = BOARD_FILES_DIR / (slug + BOARD_SUFFIX)
    try:
        board_file.unlink()
    except OSError:
        pass
    set_install_status(slug, "uploaded")
    return meta


def iter_package_paths():
    if not PACKAGES_DIR.is_dir():
        return []
    return sorted(PACKAGES_DIR.glob("*" + PACKAGE_SUFFIX))


def list_packages():
    packages = []
    for path in iter_package_paths():
        slug = path.name[:-len(PACKAGE_SUFFIX)]
        entry = {"slug": slug, "size": path.stat().st_size}
        try:
            with zipfile.ZipFile(path) as archive:
                meta = json.loads(archive.read("meta.json"))
            if isinstance(meta, dict) and "title" in meta:
                entry["title"] = meta["title"]
        except Exception:
            pass
        entry["status"] = get_install_status(slug)
        packages.append(entry)
    return packages


def _build_board_file(slug, source_path):
    group, name = split_slug(slug)
    device_prefix = "games/%s/%s/" % (group, name)
    out = io.BytesIO()
    with zipfile.ZipFile(source_path) as source, \
            zipfile.ZipFile(out, "w") as stripped:

        def add(arcname, payload, compress_type=zipfile.ZIP_DEFLATED):
            info = zipfile.ZipInfo(arcname, date_time=_ZIP_DATE_TIME)
            info.compress_type = compress_type
            info.external_attr = 0o644 << 16
            stripped.writestr(info, payload)

        for member in source.namelist():
            if member.endswith("/"):
                continue
            if member == "meta.json" or (
                    member.startswith("code/") and member.endswith(".py")):
                add(device_prefix + member, source.read(member))
            elif member == "roms/%s.rom" % slug:
                # Pre-gzipped like the flashed image (the board can't
                # compress); already-compressed data is STOREd in the zip.
                payload = gzip.compress(source.read(member),
                                        compresslevel=9, mtime=0)
                add(member + ".gz", payload, zipfile.ZIP_STORED)
            elif member == "menu-icon.rom":
                add(member, source.read(member))
            # menu.png and sounds/* stay on the base.
    return out.getvalue()


def get_board_file(slug):
    """The stripped .no-sound.vs2 for one installed package, built on demand
    and cached on disk. Returns (bytes, sha256_hex, size)."""
    source_path = package_path(slug)
    if not source_path.is_file():
        raise PackageError("no such package: %s" % slug)

    cache_path = BOARD_FILES_DIR / (slug + BOARD_SUFFIX)
    with _lock:
        if (cache_path.is_file()
                and cache_path.stat().st_mtime_ns >= source_path.stat().st_mtime_ns):
            data = cache_path.read_bytes()
        else:
            data = _build_board_file(slug, source_path)
            BOARD_FILES_DIR.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(cache_path)
    return data, hashlib.sha256(data).hexdigest(), len(data)
