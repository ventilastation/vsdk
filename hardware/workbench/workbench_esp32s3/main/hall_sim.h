#pragma once

#include <stdint.h>

// Starts driving WB_HALL_PIN with a clean negative pulse once per simulated
// revolution at WB_HALL_RPM, mimicking a real hall sensor with a pull-up
// (idle HIGH, brief LOW pulse on each "revolution").
void hall_sim_begin(void);

// Current angular column (0..WB_COLUMNS-1), reproducing the DUT's own
// gpu_step() formula: column = ((now - last_turn) * COLUMNS / period) % COLUMNS.
// Assumes column_offset == 0 (see WORKBENCH.md).
uint32_t hall_sim_current_column(void);
