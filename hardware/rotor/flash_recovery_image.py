#!/usr/bin/env python3
"""Flash only the `factory` partition + NVS -- the streamlined bring-up
procedure for a fresh Ventilastation main board (see docs/internals/ota.md).

Unlike flash_vsdk_image.py (which also writes the ota_2 `micropython` slot --
now a bench-dev convenience, not the bring-up procedure), this writes
bootloader + partition table + micropython.bin to `factory` alone. `factory`
is the permanent recovery environment (see apps/micropython/main.py): on a
fresh board there's no vfs `main.py` yet, so it runs vsdk_recovery.py, which
fetches everything else -- vfs, native apps, and the real ota_2 micropython
copy -- over WiFi via the updater. USB flashing never touches those
partitions.

After flashing, provisions NVS if missing (`vs_board` wiring + `devel_wifi`
credentials) via the existing tools/provision_board.py / tools/provision_wifi.py,
read-first so re-running this during bench iteration doesn't clobber an
already-provisioned board. Pass --force to overwrite regardless, or
--skip-nvs to flash factory only.

Bench-observed timing note: recovery's WiFi connect / mDNS resolution calls
don't yield to a Ctrl-C interrupt at all (confirmed on hardware -- a raw
Ctrl-C sent mid-attempt can go unanswered for over a minute), so
vsdk_recovery.py gives external tools an explicit, guaranteed-idle ~8s
window right at boot, before the first network attempt, specifically so a
short fixed poll interval reliably lands inside it (see `_BOOT_GRACE_MS` in
vsdk_recovery.py). Once any attempt succeeds, recovery's loop exits for
good anyway: the KeyboardInterrupt it raises isn't a subclass of Exception,
so it escapes vsdk_recovery.py's `except Exception` handler and the board
just sits at the REPL from then on -- no further contention. The retry
budget below is still generous beyond that first window as a safety net
(e.g. a board that isn't fresh and is mid-cycle when this runs), just with
a shorter poll interval to reliably catch the boot-grace window itself.
"""

import argparse
import pathlib
import subprocess
import sys
import tempfile
import time


_MPREMOTE_TRIES = 6
_MPREMOTE_RETRY_DELAY_S = 2
_MPREMOTE_ATTEMPT_TIMEOUT_S = 20
_MPREMOTE_SETTLE_S = 3


def run_mpremote_with_retry(argv, tries=_MPREMOTE_TRIES, delay=_MPREMOTE_RETRY_DELAY_S,
                             attempt_timeout=_MPREMOTE_ATTEMPT_TIMEOUT_S, settle=_MPREMOTE_SETTLE_S):
    """Run an mpremote command, retrying on failure.

    Each attempt gets a generous timeout rather than being killed fast: mpremote's
    own raw-REPL-entry retries internally, and bench testing found a single
    patient ~20s attempt reliably lands within recovery's boot-grace window
    (see vsdk_recovery.py's `_BOOT_GRACE_MS`) in well under that time, whereas
    many short, externally-restarted attempts kept failing -- each fast-killed
    attempt seems to leave the board's raw-REPL parser in a partial-handshake
    state that a fresh attempt doesn't cleanly recover from. Once one attempt
    lands, recovery's loop exits -- but a *successful* `mpremote run` itself
    appears to soft-reset the board afterward (bench-observed: a call placed
    right after another successful one needed the same patience again), so
    every call gets its own brief settle pause first rather than assuming the
    board stays cooperative indefinitely after the first success.
    """
    time.sleep(settle)
    last_result = None
    for attempt in range(1, tries + 1):
        try:
            last_result = subprocess.run(argv, capture_output=True, text=True, timeout=attempt_timeout)
        except subprocess.TimeoutExpired:
            print(f"flash_recovery_image: mpremote attempt {attempt}/{tries} timed out, retrying...")
            continue
        if last_result.returncode == 0:
            return last_result
        print(f"flash_recovery_image: mpremote attempt {attempt}/{tries} failed, retrying...")
        time.sleep(delay)
    raise RuntimeError(
        f"mpremote command failed after {tries} attempts: {' '.join(argv)}\n"
        f"{last_result.stderr if last_result else ''}"
    )


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def run(cmd, cwd=None):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def run_in_idf_env(idf_path, command, cwd):
    cmd = [
        "/bin/zsh",
        "-lc",
        f"source {shell_quote(str(idf_path / 'export.sh'))} >/dev/null && {' '.join(shell_quote(part) for part in command)}",
    ]
    run(cmd, cwd=cwd)


def find_parent_root(script_path):
    vsdk_root = script_path.parents[2]
    ventilastation_root = vsdk_root.parents[1]
    return vsdk_root, ventilastation_root


def ensure_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")


def generate_partition_table(idf_path, partition_csv, output_path):
    command = [
        "python3",
        str(idf_path / "components/partition_table/gen_esp32part.py"),
        str(partition_csv),
        str(output_path),
    ]
    run(command)


def flash_factory_only(args, bootloader_path, partition_table_path, micropython_path):
    # Only bootloader + partition table + factory (0x10000). No ota_2 write:
    # that partition is installed/updated over WiFi by the updater, never USB.
    command = [
        "python3",
        "-m",
        "esptool",
        "--chip",
        "esp32s3",
        "-p",
        args.port,
        "-b",
        str(args.baud),
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "write_flash",
        "--flash_mode",
        "dio",
        "--flash_freq",
        "80m",
        "--flash_size",
        "16MB",
        "0x0",
        str(bootloader_path),
        "0x8000",
        str(partition_table_path),
        "0x10000",
        str(micropython_path),
    ]
    run_in_idf_env(args.idf_path, command, cwd=micropython_path.parent)


_BOARD_KEYS = (
    "hall_gpio", "irdiode_gpio", "led_spi_host", "led_clk", "led_mosi",
    "led_cs", "led_freq", "serial_uart", "serial_tx", "serial_rx", "serial_baud",
)


def _check_provisioned(port):
    """Read NVS directly over mpremote; returns (board_ok, wifi_ok)."""
    script = (
        "import esp32\n"
        "def _check(ns, keys, getter):\n"
        "    try:\n"
        "        nvs = esp32.NVS(ns)\n"
        "        for k in keys:\n"
        "            getter(nvs, k)\n"
        "        return True\n"
        "    except Exception:\n"
        "        return False\n"
        "board_ok = _check('vs_board', %r, lambda nvs, k: nvs.get_i32(k))\n"
        "def _wifi_get(nvs, k):\n"
        "    buf = bytearray(70)\n"
        "    nvs.get_blob(k, buf)\n"
        "wifi_ok = _check('devel_wifi', ['ssid', 'password'], _wifi_get)\n"
        "print('BOARD_OK' if board_ok else 'BOARD_MISSING')\n"
        "print('WIFI_OK' if wifi_ok else 'WIFI_MISSING')\n"
    ) % (list(_BOARD_KEYS),)

    with tempfile.TemporaryDirectory() as tmp:
        script_path = pathlib.Path(tmp) / "check_nvs.py"
        script_path.write_text(script)
        result = run_mpremote_with_retry(["mpremote", "connect", port, "run", str(script_path)])
    output = result.stdout
    return "BOARD_OK" in output, "WIFI_OK" in output


def _run_with_retry(cmd, tries=_MPREMOTE_TRIES, delay=_MPREMOTE_RETRY_DELAY_S,
                     attempt_timeout=_MPREMOTE_ATTEMPT_TIMEOUT_S, settle=_MPREMOTE_SETTLE_S):
    """Retry an external tool (provision_board.py/provision_wifi.py) that
    itself shells out to mpremote once, internally, with no retry of its own.
    See run_mpremote_with_retry's docstring: each call gets its own settle
    pause too, since a successful mpremote call appears to soft-reset the
    board, restarting recovery's cycle (and its boot-grace window) fresh."""
    time.sleep(settle)
    result = None
    for attempt in range(1, tries + 1):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=attempt_timeout)
        except subprocess.TimeoutExpired:
            print(f"flash_recovery_image: attempt {attempt}/{tries} timed out, retrying...")
            continue
        if result.returncode == 0:
            print(result.stdout, end="")
            return
        print(f"flash_recovery_image: attempt {attempt}/{tries} failed, retrying...")
        time.sleep(delay)
    if result is not None:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
    raise RuntimeError(f"command failed after {tries} attempts: {' '.join(cmd)}")


def _provision_board(vsdk_root, args):
    _run_with_retry([
        "python3", str(vsdk_root / "tools" / "provision_board.py"),
        "--port", args.port,
        "--hall-gpio", str(args.hall_gpio),
        "--irdiode-gpio", str(args.irdiode_gpio),
        "--led-spi-host", str(args.led_spi_host),
        "--led-clk", str(args.led_clk),
        "--led-mosi", str(args.led_mosi),
        "--led-cs", str(args.led_cs),
        "--led-freq", str(args.led_freq),
        "--serial-uart", str(args.serial_uart),
        "--serial-tx", str(args.serial_tx),
        "--serial-rx", str(args.serial_rx),
        "--serial-baud", str(args.serial_baud),
    ])


def _provision_wifi(vsdk_root, args):
    if not args.wifi_ssid:
        print(
            "flash_recovery_image: no --wifi-ssid given, skipping WiFi provisioning "
            "(run 'make wifi-provision WIFI_SSID=... WIFI_PASS=...' separately)"
        )
        return
    _run_with_retry([
        "python3", str(vsdk_root / "tools" / "provision_wifi.py"),
        "--port", args.port,
        "--wifi-ssid", args.wifi_ssid,
        "--wifi-password", args.wifi_password,
    ])


def _reset_board(port):
    with tempfile.TemporaryDirectory() as tmp:
        script_path = pathlib.Path(tmp) / "reset.py"
        script_path.write_text("import machine\nmachine.reset()\n")
        try:
            run_mpremote_with_retry(["mpremote", "connect", port, "run", str(script_path)])
        except RuntimeError as e:
            # Not fatal: the board is provisioned either way, just sitting at
            # the REPL instead of running. A power cycle also gets it going.
            print(f"flash_recovery_image: final reset failed ({e}); power-cycle the board to start it")


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root, ventilastation_root = find_parent_root(script_path)
    default_build_dir = vsdk_root / "hardware/rotor/build"

    parser = argparse.ArgumentParser(description="Flash factory + NVS only (streamlined bring-up)")
    parser.add_argument("--port", required=True, help="Serial port, for example /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument(
        "--idf-path",
        type=pathlib.Path,
        default=ventilastation_root / "esp-idf/esp-5.5.2",
    )
    parser.add_argument(
        "--partition-csv",
        type=pathlib.Path,
        default=vsdk_root / "hardware/rotor/partitions-ventilastation.csv",
    )
    parser.add_argument("--board", default="VENTILASTATION")
    parser.add_argument("--board-variant", default="SPIRAM_OCT")
    parser.add_argument(
        "--micropython-root",
        type=pathlib.Path,
        default=vsdk_root / "hardware/rotor/micropython",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=default_build_dir,
    )
    parser.add_argument("--force", action="store_true", help="Overwrite NVS even if already provisioned")
    parser.add_argument("--skip-nvs", action="store_true", help="Flash factory only, skip NVS entirely")

    # vs_board defaults match `make configure-board`'s Ventilastation III values.
    parser.add_argument("--hall-gpio", type=int, default=7)
    parser.add_argument("--irdiode-gpio", type=int, default=7)
    parser.add_argument("--led-spi-host", type=int, default=2)
    parser.add_argument("--led-clk", type=int, default=12)
    parser.add_argument("--led-mosi", type=int, default=13)
    parser.add_argument("--led-cs", type=int, default=14)
    parser.add_argument("--led-freq", type=int, default=20000000)
    parser.add_argument("--serial-uart", type=int, default=2)
    parser.add_argument("--serial-tx", type=int, default=5)
    parser.add_argument("--serial-rx", type=int, default=6)
    parser.add_argument("--serial-baud", type=int, default=115200)

    parser.add_argument("--wifi-ssid", default="", help="Also provision devel_wifi if missing")
    parser.add_argument("--wifi-password", default="")

    args = parser.parse_args()

    args.idf_path = args.idf_path.resolve()
    args.partition_csv = args.partition_csv.resolve()
    args.micropython_root = args.micropython_root.resolve()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    micropython_build_dir = (
        args.micropython_root / "ports/esp32" / f"build-{args.board}-{args.board_variant}"
    )
    bootloader_path = micropython_build_dir / "bootloader/bootloader.bin"
    micropython_path = micropython_build_dir / "micropython.bin"
    partition_table_path = args.output_dir / "partition-table-ventilastation.bin"

    ensure_file(bootloader_path, "MicroPython bootloader")
    ensure_file(micropython_path, "MicroPython application")
    ensure_file(args.partition_csv, "Partition CSV")

    generate_partition_table(args.idf_path, args.partition_csv, partition_table_path)
    flash_factory_only(args, bootloader_path, partition_table_path, micropython_path)

    if args.skip_nvs:
        return

    board_ok, wifi_ok = _check_provisioned(args.port)

    if args.force or not board_ok:
        print("flash_recovery_image: provisioning vs_board NVS...")
        _provision_board(vsdk_root, args)
    else:
        print("flash_recovery_image: vs_board NVS already provisioned, skipping (use --force to overwrite)")

    if args.force or not wifi_ok:
        _provision_wifi(vsdk_root, args)
    else:
        print("flash_recovery_image: devel_wifi NVS already provisioned, skipping (use --force to overwrite)")

    _reset_board(args.port)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
