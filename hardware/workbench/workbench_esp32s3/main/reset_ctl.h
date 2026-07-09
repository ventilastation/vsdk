#pragma once

#include <stdint.h>

// Leaves the reset line released (Hi-Z) so the DUT's own pull-up holds its
// EN/reset pin high.
void reset_ctl_begin(void);

// Asserts reset (drives the line low) for low_ms, then releases it back to
// Hi-Z. Equivalent to pressing the DUT's physical reset button.
void reset_ctl_pulse(uint32_t low_ms);
