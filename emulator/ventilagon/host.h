#pragma once
#include <stdint.h>

#ifdef _WIN32
#define VENTILAGON_EXPORT __declspec(dllexport)
#else
#define VENTILAGON_EXPORT
#endif

#define VENTILAGON_FRAME_BYTES (256 * 54 * 3)
#define VENTILAGON_STEP_US 100
#define VENTILAGON_TURN_US 100000 /* virtual rotor: 600 RPM */

VENTILAGON_EXPORT void ventilagon_host_enter(uint32_t seed);
VENTILAGON_EXPORT void ventilagon_host_exit(void);
VENTILAGON_EXPORT void ventilagon_host_update(uint32_t elapsed_us, int buttons);
VENTILAGON_EXPORT int ventilagon_host_is_idle(void);
VENTILAGON_EXPORT const char *ventilagon_host_sending(void);
VENTILAGON_EXPORT const uint8_t *ventilagon_host_frame(void);

#ifdef VENTILAGON_TEST
void ventilagon_test_play(int level);
void ventilagon_test_empty(void);
void ventilagon_test_wall(int row, int value);
void ventilagon_test_state(int state);
int ventilagon_test_position(void);
int ventilagon_test_row(int row);
int ventilagon_test_section(void);
int ventilagon_test_drift(void);
void ventilagon_test_set_drift(int value);
void ventilagon_test_reference_frame(uint8_t *out);
#endif
