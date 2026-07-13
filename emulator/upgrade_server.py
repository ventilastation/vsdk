"""HTTP server that serves the OTA manifest and file/partition payloads.

Listens on port 5653 in a daemon thread. The device calls GET /manifest to
discover what's available, then fetches individual files or partition binaries.
Triggered from the emulator UI (U key) which sends "ota_start <url>" to the
device via the existing comms channel.

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
import gzip
import hashlib
import importlib.util
import json
import pathlib
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

_VSDK_ROOT = pathlib.Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "build_micropython_fs", _VSDK_ROOT / "hardware/rotor/build_micropython_fs.py"
)
_build_fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_build_fs)

_PARTITION_BINS = {
    "prboom-go":   _VSDK_ROOT / "apps/retro-go/prboom-go/build/prboom-go.bin",
    "retro-core":  _VSDK_ROOT / "apps/retro-go/retro-core/build/retro-core.bin",
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


def _file_entry(device_path, local_path):
    """Return the cached {sha256, size, gz} entry for one file, refreshing
    it when the source file changed. Sprite ROMs are stored gzip-compressed
    on device (see build_micropython_fs.py), so they are hashed and served
    in their compressed form under a ".rom.gz" device path."""
    stat = local_path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        entry = _cache.get(device_path)
        if entry and entry["stat"] == key:
            return entry
    data = local_path.read_bytes()
    gz = None
    if device_path.endswith(".rom.gz"):
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
    return remote_path + ".gz" if remote_path.endswith(".rom") else remote_path


def _build_manifest():
    files = []
    for remote_path, local_path in _lfs_files():
        if not local_path.is_file():
            continue
        device_path = _device_path(remote_path)
        entry = _file_entry(device_path, local_path)
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
        entry = _file_entry(rel, local_path)
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


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"upgrade_server: {fmt % args}")

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # File paths can contain spaces, parens, commas, etc. (many ROM
        # filenames); the device percent-encodes them when building the
        # request (see updater.py's _url_quote -- a raw space in the request
        # line breaks this server's own request-line parsing). Decode back
        # to the raw path before matching against manifest entries.
        path = urllib.parse.unquote(self.path.rstrip("/"))

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

        self._send(404, "text/plain", b"unknown endpoint")


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
