/* Host-build stub for the ESP-IDF header pulled in by gpu.c/gpu.h. */
#pragma once
#include <stdint.h>
#include <sys/param.h> /* MIN / MAX, provided by esp headers on the device */

static inline uint32_t esp_random(void) {
    return 0x12345678u;
}
