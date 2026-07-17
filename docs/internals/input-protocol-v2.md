# Ventilastation Base → Main Board: Input Protocol v2

## Hardware Architecture

```
PRODUCTION
──────────
  Players → joysticks/buttons
                 │ USB / GPIO
                 ▼
  Raspberry Pi 2  (the Base)
    • Runs the emulator (no display)
    • Handles player input
    • Plays audio as requested by the main board
                 │ Serial (UART)
                 ▼
  ESP32-S3 Main Board  (spinning, LED ring)


DEVELOPMENT / TESTING  (Workbench)
────────────────────────────────────
  Laptop (runs emulator)
                 │ USB serial  ← transparent byte bridge, no parsing
                 ▼
  Workbench board  (ESP32-S3, used only when main board is not spinning)
                 │ UART2
                 ▼
  ESP32-S3 Main Board

DESKTOP / WI-FI MODE
─────────────────────
  Laptop (runs emulator)
                 │ TCP port 5005  ← same byte-level protocol as serial
                 ▼
  ESP32-S3 Main Board
```

The Workbench board firmware is a transparent USB-to-UART bridge. It does
no parsing or mangling of the byte stream. The emulator (whether running on
the Base or a laptop) is always the sender of protocol frames.

The byte-level protocol described below is **identical** across all three
paths. `comms.py` (desktop/WiFi) and `serialcomms.py` (Base/Workbench)
implement the same parser.

---

## Frame Format

Two frame types, distinguished by their first byte:

### 1. Joystick frame  (`*` + 3 data bytes, 4 bytes total)

Sent at game-loop rate (≈ 30 fps). The receiver always uses the latest
frame; older frames are discarded — there is no input queue.

```
Byte 0:  0x2A  ('*')  — frame marker
Byte 1:  joy1         — [0 | C | B | A | down | up | right | left]
Byte 2:  joy2         — [0 | C | B | A | down | up | right | left]
Byte 3:  extra        — [0 | b6 | b5 | b4 | b3 | b2 | b1 | b0]
```

Bit 7 of every data byte is always 0. Data bytes can therefore never be
mistaken for frame starters.

Bit layout for joy1 / joy2 — identical to the existing Director / `config.h`
constants so no remapping is needed anywhere:

| Bit | 6 | 5 | 4 | 3    | 2  | 1     | 0    |
|-----|---|---|---|------|----|-------|------|
|     | C | B | A | down | up | right | left |

`extra` carries the fourth face button plus the Start and Back buttons that
do not fit in either joystick byte:

| Bit | Meaning |
|-----|---------|
| 0 | Joy1 Y (`BUTTON_D` compatibility mirror) |
| 1 | Joy2 Y (`BUTTON2_D` compatibility mirror) |
| 2 | Joy1 Start |
| 3 | Joy1 Back |
| 4 | Joy2 Start |
| 5 | Joy2 Back |
| 6 | Reserved (zero) |

Director mirrors extra bits 0 and 1 into the bit-7 Y aliases of `buttons`
and `buttons2`, so MicroPython games can use full Joy1 and Joy2 ABXY. Native
apps map all seven meaningful bits to `RG_KEY_*`; no shoulder or trigger
input is assigned in v2.

For native consumers, Start maps to `RG_KEY_START` and Back maps to
`RG_KEY_SELECT`; MicroPython games can read each controller's Start/Back bits
with `is_extra()` / `was_extra_pressed()`.

### Controller allocation

- With one connected gamepad: its left stick and D-pad drive Joy1; its right
  stick drives Joy2. Its face buttons, Start, and Back belong to Joy1, while
  its left shoulder, left trigger, right shoulder, and right trigger map to
  Joy2 A, B, X, and Y respectively.
- With two gamepads: controller 1's right stick is ignored. Controller 2's
  left stick and D-pad/cursor directions, face buttons, Start, and Back drive
  Joy2.
- The controller Home/Guide button is not encoded as held input. The emulator
  emits one `exit\n` command on its press edge.

### Keyboard allocation (desktop and web emulators)

The desktop and web emulators share the following keyboard layout. Keys may
be held together, just like controller controls.

| Input | Keys |
|-------|------|
| Joy1 directions | Arrow keys or W/A/S/D |
| Joy1 A / B / X / Y | Space / O / P / Y |
| Joy1 Start / Back | Page Up / Page Down |
| Joy2 directions | H / J / K / L (left / down / up / right) |
| Joy2 A / B / X / Y | Z / X / C / V |
| Joy2 Start / Back | Home / End |
| Exit | Escape |

### 2. Command frame  (ASCII alphanumeric + `\n`)

Sent only for discrete actions. First byte is ASCII alphanumeric (`a-z`,
`A-Z`, `0-9`). Terminated by `\n` (0x0A). Commands are queued and processed
one per game loop tick.

---

## Re-sync / Mid-Stream Connection

The receiver runs a three-state machine. On connect, all bytes are discarded
until the first valid frame starter arrives:

```
┌──────────────────────────────────────────────────────┐
│                      SCANNING                        │◄── connect / garbage byte
└──────────────────────────────────────────────────────┘
          │                           │
    b == '*'                    b is alphanumeric
          │                           │
          ▼                           ▼
  ┌──────────────┐           ┌──────────────────┐
  │   JOYSTICK   │           │     COMMAND      │
  │  read 3 bytes│           │ accumulate to \n │
  └──────────────┘           └──────────────────┘
          │                           │
   3 bytes read           '\n' OR buffer > 256 bytes
          │                           │
  update joy state        dispatch or discard
          │                           │
          └───────────┬───────────────┘
                      ▼
                   SCANNING
```

The 256-byte cap on command accumulation prevents a lost connection
mid-command from blocking the state machine indefinitely.

---

## RESYNC / Device Identification

Three separate devices speak this byte-level protocol to a host: the
workbench board, the Base Arduino, and the rotor board (either running
MicroPython or a native retro-go app, depending on which OTA partition is
currently active). Tooling (the emulator, `tools/find_board.py`, and
whatever Makefile targets pick a serial port) needs a reliable way to ask
"what are you?" that works regardless of what the device happens to be
doing — including if it's wedged.

RESYNC is a 9-byte marker recognized unconditionally, in any parser state:

```
\n \n 0xD2 'E' 'S' 'Y' 'N' 'C' \n
0A 0A D2  45  53  59  4E  43  0A
```

Only the leading `'R'` has its high bit set (`0x52 | 0x80 = 0xD2`); the rest
of "ESYNC" is plain ASCII. This is always safe to recognize mid-frame or
mid-command: bit 7 of every legitimate joystick data byte is always 0 (see
above), so `0xD2` can never appear in real data. The leading `\n\n` is not
load-bearing for recognition (the marker is matched as a fixed byte
sequence regardless of state) but flushes/no-ops whatever a receiver might
be accumulating in `COMMAND` state right up to the marker.

On receiving the full sequence, a device:

1. Stops whatever it is doing.
2. Resets — a real reboot where the platform has one; a full in-place
   reinitialization of its own state where it doesn't (e.g. the Base
   Arduino, which has no reset facility and nothing that can wedge given
   its simple non-blocking poll loop, so a state reinit is equivalent to a
   reboot for its purposes).
3. Prints one line as the first thing its application code does after
   that reset (unavoidably after any ROM/bootloader output on a device
   that reboots — "first" means first from the application, not literally
   the first byte on the wire):

```
VENTILASTATION <NAME> <version> <githash>\n
```

`NAME` is `WORKBENCH`, `BASE`, or `ROTOR`. The rotor reports `ROTOR`
regardless of whether MicroPython or a native retro-go app is currently
running — for port-identification purposes what matters is which board is
attached, not which application partition happens to be active. The
leading `VENTILASTATION` token is a fixed anchor a prober can check for
before parsing the rest of the line, since a port might have unrelated
hardware on it that never answers this protocol at all. `<githash>` is
`unknown` on builds that don't have one (see per-firmware notes).

This protocol is the canonical way to identify a connected device; prefer
it over ad hoc heuristics (port-name pattern matching, hardcoded device
paths, REPL interruption) wherever a caller needs to know what's on the
other end of a serial port. See `tools/find_board.py` and
`emulator/comms.py` for the two current callers.

The rotor board exposes two physically separate serial interfaces: the
dedicated base-station UART (`input_parser.py`'s usual command channel) and
the native USB-Serial-JTAG/UART0 console (the REPL wire). RESYNC is
recognized on *either* one independently (`input_parser.py` for the former,
`console_resync.py` for the latter), and the identification banner is
always printed to both regardless of which interface the marker arrived
on — so a prober connected only to the console (as `tools/find_board.py`
and the emulator normally are) still gets a reliable answer without
needing a wire into the base-station UART.

---

## Command Reference

| Command | Parameters | Notes |
|---------|------------|-------|
| `reset` | — | Reboot the main board |
| `exit` | — | Emulator Home/Guide action. Native apps restart and return through their normal launcher route; MicroPython pops the active game/UI scene and returns to its menu without rebooting. |
| `ota_start` | `<url>` | Start OTA from `http://host:port` |
| `wifi_config` | `<ssid> <password-hex>` | Write Wi-Fi credentials to NVS. Password is hex-encoded to avoid spaces and non-ASCII. |
| `povcal get` | — | Return the active versioned POV colour profile as `povcal_state <schema> <generation> <nbytes>` plus its binary payload. |
| `povcal set` | calibration setting and values | Apply one validated setting immediately, rebuild the active LED LUT, and return `povcal_state`. Supported keys: `source_eotf`, `master`, `white`, `radial_exponent`, `led_gain`, `gb_floor`, `gb_ceiling`. |
| `povcal test` | `<off\|gray\|red\|green\|blue\|white\|radial> [level]` | Enable a RAM-only on-rotor calibration pattern. `level` is `0..255`, default 255. It never changes NVS. |
| `povcal commit` / `revert` / `factory` | — | Persist the active profile, restore NVS, or restore the factory profile. Each successful command returns `povcal_state`. |
| `povperf status` | — | Report the opt-in GPU-task profiler's current scene, encoder, timing, deadline, and skipped-column counters. |
| `povperf start` / `stop` / `reset` | — | Begin a fresh timing window, stop collection, or discard the current samples. Profiling state is RAM-only. |
| `povperf mode` | `legacy\|calibrated` | Select the legacy intensity-table or calibrated color encoder for an A/B timing run, then reset the timing window. This does not alter NVS or the saved profile. |

Wire examples:

```
ota_start http://ventilastation-base.local:5653\n
wifi_config HomeNetwork 6d7950617373776f7264\n
povcal get\n
povcal set master 700\n
povcal test radial 200\n
povcal commit\n
povperf mode legacy\n
povperf start\n
povperf status\n
povperf stop\n
reset\n
exit\n
```

---

## Historical implementation outline (superseded)

The protocol implementation below records the original v2 rollout. It is not
the current button mapping: use the frame, controller allocation, and command
reference above as the source of truth.

### New file: `apps/micropython/ventilastation/input_parser.py`

Shared, side-effect-free parser. Both comms modules import it. No UART or
socket knowledge — bytes in, structured state out.

Public interface: `feed(data)` processes incoming bytes; `.joy1`, `.joy2`,
`.extra` hold the latest joystick state (updated in place on each complete
frame); `pop_command()` returns the next queued command string or `None`.

---

### Change: `apps/micropython/ventilastation/serialcomms.py`

Replace the current 14-line file. Import `InputParser` and create one instance
at module level. `_drain()` reads up to 64 bytes from UART and feeds them into
the parser. `receive()` calls `_drain()` and returns `bytes([parser.joy1])`
(always a byte, never `None`). Add `next_command()`, `next_joy2()`, and
`next_extra()` wrappers that expose the parser state.

---

### Change: `apps/micropython/ventilastation/comms.py`  (desktop / Wi-Fi)

Import `InputParser`; create one instance at module level. In `receive()`,
feed incoming TCP bytes into the parser and return `bytes([parser.joy1])`.
Add `next_command()`, `next_joy2()`, and `next_extra()` matching the
`serialcomms.py` interface.

Remove the `_ctrl_sock` (port 5006) listener, its poller registration, and
`_pending_commands`. Commands now arrive in-band on the existing port 5005
connection. No other board-side files reference port 5006 after this change.

---

### Change: `apps/micropython/ventilastation/director.py`

Add joy2 and extra button constants alongside the existing joy1/BUTTON_*
constants. `BUTTON_D` stays at `0x80` but is now sourced from `extra` bit 0
rather than from the wire directly.

Add `buttons2`, `last_buttons2`, `extra_buttons`, `last_extra_buttons` fields
to `__init__`.

In `step_once()`: after reading joy1 via `receive()`, call `next_joy2()` and
`next_extra()` if the comms module supports them, then mirror `extra & 0x01`
into bit 7 of `self.buttons` so `BUTTON_D` continues to work for all existing
games.

Add `is_pressed2()`, `was_pressed2()`, `was_released2()`, and `is_extra()`
methods for games that want to use joy2 or extra buttons. All existing
`is_pressed()` / `was_pressed()` calls on joy1 and BUTTON_D are unchanged.

---

### Change: `emulator/comms.py`  (laptop / Base emulator side)

Add `send_joystick(joy1, joy2=0, extra=0)` that sends a 4-byte joystick
frame (`*` + three masked bytes). Replace existing single-byte button sends
with calls to this function.

Add `send_command(cmd)` that sends a text command frame in-band over the
existing port 5005 connection.

Replace `trigger_ota()` with an in-band version using `send_command()`
instead of the old dedicated port 5006 socket.

---

## Native Apps: prboom-go, retro-core, genesis

The C input path in native apps is:

1. `vs_host_bridge_recv_input()` — reads raw bytes from TCP or UART
2. `rg_input.c` — loops until -1, keeps the last byte as `host_buttons` (`uint8_t`)
3. `RG_GAMEPAD_HOST_MAP` in `config.h` — maps bit masks to `RG_KEY_*` values

All three files need updating to speak v2.

### Change: `apps/retro-go/components/retro-go/vs_host_bridge.c`

Add `#include <esp_system.h>` and `#include <stdio.h>` to the top include
block.

Add a shared byte-stream parser above the TCP / UART `#if` split, inside the
existing `#if defined(ESP_PLATFORM) && defined(RG_VS_ENABLE_HOST_BRIDGE)` guard.
The parser is a C mirror of `InputParser`: a three-state struct
(`VS_SCAN` / `VS_JOY` / `VS_CMD`) with a `vs_feed_bytes(data, n)` function
and a command handler `vs_handle_command(cmd)`.

`vs_handle_command` handles `reset` (calls `esp_restart()`) and `ota_start
<url>` (writes `RG_STORAGE_ROOT "/ota_request"` then calls `esp_restart()`).
All other commands are silently ignored; native apps need no per-command
awareness.

Add `vs_host_bridge_get_joy2()` and `vs_host_bridge_get_extra()` functions
that return the cached joy2 / extra bytes from the shared parser state.

Change `vs_host_bridge_recv_input()` in both TCP and UART branches to drain
all available bytes through `vs_feed_bytes()` in a loop rather than reading
one byte at a time, then return the current cached `joy1` value (or -1 if the
TCP client is disconnected). The UART branch always returns the cached value
(UART is always "connected").

Add stub versions of `vs_host_bridge_get_joy2()` and
`vs_host_bridge_get_extra()` in the non-ESP stub block at the bottom.

---

### Change: `apps/retro-go/components/retro-go/vs_host_bridge.h`

Declare `vs_host_bridge_get_joy2()` and `vs_host_bridge_get_extra()`.

---

### Change: `apps/retro-go/components/retro-go/rg_input.h`

Widen `rg_keymap_host_t.mask` from `uint8_t` to `uint32_t`. This allows
future config entries to target joy2 (bits 8–15) or extra (bits 16–22)
without further struct changes. All existing entries in `config.h` use bits
0–7 and compile unchanged.

---

### Change: `apps/retro-go/components/retro-go/rg_input.c`

Replace the HOST_MAP while-loop with a single call to
`vs_host_bridge_recv_input()` (which now drains all buffered bytes
internally). After the call, mirror `vs_host_bridge_get_extra() & 0x01` into
bit 7 of `host_buttons` so `RG_KEY_START` (the BUTTON_D / START mapping)
keeps working. Clear `host_buttons` to 0 when the bridge is disconnected.
The `for` loop over `keymap_host` is unchanged.

`host_buttons` stays `uint8_t` — the current config only maps joy1 bits. Add
a `uint32_t host_state` variable if and when a config needs joy2/extra
entries.

---

### Minimal change: `apps/retro-go/components/retro-go/targets/ventilastation/config.h`

The joy1 byte layout in the v2 protocol exactly matches the existing Director
constants (`left=bit0, right=bit1, up=bit2, down=bit3, A=bit4, B=bit5,
C=bit6`), so **all existing `RG_GAMEPAD_HOST_MAP` mask values remain correct**.
`RG_KEY_START` at `(1 << 7)` continues to fire correctly because `rg_input.c`
mirrors `extra & 0x01` into bit 7 before the map lookup.

Update the comment to note that bit 7 is now mirrored from `extra` bit 0
rather than being a live BUTTON_D wire bit.

---

## Files Changed

| File | Change |
|------|--------|
| `apps/micropython/ventilastation/input_parser.py` | **New** — shared MicroPython parser |
| `apps/micropython/ventilastation/serialcomms.py` | Use parser; add `next_command()`, `next_joy2()`, `next_extra()` |
| `apps/micropython/ventilastation/comms.py` | Use parser; remove port 5006 listener |
| `apps/micropython/ventilastation/director.py` | Add joy2/extra state and constants; mirror EXTRA_BTN_0→BUTTON_D; new `is_pressed2()` / `is_extra()` |
| `emulator/comms.py` | `send_joystick()` replaces raw byte send; `trigger_ota()` goes in-band |
| `apps/retro-go/components/retro-go/vs_host_bridge.c` | Add shared C parser; `recv_input()` drains all bytes; add `get_joy2()` / `get_extra()`; handle `reset` and `ota_start` commands |
| `apps/retro-go/components/retro-go/vs_host_bridge.h` | Declare `get_joy2()` / `get_extra()` |
| `apps/retro-go/components/retro-go/rg_input.h` | `rg_keymap_host_t.mask` → `uint32_t` |
| `apps/retro-go/components/retro-go/rg_input.c` | Single-call pattern; mirror `extra & 0x01` → bit 7 |
| `apps/retro-go/components/retro-go/targets/ventilastation/config.h` | Comment update only |

## Files Not Changed

Workbench firmware, all games, system launcher, OTA updater, display pipeline,
`apps/micropython/ventilastation/platforms/`.
