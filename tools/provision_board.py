#!/usr/bin/env python3
"""Write the Ventilastation main-board wiring configuration to NVS.

NVS survives firmware and filesystem reflashes, and is shared by MicroPython
and the native Retro-Go apps. Use through ``make configure-board`` unless a
different board revision needs explicit values.
"""

import argparse
import pathlib
import subprocess
import sys
import tempfile


NVS_NAMESPACE = "vs_board"
NVS_KEYS = (
    "hall_gpio",
    "irdiode_gpio",
    "led_spi_host",
    "led_clk",
    "led_mosi",
    "led_cs",
    "led_freq",
    "serial_uart",
    "serial_tx",
    "serial_rx",
    "serial_baud",
)


def main():
    parser = argparse.ArgumentParser(description="Write main-board wiring to NVS")
    parser.add_argument("--port", "-p", help="Serial port (auto-detected by mpremote if omitted)")
    for key in NVS_KEYS:
        parser.add_argument("--" + key.replace("_", "-"), type=int, required=True)
    args = parser.parse_args()

    values = {key: getattr(args, key) for key in NVS_KEYS}
    with tempfile.TemporaryDirectory() as tmp:
        script = pathlib.Path(tmp) / "setup_board_nvs.py"
        lines = ["import esp32", "nvs = esp32.NVS(%r)" % NVS_NAMESPACE]
        lines += ["nvs.set_i32(%r, %d)" % (key, values[key]) for key in NVS_KEYS]
        lines += ["nvs.commit()", "print('Main-board configuration saved to NVS vs_board')"]
        script.write_text("\n".join(lines) + "\n")
        cmd = ["mpremote"]
        if args.port:
            cmd += ["connect", args.port]
        cmd += ["run", str(script)]
        print("$", " ".join(cmd))
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except KeyboardInterrupt:
        sys.exit(1)
