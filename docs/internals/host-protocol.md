# Host command protocol

The MicroPython runtime (or a native app) talks to a **host** — the desktop
pyglet emulator, the web worker, or the hardware base — over a byte stream.
This document specifies the runtime→host direction: line-based commands,
optionally followed by a binary payload. The host→runtime direction
(joystick frames and control commands) is specified in
[input-protocol-v2.md](input-protocol-v2.md).

Reference implementations: sender in `ventilastation/director.py` and the
platform comms modules; receiver in `emulator/comms.py`
(`dispatch_command`) and `web/wasm-worker.js`.

## Framing

Each message is one ASCII line, terminated by `\n`:

```
<command> [arg1 [arg2 ...]]\n[payload bytes]
```

Arguments are space-separated. When a command carries a payload, its length
is derivable from the arguments (or is fixed); the payload follows the
newline immediately and is read to exactly that length. Unknown commands
are logged and ignored — hosts must tolerate commands they don't handle.

## Display (emulation hosts only; hardware drives LEDs directly)

| Command | Payload | Meaning |
|---|---|---|
| `sprites` | 500 bytes | full sprite table: 100 sprites × 5 bytes (x, y, strip, frame, perspective; frame 255 = hidden) |
| `vs2_scene <nbytes>` | `<nbytes>` | v2 scene/layer payload; currently decoded by the desktop and web emulators into the sprite renderer shape |
| `imagestrip <slot> <nbytes>` | `<nbytes>` | one image strip: 4-byte header (w, h, frames, palette) + pixels, same encoding as a ROM strip entry |
| `palette <n> <version>` | `n × 1024` bytes | palette block, `n` palettes of 256 × 4-byte entries ([rom-format.md](rom-format.md)) |
| `frame_rgb` | 256 × 54 × 3 bytes | full RGB POV frame (R, G, B per LED); used by full-frame renderers such as the Ventilagon port |
| `frame_apa102` | 256 × 54 × 4 bytes | raw spatial APA102 POV frame. Every cell is the unmodified LED datum `[0xe0 \| GB, B, G, R]`; the desktop emulator decodes its light output. Sent by workbench LED-bus capture. |

`vs2_scene` is intentionally separate from the legacy 500-byte `sprites`
command. The first payload version has this little-endian layout:

| Offset | Size | Meaning |
|---:|---:|---|
| 0 | 4 | magic bytes `VS2\0` |
| 4 | 1 | version, currently `1` |
| 5 | 1 | layer count |
| 6 | 1 | sprite count |
| 7 | 1 | payload flags, currently `0` |
| 8 | 2 | header size, currently `16` |
| 10 | 2 | layer record size, currently `8` |
| 12 | 2 | sprite record size, currently `24` |
| 14 | 2 | reserved |

Layer records are 8 bytes: `id`, `mode`, `flags`, then 5 reserved bytes.
Sprite records are 24 bytes: `layer`, `strip`, `frame`, `mode`, `flags`,
3 reserved bytes, then signed 8.8 fixed-point `x` and `y` coordinates as
32-bit integers. `layer = 255` means the sprite is not owned by a layer, so
the sprite's own `mode` must be used. Otherwise the referenced layer can
hide the sprite and provides the projection mode. Flag bit `0x01` means
visible; `0x02` and `0x04` are `flip_x` and `flip_y`.

## Audio

| Command | Payload | Meaning |
|---|---|---|
| `sound <track>` | — | play a one-shot effect; track is `<group>.<game>/<name>` under the game's `sounds/` folder |
| `music <track> [loop]` | — | start a music track, optionally looping until changed/stopped |
| `music off` / `musicstop` | — | stop the current music |
| `notes <folder> <n1;n2;...>` | — | play a sequence of note samples from a folder |
| `achip <system> [args...]` | — | console emulator started: reset the matching host sound-chip synth ([emulator-audio.md](emulator-audio.md)) |
| `aframe <nbytes> <nsamples>` | `<nbytes>` | one video frame's worth of sound-chip register writes |
| `amap <nbytes>` | `<nbytes>` | mapper/synth auxiliary state |
| `astop` | — | console emulator stopped: tear down the host synth |

## Diagnostics and system

| Command | Payload | Meaning |
|---|---|---|
| `traceback <nbytes>` | `<nbytes>` | UTF-8 Python traceback from the board; hosts display it prominently |
| `info <nbytes>` | `<nbytes>` | UTF-8 line printed by the hardware MicroPython runtime; hosts write it to their standard output |
| `debug` | 512 bytes | 32 × (int64 timestamp, int64 turn duration) rotation log; hosts derive RPM/FPS |
| `povcal_state <schema> <generation> <nbytes>` | `<nbytes>` | canonical active POV colour-profile payload. The desktop emulator validates this binary record before decoding `frame_apa102` capture. |
| `ota_progress <stage> <detail> <pct>` | — | OTA status updates ([ota.md](ota.md)) |
| `ota_done <status>` / `ota_error <msg...>` | — | OTA completion / failure |
| `arduino <cmd>` | — | legacy Super Ventilagon base relay control (start/stop/reset/attract) |
| `base leds <r> <g> <b>` | — | Set every base RGB-strip LED. Channels are decimal bytes. |
| `base servo <position>` | — | Set normalized servo position (`0..255`). The Arduino alone maps this to its safe mechanical range. |
| `base buttons <mask> <blink_ms>` | — | Set button LED mask (`0..3`) and full blink period (`0` for steady, otherwise `100..10000` ms). |

## Transports

- **Desktop emulator, local simulation**: TCP to the MicroPython process
  (port 5005); named pipe on Windows.
- **Desktop emulator, hardware mode**: `frame_apa102` over TCP from the
  workbench's LED-bus capture; audio/system commands over the workbench's
  USB serial bridge. The dispatcher is shared, so every command is
  understood on either link.
- **Web emulator**: the same commands cross the WASM bridge as pointer +
  length calls (`post_command_ptr`) rather than a socket — see
  [web-emulator-architecture.md](web-emulator-architecture.md).
- **Hardware**: UART to the base station at 115200.
