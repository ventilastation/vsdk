"""Single-game package installer (.no-sound.vs2).

Runs at early boot from main.py's _check_install_boot() -- the same
network window the OTA updater uses, because WiFi and the GPU share the
SPI bus and can only run one at a time. Unlike the updater's full-manifest
sync, this fetches exactly one file: the stripped package named in
/install_request, which director.py writes when the base sends

    install_start <url> <sha256> <size>

The fetched package is kept in /packages/ (it is the board's record of the
install, and refresh_from_packages() re-merges menu icons from it after a
system OTA). Its game files extract to /games/<group>/<name>/ -- staged
under a dot-directory first so an interrupted install never leaves a
half-written game where the launcher's catalog would discover it -- and
its rom lands in /roms/. An existing installation of the same game is an
upgrade: the previous game directory and rom are deleted before the staged
tree is renamed into place.

Lives on the vfs (not frozen): recovery never needs it, and tier-1 OTA can
update it. Network plumbing is reused from the frozen updater module.

Progress mirrors the ota_* family over the comms channel:
    install_progress <stage> <detail> <pct>
    install_done <slug>
    install_error <message>
"""

try:
    import uos as os
except ImportError:
    import os

import binascii
import hashlib

from ventilastation import menurom
from ventilastation import vszip

PACKAGES_DIR = "/packages"
ICON_MEMBER = "menu-icon.rom"
# LittleFS needs headroom for metadata blocks and the copy-on-write of the
# rename step; refuse installs that would leave less than this free.
_FREE_SPACE_MARGIN = 64 * 1024

_send_fn = None


def _send(line):
    if _send_fn:
        _send_fn(line.encode() if isinstance(line, str) else line)


def _progress(stage, detail, pct):
    _send("install_progress %s %s %d\n" % (stage, detail, pct))


def _error(message):
    print("installer:", message)
    _send("install_error %s\n" % message)


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _ilistdir(path):
    """(name, type) pairs; MicroPython's os.ilistdir or a CPython shim."""
    if hasattr(os, "ilistdir"):
        return os.ilistdir(path)
    return [(entry.name, 0x4000 if entry.is_dir() else 0x8000)
            for entry in os.scandir(path)]


def _rmtree(path):
    try:
        entries = list(_ilistdir(path))
    except OSError:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    for entry in entries:
        full = path + "/" + entry[0]
        if entry[1] == 0x4000:
            _rmtree(full)
        else:
            try:
                os.remove(full)
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def _makedirs(path):
    """Create every directory leading up to (and including) path. Handles
    absolute device paths and relative ones (test roots) alike."""
    current = "/" if path.startswith("/") else ""
    for part in path.split("/"):
        if not part:
            continue
        current = current + part
        try:
            os.mkdir(current)
        except OSError:
            pass
        current = current + "/"


def _game_prefix(names):
    """The single games/<group>/<name> prefix all game members share."""
    prefix = None
    for name in names:
        if name.startswith("/") or ".." in name.split("/"):
            raise ValueError("unsafe member path: %s" % name)
        if not name.startswith("games/"):
            continue
        parts = name.split("/")
        if len(parts) < 4:
            raise ValueError("bad game member path: %s" % name)
        this_prefix = "/".join(parts[:3])
        if prefix is None:
            prefix = this_prefix
        elif prefix != this_prefix:
            raise ValueError("package holds more than one game")
    if prefix is None:
        raise ValueError("package holds no game files")
    return prefix


def _check_free_space(package, names, root):
    needed = sum(package.size(name) for name in names) + _FREE_SPACE_MARGIN
    try:
        stats = os.statvfs(root if root else "/")
        free = stats[1] * stats[4]
    except (OSError, AttributeError):
        return
    if free < needed:
        raise OSError("no_space need=%d free=%d" % (needed, free))


def install_from_file(package_path, root=""):
    """Install a fetched .no-sound.vs2. root prefixes every device path so
    tests can run against a scratch directory. Returns the game slug."""
    with vszip.ZipReader(package_path) as package:
        names = package.names()
        prefix = _game_prefix(names)
        _group, game_name = prefix.split("/")[1:3]
        slug = _group + "." + game_name
        _progress("checking", slug, 0)
        _check_free_space(package, names, root)

        # Stage everything before touching the old installation.
        staging = root + "/games/%s/.%s.new" % (_group, game_name)
        _rmtree(staging)
        rom_renames = []
        for name in names:
            if name.endswith("/"):
                continue  # explicit directory entry
            if name.startswith("games/"):
                dest = staging + name[len(prefix):]
            elif name.startswith("roms/"):
                final = root + "/" + name
                dest = final + ".tmp"
                rom_renames.append((dest, final))
            else:
                continue  # menu-icon.rom is merged below, never extracted
            _makedirs(dest.rsplit("/", 1)[0])
            _progress("writing", name.replace("/", "_"), 0)
            package.extract(name, dest)

        # Point of no return: drop the previous version, move staging in.
        old_game_dir = root + "/" + prefix
        if _exists(old_game_dir):
            _progress("writing", "remove_old_" + slug, 0)
            _rmtree(old_game_dir)
        os.rename(staging, old_game_dir)
        for tmp_path, final in rom_renames:
            # A previous install may have left the other on-flash variant
            # (plain .rom vs .romz); director.load_rom() prefers the .romz,
            # so a stale sibling would shadow the fresh rom.
            sibling = final[:-1] if final.endswith(".romz") else final + "z"
            try:
                os.remove(sibling)
            except OSError:
                pass
            os.rename(tmp_path, final)

        # Icon merge failing is not fatal: the game is installed and the
        # launcher falls back to a generic strip for missing icons.
        if package.exists(ICON_MEMBER):
            _progress("writing", "menu_icons", 0)
            try:
                menurom.merge_icon_into_menu(
                    package.read(ICON_MEMBER), roms_dir=root + "/roms")
            except Exception as e:
                print("installer: menu icon merge failed:", e)
                _progress("writing", "menu_icons_failed", 100)
    return slug


def run(request, send_fn):
    """Fetch and install the package named by an /install_request line:
    "<url> <sha256> <size>". Returns True on success; the caller resets the
    board either way."""
    global _send_fn
    _send_fn = send_fn

    import updater

    try:
        url, expected_sha, size = request.split()
        size = int(size)
    except ValueError:
        _error("bad_install_request")
        return False

    print("installer: fetching", url)
    _progress("start", "connect", 0)
    newly_connected = False
    try:
        newly_connected = updater._wifi_connect()
    except OSError as e:
        _error("wifi_connect_failed: %s" % e)
        return False

    filename = url.rsplit("/", 1)[-1]
    package_path = PACKAGES_DIR + "/" + filename
    tmp_path = package_path + ".tmp"
    try:
        url = updater._resolve_base_url(url)
        _makedirs(PACKAGES_DIR)
        sha = hashlib.sha256()
        with open(tmp_path, "wb") as f:
            def _write(chunk):
                f.write(chunk)
                sha.update(chunk)
            last_reported = -10
            for pct in updater._http_stream(url, _write, size):
                if pct >= last_reported + 10:
                    _progress("downloading", filename, pct)
                    last_reported = pct
        got = binascii.hexlify(sha.digest()).decode()
        if got != expected_sha:
            os.remove(tmp_path)
            _error("sha256_mismatch got=%s expected=%s" % (got, expected_sha))
            return False
        os.rename(tmp_path, package_path)
    except Exception as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        _error("download_failed: %s" % e)
        return False
    finally:
        if newly_connected:
            updater._wifi_disconnect()

    try:
        slug = install_from_file(package_path)
    except Exception as e:
        _error("install_failed: %s" % e)
        return False
    _send("install_done %s\n" % slug)
    print("installer: installed", slug)
    return True
