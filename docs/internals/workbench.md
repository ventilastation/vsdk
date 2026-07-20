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
   over Wi-Fi to a desktop `vsdk/emulator` (pyglet) instance using its own
   UDP telemetry protocol (see [Why UDP](#why-udp-not-tcp)) — deliberately
   not the wire protocol the DUT itself would use if it opened a display
   link directly, since a live LED preview tolerates loss far better than
   it tolerates the stalls TCP's guarantees would otherwise impose.
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
drives a chip-select (`GPIO14` in the default configuration) so the workbench's SPI slave can frame each
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
                    |  display_conn (Wi-Fi, UDP :5005):            |
                    |    <- chunked frame_apa102 datagrams          |
                    |    -> "reset\n" / "rpm <n>\n" / "hello\n"       |
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
                    |  - Wi-Fi STA + mDNS + UDP telemetry (display/control) |
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

| Signal              | Workbench pin (suggested) | DUT pin (from `vs_board` NVS)          | Direction         | Notes |
|---------------------|---------------------------|-----------------------------------------|-------------------|-------|
| Hall sensor          | `GPIO7`  (`WB_HALL_PIN`)  | `hall_gpio`                              | workbench → DUT   | Idles HIGH, pulses LOW once per simulated revolution, matching a real hall sensor with pull-up. |
| Reset / EN           | `GPIO4`  (`WB_RESET_PIN`) | DUT `EN` / reset pin                     | workbench → DUT   | Open-drain style: workbench drives LOW to assert, then releases to `INPUT` (Hi-Z) so the DUT's own pull-up brings it back HIGH. Never drive HIGH directly. |
| LED bus clock        | `GPIO12` (`WB_SPI_SCLK_PIN`) | `led_clk`                             | DUT → workbench   | Input only. 20 MHz APA102-style clock. |
| LED bus data         | `GPIO13` (`WB_SPI_MOSI_PIN`) | `led_mosi`                            | DUT → workbench   | Input only. |
| LED bus CS           | `GPIO14` (`WB_SPI_CS_PIN`)   | `led_cs`                              | DUT → workbench   | Real chip-select the DUT's LED SPI master now drives. Asserted low per 444-byte burst; frames the slave transactions — see [LED bus capture](#led-bus-capture-chip-select). |
| UART TX              | `GPIO6` (`WB_UART_TX_PIN`)  | `serial_rx`                           | workbench → DUT   | Workbench transmits into the DUT's UART RX. |
| UART RX              | `GPIO5` (`WB_UART_RX_PIN`)  | `serial_tx`                           | DUT → workbench   | Workbench receives from the DUT's UART TX. |
| Ground               | GND                        | GND                                     | —                 | Common reference, required. |

DUT pin numbers above are the Ventilastation III defaults written by
`make configure-board` (`hall_gpio=7`, `led_clk=12`, `led_mosi=13`,
`led_cs=14`, `serial_tx=5`, `serial_rx=6`). The board's NVS `vs_board`
namespace is the source of truth for both MicroPython and the native apps.
For an original Ventilastation 2 or European Edition DUT, configure it with
`make configure-board-v2` or `make configure-board-eu` and rewire to match its
actual GPIOs; the workbench-side pins in
`hardware/workbench/workbench_esp32s3/config.h` do not need to change.

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
   `ventilastation-workbench.local` over mDNS and starts sending it UDP
   datagrams on port 5005 -- there's no connection to open (see
   [Why UDP](#why-udp-not-tcp)). The workbench starts streaming chunked
   `frame_apa102` telemetry it has reconstructed from the spied LED bus to
   whichever address most recently sent it a datagram, and accepts
   `reset`/`rpm <n>` commands from the emulator's RPM slider and reset button
   (see [RPM and reset control](#rpm-and-reset-control)).
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
drives the configured `led_cs` pin (the default is `GPIO14`), which the ESP32
hardware asserts low around each `spi_device` transaction and releases
between them. The LED strips ignore it (they aren't wired to CS); the
workbench is. The default Ventilastation III wiring uses `GPIO14` for `led_cs`.

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

each LED frame being `[brightness, B, G, R]`. The workbench retains all four
bytes verbatim after the required arm/column reassembly; it never drops the
global-brightness byte or reorders colour components.
`gpu_step()` sends one such burst at 20 MHz per column change (up to 256 per
revolution), so CS pulses low once per column.

The workbench runs the ESP-IDF `spi_slave` driver on `SPI2_HOST` with
`spics_io_num = WB_SPI_CS_PIN` (`GPIO14`, wired to the DUT's configured `led_cs`) and
keeps several 444-byte DMA receive buffers queued
(`hardware/workbench/workbench_esp32s3/main/led_capture.c`). Each CS
deassertion completes a transaction with `trans_len == 444` bytes, which is
decoded into the frame buffer. Verified end-to-end on hardware at 600 RPM:
2560 clean 444-byte bursts/second (256 columns × 10 rev/s), zero malformed.
`led_capture` logs a `bursts/s: good=… other=…` health line once a second.

## Column tracking and frame reassembly

The reconstructed telemetry is conceptually a `256 * 54 * 4 = 55296`-byte
buffer: 256 angular columns, 54 LEDs each, with each four-byte cell copied
from the LED bus as `[0xe0 | GB, B, G, R]`. On the wire it's never sent as
one contiguous message (see [Why UDP](#why-udp-not-tcp)) -- the emulator's
`WorkbenchTelemetryConn` (`vsdk/emulator/comms.py`) reassembles it from
small per-chunk datagrams instead. `frame_rgb` remains a separate
three-byte-per-LED format for software full-frame renderers over the
regular TCP-framed protocol; it is not used for workbench capture.

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
- arm 1's 54 LEDs (direct order) into the current column.

Each destination retains its complete `[GB, B, G, R]` datum; the desktop
emulator converts it to a preview colour. There is a roughly one-burst
pipeline delay versus the DUT's true state (the real firmware sends the
*previous* column's buffer while it computes the next one) — negligible for a
visualization tool.

The assembled 256×54×4 buffer is snapshotted from the capture double buffer
roughly every 33 ms (`WB_TELEMETRY_FRAME_INTERVAL_MS`) and sent as
`WB_NUM_CHUNKS` (64) UDP datagrams to whichever client has most recently sent
the workbench a datagram (see [Why UDP](#why-udp-not-tcp) for the wire
format). The workbench doesn't emit `sprites`/`palette`/`sound`/etc.
telemetry, since none of that is observable from the LED bus alone.

## Why UDP, not TCP

`frame_apa102` telemetry used to be a single TCP-framed message (a
`"frame_apa102\n"` line plus the raw 55296-byte payload), matching the
shared wire protocol every other transport in this codebase speaks
([host-protocol.md](host-protocol.md)). That was a poor fit for what this
link actually is: a live "whatever's most current wins" preview, not
data that needs to arrive complete or in order. TCP's guarantees actively
worked against it -- a single lost segment head-of-line-blocks everything
queued behind it until retransmitted, which on a lossy Wi-Fi link turned
one dropped packet into a multi-second visible stall or, if a send timeout
was added to bound that stall, complicated failure modes around partial
sends (see the git history of `telemetry.c`'s TCP-era `send_all()` for what
that cost to get right). None of that is worth paying for a stream where a
client that missed a frame should just wait for the next one.

The workbench now speaks a small custom UDP protocol instead. Wire format,
workbench → client, one datagram per column-chunk
(`hardware/workbench/workbench_esp32s3/main/telemetry.c`):

| Bytes | Field | Notes |
|---:|---|---|
| 0 | magic | `WB_CHUNK_MAGIC` (`0xA1`) |
| 1-4 | `frame_seq` | `uint32`, little-endian. Increments once per `led_capture_snapshot()` call, not once per revolution -- decoupled from `led_capture.c`'s own half-turn buffer flips. |
| 5 | `chunk_index` | `0..WB_NUM_CHUNKS-1` (`0..63`) |
| 6.. | payload | `WB_CHUNK_PAYLOAD_BYTES` (864) raw APA102 bytes for columns `[chunk_index*WB_COLUMNS_PER_CHUNK, +WB_COLUMNS_PER_CHUNK)` (`WB_COLUMNS_PER_CHUNK` = 4) |

No `chunk_count` field -- both ends know `WB_NUM_CHUNKS` at compile time.
Each datagram is 870 bytes total, deliberately small enough that IP never
has to fragment it (a lost IP fragment would take the whole datagram with
it, defeating the point). A lost datagram just leaves those four columns
showing whatever they last successfully received; `WorkbenchTelemetryConn`
tracks a per-chunk `frame_seq` so a stale, reordered datagram can't stomp
fresher data that already arrived for the same columns.

Client → workbench control is still plain text lines, matching the
pre-UDP protocol, plus one addition:

- `"reset\n"` -- pulse the DUT's reset line
- `"rpm <n>\n"` -- set the simulated hall RPM
- `"hello\n"` -- no-op, sent by the client once a second purely to keep its
  subscription alive

UDP has no `accept()`, so "the current client" is simply whoever's datagram
arrived most recently -- any of the three lines above count, which is why
the client sends `hello` even when the user isn't touching the RPM slider
or reset button. The workbench stops streaming to a client after
`WB_TELEMETRY_CLIENT_TIMEOUT_MS` (5000 ms) of silence from it.

## Wi-Fi provisioning and mDNS discovery

The workbench joins an existing Wi-Fi network in station mode (`telemetry.c`)
rather than running its own access point, so the PC running the pyglet
emulator keeps normal internet access on the same network. Credentials are
read from NVS namespace `devel_wifi`, keys `ssid`/`password` — **the same
namespace and keys** `apps/micropython/ventilastation/updater.py` reads on
the DUT itself, so the mechanism (if not the physical NVS, which is
per-chip) is deliberately identical on both boards. (Workbenches provisioned
before the rename from `voom_wifi` still work: the firmware falls back to
the old namespace and logs a migration hint.)

Since the workbench is a compiled ESP-IDF app, not MicroPython, its
`tools/provision_wifi.py` builds a small NVS partition image with
`nvs_partition_gen.py` and flashes it straight to the `nvs` partition's
offset (`0x9000`, pinned by `partitions.csv`) — no rebuild or full reflash
needed to change networks. The DUT's `make wifi-provision` now works the
same way at the esptool level (see `vsdk/tools/nvs_partition.py`), except it
dumps the partition first and merges in just the changed keys, since the
DUT's `nvs` partition also holds `vs_board` wiring and `vsdk_ota` state that
must survive; the workbench's `nvs` partition holds only `devel_wifi`, so it
can overwrite the whole partition directly:

```bash
source /path/to/esp-idf/esp-5.5.2/export.sh   # once per session
make workbench-wifi-provision PORT=/dev/cu.usbmodemXXXX \
    WIFI_SSID=mywifi WIFI_PASS=mypassword
```

Other workbench make targets (see the top-level `Makefile`, next to the
DUT's `wifi-provision`):

```bash
make workbench-build                       # idf.py build
make workbench-flash PORT=/dev/cu.usbmodemXXXX
make workbench-monitor PORT=/dev/cu.usbmodemXXXX
```

After provisioning and a reset, the workbench connects, then advertises
itself over mDNS (`espressif/mdns` managed component) as
`ventilastation-workbench.local`, so the emulator doesn't need to know its
DHCP-assigned IP. `.local` resolution is handled by the OS resolver
(`socket.getaddrinfo()` in `comms.py`'s `ConnIP.setup()`) — built into
macOS (Bonjour); Linux needs `avahi`/`nss-mdns` installed, Windows needs
Bonjour (e.g. via iTunes) installed. If mDNS isn't available on a given
machine, pass the workbench's IP explicitly instead (see below).

**macOS gotcha:** if `.local` resolution hangs/fails for the emulator
specifically even though `ping ventilastation-workbench.local` and
`dns-sd -B _ventilastation-wb._udp` both work fine, check
System Settings → Privacy & Security → Local Network, and make sure the
Python interpreter running the emulator (Terminal, or the specific
python3/venv binary) is allowed there. Without it, macOS silently drops
the mDNS traffic for that process — no error, it just never resolves.

## RPM and reset control

Any datagram from the client to the workbench's UDP telemetry port also
accepts simple line commands (`telemetry.c`'s `handle_client_line()`):

- `reset\n` — pulses the DUT's reset line (`reset_ctl_pulse()`), exactly
  like the boot-time reset.
- `rpm <n>\n` — sets the simulated hall RPM at runtime
  (`hall_sim_set_rpm()`), clamped to `[0, 700]`.
- `hello\n` — no-op keepalive (see [Why UDP](#why-udp-not-tcp)).

The pyglet emulator's window (`emulator/pyglet2x/pygletdraw.py`) draws an
RPM slider (0-700, default 600) and a RESET button in the bottom-left
corner when running against real hardware; dragging the slider sends
`rpm <n>` (only when the rounded value changes), and clicking RESET sends
`reset`. Both go out via `comms.send_workbench()`, which writes directly to
the Wi-Fi connection — harmless no-ops if the workbench isn't reachable.

## Pyglet emulator transport split

`vsdk/emulator/comms.py` normally talks to a single link for everything
(the local desktop MicroPython subprocess, over a loopback TCP socket).
Against a real workbench (`python emu.py --remote` or `--no-display`) it
instead opens two:

- `display_conn` (Wi-Fi, UDP `:5005`) — a `WorkbenchTelemetryConn`
  instance: `frame_apa102` chunks in, `reset`/`rpm`/`hello` out. Everything
  covered above and in [Why UDP](#why-udp-not-tcp). Unlike every other
  transport in this codebase, this one does *not* run through the shared
  `comms.dispatch_command()` line dispatcher -- it's message-oriented UDP
  carrying exactly one payload type, so `WorkbenchTelemetryConn` gets its
  own minimal receive loop instead (see `comms.py`).
- `workbench_conn` (USB serial, via the workbench's UART bridge) — button
  state out, sound/music/notes/etc. requests in. This is exactly the
  traffic that would normally cross the DUT<->base UART link (see
  `hardware/base/README.md`: "the code running on the base gathers
  joystick movement and button presses... the cpu sends back requests for
  music and sounds"); the emulator, connected through the workbench's
  serial passthrough, is simply standing in for the base. This link *does*
  still use the shared `comms.dispatch_command()`.

In local-simulation mode (no workbench involved), `display_conn` is a
regular TCP loopback connection and everything, including audio, still
arrives on it through `comms.dispatch_command()` exactly as before UDP
telemetry existed -- the split above only applies in hardware mode.

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

## Device identification (RESYNC)

`handle_host_bytes()` in `serial_bridge.c` also watches the host→DUT byte
stream for the RESYNC marker (see
[input-protocol-v2.md](input-protocol-v2.md#resync--device-identification)),
intercepting it rather than forwarding it to the DUT. On match, the
workbench itself resets (`esp_restart()`) and prints
`VENTILASTATION WORKBENCH <version> <githash>` as the first thing
`app_main()` does — this is what `tools/find_board.py` and the emulator now
use to pick the workbench's port reliably, replacing the older
`VSDK_BOARD_PROBE` literal-match probe.

## DUT firmware: one small change

Everything the workbench does is transparent to the DUT except one addition:
the LED SPI master now drives its configured chip-select (default `GPIO14`) so the workbench slave
can frame bursts (see [LED bus capture](#led-bus-capture-chip-select)). That
is the *only* DUT firmware change — a one-line `spics_io_num` in
[`minispi.c`](hardware/rotor/modules/povdisplay/minispi.c); it's inert on the
real rotor since nothing else uses the configured chip-select. Nothing under
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
built against the same ESP-IDF release as everything else in this repo —
`esp-idf` `v5.5.2` (see [building.md](building.md)). Matching that version
matters here because the SPI slave capture in `led_capture.c` leans on
driver internals (`trans_len`, DMA-buffer requirements) that have shifted
across ESP-IDF releases.

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

- LED-bus capture requires the DUT to drive its configured chip-select (default
  `GPIO14`); the
  original CS-less "always selected" slave did not work and was replaced (see
  [LED bus capture](#led-bus-capture-chip-select)). Verified on hardware.
- `column_offset` is assumed to be 0, so the reconstructed image may be
  rotated relative to a given DUT's own calibrated display.
- Only `frame_apa102` telemetry is reproduced; no sprite/palette telemetry
  over Wi-Fi (audio telemetry is covered separately, over serial — see
  [Pyglet emulator transport split](#pyglet-emulator-transport-split)).
- Single Wi-Fi client at a time -- "the current client" is whoever's
  datagram the workbench saw most recently (see [Why UDP](#why-udp-not-tcp)).
- The telemetry/control channel is plain, unauthenticated UDP on the local
  network — acceptable for a bench tool, not something to expose beyond
  the local Wi-Fi network. UDP also means there's no built-in delivery
  guarantee at all (by design -- see [Why UDP](#why-udp-not-tcp)), so a bad
  enough link can still mean a visibly stale/choppy preview; it just can't
  desync or stall the whole stream the way the earlier TCP transport could.
- `.local` mDNS resolution depends on OS support (built into macOS; needs
  `avahi`/`nss-mdns` on Linux, Bonjour on Windows) and, on macOS, the
  Local Network permission for whichever process is running the emulator
  (see the gotcha above) — pass an explicit IP to `emu.py` if it's
  unavailable.
