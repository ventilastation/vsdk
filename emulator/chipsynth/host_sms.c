// Host-side SMS/Game Gear SN76489 synthesizer for the Ventilastation emulator
// audio bridge.
//
// The ESP32-S3 streams PSG register writes over serial as "aframe" chunks.
// Here we replay those writes through the same smsplus SN76489 core the device
// runs, then downmix the stereo output to mono PCM for pyglet.

#include <stdint.h>
#include <string.h>

#include "shared.h"
#include "emu_audio_bridge.h"

#define SMS_SAMPLE_RATE 32000
#define MAXSAMP 2048

static int16_t psg_left[MAXSAMP];
static int16_t psg_right[MAXSAMP];

static void sms_synth_reset_common(int psg_clock)
{
    SN76489_Init(0, psg_clock, SMS_SAMPLE_RATE);
    SN76489_Config(0, MUTE_ALLON, BOOST_OFF, VOL_FULL, FB_SEGAVDP);
    SN76489_Reset(0);
    memset(psg_left, 0, sizeof(psg_left));
    memset(psg_right, 0, sizeof(psg_right));
}

void sms_synth_reset_ntsc(void)
{
    sms_synth_reset_common(CLOCK_NTSC);
}

void sms_synth_reset_pal(void)
{
    sms_synth_reset_common(CLOCK_PAL);
}

int sms_synth_render(const uint8_t *payload, int payload_len, int nsamples, int16_t *out)
{
    if (nsamples > MAXSAMP)
        nsamples = MAXSAMP;
    if (nsamples < 0)
        nsamples = 0;

    memset(psg_left, 0, (size_t)nsamples * sizeof(psg_left[0]));
    memset(psg_right, 0, (size_t)nsamples * sizeof(psg_right[0]));

    const uint8_t *p = payload;
    const uint8_t *end = payload + payload_len;
    uint32_t cur = 0;
    int rendered = 0;

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

        if (target > rendered) {
            int16_t *chunk[2] = {psg_left + rendered, psg_right + rendered};
            SN76489_Update(0, chunk, target - rendered);
            rendered = target;
        }

        if (op == EMU_OP_SMS_PSG)
            SN76489_Write(0, val);
        else if (op == EMU_OP_SMS_GGSTEREO)
            SN76489_GGStereoWrite(0, val);
    }

    if (rendered < nsamples) {
        int16_t *chunk[2] = {psg_left + rendered, psg_right + rendered};
        SN76489_Update(0, chunk, nsamples - rendered);
    }

    for (int i = 0; i < nsamples; i++) {
        int s = ((int)psg_left[i] + (int)psg_right[i]) * 11 / 8;
        if (s > 32767)
            s = 32767;
        else if (s < -32768)
            s = -32768;
        out[i] = (int16_t)s;
    }

    return nsamples;
}
