"""HTTP server that serves the OTA manifest and file/partition payloads.

Listens on port 8000 in a daemon thread. The device calls GET /manifest to
discover what's available, then fetches individual files or partition binaries.
Triggered from the emulator UI (U key) which sends "ota_start <url>" to the
device via the existing comms channel.
"""

import hashlib
import json
import os
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_VSDK_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Directories and files served by each endpoint.
_MP_ROOT = _VSDK_ROOT / "apps/micropython"   # files endpoint root

_PARTITION_BINS = {
    "prboom-go":   _VSDK_ROOT / "apps/retro-go/prboom-go/build/prboom-go.bin",
    "retro-core":  _VSDK_ROOT / "apps/retro-go/retro-core/build/retro-core.bin",
    "micropython": (
        _VSDK_ROOT /
        "hardware/rotor/micropython/ports/esp32"
        "/build-VENTILASTATION-SPIRAM_OCT/micropython.bin"
    ),
}

# Directories whose Python files are included in the LFS manifest.
_FILE_DIRS = [
    _MP_ROOT / "ventilastation",
    _MP_ROOT,  # main.py etc. at root level
]

_FILE_EXTENSIONS = {".py", ".json"}


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_manifest():
    files = []
    seen = set()
    for base in _FILE_DIRS:
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix not in _FILE_EXTENSIONS:
                continue
            if not p.is_file():
                continue
            rel = p.relative_to(_MP_ROOT)
            key = str(rel)
            if key in seen:
                continue
            seen.add(key)
            files.append({
                "path": key,
                "size": p.stat().st_size,
                "sha256": _sha256_file(p),
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
        path = self.path.rstrip("/")

        if path == "/manifest":
            try:
                manifest = _build_manifest()
                body = json.dumps(manifest).encode()
                self._send(200, "application/json", body)
            except Exception as e:
                body = str(e).encode()
                self._send(500, "text/plain", body)
            return

        if path.startswith("/files/"):
            rel = path[len("/files/"):]
            file_path = _MP_ROOT / rel
            try:
                file_path = file_path.resolve()
                # Ensure the resolved path is still under _MP_ROOT.
                file_path.relative_to(_MP_ROOT)
                with open(file_path, "rb") as f:
                    body = f.read()
                self._send(200, "application/octet-stream", body)
            except (FileNotFoundError, ValueError):
                self._send(404, "text/plain", b"not found")
            return

        if path.startswith("/partitions/"):
            name = path[len("/partitions/"):]
            bin_path = _PARTITION_BINS.get(name)
            if bin_path and bin_path.is_file():
                with open(bin_path, "rb") as f:
                    body = f.read()
                self._send(200, "application/octet-stream", body)
            else:
                self._send(404, "text/plain", b"partition binary not found")
            return

        self._send(404, "text/plain", b"unknown endpoint")


def start(port=8000):
    """Start the upgrade HTTP server on the given port (default 8000)."""
    server = HTTPServer(("", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"upgrade_server: listening on port {port}")
    return server
