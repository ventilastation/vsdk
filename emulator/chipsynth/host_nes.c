// Host-side NES (nofrendo) APU synthesizer for the Ventilastation emulator
// audio bridge.
//
// The ESP32-S3 streams APU register writes over serial as "aframe" chunks.
// Here we replay those writes through the same nofrendo apu.c core the
// device runs. Unlike Genesis/SMS, this engine only renders audio once per
// video frame -- apu_process() mixes all channels from whatever register
// state is current when it's called (nes/apu.c never advances the frame
// sequencer mid-frame) -- so there is no meaningful sub-frame write timing
// to reproduce here: we just replay a frame's writes in order, then render.
//
// The DMC channel reads its sample bytes from cartridge PRG-ROM over DMA
// (addresses $C000-$FFFF). The host has no live cartridge/mapper, but it
// does have the same ROM files the board's were synced from (see
// nes_synth_load_rom() below) -- so instead of emulating bank-switching, we
// take the pragmatic shortcut of statically mapping the ROM's *last* 16KB
// PRG-ROM bank across that whole window. That's exactly correct for NROM
// (the entire window, no switching) and UNROM (that window is hardware-fixed
// to the last bank), and correct for MMC1/MMC3 whenever they're in their
// common configuration (games conventionally keep DMC samples in the fixed
// bank). It can be wrong if a game dynamically banks the $C000-$DFFF part of
// that window mid-sample -- full fidelity there would need the device to
// also stream mapper bank-switch writes, which it doesn't today.

#include <stdint.h>
#include <string.h>

#include "nes.h"
#include "emu_audio_bridge.h"

#define NES_SAMPLE_RATE 32000
#define MAXSAMP 2048

static int16_t mono[MAXSAMP];
static nes_t host_nes;

// Last 16KB of the loaded ROM's PRG-ROM, statically mapped at $C000-$FFFF
// (see file header). Zeroed / has_rom=false until nes_synth_load_rom() is
// called, so DMC just reads silence if no ROM was supplied.
#define PRG_BANK_SIZE 0x4000
static uint8_t prg_last_bank[PRG_BANK_SIZE];
static bool has_rom = false;

// Called by the host (emu_audio.py) after locating the same ROM file the
// board loaded. `data`/`len` is the ROM's PRG-ROM data (or any prefix of
// it); only the last PRG_BANK_SIZE bytes matter, since that's what maps to
// the DMC's fixed address window.
void nes_synth_load_rom(const uint8_t *data, int len)
{
    memset(prg_last_bank, 0, sizeof(prg_last_bank));
    has_rom = false;
    if (!data || len <= 0)
        return;
    int n = len < PRG_BANK_SIZE ? len : PRG_BANK_SIZE;
    memcpy(prg_last_bank + (PRG_BANK_SIZE - n), data + (len - n), n);
    has_rom = true;
}

// --- nofrendo glue the host has no real implementation for ---

nes_t *nes_getptr(void)
{
    return &host_nes;
}

uint8 mem_getbyte(uint32 address)
{
    if (has_rom && address >= 0xC000)
        return prg_last_bank[address - 0xC000];
    return 0; // no ROM loaded; silences DMC, doesn't crash it
}

void nes6502_burn(int cycles)
{
    (void)cycles;
}

void nes6502_irq(void)
{
}

// apu.c itself taps register writes via emu_audio_write() (it's the reused
// device core); on the host we're replaying already-captured writes, not
// capturing our own, so this is a no-op (same pattern as host_chip.c).
void emu_audio_write(uint8_t op, uint8_t val, uint16_t idx)
{
    (void)op;
    (void)val;
    (void)idx;
}

static void nes_synth_reset_common(int cpu_clock, int refresh_rate)
{
    apu_init(NES_SAMPLE_RATE, false);
    memset(&host_nes, 0, sizeof(host_nes));
    host_nes.cpu_clock = cpu_clock;
    host_nes.refresh_rate = refresh_rate;
    apu_reset();
    memset(mono, 0, sizeof(mono));
}

void nes_synth_reset_ntsc(void)
{
    nes_synth_reset_common(NES_CPU_CLOCK_NTSC, NES_REFRESH_RATE_NTSC);
}

void nes_synth_reset_pal(void)
{
    nes_synth_reset_common(NES_CPU_CLOCK_PAL, NES_REFRESH_RATE_PAL);
}

int nes_synth_render(const uint8_t *payload, int payload_len, int nsamples, int16_t *out)
{
    if (nsamples > MAXSAMP)
        nsamples = MAXSAMP;
    if (nsamples < 0)
        nsamples = 0;

    const uint8_t *p = payload;
    const uint8_t *end = payload + payload_len;

    while (p < end) {
        // Sub-frame delta is not meaningful for this engine (see file header);
        // decode and discard it, just to stay on record boundaries.
        int shift = 0;
        uint8_t b;
        do {
            b = *p++;
            shift += 7;
        } while ((b & 0x80) && p < end && shift < 32);

        if (end - p < 2)
            break;

        uint8_t op = *p++;
        uint8_t val = *p++;

        if (op >= EMU_OP_NES_BASE && op <= 0x3f)
            apu_write(0x4000 + (op - EMU_OP_NES_BASE), val);
    }

    apu_process(mono, (size_t)nsamples, false);
    memcpy(out, mono, (size_t)nsamples * sizeof(int16_t));
    return nsamples;
}
