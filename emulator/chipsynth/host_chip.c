// Host-side Genesis sound-chip synthesizer for the Ventilastation emulator
// audio bridge.
//
// This compiles the *same* gwenesis YM2612 + SN76489 cores that run on the
// ESP32-S3 (from apps/retro-go/gwenesis), so audio regenerated here is
// bit-faithful to the device. The spinning board streams the chip register
// writes over serial ("aframe" chunks); we replay them through these cores and
// render PCM for pyglet to play. See EMULATOR_AUDIO_PLAN.md.
//
// Built as a shared library and driven from emu_audio.py via ctypes.

#include <stdint.h>
#include <string.h>

#include "ym2612.h"
#include "gwenesis_sn76489.h"
#include "emu_audio_bridge.h" // EMU_OP_* constants + the tap declaration

// m68k cycles per audio sample (gwenesis AUDIO_FREQ_DIVISOR). The device sends
// each write's sample index; target_cycles = index * DIVISOR reproduces the
// exact moment the chip core advanced to on the device.
#define DIVISOR 1009
#define MAXSAMP 2048

// Globals the gwenesis cores expect (normally defined in gwenesis/main/main.c).
int16_t gwenesis_ym2612_buffer[MAXSAMP];
int     ym2612_index, ym2612_clock;
int16_t gwenesis_sn76489_buffer[MAXSAMP];
int     sn76489_index, sn76489_clock;
int     frame_counter, scan_line;

// The device taps this from the chip sources; on the host it is a no-op (we are
// the consumer, not a producer).
void emu_audio_write(uint8_t op, uint8_t val, uint16_t idx) { (void)op; (void)val; (void)idx; }

// Save-state symbols referenced by ym2612.c's (uncalled) save/load functions.
// Stubbed so the cores link standalone; the host never serializes chip state.
typedef struct SaveState SaveState;
SaveState *saveGwenesisStateOpenForRead(const char *n) { (void)n; return 0; }
SaveState *saveGwenesisStateOpenForWrite(const char *n) { (void)n; return 0; }
int  saveGwenesisStateGet(SaveState *s, const char *t) { (void)s; (void)t; return 0; }
void saveGwenesisStateSet(SaveState *s, const char *t, int v) { (void)s; (void)t; (void)v; }
void saveGwenesisStateGetBuffer(SaveState *s, const char *t, void *b, int l) { (void)s; (void)t; (void)b; (void)l; }
void saveGwenesisStateSetBuffer(SaveState *s, const char *t, void *b, int l) { (void)s; (void)t; (void)b; (void)l; }

// Reset both cores. Call once when the device announces "achip genesis".
void genesis_synth_reset(void)
{
    YM2612Init();
    YM2612Config(9);
    // YM2612ResetChip() runs setup_connection(), which points each channel's
    // operator-output routing at the mixing accumulators. Without it those
    // pointers are NULL and YM2612Update() segfaults on the first sample. The
    // device gets this via reset_emulation(); we must do it explicitly here.
    YM2612ResetChip();
    // Match the device's init: PSG clock, sampling rate (888*60), divisor.
    gwenesis_SN76489_Init(3579545, 53280, DIVISOR);
    gwenesis_SN76489_Reset();
    ym2612_index = ym2612_clock = 0;
    sn76489_index = sn76489_clock = 0;
    memset(gwenesis_ym2612_buffer, 0, sizeof(gwenesis_ym2612_buffer));
    memset(gwenesis_sn76489_buffer, 0, sizeof(gwenesis_sn76489_buffer));
}

// Decode one "aframe" payload (varint delta-samples, op, val)* and render
// `nsamples` mono samples, mixing YM2612 + SN76489 into `out` (int16). Returns
// the number of samples written. Mirrors gwenesis/main/main.c's per-frame loop:
// indices reset to 0, writes applied at their sample positions, then both cores
// run out to the end of the frame.
int genesis_synth_render(const uint8_t *payload, int payload_len, int nsamples, int16_t *out)
{
    if (nsamples > MAXSAMP)
        nsamples = MAXSAMP;
    if (nsamples < 0)
        nsamples = 0;

    ym2612_index = ym2612_clock = 0;
    sn76489_index = sn76489_clock = 0;

    const uint8_t *p = payload;
    const uint8_t *end = payload + payload_len;
    uint32_t cur = 0;

    while (p < end) {
        // LEB128 unsigned varint: sample delta since the previous write.
        uint32_t delta = 0;
        int shift = 0;
        uint8_t b;
        do {
            b = *p++;
            delta |= (uint32_t)(b & 0x7f) << shift;
            shift += 7;
        } while ((b & 0x80) && p < end);

        if (end - p < 2) // need op + val
            break;
        uint8_t op = *p++;
        uint8_t val = *p++;

        cur += delta;
        int target = (int)(cur * DIVISOR);
        if (op <= EMU_OP_SN76489 - 1) {        // 0x00..0x03 → YM2612 bus write
            YM2612Write(op, val, target);
        } else if (op == EMU_OP_SN76489) {     // 0x04 → SN76489 byte
            gwenesis_SN76489_Write(val, target);
        }
        // Other op ranges (NES, Lynx) are handled by their own synth libs.
    }

    int target = nsamples * DIVISOR;
    ym2612_run(target);
    gwenesis_SN76489_run(target);

    for (int i = 0; i < nsamples; i++) {
        int s = gwenesis_ym2612_buffer[i] + gwenesis_sn76489_buffer[i];
        if (s > 32767) s = 32767;
        else if (s < -32768) s = -32768;
        out[i] = (int16_t)s;
    }
    return nsamples;
}
