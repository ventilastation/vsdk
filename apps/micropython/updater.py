"""Three-tier OTA update client for Ventilastation.

Called from the comms/director layer when the emulator sends:
    ota_start http://<emulator-ip>:5653

Tiers run in order:
  1. LFS file sync     — the full LittleFS content (code, ROMs, game assets);
                         SHA256-skip so only changed files transfer, atomic
                         rename per file
  2. Native partitions — prboom-go, retro-core, fmsx; stream + SHA256 verify
  3. MicroPython fw    — micropython (ota_2); stream + SHA256 verify + set_boot + reboot

Progress is reported back over the comms channel as:
    ota_progress <stage> <detail> <pct>
Completion:
    ota_done ok
Errors:
    ota_error <message>
"""

import gc
import os
import hashlib
import binascii

try:
    import ujson as json
except ImportError:
    import json

try:
    import usocket as socket
except ImportError:
    import socket

# Manifest file paths are raw (unescaped) filesystem paths and can contain
# spaces, parens, commas, etc. (e.g. many console ROM filenames). An HTTP
# request line is whitespace-delimited, so a literal space in the path
# breaks the server's own request parsing ("Bad request syntax"). No
# urllib on this build, so a minimal RFC 3986 percent-encoder: keep '/' as
# a literal separator, escape everything outside the unreserved set.
_URL_SAFE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~/"


def _url_quote(path):
    out = []
    for ch in path:
        if ch in _URL_SAFE:
            out.append(ch)
        else:
            for b in ch.encode("utf-8"):
                out.append("%%%02X" % b)
    return "".join(out)


# Persistent state: NVS namespace "vsdk_ota" tracks SHA256 of each partition
# so unchanged binaries are skipped without downloading.
_NVS_NS = "vsdk_ota"
_NVS_KEYS = {
    "prboom-go":   "prboom_sha",
    "retro-core":  "retro_sha",
    "fmsx":        "fmsx_sha",
    "micropython": "mp_sha",
}

_comms_send = None   # set by run()


def _send(line):
    if _comms_send:
        _comms_send(line.encode() if isinstance(line, str) else line)


def _progress(stage, detail, pct):
    _send("ota_progress %s %s %d\n" % (stage, detail, pct))


def _nvs_get(key):
    try:
        import esp32
        nvs = esp32.NVS(_NVS_NS)
        buf = bytearray(70)
        n = nvs.get_blob(key, buf)
        return buf[:n].decode()
    except Exception:
        return None


def _nvs_set(key, value):
    try:
        import esp32
        nvs = esp32.NVS(_NVS_NS)
        nvs.set_blob(key, value.encode() if isinstance(value, str) else value)
        nvs.commit()
    except Exception as e:
        print("updater: NVS write failed:", e)


def _http_get_json(url):
    host, port, path = _parse_url(url)
    s = socket.socket()
    try:
        s.settimeout(15)
        s.connect(socket.getaddrinfo(host, port)[0][-1])
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (path, host)).encode())
        # Skip HTTP headers.
        sf = s.makefile("rb")
        while True:
            line = sf.readline()
            if not line or line == b"\r\n":
                break
        body = sf.read()
        return json.loads(body)
    finally:
        s.close()


def _parse_url(url):
    # "http://host:port/path"
    url = url.replace("http://", "")
    if "/" in url:
        hostport, path = url.split("/", 1)
        path = "/" + path
    else:
        hostport = url
        path = "/"
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
        port = int(port)
    else:
        host = hostport
        port = 80
    return host, port, path


def _http_stream(url, callback, total_size):
    """Stream url, calling callback(chunk) for each received chunk."""
    host, port, path = _parse_url(url)
    s = socket.socket()
    try:
        s.settimeout(15)
        s.connect(socket.getaddrinfo(host, port)[0][-1])
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (path, host)).encode())
        sf = s.makefile("rb")
        while True:
            line = sf.readline()
            if not line or line == b"\r\n":
                break
        received = 0
        while True:
            chunk = sf.read(4096)
            if not chunk:
                break
            callback(chunk)
            received += len(chunk)
            if total_size:
                yield received * 100 // total_size
            else:
                yield 0
    finally:
        s.close()


def _sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return None
    return binascii.hexlify(h.digest()).decode()


def _cleanup_tmp_files():
    """Remove any .tmp files left over from a previous interrupted sync."""
    count = 0
    stack = ["/"]
    while stack:
        d = stack.pop()
        try:
            for name, ftype, *_ in os.ilistdir(d):
                full = d.rstrip("/") + "/" + name
                if ftype == 0x4000:  # directory
                    stack.append(full)
                elif name.endswith(".tmp"):
                    try:
                        os.remove(full)
                        count += 1
                        print("updater: removed stale tmp:", full)
                    except OSError as e:
                        print("updater: failed to remove tmp:", full, e)
        except OSError:
            pass
    if count:
        print("updater: cleaned up %d .tmp file(s)" % count)


def _makedirs(path):
    parts = path.lstrip("/").split("/")
    current = ""
    for part in parts[:-1]:
        current = current + "/" + part
        try:
            os.mkdir(current)
        except OSError:
            pass


def _sync_lfs_files(base_url, files):
    total = len(files)
    for i, entry in enumerate(files):
        rel_path = entry["path"]
        expected_sha = entry["sha256"]
        size = entry["size"]
        local_path = "/" + rel_path

        gc.collect()
        local_sha = _sha256_file(local_path)
        if local_sha == expected_sha:
            continue  # already up to date

        _progress("file", rel_path.replace("/", "_"), i * 100 // total)
        tmp_path = local_path + ".tmp"
        file_url = base_url + "/files/" + _url_quote(rel_path)
        sha = hashlib.sha256()

        try:
            _makedirs(local_path)
            with open(tmp_path, "wb") as f:
                def _write(chunk):
                    f.write(chunk)
                    sha.update(chunk)
                for pct in _http_stream(file_url, _write, size):
                    pass  # per-file progress not sent to save bandwidth
            got = binascii.hexlify(sha.digest()).decode()
            if got != expected_sha:
                print("updater: SHA256 mismatch for", rel_path, "- got", got, "expected", expected_sha)
                os.remove(tmp_path)
                continue
            os.rename(tmp_path, local_path)
            print("updater: updated", rel_path)
        except Exception as e:
            print("updater: failed to update", rel_path, ":", e)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    _progress("file", "done", 100)


def _running_label():
    try:
        import esp32
        return esp32.Partition(esp32.Partition.RUNNING).info()[4]
    except Exception:
        return None


def _update_partitions(base_url, partitions):
    import esp32

    running = _running_label()
    # ioctl(5) returns the block size (4096 bytes for SPI flash).
    # ioctl(6, block_num) erases a single 4096-byte sector.
    # writeblocks(block_num, buf) writes aligned 4096-byte blocks.
    _BLOCK = 4096

    order = ["fmsx", "retro-core", "prboom-go", "micropython"]
    for name in order:
        if name not in partitions:
            continue
        entry = partitions[name]
        expected_sha = entry["sha256"]
        size = entry["size"]
        url = base_url + entry["url"]
        nvs_key = _NVS_KEYS.get(name)

        # Skip if we already have this exact binary.
        if nvs_key:
            stored_sha = _nvs_get(nvs_key)
            if stored_sha == expected_sha:
                print("updater: partition %s up to date" % name)
                continue

        # Can't erase the partition we're currently executing from -- hand
        # off to factory instead of skipping forever. factory is the
        # permanent recovery environment (see apps/micropython/main.py); its
        # own OTA pass re-fetches the manifest and reaches this same branch
        # with running != name, where it's safe to erase+write+verify the
        # real update below. A missing/absent stored hash (first-ever OTA
        # after a factory-only flash) is treated the same as "differs".
        if name == running:
            print("updater: %s needs updating but is currently running — handing off to factory" % name)
            factory_parts = esp32.Partition.find(esp32.Partition.TYPE_APP, label="factory")
            if not factory_parts:
                print("updater: factory partition not found, cannot hand off")
                continue
            _send("ota_progress micropython handoff 100\n")
            import machine
            factory_parts[0].set_boot()
            machine.reset()

        _progress("partition", name, 0)
        print("updater: flashing partition", name, "(%d bytes)" % size)

        try:
            parts = esp32.Partition.find(esp32.Partition.TYPE_APP, label=name)
            if not parts:
                print("updater: partition not found:", name)
                continue
            part = parts[0]

            # Erase sectors that will be written.
            sectors = (size + _BLOCK - 1) // _BLOCK
            print("updater: erasing", sectors, "sectors ...")
            for i in range(sectors):
                part.ioctl(6, i)

            sha = hashlib.sha256()
            offset = 0
            # Fixed 4096-byte block buffer; avoids bytearray slice deletion.
            block_buf = bytearray(_BLOCK)
            block_pos = 0

            def write_chunk(chunk):
                nonlocal offset, block_pos
                sha.update(chunk)
                chunk_off = 0
                while chunk_off < len(chunk):
                    space = _BLOCK - block_pos
                    n = min(space, len(chunk) - chunk_off)
                    block_buf[block_pos:block_pos + n] = chunk[chunk_off:chunk_off + n]
                    block_pos += n
                    chunk_off += n
                    if block_pos == _BLOCK:
                        part.writeblocks(offset // _BLOCK, block_buf)
                        offset += _BLOCK
                        block_pos = 0

            for pct in _http_stream(url, write_chunk, size):
                _progress("partition", name, pct)
                gc.collect()

            # Flush remaining bytes padded to _BLOCK boundary.
            if block_pos > 0:
                for i in range(block_pos, _BLOCK):
                    block_buf[i] = 0xFF
                part.writeblocks(offset // _BLOCK, block_buf)
                offset += _BLOCK

            got = binascii.hexlify(sha.digest()).decode()
            if got != expected_sha:
                print("updater: SHA256 mismatch for partition", name)
                print("  got:      ", got)
                print("  expected: ", expected_sha)
                # Don't update NVS — will retry next session.
                continue

            if nvs_key:
                _nvs_set(nvs_key, expected_sha)
            print("updater: partition", name, "flashed OK")
            _progress("partition", name, 100)

            # MicroPython firmware is handled last: set it as boot and reboot.
            # The new image will call mark_app_valid_cancel_rollback() after WiFi.
            if name == "micropython":
                _send("ota_progress micropython reboot 100\n")
                import machine
                part.set_boot()
                machine.reset()

        except Exception as e:
            print("updater: error flashing partition", name, ":", e)
            _progress("partition", name + "_error", 0)
            # Continue to next partition rather than aborting entirely.


def _wifi_connect():
    """Connect WiFi using NVS credentials.

    Returns True if we brought WiFi up (caller must disconnect after OTA),
    False if WiFi was already connected (caller must leave it alone).
    Raises OSError if connection fails.
    """
    import network, utime
    sta = network.WLAN(network.STA_IF)
    if sta.isconnected():
        return False
    try:
        import esp32
        nvs = esp32.NVS("devel_wifi")
        ssid_buf = bytearray(33)
        pass_buf = bytearray(65)
        ssid_len = nvs.get_blob("ssid", ssid_buf)
        pass_len = nvs.get_blob("password", pass_buf)
        ssid = ssid_buf[:ssid_len].decode()
        password = pass_buf[:pass_len].decode()
    except Exception as e:
        raise OSError("NVS read failed: %s" % e)
    if not ssid:
        raise OSError("no WiFi credentials in NVS (run: make wifi-provision)")
    print("updater: connecting WiFi to", ssid)
    sta.active(True)
    sta.connect(ssid, password)
    for _ in range(60):
        if sta.isconnected():
            print("updater: WiFi connected:", sta.ifconfig()[0])
            return True
        utime.sleep_ms(500)
    sta.active(False)
    raise OSError("WiFi connection timeout")


def _wifi_disconnect():
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        sta.disconnect()
        sta.active(False)
        print("updater: WiFi disconnected")
    except Exception:
        pass


def run(base_url, send_fn):
    """Run the full 3-tier OTA update.

    base_url  — e.g. "http://192.168.1.5:5653"
    send_fn   — callable that sends a bytes line back over the comms channel
    """
    global _comms_send
    _comms_send = send_fn

    print("updater: starting OTA from", base_url)
    _send("ota_progress start fetching_manifest 0\n")

    # Bring WiFi up only for the duration of the OTA session.
    _newly_connected = False
    try:
        _newly_connected = _wifi_connect()
    except OSError as e:
        _send(("ota_error wifi_connect_failed: %s\n" % e).encode())
        return

    try:
        try:
            manifest = _http_get_json(base_url + "/manifest")
        except Exception as e:
            _send(("ota_error manifest_fetch_failed: %s\n" % e).encode())
            return

        _cleanup_tmp_files()
        _sync_lfs_files(base_url, manifest.get("files", []))
        _update_partitions(base_url, manifest.get("partitions", {}))

        _send("ota_done ok\n")
        print("updater: OTA complete")
    finally:
        # Only disconnect if we brought WiFi up — don't kill a pre-existing connection
        # (e.g. desktop mode where comms.py already holds the link).
        # Note: if _update_partitions flashed micropython and called machine.reset(),
        # we never reach here — that's fine, the reboot drops WiFi anyway.
        if _newly_connected:
            _wifi_disconnect()
