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
where stage is `checking` while checksums are calculated, `downloading`
while a file is fetched, or `writing` while a flash partition is erased or
written.
Completion:
    ota_done ok
Errors:
    ota_error <message>

Separately (and unrelated to the comms/base-station line above), this
device's own POV display shows the same progress locally as concentric
rings -- see vsdk_ota_rings.py. That module already no-ops when the native
display isn't linked in (desktop/emulator), so the calls below are
unconditional.
"""

import gc
import os
import hashlib
import binascii

import vsdk_ota_rings

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
_feed_wdt = None     # set by run()


def _send(line):
    if _comms_send:
        _comms_send(line.encode() if isinstance(line, str) else line)


def _prep_checkpoint():
    """One step of the long, quiet stretch between "WiFi connecting" and the
    first real file/partition total: bounce the on-device activity ring *and*
    feed the caller's watchdog.

    The two belong together. Everywhere else in this file the watchdog is fed
    as a side effect of emitting a progress line (recovery's handler feeds on
    every line it receives -- see vsdk_recovery._make_progress_handler), but
    this phase deliberately emits none, so it used to feed nothing at all:
    WiFi connect, address resolution, the manifest fetch and the .tmp scan
    together ran for as long as they needed with recovery's 30s watchdog
    counting down untouched, and anything slower than that rebooted the board
    mid-attempt instead of failing into recovery's own backoff retry. That
    also made _wifi_connect()'s indefinite retry unreachable in practice: its
    red "wifi problem" ring needs three attempts (~24-36s), so the reboot
    always won first. Keeping the ring pulse and the feed in one call is what
    stops them drifting apart again.
    """
    vsdk_ota_rings.pulse_prep_activity()
    if _feed_wdt:
        _feed_wdt()


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


def _is_ipv4_literal(host):
    parts = host.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or not (0 <= int(p) <= 255):
            return False
    return True


# mDNS multicast group/port, and how patiently to ask. Three tries at 2s
# each keeps a whole resolution attempt well inside recovery's 30s watchdog
# (see vsdk_recovery._WDT_TIMEOUT_MS) even when nothing answers at all.
_MDNS_GROUP = "224.0.0.251"
_MDNS_PORT = 5353
_MDNS_TIMEOUT_MS = 2000
_MDNS_ATTEMPTS = 3


def _dns_skip_name(buf, i):
    """Advance past the encoded name starting at i, returning the next index."""
    while i < len(buf):
        length = buf[i]
        if length == 0:
            return i + 1
        if length & 0xC0 == 0xC0:
            return i + 2  # a compression pointer is always the whole name
        i += 1 + length
    raise ValueError("truncated name")


def _dns_read_name(buf, i, depth=0):
    parts = []
    while i < len(buf):
        length = buf[i]
        if length == 0:
            break
        if length & 0xC0 == 0xC0:
            if depth > 4:
                raise ValueError("compression pointer loop")
            parts.append(_dns_read_name(buf, ((length & 0x3F) << 8) | buf[i + 1], depth + 1))
            break
        parts.append(bytes(buf[i + 1:i + 1 + length]).decode())
        i += 1 + length
    return ".".join(parts)


def _mdns_parse_a(buf, host):
    """Pull host's A record out of an mDNS response, or None if it has none.

    Records are matched by name rather than taking the first A record in the
    packet: a responder is free to bundle unrelated records (its own other
    services, another host's announcement it happened to be sending) into the
    same message, and answering with one of those would send the whole OTA
    session to the wrong machine.
    """
    if len(buf) < 12:
        return None
    questions = (buf[4] << 8) | buf[5]
    records = ((buf[6] << 8) | buf[7]) + ((buf[8] << 8) | buf[9]) + ((buf[10] << 8) | buf[11])
    i = 12
    for _ in range(questions):
        i = _dns_skip_name(buf, i) + 4  # + QTYPE, QCLASS
    wanted = host.lower().rstrip(".")
    for _ in range(records):
        name = _dns_read_name(buf, i)
        i = _dns_skip_name(buf, i)
        rtype = (buf[i] << 8) | buf[i + 1]
        rdlength = (buf[i + 8] << 8) | buf[i + 9]
        i += 10
        if rtype == 1 and rdlength == 4 and name.lower().rstrip(".") == wanted:
            return "%d.%d.%d.%d" % (buf[i], buf[i + 1], buf[i + 2], buf[i + 3])
        i += rdlength
    return None


def _mdns_resolve(host, feed=None):
    """Resolve a .local hostname with our own bounded mDNS query.

    Not socket.getaddrinfo(): that call has no timeout of its own on this
    port (unlike the socket itself), and on hardware it does not merely run
    slowly -- while the POV display's GPU task is running (which in recovery
    it always is, drawing the progress rings) a `.local` lookup never returns
    at all. Measured on a rotor board, same session and network, seconds
    apart: display off, `ventilastation-base.local` resolved in 0.4-0.5s
    three times running; display on, the identical call never came back
    (still blocked after ten minutes). Plain unicast DNS (10ms) and TCP to
    the base station by IP (0.5s, HTTP 200) both stayed fine throughout, so
    it is the multicast path specifically -- consistent with the GPU task
    being a `while(true)` loop that never yields, pinned to a core at
    priority 10 (see coreTask() in modules/povdisplay/povdisplay.c), and with
    director.py's existing note that the normal OTA path reboots so the
    transfer runs *before* that task starts.

    Asking for a *unicast* response (the QU bit below) is what makes this
    work where getaddrinfo doesn't: the reply comes back as an ordinary UDP
    datagram to our own ephemeral port instead of arriving on the multicast
    group, so nothing here depends on the receive path that breaks. The
    socket timeout then bounds the whole thing, turning "base station is off"
    into a normal ota_error and a recovery backoff retry rather than a hang.

    feed, if given, is called between attempts -- a resolution that takes all
    three tries still has to keep the caller's watchdog fed.
    """
    import utime

    labels = b""
    for part in host.split("."):
        raw = part.encode()
        labels += bytes([len(raw)]) + raw
    labels += b"\x00"
    # id 0 (mDNS responders ignore it), no flags, one question, QTYPE=A(1),
    # QCLASS=IN(1) with the top "unicast response requested" bit set.
    query = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + labels + b"\x00\x01\x80\x01"
    group = socket.getaddrinfo(_MDNS_GROUP, _MDNS_PORT)[0][-1]

    for attempt in range(_MDNS_ATTEMPTS):
        if feed:
            feed()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(_MDNS_TIMEOUT_MS / 1000)
            s.sendto(query, group)
            deadline = utime.ticks_add(utime.ticks_ms(), _MDNS_TIMEOUT_MS)
            while utime.ticks_diff(deadline, utime.ticks_ms()) > 0:
                try:
                    data, _addr = s.recvfrom(512)
                except OSError:
                    break  # timed out waiting for this attempt's answer
                try:
                    addr = _mdns_parse_a(data, host)
                except (ValueError, IndexError):
                    continue  # malformed packet from someone else on the group
                if addr:
                    return addr
        except OSError as e:
            print("updater: mDNS attempt %d failed:" % (attempt + 1), e)
        finally:
            s.close()
    return None


def _resolve_base_url(base_url, feed=None):
    """Resolve base_url's hostname to a numeric IP once, so every subsequent
    per-file/per-partition connection this session reuses it instead of
    repeating a fresh DNS/mDNS lookup -- bounding the exposure to one lookup
    per session instead of one per file."""
    host, port, _path = _parse_url(base_url)
    if _is_ipv4_literal(host):
        return base_url
    if host.lower().endswith(".local"):
        addr = _mdns_resolve(host, feed)
        if not addr:
            raise OSError("mDNS lookup for %s found nothing" % host)
    else:
        # Ordinary unicast DNS, which works fine alongside the GPU task.
        addr = socket.getaddrinfo(host, port)[0][-1][0]
    print("updater: resolved", host, "->", addr)
    return base_url.replace(host, addr, 1)


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
        # One checkpoint per directory -- this walk is the other real source
        # of "quiet time" between WiFi connecting and file-sync's own
        # progress ring (see run()'s prep-ring comment); most boards have few
        # enough directories that this barely matters, but it keeps the ring
        # alive (and the watchdog fed) instead of static on any board with
        # more of them.
        _prep_checkpoint()
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


# Scanning + checksumming hundreds of files (games/ROMs/system assets) can
# take a while with nothing to show for it when everything is already up to
# date -- print a heartbeat at most this often so the dev loop doesn't look
# stuck.
_SCAN_PROGRESS_INTERVAL_MS = 3000

# Cache of the last verified sha256 for each LFS path, keyed by manifest path
# -- lets a session skip re-reading + re-hashing files that were already
# confirmed correct, instead of hashing the full LFS content tree (195 files,
# ~15s on real hardware) on every single OTA session. Trust model mirrors the
# NVS-cached partition hashes in _update_partitions(): a cache hit is trusted
# outright rather than re-verified against flash content, which is only safe
# because nothing besides this updater (or a full authoritative
# deploy_micropython_fs.py reflash, which replaces this file along with
# everything else in one shot) ever writes LFS files on a fielded board. A
# manual mpremote cp of a single file, bypassing OTA, would go undetected --
# not a concern for the intended field update path, but worth knowing if
# debugging a "file didn't update" report.
_LFS_HASH_CACHE_PATH = "/.vsdk_lfs_cache.json"


def _load_hash_cache():
    # Best-effort like the NVS reads elsewhere in this file (_nvs_get): a
    # missing file, corrupt JSON, or anything else wrong with it just means
    # no cache -- never worth failing the sync over.
    try:
        with open(_LFS_HASH_CACHE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_hash_cache(cache):
    tmp_path = _LFS_HASH_CACHE_PATH + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(cache, f)
        os.rename(tmp_path, _LFS_HASH_CACHE_PATH)
    except OSError as e:
        print("updater: failed to save LFS hash cache:", e)


def _sync_lfs_files(base_url, files):
    import utime

    cache = _load_hash_cache()
    cache_dirty = False

    # Upfront estimate of "bytes that need transferring", for the file-sync
    # ring (vsdk_ota_rings.set_file_progress()): every file whose cached hash
    # doesn't already match the manifest. This can slightly overcount (a
    # cache miss sometimes turns out, after the real read+hash below, to
    # already be correct -- e.g. a fresh cache after a USB reflash) but never
    # undercounts, so the ring can only reach 100% a little early, never get
    # stuck short of it -- fine for a progress indicator, not worth a second
    # full scan just to be exact.
    total_bytes = sum(e["size"] for e in files if cache.get(e["path"]) != e["sha256"])
    done_bytes = 0
    vsdk_ota_rings.set_file_progress(0, total_bytes)

    total = len(files)
    checked = 0
    last_report = utime.ticks_ms()
    _progress("checking", "files", 0)
    for i, entry in enumerate(files):
        rel_path = entry["path"]
        expected_sha = entry["sha256"]
        size = entry["size"]
        local_path = "/" + rel_path
        needed_work = cache.get(rel_path) != expected_sha

        # A cache hit means this exact content was already verified on flash
        # in a previous session -- skip touching flash at all. Anything else
        # (no entry, or a stale hash because the manifest says the file
        # changed) falls back to a real read+hash, so an incorrect or
        # missing cache entry can never cause a bad file to be accepted, only
        # cost the same work this loop always used to do.
        if not needed_work:
            local_sha = expected_sha
        else:
            gc.collect()
            local_sha = _sha256_file(local_path)
            if local_sha == expected_sha:
                cache[rel_path] = local_sha
                cache_dirty = True
        checked += 1

        now = utime.ticks_ms()
        if utime.ticks_diff(now, last_report) >= _SCAN_PROGRESS_INTERVAL_MS:
            pct = checked * 100 // total
            print("updater: checksummed %d/%d files (%d%%)" % (checked, total, pct))
            _progress("checking", "files", pct)
            last_report = now

        if local_sha == expected_sha:
            if needed_work:
                # Counted in total_bytes above but turned out not to need a
                # download after all (see the overcount note) -- still counts
                # as "done" so the ring's denominator gets fully accounted for.
                done_bytes += size
                vsdk_ota_rings.set_file_progress(done_bytes, total_bytes)
            continue  # already up to date

        _progress("downloading", rel_path.replace("/", "_"), i * 100 // total)
        tmp_path = local_path + ".tmp"
        file_url = base_url + "/files/" + _url_quote(rel_path)
        sha = hashlib.sha256()

        try:
            _makedirs(local_path)
            file_received = 0
            with open(tmp_path, "wb") as f:
                def _write(chunk):
                    nonlocal file_received
                    f.write(chunk)
                    sha.update(chunk)
                    # Advance the white ring within this single file, not
                    # just once it finishes -- a multi-MB WAD/ROM can take
                    # tens of seconds, and without this the ring sat frozen
                    # at the previous file's tally for the whole transfer,
                    # then jumped straight to "done". _set_ring() no-ops
                    # unless the row actually changes, so this is as cheap as
                    # the per-block update _update_partitions() already does
                    # for the gray ring.
                    file_received += len(chunk)
                    vsdk_ota_rings.set_file_progress(done_bytes + file_received, total_bytes)
                # A large file (e.g. a multi-MB WAD) can take longer than the
                # watchdog timeout to transfer; nothing else feeds it during
                # this loop (unlike the per-chunk feed in _update_partitions),
                # so a slow download used to trip the WDT mid-transfer once it
                # was actually armed. Throttled like the checksumming
                # heartbeat above -- most files are small enough that this
                # never fires.
                last_report = utime.ticks_ms()
                for pct in _http_stream(file_url, _write, size):
                    vsdk_ota_rings.pulse_file_activity()
                    now = utime.ticks_ms()
                    if utime.ticks_diff(now, last_report) >= _SCAN_PROGRESS_INTERVAL_MS:
                        _progress("downloading", rel_path.replace("/", "_"), pct)
                        last_report = now
            _progress("checking", rel_path.replace("/", "_"), 100)
            got = binascii.hexlify(sha.digest()).decode()
            if got != expected_sha:
                print("updater: SHA256 mismatch for", rel_path, "- got", got, "expected", expected_sha)
                os.remove(tmp_path)
                continue
            os.rename(tmp_path, local_path)
            cache[rel_path] = got
            cache_dirty = True
            print("updater: updated", rel_path)
            done_bytes += size
            vsdk_ota_rings.set_file_progress(done_bytes, total_bytes)
        except Exception as e:
            print("updater: failed to update", rel_path, ":", e)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    _progress("checking", "files", 100)

    # Drop entries for paths no longer in the manifest so the cache doesn't
    # grow unboundedly over the life of a board (deleted-from-host files
    # that are still on-device per the "deletions" open question below are
    # simply re-hashed once, next time they reappear). Checked unconditionally
    # -- not just when cache_dirty -- because a manifest that only shrank
    # (every remaining path was a cache hit) wouldn't otherwise set that flag
    # at all, and the stale entries would never get pruned.
    manifest_paths = set(entry["path"] for entry in files)
    pruned_cache = {k: v for k, v in cache.items() if k in manifest_paths}
    if cache_dirty or len(pruned_cache) != len(cache):
        _save_hash_cache(pruned_cache)

    # Tier 1 is done -- don't leave white/green showing their last position
    # through tier 2/3's writes below.
    vsdk_ota_rings.hide_file_rings()


def _running_label():
    try:
        import esp32
        return esp32.Partition(esp32.Partition.RUNNING).info()[4]
    except Exception:
        return None


def _partition_matches(part, size, expected_sha, _block=4096, progress_fn=None):
    """Hash the partition's actual on-flash content (bounded to the real
    file size, not the whole partition capacity) and compare to expected_sha.
    Used to double-check an NVS-cached "up to date" hash actually reflects
    what's on flash -- the partition may have been rewritten (a bench
    reflash, a wipe, corruption) without the updater ever running, in which
    case the cache is stale and must not be trusted (see docs/internals/ota.md
    and the TODO note about recovery wrongly triggering after a manual flash
    that didn't update NVS checksums)."""
    h = hashlib.sha256()
    buf = bytearray(_block)
    remaining = size
    block_num = 0
    last_progress = -1
    while remaining > 0:
        part.readblocks(block_num, buf)
        n = min(_block, remaining)
        h.update(buf[:n] if n < _block else buf)
        remaining -= n
        block_num += 1
        if progress_fn:
            pct = (size - remaining) * 100 // size
            # Ten-percent increments make validation visible without flooding
            # the serial status channel once per 4 KiB flash block.
            if pct == 100 or pct >= last_progress + 10:
                progress_fn(pct)
                last_progress = pct
    return binascii.hexlify(h.digest()).decode() == expected_sha


def _update_partitions(base_url, partitions):
    import esp32

    running = _running_label()
    # ioctl(5) returns the block size (4096 bytes for SPI flash).
    # ioctl(6, block_num) erases a single 4096-byte sector.
    # writeblocks(block_num, buf) writes aligned 4096-byte blocks.
    _BLOCK = 4096

    order = ["fmsx", "retro-core", "prboom-go", "micropython"]

    # Upfront estimate of "blocks that need writing" across every partition
    # in this session, for the partition-write ring
    # (vsdk_ota_rings.set_partition_progress()). Just the NVS-hash comparison
    # -- not the extra on-flash _partition_matches() verify-read below -- so
    # this can occasionally undercount in the rare case of a stale NVS cache
    # (see that check's own comment); a progress ring is worth this
    # imprecision rather than a second, flash-reading pass just to be exact.
    total_blocks = 0
    for name in order:
        if name not in partitions:
            continue
        entry = partitions[name]
        nvs_key = _NVS_KEYS.get(name)
        stored_sha = _nvs_get(nvs_key) if nvs_key else None
        if stored_sha != entry["sha256"]:
            total_blocks += (entry["size"] + _BLOCK - 1) // _BLOCK
    done_blocks = 0
    vsdk_ota_rings.set_partition_progress(0, total_blocks)

    for name in order:
        if name not in partitions:
            continue
        entry = partitions[name]
        expected_sha = entry["sha256"]
        size = entry["size"]
        url = base_url + entry["url"]
        nvs_key = _NVS_KEYS.get(name)

        # Skip only if the NVS-cached hash matches the manifest AND (unless
        # this is the partition we're currently executing -- if it didn't
        # still hold a valid, bootable image we couldn't be running from it
        # right now) the partition's actual on-flash bytes still match it.
        # A stale cache (the partition was rewritten outside the updater,
        # bypassing NVS) must not be trusted, or a wiped/corrupted partition
        # would report "up to date" forever.
        if nvs_key:
            stored_sha = _nvs_get(nvs_key)
            if stored_sha == expected_sha:
                if name == running:
                    print("updater: partition %s up to date" % name)
                    continue
                verify_parts = esp32.Partition.find(esp32.Partition.TYPE_APP, label=name)
                if verify_parts:
                    gc.collect()
                    _progress("checking", name, 0)
                    if _partition_matches(
                        verify_parts[0], size, expected_sha,
                        progress_fn=lambda pct: _progress("checking", name, pct),
                    ):
                        print("updater: partition %s up to date" % name)
                        continue
                    print("updater: partition %s NVS hash matched but on-flash content didn't -- reinstalling" % name)

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

        _progress("writing", name, 0)
        print("updater: flashing partition", name, "(%d bytes)" % size)

        try:
            parts = esp32.Partition.find(esp32.Partition.TYPE_APP, label=name)
            if not parts:
                print("updater: partition not found:", name)
                continue
            part = parts[0]

            # No separate erase pass: writeblocks(block_num, buf) below (the
            # 3-arg form) already erases each 4096-byte block immediately
            # before writing it -- see esp32_partition_writeblocks() in
            # ports/esp32/esp32_partition.c, the "efficient erase" branch
            # taken whenever block_size >= NATIVE_BLOCK_SIZE_BYTES (always
            # true here). A prior explicit ioctl(6, i) pre-erase loop here
            # duplicated that same erase for every sector, doubling flash
            # erase time for no benefit (measured ~20-30% of total tier-2/3
            # time on real hardware).
            sha = hashlib.sha256()
            offset = 0
            # Fixed 4096-byte block buffer; avoids bytearray slice deletion.
            block_buf = bytearray(_BLOCK)
            block_pos = 0

            def write_chunk(chunk):
                nonlocal offset, block_pos, done_blocks
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
                        done_blocks += 1
                        vsdk_ota_rings.pulse_partition_activity()
                        vsdk_ota_rings.set_partition_progress(done_blocks, total_blocks)

            for pct in _http_stream(url, write_chunk, size):
                _progress("writing", name, pct)
                gc.collect()

            # Flush remaining bytes padded to _BLOCK boundary.
            if block_pos > 0:
                for i in range(block_pos, _BLOCK):
                    block_buf[i] = 0xFF
                part.writeblocks(offset // _BLOCK, block_buf)
                offset += _BLOCK
                done_blocks += 1
                vsdk_ota_rings.pulse_partition_activity()
                vsdk_ota_rings.set_partition_progress(done_blocks, total_blocks)

            _progress("checking", name, 100)
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

            # MicroPython firmware is handled last: set it as boot and reboot.
            # The new image will call mark_app_valid_cancel_rollback() after WiFi.
            if name == "micropython":
                _send("ota_progress micropython reboot 100\n")
                import machine
                part.set_boot()
                machine.reset()

        except Exception as e:
            print("updater: error flashing partition", name, ":", e)
            _progress("writing", name + "_error", 0)
            # Continue to next partition rather than aborting entirely.

    # Tier 2/3 is done -- don't leave gray/yellow showing their last
    # position (run()'s own vsdk_ota_rings.clear() would catch it a moment
    # later anyway, but a finished operation should look finished right
    # away, not after whatever comes next in run() gets around to it).
    vsdk_ota_rings.hide_partition_rings()


# How long to wait for one connect() to succeed before trying again, and how
# many of those attempts to give a quiet chance before saying so on-device --
# see the ring/label switch to red/"wifi problem" below. Chosen so the total
# time to that switch (~30s) roughly matches this function's old one-shot
# timeout, just broken into visible sub-attempts instead of one long silent
# wait -- see docs/internals/ota.md.
_WIFI_ATTEMPT_TIMEOUT_MS = 10000
_WIFI_ATTEMPTS_BEFORE_WARNING = 3


def _wifi_connect():
    """Connect WiFi using NVS credentials.

    Returns True if we brought WiFi up (caller must disconnect after OTA),
    False if WiFi was already connected (caller must leave it alone).
    Raises OSError only for something retrying can't fix (missing/unreadable
    NVS credentials) -- a slow or unreachable AP is not treated as fatal; this
    keeps retrying indefinitely, switching the on-device rings/label to a
    red "wifi problem" indicator after a few quiet attempts so a real outage
    is visible rather than looking like a hang (see vsdk_ota_rings.py).
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

    sta.active(True)
    attempt = 0
    warned = False
    while True:
        attempt += 1
        # Called every attempt, not just once at the attempt-3 transition:
        # ensure_started() (inside these) can itself fail the first time
        # it's tried -- confirmed on hardware, right after a hard reset,
        # some dependency (NVS/SPI) isn't consistently ready yet at the very
        # first call. Normally that's masked by however long WiFi/manifest/
        # LFS-scan naturally takes, giving it many later chances across
        # run() -- but when connect() itself raises immediately (see below)
        # every attempt after the first used to complete in well under a
        # second, so ensure_started() got at most one or two tries total
        # near t=0 and then never again, leaving the display dark for the
        # rest of a retry loop that (correctly) never gives up. Calling
        # these every attempt costs nothing once already showing the right
        # state -- see _set_ring()'s own early-return -- and keeps retrying
        # ensure_started() for as long as this loop runs.
        if attempt >= _WIFI_ATTEMPTS_BEFORE_WARNING:
            vsdk_ota_rings.show_wifi_problem()
        else:
            vsdk_ota_rings.show_wifi_connecting()
        if _feed_wdt:
            _feed_wdt()
        print("updater: connecting WiFi to", ssid, "(attempt %d)" % attempt)
        try:
            # A bad password or a driver-level hiccup (e.g. repeated failed
            # associations) can make connect() itself raise rather than just
            # leaving isconnected() False -- caught here so it counts as one
            # more failed attempt, not a reason to give up. Confirmed on
            # hardware: an uncaught exception here previously escaped all
            # the way out to run()'s own `except OSError`, ending the retry
            # loop entirely instead of eventually turning the ring red.
            sta.connect(ssid, password)
            waited_ms = 0
            while waited_ms < _WIFI_ATTEMPT_TIMEOUT_MS:
                if sta.isconnected():
                    print("updater: WiFi connected:", sta.ifconfig()[0])
                    return True
                utime.sleep_ms(500)
                waited_ms += 500
                if _feed_wdt:
                    _feed_wdt()
        except Exception as e:
            print("updater: WiFi attempt %d failed:" % attempt, e)
            # Also confirmed on hardware: without this, an immediately-
            # raising connect() turns this into a tight busy-loop (hundreds
            # of attempts/second) instead of a paced retry.
            utime.sleep_ms(2000)
        if attempt == _WIFI_ATTEMPTS_BEFORE_WARNING and not warned:
            print("updater: WiFi still not connected after %d attempts, will keep trying" % attempt)
            warned = True


def _wifi_disconnect():
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        sta.disconnect()
        sta.active(False)
        print("updater: WiFi disconnected")
    except Exception:
        pass


def run(base_url, send_fn, feed_fn=None, disconnect_wifi=True):
    """Run the full 3-tier OTA update.

    base_url  — e.g. "http://192.168.1.5:5653"
    send_fn   — callable that sends a bytes line back over the comms channel
    feed_fn   — optional zero-arg callable that feeds the caller's watchdog.
                Needed for the prep phase specifically (see
                _prep_checkpoint()); every later stage already feeds it
                indirectly, by way of the progress lines it sends.
    disconnect_wifi — tear the link down again on the way out (only if we
                brought it up). False for a caller that is about to retry
                anyway: recovery loops here every few seconds, and bringing
                WiFi down and straight back up each time costs real seconds
                and, with the GPU task running, is where an attempt that had
                already failed cleanly still went on to trip the watchdog --
                measured on hardware, ota_error at t+16s then a WDT reset at
                t+46s, exactly 30s later, with nothing in between. Nothing in
                recovery needs the link down: it either retries or reboots,
                and a reboot drops WiFi regardless.
    """
    global _comms_send, _feed_wdt
    _comms_send = send_fn
    _feed_wdt = feed_fn

    print("updater: starting OTA from", base_url)
    _send("ota_progress start fetching_manifest 0\n")
    vsdk_ota_rings.clear()  # fresh slate -- a previous failed attempt may have left rings lit
    vsdk_ota_rings.show_wifi_connecting()

    # Bring WiFi up only for the duration of the OTA session.
    _newly_connected = False
    try:
        _newly_connected = _wifi_connect()
    except OSError as e:
        _send(("ota_error wifi_connect_failed: %s\n" % e).encode())
        return
    finally:
        vsdk_ota_rings.hide_wifi()

    # Between "WiFi connected" and the first real file/partition total (once
    # _sync_lfs_files() below computes one), there's nothing to show a
    # progress ring against yet -- resolving the base station's address,
    # fetching the manifest, and scanning for stale .tmp files can together
    # take a real handful of seconds. Previously nothing was shown here at
    # all (the WiFi ring had just been hidden above), which reads as a
    # stall. pulse_prep_activity() gives this stretch its own bouncing
    # ring, pulsed at each checkpoint below; hide_prep_activity() below
    # retires it once _sync_lfs_files() takes over with real progress.
    _prep_checkpoint()

    try:
        try:
            base_url = _resolve_base_url(base_url, feed=_prep_checkpoint)
            _prep_checkpoint()
            manifest = _http_get_json(base_url + "/manifest")
            _prep_checkpoint()
        except Exception as e:
            _send(("ota_error manifest_fetch_failed: %s\n" % e).encode())
            return

        _cleanup_tmp_files()
        vsdk_ota_rings.hide_prep_activity()
        _sync_lfs_files(base_url, manifest.get("files", []))
        _update_partitions(base_url, manifest.get("partitions", {}))

        _send("ota_done ok\n")
        print("updater: OTA complete")
    finally:
        # Feed on the way out too: this teardown runs after the last progress
        # line, so without it the caller's watchdog is already counting down
        # untouched by the time we get here.
        if _feed_wdt:
            _feed_wdt()
        # Only disconnect if we brought WiFi up — don't kill a pre-existing connection
        # (e.g. desktop mode where comms.py already holds the link) — and only
        # if the caller isn't about to reconnect anyway (see disconnect_wifi).
        # Note: if _update_partitions flashed micropython and called machine.reset(),
        # we never reach here — that's fine, the reboot drops WiFi anyway.
        if _newly_connected and disconnect_wifi:
            _wifi_disconnect()
        vsdk_ota_rings.clear()
        if _feed_wdt:
            _feed_wdt()
