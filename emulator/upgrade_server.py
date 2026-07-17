"""HTTP server that serves the OTA manifest and file/partition payloads.

Listens on port 5653 in a daemon thread. The device calls GET /manifest to
discover what's available, then fetches individual files or partition binaries.
Triggered from the emulator UI (Ctrl-U or Command-U) which sends
"ota_start <url>" to the device via the existing comms channel.

Also advertises itself as "ventilastation-base.local" over mDNS (via the
"zeroconf" package) so the device can find it without any NVS-stored IP.
This matters for the desktop dev loop specifically: a production base (a
Raspberry Pi) gets this for free from Avahi once its OS hostname is set to
"ventilastation-base" -- but a dev machine's own Bonjour name is whatever
its computer name already is, so without this the emulator would bind the
port fine but never actually be reachable at that hostname.

The file manifest covers the complete LittleFS content — the same file set,
device paths and gzip transform as the USB-flashed image — by reusing
hardware/rotor/build_micropython_fs.py's iter_copy_jobs(). The device skips
files whose SHA256 already matches, so a typical dev-loop sync transfers
only the files that changed since the last OTA.

Can also run standalone (not just imported by the desktop emulator), serving
a fixed pre-built bundle instead of computing the manifest live from dev
build-output paths -- for a production base that doesn't have the
ESP-IDF/Retro-Go toolchain installed:

    python3 emulator/upgrade_server.py --bundle <dir> [--port 5653]

See tools/package_release.py for assembling that bundle directory.
"""

import argparse
import atexit
import gzip
import hashlib
import importlib.util
import json
import mimetypes
import pathlib
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    import package_manager
except ImportError:
    # Loaded by file path (tests use importlib on this module) rather than
    # with emulator/ on sys.path; register the sibling module under its
    # canonical name so every importer shares one instance (hooks + status).
    _pm_spec = importlib.util.spec_from_file_location(
        "package_manager",
        pathlib.Path(__file__).resolve().parent / "package_manager.py",
    )
    package_manager = importlib.util.module_from_spec(_pm_spec)
    sys.modules["package_manager"] = package_manager
    _pm_spec.loader.exec_module(package_manager)

try:
    from zeroconf import Zeroconf, ServiceInfo
except ImportError:
    Zeroconf = None
    ServiceInfo = None

_MDNS_HOSTNAME = "ventilastation-base"

_VSDK_ROOT = pathlib.Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "build_micropython_fs", _VSDK_ROOT / "hardware/rotor/build_micropython_fs.py"
)
_build_fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_build_fs)

_PARTITION_BINS = {
    "prboom-go":   _VSDK_ROOT / "apps/retro-go/prboom-go/build/prboom-go.bin",
    "retro-core":  _VSDK_ROOT / "apps/retro-go/retro-core/build/retro-core.bin",
    "fmsx":        _VSDK_ROOT / "apps/retro-go/fmsx/build/fmsx.bin",
    "micropython": (
        _VSDK_ROOT /
        "hardware/rotor/micropython/ports/esp32"
        "/build-VENTILASTATION-SPIRAM_OCT/micropython.bin"
    ),
}

# Set by start(bundle_dir=...): switches every request from computing the
# manifest/files/partitions live off dev build-output paths to serving a
# fixed pre-built layout instead (see tools/package_release.py).
_BUNDLE_DIR = None

# Wired up by comms.start() when this server runs inside the emulator
# process; standalone runs leave them None (uploads still work, but nothing
# rescans audio and installs can't be triggered without a board link).
on_package_saved = None   # called with (slug) after a successful upload
trigger_install = None    # called with (slug) to send install_start

# The web editor is served from the checkout so the base is its own origin
# (a GitHub-Pages HTTPS editor can't POST to this plain-HTTP server).
_WEB_ROOT = _VSDK_ROOT / "web"

# Directories /api/listdir may enumerate (the editor merges tree game
# assets, e.g. sounds, with its in-browser workspace).
_LISTABLE_ROOTS = ("games", "system")

_EXTRA_MIME_TYPES = {
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".wasm": "application/wasm",
    ".rom": "application/octet-stream",
    ".vs2": "application/octet-stream",
    ".py": "text/plain; charset=utf-8",
    ".yaml": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}

# Per-device-path cache keyed on (mtime_ns, size) of the source file, so
# repeated /manifest requests don't re-hash (and re-gzip) unchanged files.
# Entries: {"stat": (mtime_ns, size), "sha256": hex, "size": served size,
#           "gz": compressed bytes or None}
_cache = {}
_cache_lock = threading.Lock()


def _lfs_files():
    """Yield (device_path, local_path) for every file in the LFS image."""
    for kind, remote_path, local_path in _build_fs.iter_copy_jobs(_VSDK_ROOT):
        if kind == "file":
            yield remote_path, local_path


def _file_entry(device_path, remote_path, local_path):
    """Return the cached {sha256, size, gz} entry for one file, refreshing
    it when the source file changed. Sprite ROMs and MSX cartridge/BIOS
    dumps are stored gzip-compressed on device (see build_micropython_fs.py),
    so they are hashed and served in their compressed form under a ".romz"
    or ".rom.gz" device path respectively."""
    stat = local_path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        entry = _cache.get(device_path)
        if entry and entry["stat"] == key:
            return entry
    data = local_path.read_bytes()
    gz = None
    if _build_fs.is_sprite_rom_path(remote_path):
        gz = _build_fs.compress_sprite_rom(data)
        data = gz
    elif device_path.endswith(".rom.gz"):
        # mtime=0 keeps the output deterministic, matching the flashed image.
        gz = gzip.compress(data, compresslevel=9, mtime=0)
        data = gz
    entry = {
        "stat": key,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "gz": gz,
    }
    with _cache_lock:
        _cache[device_path] = entry
    return entry


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _device_path(remote_path):
    if _build_fs.is_sprite_rom_path(remote_path):
        return remote_path + "z"
    return remote_path + ".gz" if remote_path.endswith(".rom") else remote_path


def _build_manifest():
    files = []
    for remote_path, local_path in _lfs_files():
        if not local_path.is_file():
            continue
        device_path = _device_path(remote_path)
        entry = _file_entry(device_path, remote_path, local_path)
        files.append({
            "path": device_path,
            "size": entry["size"],
            "sha256": entry["sha256"],
        })

    partitions = {}
    for name, bin_path in _PARTITION_BINS.items():
        if not bin_path.is_file():
            continue
        partitions[name] = {
            "size": bin_path.stat().st_size,
            "sha256": _sha256_file(bin_path),
            "url": f"/partitions/{name}",
        }

    return {"files": files, "partitions": partitions}


def _read_device_file(rel):
    """Return the served bytes for one manifest path, or None if unknown."""
    for remote_path, local_path in _lfs_files():
        if _device_path(remote_path) != rel:
            continue
        if not local_path.is_file():
            return None
        entry = _file_entry(rel, remote_path, local_path)
        if entry["gz"] is not None:
            return entry["gz"]
        return local_path.read_bytes()
    return None


def _get_manifest():
    if _BUNDLE_DIR is not None:
        return json.loads((_BUNDLE_DIR / "manifest.json").read_text())
    return _build_manifest()


def _get_device_file(rel):
    if _BUNDLE_DIR is not None:
        path = _BUNDLE_DIR / "files" / rel
        return path.read_bytes() if path.is_file() else None
    return _read_device_file(rel)


def _get_partition(name):
    if _BUNDLE_DIR is not None:
        path = _BUNDLE_DIR / "partitions" / name
        return path.read_bytes() if path.is_file() else None
    bin_path = _PARTITION_BINS.get(name)
    if bin_path and bin_path.is_file():
        return bin_path.read_bytes()
    return None


def _safe_relative_path(url_path):
    """URL path -> relative segments, or None when it escapes the root."""
    segments = [s for s in url_path.split("/") if s and s != "."]
    if any(s == ".." for s in segments):
        return None
    return segments


def _guess_type(path):
    mime = _EXTRA_MIME_TYPES.get(path.suffix.lower())
    if mime:
        return mime
    guessed, _encoding = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"upgrade_server: {fmt % args}")

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, code=200):
        self._send(code, "application/json", json.dumps(payload).encode())

    def _serve_editor(self, path):
        """Static file from the web/ tree (the editor and, through its
        apps/games/system symlinks, the runtime files and game assets)."""
        segments = _safe_relative_path(path)
        if segments is None:
            self._send(404, "text/plain", b"not found")
            return
        target = _WEB_ROOT.joinpath(*segments) if segments else _WEB_ROOT
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send(404, "text/plain", b"not found")
            return
        self._send(200, _guess_type(target), target.read_bytes())

    def _handle_listdir(self, query):
        rel = urllib.parse.parse_qs(query).get("path", [""])[0]
        segments = _safe_relative_path(rel)
        if not segments or segments[0] not in _LISTABLE_ROOTS:
            self._send_json({"error": "path must be under games/ or system/"}, 400)
            return
        target = _VSDK_ROOT.joinpath(*segments)
        if not target.is_dir():
            self._send_json({"path": "/".join(segments), "entries": []})
            return
        entries = [
            {"name": child.name, "dir": child.is_dir(), "size": child.stat().st_size}
            for child in sorted(target.iterdir())
            if not child.name.startswith(".")
        ]
        self._send_json({"path": "/".join(segments), "entries": entries})

    def _handle_packages_get(self, path):
        if path == "/packages":
            self._send_json({"packages": package_manager.list_packages()})
            return
        rest = path[len("/packages/"):]
        if rest.endswith(package_manager.BOARD_SUFFIX):
            slug = rest[:-len(package_manager.BOARD_SUFFIX)]
            try:
                body, _sha, _size = package_manager.get_board_file(slug)
            except package_manager.PackageError as error:
                self._send(404, "text/plain", str(error).encode())
                return
            package_manager.set_install_status(slug, "serving")
            self._send(200, "application/octet-stream", body)
            return
        if rest.endswith("/status"):
            slug = rest[:-len("/status")]
            self._send_json(package_manager.get_install_status(slug))
            return
        if rest.endswith(package_manager.PACKAGE_SUFFIX):
            slug = rest[:-len(package_manager.PACKAGE_SUFFIX)]
            source = package_manager.package_path(slug)
            if source.is_file():
                self._send(200, "application/octet-stream", source.read_bytes())
            else:
                self._send(404, "text/plain", b"no such package")
            return
        self._send(404, "text/plain", b"unknown packages endpoint")

    def do_POST(self):
        raw_path, _, _query = self.path.partition("?")
        path = urllib.parse.unquote(raw_path).rstrip("/")

        if path.startswith("/packages/"):
            rest = path[len("/packages/"):]

            if rest.endswith(package_manager.PACKAGE_SUFFIX):
                slug = rest[:-len(package_manager.PACKAGE_SUFFIX)]
                length = int(self.headers.get("Content-Length", 0))
                data = self.rfile.read(length)
                try:
                    meta = package_manager.save_package(slug, data)
                except package_manager.PackageError as error:
                    self._send_json({"error": str(error)}, 400)
                    return
                if on_package_saved is not None:
                    try:
                        on_package_saved(slug)
                    except Exception as error:
                        print(f"upgrade_server: on_package_saved failed: {error}")
                self._send_json({"ok": True, "slug": slug, "meta": meta})
                return

            if rest.endswith("/install"):
                slug = rest[:-len("/install")]
                if not package_manager.package_path(slug).is_file():
                    self._send_json({"error": "no such package"}, 404)
                    return
                if trigger_install is None:
                    self._send_json(
                        {"error": "no board link (standalone server)"}, 503)
                    return
                try:
                    trigger_install(slug)
                except Exception as error:
                    self._send_json({"error": str(error)}, 500)
                    return
                self._send_json(package_manager.get_install_status(slug))
                return

        self._send(404, "text/plain", b"unknown endpoint")

    def do_GET(self):
        # File paths can contain spaces, parens, commas, etc. (many ROM
        # filenames); the device percent-encodes them when building the
        # request (see updater.py's _url_quote -- a raw space in the request
        # line breaks this server's own request-line parsing). Decode back
        # to the raw path before matching against manifest entries.
        raw_path, _, query = self.path.partition("?")
        path = urllib.parse.unquote(raw_path).rstrip("/")

        if path.startswith("/packages"):
            self._handle_packages_get(path)
            return

        if path == "/api/listdir":
            self._handle_listdir(query)
            return

        if path == "/manifest":
            try:
                manifest = _get_manifest()
                body = json.dumps(manifest).encode()
                self._send(200, "application/json", body)
            except Exception as e:
                body = str(e).encode()
                self._send(500, "text/plain", body)
            return

        if path.startswith("/files/"):
            rel = path[len("/files/"):]
            try:
                body = _get_device_file(rel)
            except OSError:
                body = None
            if body is None:
                self._send(404, "text/plain", b"not found")
            else:
                self._send(200, "application/octet-stream", body)
            return

        if path.startswith("/partitions/"):
            name = path[len("/partitions/"):]
            body = _get_partition(name)
            if body is not None:
                self._send(200, "application/octet-stream", body)
            else:
                self._send(404, "text/plain", b"partition binary not found")
            return

        # Anything else is the web editor (index.html for "/").
        self._serve_editor(path)


_mdns_zc = None
_mdns_info = None


def _lan_ip():
    """Best-effort LAN IP for this machine. Doesn't actually send anything --
    UDP connect() just makes the OS pick the outbound route/interface."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _register_mdns(port):
    global _mdns_zc, _mdns_info
    if Zeroconf is None:
        print(
            "upgrade_server: 'zeroconf' package not installed -- skipping mDNS "
            f"advertisement. The device won't find this server at "
            f"{_MDNS_HOSTNAME}.local without it (pip install zeroconf, or "
            "register the hostname manually, e.g. with dns-sd -P on macOS)."
        )
        return
    ip = _lan_ip()
    # Restrict to just this interface: registering on InterfaceChoice.All
    # (the default) advertises the same hostname/address from every
    # interface, and some clients (confirmed: curl without -4) pick an
    # unreachable duplicate and fail intermittently instead of using the
    # one that actually routes.
    _mdns_zc = Zeroconf(interfaces=[ip])
    _mdns_info = ServiceInfo(
        "_http._tcp.local.",
        f"{_MDNS_HOSTNAME}._http._tcp.local.",
        port=port,
        server=f"{_MDNS_HOSTNAME}.local.",
        parsed_addresses=[ip],
    )
    _mdns_zc.register_service(_mdns_info)
    atexit.register(_unregister_mdns)
    print(f"upgrade_server: advertising {_MDNS_HOSTNAME}.local ({ip}) via mDNS")


def _unregister_mdns():
    global _mdns_zc, _mdns_info
    if _mdns_zc is not None:
        try:
            _mdns_zc.unregister_service(_mdns_info)
            _mdns_zc.close()
        except Exception:
            pass
        _mdns_zc = None
        _mdns_info = None


def start(port=5653, bundle_dir=None):
    """Start the upgrade HTTP server on the given port (default 8000).

    bundle_dir, if given, serves a fixed pre-built layout from that directory
    (manifest.json + files/ + partitions/, see tools/package_release.py)
    instead of computing everything live from dev build-output paths.
    """
    global _BUNDLE_DIR
    _BUNDLE_DIR = pathlib.Path(bundle_dir).resolve() if bundle_dir else None
    server = HTTPServer(("", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    if _BUNDLE_DIR is not None:
        print(f"upgrade_server: listening on port {port}, serving bundle {_BUNDLE_DIR}")
    else:
        print(f"upgrade_server: listening on port {port}")
    _register_mdns(port)
    return server


def main():
    parser = argparse.ArgumentParser(description="Standalone OTA upgrade server")
    parser.add_argument("--port", type=int, default=5653)
    parser.add_argument(
        "--bundle", type=pathlib.Path, default=None,
        help="Serve a fixed pre-built bundle (see tools/package_release.py) "
             "instead of live dev build-output paths",
    )
    args = parser.parse_args()

    if args.bundle is not None:
        manifest_path = args.bundle / "manifest.json"
        if not manifest_path.is_file():
            print(f"upgrade_server: no manifest.json in {args.bundle}", file=sys.stderr)
            raise SystemExit(1)

    start(port=args.port, bundle_dir=args.bundle)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
