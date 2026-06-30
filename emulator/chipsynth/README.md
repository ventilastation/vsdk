# chipsynth — host-side console sound-chip synthesizers

These shared libraries regenerate emulator audio on the pyglet host from the
sound-chip register writes the spinning ESP32-S3 streams over serial. They
compile the **same** chip cores that run on the device (from
`../../apps/retro-go`), so the host output matches the board exactly. See
`../../EMULATOR_AUDIO_PLAN.md` for the full design.

## Build

```sh
make            # builds libgenesissynth.<dylib|so>
```

`emu_audio.py` loads the library via ctypes at runtime. If it is missing, the
emulator still runs — it just prints a one-time note and stays silent for that
console.

Override the path to the retro-go checkout if yours differs:

```sh
make RETROGO=/path/to/apps/retro-go
```

## Libraries

| Library              | System            | Cores                         | Status |
|----------------------|-------------------|-------------------------------|--------|
| `libgenesissynth.*`  | Genesis/Mega Drive| gwenesis YM2612 + SN76489     | Phase 1 |
| (planned) NES        | NES               | nofrendo APU                  | Phase 2 |
| (planned) Lynx       | Atari Lynx        | handy Mikey                   | Phase 3 |

## API (ctypes)

```c
void genesis_synth_reset(void);
int  genesis_synth_render(const uint8_t *payload, int payload_len,
                          int nsamples, int16_t *out);
```

`genesis_synth_render` decodes one `aframe` payload — a sequence of
`varint(delta_samples), op, val` records — applies the writes at their sample
positions, and renders `nsamples` of int16 mono PCM (YM2612 + SN76489 mixed)
into `out`. Returns the sample count written.

`op` encodes the chip/register (see `emu_audio_bridge.h`): `0x00..0x03` =
YM2612 bus write, `0x04` = SN76489 byte.

## Note on the SN76489

The device firmware currently generates the PSG but does **not** mix it into its
(discarded) audio output — see the `// TODO: Mix in gwenesis_sn76489_buffer` in
`gwenesis/main/main.c`. The host mixes both chips, so regenerated audio here is
actually more complete than what the board's dummy sink would produce.
