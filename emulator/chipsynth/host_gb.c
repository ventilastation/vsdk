// Host-side Game Boy (gnuboy) APU synthesizer for the Ventilastation
// emulator audio bridge.
//
// The ESP32-S3 streams APU register writes over serial as "aframe" chunks.
// Here we replay those writes through the same gnuboy sound.c core the
// device runs. Unlike NES, this engine renders audio incrementally as CPU
// cycles elapse -- gb_sound_write() "catches up" the render via
// gb_sound_emulate() before applying each new register value -- so, like
// Genesis/SMS, sub-frame write timing matters here and we replay it using
// the payload's delta timestamps by advancing GB.snd->cycles by the right
// amount before each write.
//
// All 4 GB channels are fully self-contained (the wave channel plays a RAM
// table the game itself writes, not cartridge ROM), so unlike NES DMC no
// ROM access is needed on the host.

#include <stdint.h>
#include <string.h>

#include "gnuboy.h"
#include "sound.h"
#include "hw.h"
#include "emu_audio_bridge.h"

#define GB_SYNTH_SAMPLE_RATE 32000
#define MAXSAMP 2048

static int16_t mono[MAXSAMP];

// Definitions for the externs sound.c/hw.h expect (see host_nes.c for the
// same pattern) -- we only need these as valid, zeroed structs; the CPU/
// PPU/mapper/cart subsystems they otherwise describe are never exercised.
gb_cart_t cart;
gb_t GB;

// sound.c itself taps register writes via emu_audio_write() (it's the
// reused device core); on the host we're replaying already-captured writes,
// not capturing our own, so this is a no-op (same pattern as host_nes.c).
void emu_audio_write(uint8_t op, uint8_t val, uint16_t idx)
{
    (void)op;
    (void)val;
    (void)idx;
}

static void gb_synth_reset_common(void)
{
    memset(&GB, 0, sizeof(GB));
    GB.hwtype = GB_HW_CGB; // doesn't affect ongoing synthesis, only the
                            // default (pre-game-write) wave RAM contents
    GB.snd = gb_sound_init();
    GB.audio.samplerate = GB_SYNTH_SAMPLE_RATE;
    GB.audio.format = GB_AUDIO_MONO_S16; // skip the device's L/R downmix
    gb_sound_reset(true);
    memset(mono, 0, sizeof(mono));
}

void gb_synth_reset(void)
{
    gb_synth_reset_common();
}

int gb_synth_render(const uint8_t *payload, int payload_len, int nsamples, int16_t *out)
{
    if (nsamples > MAXSAMP)
        nsamples = MAXSAMP;
    if (nsamples < 0)
        nsamples = 0;

    GB.audio.buffer = mono;
    GB.audio.pos = 0;
    GB.audio.len = (size_t)nsamples;
    GB.audio.callback = NULL; // sized so gb_sound_emulate() never overflows it

    const uint8_t *p = payload;
    const uint8_t *end = payload + payload_len;
    uint32_t cur = 0;
    int rendered_to = 0; // how many samples' worth of cycles we've advanced

    while (p < end) {
        uint32_t delta = 0;
        int shift = 0;
        uint8_t b;
        do {
            b = *p++;
            delta |= (uint32_t)(b & 0x7f) << shift;
            shift += 7;
        } while ((b & 0x80) && p < end);

        if (end - p < 2)
            break;

        uint8_t op = *p++;
        uint8_t val = *p++;

        cur += delta;
        int target = (int)cur;
        if (target > nsamples)
            target = nsamples;

        if (target > rendered_to) {
            GB.snd->cycles += (target - rendered_to) * GB.snd->rate;
            rendered_to = target;
        }

        if (op >= EMU_OP_GB_BASE && op <= EMU_OP_GB_BASE + 0x2F)
            gb_sound_write((byte)(0x10 + (op - EMU_OP_GB_BASE)), val);
    }

    if (nsamples > rendered_to) {
        GB.snd->cycles += (nsamples - rendered_to) * GB.snd->rate;
        gb_sound_emulate();
    }

    int n = (int)GB.audio.pos;
    if (n > nsamples)
        n = nsamples;
    memcpy(out, mono, (size_t)n * sizeof(int16_t));
    if (n < nsamples)
        memset(out + n, 0, (size_t)(nsamples - n) * sizeof(int16_t));

    return nsamples;
}
