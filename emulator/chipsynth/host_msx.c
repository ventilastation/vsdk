// Host-side MSX AY8910 PSG synthesizer for the Ventilastation emulator
// audio bridge.
//
// The ESP32-S3 streams AY8910 register writes over serial as "aframe"
// chunks. Here we replay those writes through the same AY8910.c + Sound.c
// core the device runs: AY8910.c decodes raw register pokes into abstract
// Sound()/SetSound()/SetNoise() calls (Sound.c's generic multi-system tone
// mixer), and Sound.c's RenderAudio() mixes those into PCM. Audio-relevant
// writes happen at most every 8 scanlines on the device (Loop8910/Sync8910
// cadence in MSX.c), so we replay with that same granularity via the
// payload's delta timestamps rather than assuming per-sample precision.
//
// Only the AY8910 (the base PSG every MSX has) is bridged. SCC and
// MSX-MUSIC/YM2413 are cartridge/hardware-dependent expansion audio and
// are not tapped today.

#include <stdint.h>
#include <string.h>
#include <stdio.h>

#include "AY8910.h"
#include "Sound.h"
#include "emu_audio_bridge.h"

#define MSX_SAMPLE_RATE 32000
#define MSX_PSG_CLOCK (3579545 / 2) // MSX.h: PSG_CLOCK = CPU_CLOCK/2
#define MAXSAMP 2048

static AY8910 PSG;
static int wave[MAXSAMP];

extern int MasterVolume; // Sound.c global; not exposed via Sound.h

// --- Sound.c/AY8910.c taps + platform hooks the host has no real use for ---

// AY8910.c itself taps register writes via emu_audio_write() (it's the
// reused device core); on the host we're replaying already-captured writes,
// not capturing our own, so this is a no-op (same pattern as host_nes.c).
void emu_audio_write(uint8_t op, uint8_t val, uint16_t idx)
{
    (void)op;
    (void)val;
    (void)idx;
}

// Sound.c's InitSound()/PlayAudio()/MIDI-logging paths expect these platform
// hooks to exist; we call RenderAudio() directly and do our own int16
// conversion (see msx_synth_render), so none of these are ever meaningfully
// exercised -- they just need to link.
unsigned int InitAudio(unsigned int Rate, unsigned int Latency)
{
    (void)Latency;
    return Rate ? Rate : MSX_SAMPLE_RATE;
}

void TrashAudio(void)
{
}

unsigned int GetFreeAudio(void)
{
    return 0x7FFFFFFF;
}

unsigned int WriteAudio(sample *Data, unsigned int Length)
{
    (void)Data;
    return Length;
}

FILE *OpenRealFile(const char *name, const char *mode)
{
    (void)name;
    (void)mode;
    return NULL;
}

void msx_synth_reset(void)
{
    InitSound(MSX_SAMPLE_RATE, 150);
    SetChannels(64, 0xFFFFFFFF);
    Reset8910(&PSG, MSX_PSG_CLOCK, 0);
    memset(wave, 0, sizeof(wave));
}

int msx_synth_render(const uint8_t *payload, int payload_len, int nsamples, int16_t *out)
{
    if (nsamples > MAXSAMP)
        nsamples = MAXSAMP;
    if (nsamples < 0)
        nsamples = 0;

    const uint8_t *p = payload;
    const uint8_t *end = payload + payload_len;
    uint32_t cur = 0;
    int rendered_to = 0; // how many samples we've already mixed into wave[]

    memset(wave, 0, (size_t)nsamples * sizeof(int));

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
            RenderAudio(wave + rendered_to, (unsigned int)(target - rendered_to));
            rendered_to = target;
        }

        if (op >= EMU_OP_MSX_AY_BASE && op < EMU_OP_MSX_AY_BASE + 16)
            Write8910(&PSG, (byte)(op - EMU_OP_MSX_AY_BASE), val);
    }

    if (nsamples > rendered_to) {
        RenderAudio(wave + rendered_to, (unsigned int)(nsamples - rendered_to));
        rendered_to = nsamples;
    }

    // Same normalize/clip math as Sound.c's PlayAudio() (BPS16 case).
    for (int i = 0; i < nsamples; i++) {
        int d = (wave[i] * MasterVolume) >> 8;
        if (d > 32767) d = 32767;
        else if (d < -32768) d = -32768;
        out[i] = (int16_t)d;
    }

    return nsamples;
}
