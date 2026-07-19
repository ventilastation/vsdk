#!/usr/bin/env python3
"""Host-side read/modify/write of an ESP32 NVS partition, without depending
on mpremote running code on the board.

Used by provision_board.py, provision_wifi.py and flash_recovery_image.py to
change a handful of NVS keys (vs_board wiring, devel_wifi credentials) while
preserving every other key already on the board -- notably vsdk_ota's stored
partition hashes (see docs/internals/ota.md). The flow: dump the whole "nvs"
partition over esptool (which only needs the ROM bootloader, not a booted
MicroPython), decode it with ESP-IDF's own nvs_tool.py, patch in the
requested keys, re-encode the whole partition with ESP-IDF's own
nvs_partition_gen.py, and write it back over esptool. The NVS binary format
itself is never hand-parsed here -- both directions are delegated to
Espressif's own bundled tools.

Requires an ESP-IDF environment already sourced in this shell (for esptool
and the nvs_partition_gen package installed alongside idf.py) -- callers
resolve idf_path from $IDF_PATH, so run `source .../export.sh` once before
using any of this.
"""

import csv
import io
import json
import pathlib
import subprocess
import tempfile


def _run(cmd, capture=False):
    print("$", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, capture_output=capture, text=capture)


# nvs_tool.py's decoded type name -> nvs_partition_gen.py's CSV encoding.
# blob/blob_data both round-trip through the same base64 CSV encoding;
# blob_index entries carry no value of their own (multi-chunk bookkeeping)
# and are skipped -- nvs_tool.py's own minimal dump already excludes them.
_TYPE_TO_ENCODING = {
    "uint8_t": "u8", "int8_t": "i8",
    "uint16_t": "u16", "int16_t": "i16",
    "uint32_t": "u32", "int32_t": "i32",
    "uint64_t": "u64", "int64_t": "i64",
    "string": "string",
    "blob": "base64", "blob_data": "base64",
}


def dump(idf_path, port, offset, size, baud=460800):
    """Read `size` bytes at `offset` from the board's flash via esptool.
    Returns the path to a temp file holding the raw dump; caller unlinks it."""
    fd, path = tempfile.mkstemp(suffix=".bin")
    import os
    os.close(fd)
    dump_path = pathlib.Path(path)
    _run([
        "python3", "-m", "esptool",
        "--chip", "esp32s3",
        "-p", port,
        "-b", str(baud),
        "read_flash", hex(offset), hex(size), str(dump_path),
    ])
    return dump_path


def read_entries(idf_path, dump_path):
    """Decode a dumped NVS partition into {(namespace, key): (encoding, value)}
    ready to feed back into write(), using ESP-IDF's own nvs_tool.py."""
    nvs_tool = pathlib.Path(idf_path) / "components/nvs_flash/nvs_partition_tool/nvs_tool.py"
    result = _run(["python3", str(nvs_tool), "-f", "json", "-d", "minimal", str(dump_path)], capture=True)
    parsed = json.loads(result.stdout)
    entries = {}
    for e in parsed:
        if e["state"] != "Written":
            continue
        encoding = _TYPE_TO_ENCODING.get(e["encoding"])
        if encoding is None:
            continue
        entries[(e["namespace"], e["key"])] = (encoding, str(e["data"]))
    return entries


def encode_update(value):
    """int -> i32 (matches MicroPython's nvs.set_i32/get_i32);
    str/bytes -> a binary blob (matches nvs.set_blob/get_blob)."""
    if isinstance(value, bool):
        raise TypeError("bool is not a supported NVS value type")
    if isinstance(value, int):
        return ("i32", str(value))
    if isinstance(value, bytes):
        value = value.decode()
    return ("binary", value)


def _build_csv(entries):
    by_namespace = {}
    for (namespace, key), (encoding, value) in entries.items():
        by_namespace.setdefault(namespace, []).append((key, encoding, value))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["key", "type", "encoding", "value"])
    for namespace, rows in by_namespace.items():
        writer.writerow([namespace, "namespace", "", ""])
        for key, encoding, value in rows:
            writer.writerow([key, "data", encoding, value])
    return buf.getvalue()


def write(idf_path, port, offset, size, entries, baud=460800):
    """entries: {(namespace, key): (encoding, value)} -- the complete desired
    partition content (see read_entries()/encode_update()). Regenerates the
    whole partition and writes it back; nothing not in `entries` survives."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        csv_path = tmp / "nvs.csv"
        bin_path = tmp / "nvs.bin"
        csv_path.write_text(_build_csv(entries))

        gen_script = pathlib.Path(idf_path) / "components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py"
        _run(["python3", str(gen_script), "generate", str(csv_path), str(bin_path), hex(size)])

        _run([
            "python3", "-m", "esptool",
            "--chip", "esp32s3",
            "-p", port,
            "-b", str(baud),
            "write_flash", hex(offset), str(bin_path),
        ])


def provision(idf_path, port, offset, size, updates, baud=460800):
    """Dump the partition, decode it, patch in `updates`
    ({(namespace, key): python value}), and write the merged result back.
    Every other existing key (e.g. vsdk_ota's OTA hashes) is preserved."""
    dump_path = dump(idf_path, port, offset, size, baud=baud)
    try:
        existing = read_entries(idf_path, dump_path)
    finally:
        dump_path.unlink(missing_ok=True)

    merged = dict(existing)
    for key, value in updates.items():
        merged[key] = encode_update(value)

    write(idf_path, port, offset, size, merged, baud=baud)


def read_values(idf_path, port, offset, size, baud=460800):
    """Dump + decode only -- for callers that just want to inspect NVS
    (e.g. checking whether a board is already provisioned)."""
    dump_path = dump(idf_path, port, offset, size, baud=baud)
    try:
        return read_entries(idf_path, dump_path)
    finally:
        dump_path.unlink(missing_ok=True)
