#pragma once

#include <stdint.h>

// Starts driving WB_HALL_PIN with a clean negative pulse once per simulated
// revolution at WB_HALL_RPM_DEFAULT, mimicking a real hall sensor with a
// pull-up (idle HIGH, brief LOW pulse on each "revolution").
void hall_sim_begin(void);

// Changes the simulated rotation speed at runtime (e.g. from the pyglet
// UI's RPM slider, via telemetry.c). Clamped to [0, WB_HALL_RPM_MAX]; 0
// stops the pulse train entirely (simulates a stopped rotor).
void hall_sim_set_rpm(uint32_t rpm);
uint32_t hall_sim_get_rpm(void);

// Current angular column (0..WB_COLUMNS-1), reproducing the DUT's own
// gpu_step() formula: column = ((now - last_turn) * COLUMNS / period) % COLUMNS.
// Assumes column_offset == 0 (see docs/internals/workbench.md). Returns 0 while stopped
// (rpm == 0).
uint32_t hall_sim_current_column(void);

// Number of simulated revolutions (hall pulses) since boot. The LED capture
// uses changes in this to resync its per-burst column counter to column 0 at
// the start of each revolution.
uint32_t hall_sim_turn_count(void);
