# Hardware Workbench

The workbench is a second ESP32-S3 board used to test a real Ventilastation
rotor board ("the DUT" — device under test) as close to normal production
operation as possible, without a spinning fan, a real hall sensor, or a
laptop's UART cable hanging off the rotor.

It plays three roles at once:

1. **Stimulus generator** — resets the DUT, then feeds it a clean,
   remote-controllable hall-sensor pulse train (0-700 RPM, default 600),
   exactly like the DUT would see spinning on a real fan. Both the reset
   and the RPM are controllable live from the pyglet emulator's UI over
   Wi-Fi.
2. **LED bus spy** — taps the DUT's LED SPI bus (clock + data only, no CS,
   no MISO) as a passive SPI slave, decodes the APA102-style frames the DUT
   is already driving out to its physical LED strips, and re-streams them
   over Wi-Fi to a desktop `vsdk/emulator` (pyglet) instance using the exact
   same wire protocol the DUT itself would use if it opened that link
   directly.
3. **Serial bridge** — bridges the DUT's UART link (used today for
   base/rotor and multi-unit sync traffic — buttons in, sound/music
   requests out) to the workbench's USB port, so the pyglet emulator can
   stand in for the base over serial without being wired to the DUT
   directly.

The workbench joins an existing Wi-Fi network (station mode, like the DUT
itself does) rather than running its own access point, so the PC running
the pyglet emulator keeps normal internet access on the same network, and
finds the workbench via mDNS instead of a hardcoded IP.

The DUT runs its normal firmware, with one small addition: its LED SPI master
drives a chip-select (`GPIO17`) so the workbench's SPI slave can frame each
burst. See ["DUT firmware: one small change"](#dut-firmware-one-small-change).

Firmware for the workbench itself lives in
[`hardware/workbench/`](hardware/workbench/).

## Architecture

```
                    +-----------------------------------------+
                    |               Desktop PC                 |
                    |            vsdk/emulator (pyglet)         |
                    |  python emu.py --remote                   |
                    |  ------------------------------------      |
                    |  display_conn (Wi-Fi, TCP :5005):           |
                    |    <- "frame_rgb\n" + 41472 bytes            |
                    |    -> "reset\n" / "rpm <n>\n"                 |
                    |    (RPM slider + reset button in the UI)       |
                    |  workbench_conn (USB serial):                   |
                    |    -> button-state byte                          |
                    |    <- sound/music/notes/... commands              |
                    +---------+----------------------+------------------+
                              ^ Wi-Fi (joins existing   ^ USB serial
                              | AP; found via mDNS as   |
                              | ventilastation-workbench.local:5005
                              |                          |
                    +---------+--------------------------+-------------+
                    |                Workbench ESP32-S3                 |
                    |  - Wi-Fi STA + mDNS + TCP server (display/control)  |
                    |  - SPI slave (LED bus spy)                           |
                    |  - hall pulse generator (0-700 RPM, remote-settable)  |
                    |  - reset driver (remote-triggerable)                   |
                    |  - UART <-> USB bridge                                  |
                    +---+-----+-----+-----+-----------------------------------+
                        |     |     |     |
                  hall  |     |     |     | UART tx/rx
                  pulse |     |     |     |
                        |   led_clk |   led_mosi
                        |     |     |     |
                    +---v-----v-----v-----v-------+
                    |   DUT: real Ventilastation    |
                    |   rotor board (unmodified      |
                    |   firmware)                     |
                    +-----------------------------------+
                                        |
                                reset (EN) pin, driven
                                by the workbench at boot
                                or on request from the UI
```

The workbench never drives the LED bus (its SPI MOSI/CLK pins are inputs
only, MISO is unused) and only drives its UART TX with whatever bytes the
pyglet emulator sends as button state, so the DUT's physical LED strips
and its UART behavior keep working exactly as they would standalone — the
workbench mostly listens in, plus the two things it's explicitly asked to
control (reset, RPM).

## Pin connections

All signals are 3.3V and directly compatible between the two ESP32-S3
boards. Tie the grounds of the workbench and the DUT together.

| Signal              | Workbench pin (suggested) | DUT pin (from `hw_config.py`)         | Direction         | Notes |
|---------------------|---------------------------|-----------------------------------------|-------------------|-------|
| Hall sensor          | `GPIO7`  (`WB_HALL_PIN`)  | `hall_gpio`                              | workbench → DUT   | Idles HIGH, pulses LOW once per simulated revolution, matching a real hall sensor with pull-up. |
| Reset / EN           | `GPIO4`  (`WB_RESET_PIN`) | DUT `EN` / reset pin                     | workbench → DUT   | Open-drain style: workbench drives LOW to assert, then releases to `INPUT` (Hi-Z) so the DUT's own pull-up brings it back HIGH. Never drive HIGH directly. |
| LED bus clock        | `GPIO12` (`WB_SPI_SCLK_PIN`) | `led_clk`                             | DUT → workbench   | Input only. 20 MHz APA102-style clock. |
| LED bus data         | `GPIO13` (`WB_SPI_MOSI_PIN`) | `led_mosi`                            | DUT → workbench   | Input only. |
| LED bus CS           | `GPIO14` (`WB_SPI_CS_PIN`)   | `led_cs`                              | DUT → workbench   | Real chip-select the DUT's LED SPI master now drives. Asserted low per 444-byte burst; frames the slave transactions — see [LED bus capture](#led-bus-capture-chip-select). |
| UART TX              | `GPIO6` (`WB_UART_TX_PIN`)  | `serial_rx`                           | workbench → DUT   | Workbench transmits into the DUT's UART RX. |
| UART RX              | `GPIO5` (`WB_UART_RX_PIN`)  | `serial_tx`                           | DUT → workbench   | Workbench receives from the DUT's UART TX. |
| Ground               | GND                        | GND                                     | —                 | Common reference, required. |

DUT pin numbers above are the current Ventilastation III config in
[`apps/micropython/ventilastation/hw_config.py`](apps/micropython/ventilastation/hw_config.py)
(`hall_gpio=7`, `led_clk=12`, `led_mosi=13`, `led_cs=14`, `serial_tx=5`, `serial_rx=6`).
That file also has commented-out pin sets for the "European Edition" and
"Ventilastation 2" boards — if the DUT under test is one of those
revisions, rewire to match its actual GPIOs; the workbench-side pins in
`hardware/workbench/workbench_esp32s3/config.h` don't need to change.

The workbench-side pin choices are arbitrary GPIOs picked to avoid
ESP32-S3 strapping pins (0, 3, 45, 46), the native USB pins (19, 20), and
the octal-PSRAM pins used on `N16R8`-style modules (35-37); swap them in
`config.h` to fit whatever workbench dev board is on hand.

## Sequence of operation

1. Workbench boots, brings up its USB serial console, the DUT UART bridge,
   and the LED-bus SPI slave, then joins the Wi-Fi network provisioned into
   its NVS (see [Wi-Fi provisioning](#wi-fi-provisioning-and-mdns-discovery)
   below) and starts advertising itself over mDNS.
2. Workbench pulses the reset line low for ~150 ms and releases it —
   equivalent to pressing the DUT's reset button — then starts generating
   the hall pulse train (600 RPM by default) immediately so the DUT sees
   rotation from very early in its boot.
3. DUT boots its normal firmware, sees hall pulses, and starts driving its
   LED SPI bus as if it were spinning on a real fan.
4. Whenever a PC on the same Wi-Fi network runs the desktop emulator in
   hardware mode (`cd vsdk && python emulator/emu.py --remote`), it resolves
   `ventilastation-workbench.local` over mDNS and opens a TCP connection to
   port 5005. From then on the workbench streams `frame_rgb` frames it has
   reconstructed from the spied LED bus, and accepts `reset`/`rpm <n>`
   commands from the emulator's RPM slider and reset button (see
   [RPM and reset control](#rpm-and-reset-control)).
5. The same emulator process also opens the workbench's USB serial port,
   over which it sends button-state bytes toward the DUT and receives
   sound/music requests from it — see
   [Pyglet transport split](#pyglet-emulator-transport-split).
6. The UART bridge itself runs continuously regardless of what's connected
   over USB: bytes from the DUT's UART TX are forwarded to the workbench's
   USB serial output, and anything arriving on the USB serial input is
   forwarded to the DUT's UART RX.

## LED bus capture (chip-select)

The DUT's LED SPI master feeds an APA102-style LED chain, which doesn't
itself need a chip-select. Originally the bus was clock+data only
(`spics_io_num = -1` in `minispi.c`), and the workbench tried to spy on it
with an ESP-IDF `spi_slave` held "always selected" (CS tied low). **That did
not work:** the ESP32-S3 SPI slave peripheral needs CS edges to delimit
transactions, so with a static CS it never completed a single transfer
(confirmed on real hardware — clock toggling, zero bursts decoded).

The fix is to give the bus a real chip-select. The DUT's LED SPI master now
drives CS on `GPIO17` (`LEDS_SPI_CS_PIN` in
[`minispi.c`](hardware/rotor/modules/povdisplay/minispi.c)), which the ESP32
hardware asserts low around each `spi_device` transaction and releases
between them. The LED strips ignore it (they aren't wired to CS); the
workbench is. `GPIO17` is unused in the active `hw_config`.

Each burst the master sends is a 444-byte buffer built by
[`povdisplay.c`](hardware/rotor/modules/povdisplay/povdisplay.c)
`init_buffers()`:

```
[ 4-byte zero start frame ]
[ 54 × 4-byte LED frame  ]   <- "arm 0" (dma_pixels0, mirror column, LED order reversed)
[ 54 × 4-byte LED frame  ]   <- "arm 1" (dma_pixels1, current column, direct LED order)
[ 8-byte end frame        ]
= 444 bytes total (with the 54-LED bar used today)
```

each LED frame being `[brightness, B, G, R]` (brightness dropped on decode).
`gpu_step()` sends one such burst at 20 MHz per column change (up to 256 per
revolution), so CS pulses low once per column.

The workbench runs the ESP-IDF `spi_slave` driver on `SPI2_HOST` with
`spics_io_num = WB_SPI_CS_PIN` (`GPIO14`, wired to the DUT's `GPIO17`) and
keeps several 444-byte DMA receive buffers queued
(`hardware/workbench/workbench_esp32s3/main/led_capture.c`). Each CS
deassertion completes a transaction with `trans_len == 444` bytes, which is
decoded into the frame buffer. Verified end-to-end on hardware at 600 RPM:
2560 clean 444-byte bursts/second (256 columns × 10 rev/s), zero malformed.
`led_capture` logs a `bursts/s: good=… other=…` health line once a second.

## Column tracking and frame reassembly

The pyglet emulator (`vsdk/emulator/comms.py` `dispatch_command()`) expects a
`frame_rgb` command over the TCP link followed by exactly
`256 * 54 * 3 = 41472` raw bytes: 256 angular columns, 54 LEDs each, plain
`R, G, B` (see `vsdk/apps/micropython/ventilastation/ventilagon_emu.py`
`render_frame()` for the reference layout the real firmware also uses when
it pushes `frame_rgb` telemetry itself).

Since the workbench is also the thing generating the hall pulses, it
already knows the current rotation phase precisely — no need to infer it
from a captured hall edge. `hall_sim.c` tracks the timestamp of the last
simulated pulse and the current RPM (settable at runtime — see
[RPM and reset control](#rpm-and-reset-control) — and clamped to
`[0, WB_HALL_RPM_MAX]`, where 0 stops the pulse train and freezes the
column at 0) and reproduces the DUT's own column formula from
`gpu_step()`: 

```
column = ((now_us - last_turn_us) * 256 / rotation_period_us) % 256
```

(`column_offset`, a runtime calibration value on real DUTs, is assumed to
be 0 — the workbench has no way to know a given DUT's calibrated offset,
so the reconstructed image may appear rotated relative to what that DUT's
own physical LEDs show. This is a cosmetic limitation only.)

When a 444-byte burst is decoded, `led_capture.c` reads the column at
that moment, computes the mirror column (`(column + 128) % 256`), and
writes:

- arm 0's 54 LEDs (order reversed, per `dma_pixels0[n] = draw_buffer0[53-n]`
  in the real firmware) into the mirror column of the frame buffer,
- arm 1's 54 LEDs (direct order) into the current column,

dropping each LED's brightness byte and keeping `R, G, B`. There is a
roughly one-burst pipeline delay versus the DUT's true state (the real
firmware sends the *previous* column's buffer while it computes the next
one) — negligible for a visualization tool.

The assembled 256×54×3 buffer is snapshotted under a mutex and sent as one
`frame_rgb` message roughly every 33 ms (`WB_TELEMETRY_FRAME_INTERVAL_MS`)
to whichever client is currently connected. Only `frame_rgb` is
implemented; the workbench doesn't emit `sprites`/`palette`/`sound`/etc.
telemetry, since none of that is observable from the LED bus alone.

## Wi-Fi provisioning and mDNS discovery

The workbench joins an existing Wi-Fi network in station mode (`telemetry.c`)
rather than running its own access point, so the PC running the pyglet
emulator keeps normal internet access on the same network. Credentials are
read from NVS namespace `voom_wifi`, keys `ssid`/`password` — **the same
namespace and keys** `apps/micropython/ventilastation/comms.py` reads on
the DUT itself, so the mechanism (if not the physical NVS, which is
per-chip) is deliberately identical on both boards.

Since the workbench is a compiled ESP-IDF app rather than a live
MicroPython REPL, it can't be provisioned the way `make dev-deploy` does
for the DUT (`mpremote run` against a live interpreter). Instead,
`tools/provision_wifi.py` builds a small NVS partition image with
`nvs_partition_gen.py` and flashes it straight to the `nvs` partition's
offset (`0x9000`, pinned by `partitions.csv`) — no rebuild or full reflash
needed to change networks:

```bash
source /path/to/esp-idf/esp-5.5.2/export.sh
make workbench-wifi-provision PORT=/dev/cu.usbmodemXXXX \
    WIFI_SSID=mywifi WIFI_PASS=mypassword
```

Other workbench make targets (see the top-level `Makefile`, next to the
DUT's `dev-deploy`/`dev-emulator`):

```bash
make workbench-build                       # idf.py build
make workbench-flash PORT=/dev/cu.usbmodemXXXX
make workbench-monitor PORT=/dev/cu.usbmodemXXXX
```

After provisioning and a reset, the workbench connects, then advertises
itself over mDNS (`espressif/mdns` managed component) as
`ventilastation-workbench.local`, with a `_ventilastation-wb._tcp` service
record, so the emulator doesn't need to know its DHCP-assigned IP.

The emulator resolves that service itself with the `zeroconf` Python
package (`comms.py`'s `ConnIP._resolve_mdns()`) rather than asking the OS
resolver for `ventilastation-workbench.local` — plenty of Python builds
(including a plain venv on macOS) don't get the same Bonjour `.local`
special-casing that macOS CLI tools (`ping`, `dns-sd`) and the
Apple-provided system Python get, and fail the hostname lookup instantly
without ever attempting an mDNS query. Querying the service directly with
`zeroconf` sidesteps that entirely and works the same way regardless of
which Python build or OS is running the emulator. If mDNS is somehow
unavailable on a given network, pass the workbench's IP explicitly instead
(see below).

## RPM and reset control

Once connected, the same TCP link that streams `frame_rgb` also accepts
simple line commands from the client (`telemetry.c`'s
`poll_client_commands()`/`handle_client_line()`):

- `reset\n` — pulses the DUT's reset line (`reset_ctl_pulse()`), exactly
  like the boot-time reset.
- `rpm <n>\n` — sets the simulated hall RPM at runtime
  (`hall_sim_set_rpm()`), clamped to `[0, 700]`.

The pyglet emulator's window (`emulator/pyglet2x/pygletdraw.py`) draws an
RPM slider (0-700, default 600) and a RESET button in the bottom-left
corner when running against real hardware; dragging the slider sends
`rpm <n>` (only when the rounded value changes), and clicking RESET sends
`reset`. Both go out via `comms.send_workbench()`, which writes directly to
the Wi-Fi connection — harmless no-ops if the workbench isn't connected.

## Pyglet emulator transport split

`vsdk/emulator/comms.py` normally talks to a single link for everything
(the local desktop MicroPython subprocess, over a loopback TCP socket).
Against a real workbench (`python emu.py --remote` or `--no-display`) it
instead opens two:

- `display_conn` (Wi-Fi, TCP `:5005`) — `frame_rgb` in, `reset`/`rpm` out.
  Everything covered above.
- `workbench_conn` (USB serial, via the workbench's UART bridge) — button
  state out, sound/music/notes/etc. requests in. This is exactly the
  traffic that would normally cross the DUT<->base UART link (see
  `hardware/base/README.md`: "the code running on the base gathers
  joystick movement and button presses... the cpu sends back requests for
  music and sounds"); the emulator, connected through the workbench's
  serial passthrough, is simply standing in for the base.

Both connections share the same command dispatcher
(`comms.dispatch_command()`), so nothing needs to know in advance which
transport a given command arrives on — in local-simulation mode (no
workbench involved) everything, including audio, still arrives on
`display_conn` exactly as before this change.

The workbench's serial port is auto-detected (matching common USB-serial
device names on macOS/Linux) or can be set explicitly with
`--serial-port /dev/cu.usbmodemXXXX`.

```bash
cd vsdk
python emulator/emu.py --remote                          # mDNS + serial auto-detect
python emulator/emu.py 192.168.1.42 --remote \
    --serial-port /dev/cu.usbmodem14201                   # explicit overrides
```

## UART bridge

`serial_bridge.c` opens a hardware UART (`UART_NUM_1`) on
`WB_UART_RX_PIN`/`WB_UART_TX_PIN` at `WB_UART_BAUD` (115200, matching
`machine.UART(2, ...)` in
[`apps/micropython/ventilastation/serialcomms.py`](apps/micropython/ventilastation/serialcomms.py))
and copies bytes in both directions between that UART and the workbench's
**native USB-Serial-JTAG** — the interface the PC actually opens as
`/dev/ttyACM*` / `/dev/cu.usbmodem*`. (The host side is *not* `UART_NUM_0`;
its GPIO43/44 pins aren't on the USB link, so an earlier `UART_NUM_0`
version silently dropped all button/sound traffic. The console is set to
USB-Serial-JTAG in `sdkconfig.defaults`, and the bridge installs its driver
via `usb_serial_jtag_vfs_use_driver()`.) Diagnostic log lines from this
firmware share that same USB endpoint, so they're interleaved with raw DUT
traffic on whatever terminal is watching the workbench's USB port. This is
the link the pyglet emulator's `workbench_conn` (above) uses for button
state and audio requests.

## DUT firmware: one small change

Everything the workbench does is transparent to the DUT except one addition:
the LED SPI master now drives a chip-select (`GPIO17`) so the workbench slave
can frame bursts (see [LED bus capture](#led-bus-capture-chip-select)). That
is the *only* DUT firmware change — a one-line `spics_io_num` in
[`minispi.c`](hardware/rotor/modules/povdisplay/minispi.c); it's inert on the
real rotor since nothing else is wired to `GPIO17`. Nothing under
`vsdk/apps/micropython/ventilastation/*` changes.

Otherwise the DUT behaves exactly as in normal operation:

- **Hall pin**: the DUT firmware just reads a plain GPIO with a
  negative-edge interrupt (`hall_init()` in `povdisplay.c`) — it can't
  tell a workbench-driven square wave from a real hall sensor.
- **Reset**: pulsing `EN` low/high is a normal hardware reset, identical to
  pressing the physical reset button.
- **LED bus**: the workbench only listens on CLK/MOSI (inputs) and receives
  the CS the DUT drives; it never drives the DUT's bus, so the DUT's real
  physical LEDs, if attached, keep working exactly as normal.
- **UART**: the DUT's UART is already a general-purpose bidirectional link
  in current firmware (`serialcomms.py`); the workbench just sits on the
  other end of it instead of another rotor/base unit.

## Firmware location and build

Workbench firmware: [`hardware/workbench/workbench_esp32s3/`](hardware/workbench/workbench_esp32s3/).

It's a plain ESP-IDF project (`idf.py` / CMake, C, no Arduino layer),
built against **the same ESP-IDF release used to build the DUT's
MicroPython firmware** — `esp-idf` `v5.5.2`, per
[`Makefile`](Makefile)'s `VOOM_MICROPYTHON_IDF_PATH`. Matching that
version matters here because the SPI slave capture in `led_capture.c`
leans on driver internals (`trans_len`, DMA-buffer requirements) that have
shifted across ESP-IDF releases.

```bash
# once, to point the environment at the same IDF tree the DUT uses:
source /path/to/esp-idf/esp-5.5.2/export.sh

cd vsdk/hardware/workbench/workbench_esp32s3
idf.py set-target esp32s3   # only needed once, regenerates sdkconfig
idf.py build
idf.py -p /dev/tty.<workbench-port> flash monitor
```

This has been built (not yet flashed to real hardware) against
`esp-idf` `v5.5.2` for `esp32s3` with no warnings in any of the
workbench's own sources. `sdkconfig` is generated from
`sdkconfig.defaults` by `idf.py set-target` and isn't checked in.

Beyond what ships with ESP-IDF (`driver`, `esp_wifi`, `esp_netif`,
`esp_event`, `nvs_flash`, `esp_timer`, `lwip`), the project pulls in one
managed component, `espressif/mdns` (declared in `main/idf_component.yml`,
pinned by `dependencies.lock`; `idf.py build` fetches it into
`managed_components/` on first build).

## Known limitations / open risks

- LED-bus capture requires the DUT to drive a chip-select (`GPIO17`); the
  original CS-less "always selected" slave did not work and was replaced (see
  [LED bus capture](#led-bus-capture-chip-select)). Verified on hardware.
- `column_offset` is assumed to be 0, so the reconstructed image may be
  rotated relative to a given DUT's own calibrated display.
- Only `frame_rgb` telemetry is reproduced; no sprite/palette telemetry
  over Wi-Fi (audio telemetry is covered separately, over serial — see
  [Pyglet emulator transport split](#pyglet-emulator-transport-split)).
- Single Wi-Fi client at a time.
- The `reset`/`rpm` control channel is plain, unauthenticated TCP on the
  local network — acceptable for a bench tool, not something to expose
  beyond the local Wi-Fi network.
- mDNS resolution needs the `zeroconf` Python package (see
  `requirements.txt`); pass an explicit IP to `emu.py` to skip it entirely.
