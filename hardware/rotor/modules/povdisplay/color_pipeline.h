#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define COLOR_PIPELINE_LEDS 54
#define COLOR_PIPELINE_PROFILE_BYTES 319

// Parse and atomically activate a canonical PCAL v1 profile. The profile is
// built into the inactive buffer before the active index is swapped, so the
// GPU task always reads a complete LUT.
bool color_pipeline_apply(const uint8_t *profile, size_t length);

// Create the canonical factory PCAL v1 profile. Native apps use this for
// `povcal factory` even when NVS has not yet been provisioned.
bool color_pipeline_build_default(uint8_t *profile, size_t length, uint32_t generation);

// False until a valid profile has been applied. The legacy renderer remains a
// safe fallback during early boot and for invalid profiles.
bool color_pipeline_is_active(void);

// Convert source display RGB bytes into the little-endian 32-bit APA102 word
// used by the existing SPI DMA buffer: memory bytes are [GB, B, G, R].
uint32_t color_pipeline_encode_rgb(uint8_t led, uint8_t red, uint8_t green, uint8_t blue);
