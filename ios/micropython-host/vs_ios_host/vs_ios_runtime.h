#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "vs_ios_host.h"

// This VM is intentionally single-threaded.  Start and tick it from the same
// serial executor (the iOS main actor in the first native host).
bool vs_ios_runtime_start(const char *runtime_root, const vs_ios_host_callbacks_t *callbacks);
bool vs_ios_runtime_tick(void);
void vs_ios_runtime_set_input(uint8_t joy1, uint8_t joy2, uint8_t extra, bool exit_requested);
const char *vs_ios_runtime_last_error(void);
