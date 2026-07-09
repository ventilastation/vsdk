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
| `imagestrip <slot> <nbytes>` | `<nbytes>` | one image strip: 4-byte header (w, h, frames, palette) + pixels, same encoding as a ROM strip entry |
| `palette <n> <version>` | `n × 1024` bytes | palette block, `n` palettes of 256 × 4-byte entries ([rom-format.md](rom-format.md)) |
| `frame_rgb` | 256 × 54 × 3 bytes | full RGB POV frame (R, G, B per LED); sent by the workbench's LED-bus capture and by full-frame renderers such as the Ventilagon port |

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
| `debug` | 512 bytes | 32 × (int64 timestamp, int64 turn duration) rotation log; hosts derive RPM/FPS |
| `ota_progress <stage> <detail> <pct>` | — | OTA status updates ([ota.md](ota.md)) |
| `ota_done <status>` / `ota_error <msg...>` | — | OTA completion / failure |
| `arduino <cmd>` | — | legacy Super Ventilagon base relay control (start/stop/reset/attract) |

## Transports

- **Desktop emulator, local simulation**: TCP to the MicroPython process
  (port 5005); named pipe on Windows.
- **Desktop emulator, hardware mode**: `frame_rgb` over TCP from the
  workbench's LED-bus capture; audio/system commands over the workbench's
  USB serial bridge. The dispatcher is shared, so every command is
  understood on either link.
- **Web emulator**: the same commands cross the WASM bridge as pointer +
  length calls (`post_command_ptr`) rather than a socket — see
  [web-emulator-architecture.md](web-emulator-architecture.md).
- **Hardware**: UART to the base station at 115200.
