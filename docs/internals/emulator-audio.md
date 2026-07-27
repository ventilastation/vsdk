# Streaming NES / SMS / MSX / Genesis / GB audio over the register-log bridge

Originally a plan (branch `emulator-audio-serial-bridge`) for the desktop
pyglet emulator only; see the status section below for what is real. The
same device-side bridge is now also the source for chip audio in the
**browser** web emulator's remote-workbench mode (§13).

## 0. Implementation status

**Device-side taps are wired for every console except Lynx**, not just
Genesis:

- `components/retro-go/emu_audio_bridge.{c,h}` — UART transport, per-frame
  varint register-log encoder, `achip`/`aframe`/`astop` wire commands, periodic
  bandwidth/drop stats. Inert on non-ventilastation targets
  (`RG_VS_ENABLE_HOST_BRIDGE` in `targets/ventilastation/config.h`).
- Register taps + per-frame `emu_audio_begin`/`emu_audio_frame_begin`/
  `emu_audio_frame_end` calls next to each core's existing
  `rg_audio_submit()`:
  - Genesis (gwenesis): `ym2612.c` (`YM2612Write`),
    `gwenesis_sn76489.c` (`gwenesis_SN76489_Write`); `gwenesis/main/main.c`.
  - SMS/Game Gear (smsplus): `sound.c`; `retro-core/main/main_sms.c`.
  - NES (nofrendo): `nes/apu.c` (`apu_write`); `retro-core/main/main_nes.c`.
  - Game Boy (gnuboy): `sound.c`; `retro-core/main/main_gbc.c`.
  - MSX (fMSX): `EMULib/AY8910.c` (`Write8910`); `fmsx/main/main.c`.
  - Lynx (handy) is **not** wired — the shared-timer-driven audio makes a
    faithful register-log replay hard (see §4); descoped for now.
- **Builds clean** for the ventilastation target.

Host (desktop pyglet emulator, `emulator/`):
- `emulator/chipsynth/` — `host_chip.c`/`host_sms.c`/`host_nes.c`/
  `host_gb.c`/`host_msx.c` + `Makefile`, each building a small shared library
  from the *unmodified* device chip-emulation sources (`ym2612.c`+
  `gwenesis_sn76489.c`, `sn76489.c`, `nes/apu.c`, `sound.c`, `AY8910.c`+
  `Sound.c`). All five build with `make -C emulator/chipsynth`; only
  `libgenesissynth`/`libsmssynth` ship pre-built in the repo, the rest build
  on demand.
- `emulator/emu_audio.py` — ctypes synth wrapper (`_Synth`), per-system
  factory/sample-rate/ROM-loader tables (`_SYNTH_FACTORIES`, `_SYSTEM_RATE`,
  `_ROM_LOADERS`), lock-protected PCM ring buffer, pyglet streaming
  `Source`/`Player` (lifecycle on the main thread, rendering on the comms
  thread).
- `emulator/comms.py` + `pygletengine.py` — dispatch the wire commands and
  pump the player each tick.

Verified statically: device + host both compile; the ctypes load path and chip
ABI ran (an early load reached reset/render); the varint encode/decode is
symmetric. One host crash was found and fixed by source analysis — the
Genesis synth must call `YM2612ResetChip()` (sets the channels' output-routing
pointers, which are NULL otherwise and segfault `YM2612Update`).

**Not yet done — verify on real hardware with audio output:**
1. `make -C emulator/chipsynth` (builds all five libraries).
2. Flash a console app, run a ROM on the spinning board.
3. Run the pyglet emulator pointed at the board over serial; confirm music/SFX
   play and check the device's `emu_audio: N B/s … dropped` stat stays within
   the ~11.5 KB/s link budget. Tune the encoder governor (§8) if needed.

## 1. Goal

When a retro-go emulator (NES, Genesis/Mega Drive, Atari Lynx) runs on the
spinning ESP32-S3 in LED-POV mode, its sound and music should be heard from the
base-station **pyglet** host, which is connected only by a **115200 8N1 UART**
link. The board is spinning and driving the LED strip over SPI, so the serial
link is the only path to the host and it is slow.

This must work like the existing Voom/Doom audio bridge in spirit: the device
does **not** ship raw audio; it ships compact *triggers*, and the host
reproduces the sound from its own local assets.

## 2. Why the Doom approach doesn't port directly

The Doom bridge works because Doom audio is a **fixed, enumerable set of named
clips** (WAD sound lumps + per-level music). The host pre-converts them to
MP3/WAV once (`audio.py`), and the device just sends `sound voom/<name>` /
`music voom/<name> loop` over the existing line protocol
(`prboom-go/main/voom_audio_bridge.c`). Tiny bandwidth, trivial.

Emulator audio is the opposite: it is **synthesized in real time** by emulated
sound chips. Each core produces a continuous PCM stream and submits it via
`rg_audio_submit()`:

| Emulator | Core | Sample rate | Stream size (16-bit stereo) |
|----------|------|-------------|------------------------------|
| NES      | nofrendo (`apu.c`)        | 32 000 Hz | ~128 KB/s |
| Genesis  | gwenesis (`ym2612.c` + `gwenesis_sn76489.c`) | 26 633 Hz | ~106 KB/s |
| Lynx     | handy (`mikie.cpp`)       | 32 000 Hz | ~128 KB/s |

A 115200 8N1 link carries **~11.5 KB/s** usable (10 bits/byte). Raw PCM is
**~10× too big**, even mono/8-bit would be marginal and ugly. So we cannot
stream samples. (On this target the audio sink is already the **Dummy** driver —
`config.h` sets both DACs off — so today the PCM is generated only for emulation
pacing and then discarded.)

## 3. Recommended approach: stream the chip *register writes*, re-synthesize on the host

This is the faithful analog of the Doom model:

> Doom: host owns the **sound assets**, device sends **which clip to play**.
> Here: host owns the **sound chip emulator** (the synthesizer), device sends
> the **register writes** (the "score") that drive it.

This is exactly what the **VGM** music format does. Register writes happen far
less often than audio samples — hundreds to low-thousands per second even during
busy music — so the data rate drops from ~100 KB/s of PCM to a few KB/s of
register traffic, which fits the link.

The whole console audio output (music *and* SFX, all channels) becomes a single
combined PCM stream regenerated on the host. There is no music/SFX split to
manage as in Doom — it is simpler and bit-exact, because the host runs the same
synthesis code.

### Key property: the chips keep running on-device

The cores must keep emulating their sound chips regardless, because:
- NES and Lynx **pace emulation off the audio sample count**
  (`rg_system_set_tick_rate(AUDIO_SAMPLE_RATE / …)`).
- Game logic reads chip status registers.

So we only **tap** the existing register-write entry points; we don't change
emulation. The generated PCM is still handed to the Dummy sink and discarded.

## 4. Hook points (verified in the tree)

All three cores funnel register writes through a small number of functions:

**Genesis (gwenesis)** — cleanest:
- `YM2612Write(unsigned int a, unsigned int v, int target)` — `ym2612.c:2171`
- `gwenesis_SN76489_Write(int data, int target)` — `gwenesis_sn76489.c:221`
- Few call sites (`gwenesis_bus.c`, `z80inst.c`, `gwenesis_vdp_mem.c`).
- `target` is the chip cycle timestamp → gives us intra-frame timing for free.

**NES (nofrendo)** — clean:
- `apu_write(uint32 address, uint8 value)` — `apu.c:427`, single handler for the
  whole `0x4000–0x4017` register range (`mem.c`).

**Lynx (handy)** — hookable but hardest:
- `CMikie::Poke(ULONG addr, UBYTE data)` — `mikie.cpp:1024`, single entry for all
  Mikey registers (filter to the audio/stereo range `0xFD20–0xFD3F`, `0xFD44…`).
- **Risk:** Lynx audio is produced by the shared **timer** hardware, not an
  isolated sound chip, so faithful host replay needs the relevant timer state,
  not just the audio registers. This is the known-difficult console for
  VGM-style logging. Treat as Phase 3 with a fidelity caveat (see §10/§11).

## 5. Wire protocol (extends the existing line framing)

Reuse the current `"<command>\n"` + optional binary-by-length framing
(`comms.py` `receive_loop`, `host_comms.h`). New commands:

- `achip <system>\n` — sent once when an emulator app starts; tells the host to
  instantiate/reset the matching synthesizer (`nes` | `genesis` | `lynx`) and
  start its streaming player. Mirrors how a new app announces itself.
- `astop\n` — emulator exiting; host tears down the synth/player.
- `aframe <len>\n` + `<len>` bytes — **one chunk per emulated video frame
  (~60 Hz)**: the packed register writes captured during that frame.

`aframe` payload = a sequence of small records:

```
[ delta_cycles : varint ][ op : 1 byte ][ value : 1 byte ]
  op encodes chip + register:
    0x00..0x5F  YM2612 part-0 reg
    0x60..0xBF  YM2612 part-1 reg
    0xC0        SN76489 byte (value only)
    0xD0..0xDF  NES APU reg (0x4000+low)
    0xE0..0xEF  Lynx Mikey audio reg
```

`delta_cycles` is the chip-cycle gap since the previous write in the chunk
(VGM-style "wait"). The chunk implicitly spans exactly one frame, so the host
renders one frame of audio per chunk and stays time-aligned without absolute
timestamps. (Exact opcode map to be finalized per core; the shape is what
matters.)

## 6. On-device components (retro-go)

1. **`emu_audio_bridge.c/.h`** in `components/retro-go/` (shared, like the POV
   driver), behind `RG_VS_ENABLE_POV_DISPLAY` / a new `RG_VS_EMU_AUDIO` flag:
   - `emu_audio_begin(system)` → emits `achip`.
   - `emu_audio_log(op, value, cycle)` → append to a per-frame ring buffer
     (IRAM-friendly, no malloc on the hot path).
   - `emu_audio_flush_frame()` → encode varint deltas + emit `aframe` via
     `host_send` (the existing `sb_send`/`wb_send` selector in `host_comms.h`).
   - `emu_audio_end()` → emits `astop`.
2. **Tap insertion** (minimal, `#if RG_VS_EMU_AUDIO`):
   - gwenesis: one line in `YM2612Write` and `gwenesis_SN76489_Write`.
   - NES: one line in `apu_write`.
   - Lynx: one line in `CMikie::Poke` (audio-range filtered).
3. **Per-frame flush** at each core's end-of-frame, next to the existing
   `rg_audio_submit()` call (`gwenesis/main/main.c:403`, `main_nes.c:300`,
   `main_lynx.cpp:272`).
4. **UART TX buffer** enlarged in `serial_bridge.c` (`sb_init`) so a frame chunk
   is copied to the driver ring buffer and drains asynchronously instead of
   blocking the game loop on core 0.

## 7. Host components (pyglet emulator, `vsdk/emulator/`)

1. **`comms.py`**: handle `achip` / `astop` / `aframe` (read `<len>` bytes like
   `frame`), forward to a new `emu_audio` module.
2. **`emu_audio.py`**: owns one synthesizer instance + one pyglet streaming
   player. Decodes each `aframe` chunk, applies the register writes at their
   sub-frame offsets, renders one frame of PCM, pushes it into a small
   thread-safe ring buffer (3–4 frame jitter ≈ 50–66 ms).
3. **Synthesizer** — recommended: **compile the device's own chip C sources as a
   small host shared library** (`ctypes`/`cffi`), one entry set per system:
   `reset()`, `write(op,val)`, `render(nsamples) -> int16 PCM`. Reusing the exact
   same `ym2612.c` / `gwenesis_sn76489.c` / nofrendo `apu.c` / handy mikie
   synthesis **guarantees fidelity** and is little code (the chip files are
   self-contained). Alternative: an existing `libvgm`/Python chip lib — less
   build glue but risks subtle mismatches vs gwenesis' specific cores.
4. **Player**: a `pyglet` streaming source backed by the ring buffer, started on
   `achip`, stopped/flushed on `astop`. No per-clip asset loading needed.

## 8. Bandwidth budget & governor

- Sustained budget: ~11.5 KB/s ÷ 60 fps ≈ **~190 bytes/frame** average.
- Typical busy Genesis music ≈ 3–4 KB/s ≈ 55–70 bytes/frame → comfortable.
  NES is lower. SFX cause transient bursts.
- Protections (device side):
  - **Coalesce same-register writes within a frame** (keep last value) — large,
    near-lossless win for slow-changing regs.
  - **Per-frame byte budget** with a drop policy under sustained pressure
    (e.g. shed SN76489/PSG or a noise channel before FM), and a `log()`-style
    note so dropping is visible, never silent.
- UART is full-duplex, so outbound audio does not compete with the inbound
  input/joystick bytes.

## 9. Latency

Device buffers one frame, host holds a 3–4 frame jitter buffer → **~50–80 ms**
end-to-end. Fine for ambient game audio; not tight enough for rhythm games, but
that is not the use case.

## 10. Phasing

1. **Phase 1 — Genesis** (proof of concept; cleanest hooks, richest audio):
   device tap + protocol + host YM2612/SN76489 synth + streaming player.
   Validates the whole pipeline end to end.
2. **Phase 2 — NES**: add `apu_write` tap + host NES APU synth. Reuses all
   protocol/host plumbing.
3. **Phase 3 — Lynx**: `Poke` tap + host Mikey synth; resolve the timer-state
   replay problem, or accept reduced fidelity. Decide go/no-go after Phase 1–2.

## 11. Risks & open decisions

- **Host synthesizer source** (decision): reuse device chip C sources as a host
  lib (recommended, faithful) vs. an off-the-shelf VGM chip lib (less glue,
  fidelity risk). Affects host build.
- **Lynx feasibility**: timer-driven audio may not replay faithfully from
  register writes alone; may need extra timer state in the stream, or Lynx is
  descoped.
- **TX backpressure**: must not stall the spinning core-0 game loop; needs an
  enlarged async UART TX buffer and the byte governor.
- **Scope** (decision): land **Genesis only** first as a vertical slice, or build
  all three together. Recommendation: Genesis first.

## 12. Testing

- Bench: run on hardware over USB-serial to a dev host running the pyglet
  emulator; compare regenerated audio against the same ROM in standalone
  gwenesis/nofrendo/handy.
- Instrument the device governor to report bytes/frame and drop counts.
- Reuse the existing `render-parity-test` discipline: a fixed input script →
  deterministic register log → byte-compare host PCM against a reference render.

## 13. Browser playback (remote-workbench mode)

This is a **different transport and a different synth build** from the
desktop pyglet path above, sharing only the device-side bridge and the
`host_nes.c`/`host_sms.c`/`host_msx.c` wrapper sources. Do not confuse the
two:

- Transport: `emulator/remote_gateway.py`'s `HostProtocolParser` already
  parses `achip`/`aframe`/`astop` off the same USB-serial link (it exists
  specifically so the gateway doesn't need the desktop host's audio code).
  `_broadcast_host_event()` forwards them to the browser over the existing
  WSS host-event channel used for `sound`/`music`/etc — no WebRTC/Opus
  involved, no server-side resynthesis.
- Synth: the browser has its own build of the chip cores, compiled to
  WebAssembly by `tools/build-chipsynth-wasm.sh` (mirrors
  `tools/build-micropython-webassembly.sh`'s emsdk bootstrap) from the same
  `emulator/chipsynth/host_nes.c`/`host_sms.c`/`host_msx.c` +
  vendored-core sources, output to `web/vendor/chipsynth/*.mjs`. Only
  SMS/NES/MSX are built for the browser today (no Genesis/GB/Lynx WASM
  build); Lynx isn't wired on-device at all (§0).
- Playback: `web/chip-audio-host.js` loads the matching WASM module on
  `achip`, renders PCM per `aframe` (reusing the exact `reset()`/
  `render(payload,len,nsamples,out)` C ABI the ctypes host already calls),
  and feeds it to `web/chip-audio-worklet-processor.js` (an
  `AudioWorkletProcessor`) over a dedicated `AudioContext({ sampleRate:
  32000 })` — the chips' native rate, so no resampling is needed anywhere.
  `web/app.js`'s `processFrameEvents()` dispatches the three commands to
  `this.chipAudio`.
- NES DMC sample playback needs real PRG-ROM bytes (see `host_nes.c`); the
  browser bundle doesn't ship ROM files, so DMC silently stays quiet here,
  same graceful fallback as the desktop host when it can't find a ROM either.
