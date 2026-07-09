# Streaming NES / Genesis / Lynx audio to the pyglet emulator over 115200 serial

Originally a plan (branch `emulator-audio-serial-bridge`); phase 1 has shipped,
see the status section below for what is real vs still planned.

## 0. Implementation status

**Phase 1 (Genesis) is implemented.** What landed:

Device (retro-go):
- `components/retro-go/emu_audio_bridge.{c,h}` — UART transport, per-frame
  varint register-log encoder, `achip`/`aframe`/`astop` wire commands, periodic
  bandwidth/drop stats. Inert on non-ventilastation targets.
- Register taps in `gwenesis/.../ym2612.c` (`YM2612Write`) and
  `gwenesis_sn76489.c` (`gwenesis_SN76489_Write`), timestamped with each chip's
  in-frame sample index.
- `gwenesis/main/main.c` — `emu_audio_begin("genesis")` + per-frame
  begin/end around the existing chip run.
- **Builds clean** for the ventilastation target (`rg_tool.py build gwenesis`).

Host (pyglet emulator):
- `emulator/chipsynth/` — `host_chip.c` + `Makefile` building
  `libgenesissynth.*` from the unmodified gwenesis YM2612 + SN76489 cores.
  **Compiles clean.**
- `emulator/emu_audio.py` — ctypes synth wrapper, lock-protected PCM ring
  buffer, pyglet streaming `Source`/`Player` (lifecycle on the main thread,
  rendering on the comms thread).
- `emulator/comms.py` + `pygletengine.py` — dispatch the new commands and pump
  the player each tick.

Verified statically: device + host both compile; the ctypes load path and chip
ABI ran (an early load reached reset/render); the varint encode/decode is
symmetric. One host crash was found and fixed by source analysis — the synth
must call `YM2612ResetChip()` (sets the channels' output-routing pointers, which
are NULL otherwise and segfault `YM2612Update`).

**Not yet done — verify on a Mac with audio hardware** (the dev sandbox could
not exercise the freshly built dylib or play audio):
1. `cd emulator/chipsynth && make`.
2. Flash the gwenesis app, run a Genesis ROM on the spinning board.
3. Run the pyglet emulator pointed at the board over serial; confirm music/SFX
   play and check the device's `emu_audio: N B/s … dropped` stat stays within
   the ~11.5 KB/s link budget. Tune the encoder governor (§8) if needed.

Phases 2 (NES) and 3 (Lynx) are not started; the device bridge and host
plumbing are generic and ready for their op ranges.

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
