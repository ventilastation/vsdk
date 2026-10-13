# Serial link stress test

Measures the serial link between the base (Raspberry Pi) and the rotor
(ESP32-S3), and tells the wire's errors apart from the software's. Both ends
exchange test traffic at controlled rates; every frame's content is a pure
function of its phase and sequence number, so the receiver knows exactly
what should have arrived and can say *how* a bad frame differs:

- **bytes changed in place** (same length, a few flipped bits): only the
  wire does that. No buffer in either software stack rewrites bytes; they
  can only lose them.
- **runs of missing bytes**: a buffer that overflowed -- or the wire. The
  rest of the evidence (buffer high-water marks, adapter counters, load)
  decides which.

## The pieces

| Piece | Path | Role |
|---|---|---|
| Serial Stress app | `games/demos/serialstress/` (Tech Demos menu, slug `demos.serialstress`) | The rotor's end. Drives the run phase by phase, sends uplink frames, checks downlink lines, reports its own counters, shows totals and the verdict. |
| Protocol and test data | `apps/micropython/ventilastation/serial_stress.py` | Shared by both ends (MicroPython and CPython): commands, the plan, test patterns, per-phase accounting, error diagnosis. |
| Base-side checker | `emulator/serial_stress_host.py` | Checks the uplink, paces the downlink, reads the adapter's error counters, prints the report and the verdict. |
| Emulator hook | `emulator/comms.py` (`serialtest_*` lines) | Runs the checker inside the production base software. |
| Standalone tool | `tools/serial_stress.py` | The same checker behind a lean reader (`rotor` mode), and a loopback mode with no rotor software at all. |

## Running it

Each step takes one more thing out of the picture. Start at the top.

### 0. Desktop emulator (optional sanity check)

```sh
./vs-emu.sh --game demos.serialstress     # then press A (Space)
```

TCP never loses data, so anything but `CLEAN` here is a software bug in the
test or the runtime, not the cable.

### 1. On the console, through the emulator

This measures the link exactly as games use it: the base's own software on
one end, the rotor's on the other. The base runs `emu.py SERIAL
--no-display` (started by `hardware/base/base-remote.sh`), which prints to
`/tmp/remote-out.log` on the Pi:

```sh
tail -f /tmp/remote-out.log | grep serialtest
```

On the console open **Tech Demos → Serial Stress**. It shows `NO BASE ANSWER
YET` until the base answers; a base running older software never will.

- **A** runs the plan (about 90 seconds).
- **LEFT/RIGHT** pick a phase, **B** repeats it until stopped: a soak test,
  e.g. once with the rotor still and once spinning.
- While running, **hold A or B for a second** to stop after the current
  phase. Single presses are ignored mid-run, and so are Y/BACK: a lossy
  link can fake a press.
- **Y/BACK** leaves when idle.

### 2. Same link, the tool as the base

Rules the emulator's reader in or out. Stop the base software first (only
one program can own the port), then:

```sh
pkill -f base-remote.sh; pkill -f "emu.py SERIAL"
python3 tools/serial_stress.py rotor --port /dev/ttyUSB0
python3 tools/serial_stress.py rotor --port /dev/ttyUSB0 --phase up90 --loop   # Ctrl-C stops
```

The tool sends `exit` and `launch demos.serialstress`, waits for the app,
starts the run, prints the same report and exits 0 only on `CLEAN`. Use
`--no-launch` if the app is already open. Restart the base afterwards with
`hardware/base/base-remote.sh &` (or reboot the Pi).

### 3. Loopback: no rotor software at all

Bridge TX to RX and the tool checks its own traffic:

```sh
python3 tools/serial_stress.py loopback --port /dev/ttyUSB0 --rate 90 --seconds 30
python3 tools/serial_stress.py loopback --port /dev/ttyUSB0 --loop             # soak
```

1. **At the base's USB-serial adapter** (jumper TX to RX, cable
   unplugged): checks the adapter and the Pi.
2. **At the far end of the cable**: disconnect the rotor board's UART and
   bridge the two signal wires on the rotor side of the cable and slip
   ring. Now the bytes cross the suspect wiring twice, with no rotor
   software involved. If the mechanics allow it, run it still and spinning.

`--baud` tries other speeds (loopback only: the rotor's speed is
`serial_baud` in its NVS board configuration). Errors that grow with the
baud rate are signal-integrity trouble.

## Reading the results

### Where the fault is

| Loopback at the adapter | Loopback at the far end | Tool + rotor (2) | Emulator + rotor (1) | Points at |
|---|---|---|---|---|
| errors | | | | the base's adapter or the Pi |
| clean | errors | | | the cable / slip ring / connectors |
| clean | clean | errors | errors | the rotor's end: its UART wiring, or its software (read the per-phase evidence) |
| clean | clean | clean | errors | the emulator's reader on the base |
| clean | clean | clean | clean | the link is fine; look elsewhere |

### The report

The base prints one block per phase, then a summary:

```
serialtest: #4 up90   UP    90% x512    163 ok   0 bad   0 lost   10400 B/s
                      rotor: rx buffer peak 31/256, 0 bit-7 / 0 overlong lines dropped, 0 junk,
                             0 joystick changes, loop max gap 47 ms, tx blocked 674 ms
                      base adapter: 0 framing, 0 parity, 0 breaks, 0 overruns, 0 tty overruns; 0 junk lines
serialtest: #7 down20 DOWN  20% x100    175 ok   1 bad   0 lost  sent 176 (1 bitflip)
...
serialtest:   [hardware] down20: 1 downlink lines arrived with bits changed in place
serialtest: VERDICT HARDWARE -- errors the wire caused: look at the cables/slip ring/connectors
```

| Signal | Meaning |
|---|---|
| bad frames of kind `bitflip` / `zeroed` | Bytes changed in place: the wire. `zeroed` (every bad byte arrived as 0x00) is the line held low, e.g. an intermittent contact. |
| `dropped` / `short` / `inserted` / `garbled` | Bytes lost or extra; the cause comes from the rest of the evidence. The first few are printed with their offset. |
| `bit-7 lines dropped` (rotor) | Command lines with a byte above 0x7F. The base never sends one: the wire flipped bit 7. |
| `overlong lines dropped` (rotor) | Lines past the 256-byte cap: a newline went missing (wire or overflow). |
| `rx buffer peak` *n*/256 (rotor) | Fullest the rotor's UART receive buffer was when the main loop came to drain it. At the size, the rotor dropped input itself: rotor software. Never near it, yet lines lost: the wire. |
| base adapter `framing` / `parity` / `breaks` | Counted by the USB-serial driver on bytes from the rotor (Linux `TIOCGICOUNT`): electrical trouble. FTDI, PL2303 and the Pi's own UARTs count them; other drivers may report zeros, or nothing (the line is then omitted). |
| base adapter `overruns` / `tty overruns` | The adapter or the tty buffer filled: the base read too slowly. |
| `junk` lines | Lines neither end could parse: corrupted headers, or the debris of lost bytes. Any during `idle` is noise on a quiet line. |
| `joystick changes` (rotor) | Changes in the controllers' state. The tool repeats an idle joystick frame 30 times a second, so in step 2 with nobody touching the controls each change is a corrupted frame -- a phantom press. The emulator sends a frame only when the controls change, so in step 1 this mostly counts real presses. |
| `loop max gap` / `tx blocked` (rotor) | Main-loop stalls, and time spent blocked writing (expected in `up90`/`upmax`: the wire is full). |

Verdicts: `CLEAN`; `HARDWARE` (evidence only the wire produces);
`ROTOR_SOFTWARE` / `BASE_SOFTWARE` (an overrun on that side explains the
losses); `MIXED`; `INCONCLUSIVE` (errors without evidence to place them --
typically uplink losses at high load on an adapter that reports no
counters: compare steps 1 and 2).

### The plan

| Phase | Uplink | Downlink | Purpose |
|---|---|---|---|
| `idle` | -- | joystick frames only (the tool's; none from the emulator unless the controls move) | baseline: anything here is noise |
| `up10`, `up50`, `up90` | 10/50/90% of the line, 128-512-byte frames | -- | BER and the base's reading capacity |
| `upmax` | offered at 150% | -- | the real ceiling; rotor writes block |
| `down10`, `down20` | -- | 100-char lines | BER rotor-bound |
| `both` | 40% | 15% | full duplex |
| `down60` (not in the plan) | -- | 200-char lines at 60% | positive control: overruns the rotor on purpose |

Phases last 8 seconds; select one and press B (or `--phase NAME --loop`)
to soak it.

## Software limits found along the way

- **Rotor input capacity.** The main loop drains 3 x 64 bytes and hands one
  command line to the director per ~30 ms tick, out of a 256-byte UART
  receive buffer (MicroPython's default `rxbuf`). That is ~6 KB/s of raw
  input, and line traffic is limited further: a 225-byte line nearly fills
  the buffer alone, two back to back overflow it. The plan stays well
  inside; production traffic (4-byte joystick frames, ~120 B/s) is nowhere
  near. `down60` shows what an overrun looks like.
- **Rotor output** never drops: `uart.write()` blocks once the 256-byte TX
  buffer and the 128-byte FIFO are full.
- **UART interrupt starvation.** The receive-buffer peak rules out the main
  loop, not the interrupt: flash writes (NVS, filesystem) can hold off the
  UART interrupt longer than the 128-byte FIFO lasts at 115200 (~11 ms).
  The app writes nothing to flash during a run.
- **The emulator's reader** reads lines byte by byte and trusts declared
  payload lengths. After a byte is lost inside a binary payload it reads
  the next frames out of step and realigns only by chance, when some
  payload happens to end in a newline. The test resynchronises on its own
  headers; real binary traffic (`aframe`/`amap` from native apps) does not.
- **Joystick frames are sent only on change** (`consoleengine.py`,
  `pygletengine.py`). A corrupted one leaves a phantom state -- a button
  held, a direction pushed -- until the player next touches the controls.
  Repeating the state periodically, as the tool does, would bound that to
  one frame (~33 ms).
- **A malformed known command** (e.g. `info 1x`) raises inside
  `dispatch_command`; `_receive_loop` then closes and reopens the port, and
  pyserial's open flushes the input buffer: one corrupted byte can cost
  everything buffered.
- **Fixed:** a byte with bit 7 set inside a command line made MicroPython's
  `InputParser` raise `UnicodeError` out of the main loop, and `main.py`
  rebooted the rotor. Such lines are now dropped and counted.

## Protocol

Rotor to base, host-protocol lines ([host-protocol.md](host-protocol.md)):

| Command | Payload | Meaning |
|---|---|---|
| `serialtest_hello <version>` | -- | the app is up (every 2 s until answered) |
| `serialtest_phase <phase> k=v...` | -- | a phase starts: `name`, `up_bps`, `up_frame`, `down_bps`, `down_chars`, `ms`, `baud` |
| `serialtest_up <nbytes> <phase> <seq>` | `<nbytes>` | uplink test frame |
| `serialtest_end <phase> k=v...` | -- | the rotor's counters: `frames`, `bytes`, `dn_*`, `rx_hwm`, `rx_buf`, `nonascii`, `overlong`, `joy`, `ticks`, `tick_max`, `tx_ms` |
| `serialtest_done [aborted=1]` | -- | the run is over (or the app was left mid-run) |

Base to rotor, input-protocol command lines
([input-protocol-v2.md](input-protocol-v2.md)):

| Command | Meaning |
|---|---|
| `serialtest_ready <version>` | answer to hello |
| `serialtest_run plan\|<phase> [loop]` / `serialtest_run stop` | remote start / stop after the current phase (the tool) |
| `serialtest_down <phase> <seq> <payload>` | downlink test line; payload inline, printable ASCII without space or `*` |
| `serialtest_sent <phase> frames=<n>` | the phase's downlink is over; queued behind every line in flight |
| `serialtest_result <phase> k=v...` | the base's counters: `ok`, `bad`, `lost`, `junk`, `wire`, `dn_lost` |
| `serialtest_verdict <code>` | `clean`, `hardware`, `rotor_software`, `base_software`, `mixed`, `inconclusive` |

The director hands `serialtest_*` lines to the app through the scene hook
`on_command(cmd_line)`: the top scene sees any command the director doesn't
recognise and returns True to claim it.

Test data: uplink frames are slices of a 1024-byte shuffle of every byte
value (led by 0x55, 0x00 and 0xFF runs), downlink lines slices of 1024
printable characters, both at offset `(seq * 389 + phase * 101) % 1024`.
`tests/test_serial_stress_protocol.py` pins their checksums and runs on both
interpreters: change the data and both ends must be updated together.
