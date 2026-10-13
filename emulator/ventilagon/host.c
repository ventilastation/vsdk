/* Run the rotor's game sources with a deterministic virtual clock and no SPI.
 * Desktop and WASM build this exact adapter and the same original C files.
 */
#include <assert.h>
#include <string.h>
#include "ventilagon.h"
#include "host.h"

struct HostQueue {
    int size, head, count;
    unsigned char items[20][sizeof(const char *)];
};
static struct HostQueue queues[2];
static int queue_count;
static bool initialized, active;
static uint32_t random_state;
static int64_t clock_us;
static uint32_t pending_us;
volatile int64_t last_turn;
volatile int64_t last_turn_duration = VENTILAGON_TURN_US;
int column_offset;
static uint32_t draw0[54], draw1[54], dma[107];
uint32_t *draw_buffer0 = draw0, *draw_buffer1 = draw1;
/* Match the real continuous strip, including the shared centre word. */
uint32_t *dma_pixels0 = dma, *dma_pixels1 = dma + 53;
static uint8_t frame[VENTILAGON_FRAME_BYTES];

extern int64_t last_drift;
extern int last_ship_rows, last_infront_ship_rows;
extern unsigned int display_drift_counter;
extern int drift_pos, drift_speed;
extern bool calibrating;
extern int64_t win_last_step;
extern int display_ship_rows(int pos);
extern void credits_draw_column(int column);
extern void ventilagon_process_received(void);

/* libc rand differs on ESP32, Unix and WASM. Host builds substitute these
 * functions so identical seeds/input produce identical desktop/web replays.
 */
int ventilagon_host_rand(void) {
    random_state = random_state * 1664525u + 1013904223u;
    return (int)(random_state >> 1);
}
void ventilagon_host_srand(unsigned int seed) { random_state = seed; }
int64_t esp_timer_get_time(void) { return clock_us; }

QueueHandle_t xQueueCreate(int count, int size) {
    assert(count == 20 && size <= (int)sizeof(const char *) && queue_count < 2);
    struct HostQueue *q = &queues[queue_count++];
    memset(q, 0, sizeof(*q));
    q->size = size;
    return q;
}
int xQueueSend(QueueHandle_t q, const void *value, int timeout) {
    (void)timeout;
    if (q->count == 20) return 0;
    memcpy(q->items[(q->head + q->count++) % 20], value, q->size);
    return 1;
}
int xQueueReceive(QueueHandle_t q, void *value, int timeout) {
    (void)timeout;
    if (!q->count) return 0;
    memcpy(value, q->items[q->head], q->size);
    q->head = (q->head + 1) % 20;
    q->count--;
    return 1;
}

#ifdef VENTILAGON_TEST
static uint8_t *capture;
static int capture_column;
#endif
static void write_rgb(uint8_t *out, uint32_t color) {
    out[0] = color >> 24;
    out[1] = color >> 16;
    out[2] = color >> 8;
}
void spi_write_HSPI(void) {
#ifdef VENTILAGON_TEST
    if (capture) {
        for (int led = 0; led < 54; led++) {
            write_rgb(capture + (capture_column * 54 + led) * 3, dma_pixels1[led]);
            int opposed = (capture_column + 128) % 256;
            write_rgb(capture + (opposed * 54 + led) * 3, dma_pixels0[53 - led]);
        }
    }
#endif
}
void spiWaitComplete(void) {}

void ventilagon_host_enter(uint32_t seed) {
    clock_us = 0;
    pending_us = 0;
    last_turn = 0;
    last_move = last_step = last_drift = win_last_step = 0;
    last_ship_rows = last_infront_ship_rows = 0;
    display_drift_counter = 0;
    queued_steps = 0;
    nave_pos = 360;
    nave_calibrate = 0;
    boton_cw = boton_ccw = is_idle = false;
    current_level = levels[0];
    new_level = 0;
    ventilagon_host_srand(seed);
    if (!initialized) {
        ventilagon_init();
        initialized = true;
    } else {
        queues[0].head = queues[0].count = 0;
        queues[1].head = queues[1].count = 0;
        board_init();
    }
    ventilagon_enter();
    active = true;
}
void ventilagon_host_exit(void) {
    if (active) ventilagon_exit();
    active = false;
}
void ventilagon_host_update(uint32_t elapsed_us, int buttons) {
    if (!active) return;
    byte value = (byte)buttons;
    /* Input is sampled at the presentation boundary, not queued once per
     * simulation substep. Consume it even when no full substep is due yet.
     */
    xQueueSend(queue_received, &value, 0);
    ventilagon_process_received();
    /* A suspended tab pauses the game instead of replaying minutes of input.
     * At normal/slow frame rates all time is accumulated, including remainder.
     */
    if (elapsed_us > 250000) elapsed_us = 250000;
    pending_us += elapsed_us;
    while (pending_us >= VENTILAGON_STEP_US) {
        pending_us -= VENTILAGON_STEP_US;
        clock_us += VENTILAGON_STEP_US;
        last_turn = clock_us - clock_us % VENTILAGON_TURN_US;
        ventilagon_loop();
    }
}
int ventilagon_host_is_idle(void) { return active && ventilagon_is_idle(); }
const char *ventilagon_host_sending(void) {
    const char *line = NULL;
    if (initialized) xQueueReceive(queue_sending, &line, 0);
    return line;
}

const uint8_t *ventilagon_host_frame(void) {
    memset(frame, 0, sizeof(frame));
    if (!active) return frame;
    if (current_state == &credits_state) {
        /* text_loop2 draws on only the upper half, in the outer 16 LEDs.
         * Both physical arms paint the same visible columns each revolution.
         */
        for (int col = 64; col < 192; col++) {
            memset(draw0, 0, sizeof(draw0));
            credits_draw_column(col - 64);
            for (int led = 0; led < 16; led++)
                write_rgb(frame + (col * 54 + 38 + led) * 3, draw0[led]);
        }
        return frame;
    }
    uint32_t strips[6][48];
    for (int col = 0; col < 6; col++) board_draw_column(col, strips[col]);
    for (int col = 0; col < 256; col++) {
        /* The host indexes arm1's angle. display_tick writes the opposed
         * game column to that arm, and both arms have a six-LED hub gap.
         * Retain the rotor's integer division when converting drift to time.
         */
        int64_t phase = (int64_t)col * VENTILAGON_TURN_US / 256;
        int64_t drift = (int64_t)drift_pos * VENTILAGON_TURN_US / SUBDEGREES;
        int pos = ((drift + phase) * SUBDEGREES / VENTILAGON_TURN_US
                   + SUBDEGREES / 2) & SUBDEGREES_MASK;
        int sector = ((drift + phase) * 6 / VENTILAGON_TURN_US + 3) % 6;
        int ship_rows = display_ship_rows(pos);
        for (int row = 0; row < 48; row++) {
            uint32_t color = strips[sector][row];
            if (row >= ROW_SHIP && row < ROW_SHIP + ship_rows) color = SHIP_COLOR;
            write_rgb(frame + (col * 54 + row + 6) * 3, color);
        }
    }
    return frame;
}

#ifdef VENTILAGON_TEST
extern byte buffer[NUM_ROWS], first_row;
extern bool paused;
extern int section;
extern unsigned int last_column_drawn;
void ventilagon_test_play(int level) { new_level = level; change_state(&play_state); }
void ventilagon_test_empty(void) { memset(buffer, 0, NUM_ROWS); paused = true; }
void ventilagon_test_wall(int row, int value) { buffer[(first_row + row) % NUM_ROWS] = value; }
void ventilagon_test_state(int state) {
    State *states[] = {&resetting_state, &play_state, &gameover_state, &credits_state, &win_state};
    assert(state >= 0 && state < 5);
    change_state(states[state]);
}
int ventilagon_test_position(void) { return nave_pos; }
int ventilagon_test_row(int row) { return buffer[(first_row + row) % NUM_ROWS]; }
int ventilagon_test_section(void) { return section; }
int ventilagon_test_drift(void) { return drift_pos; }
void ventilagon_test_set_drift(int value) { drift_pos = value; }
void ventilagon_test_reference_frame(uint8_t *out) {
    /* Capture the original display/credits SPI outputs, frozen game state.
     * Force each column's write so comparison doesn't depend on held colors.
     */
    int64_t saved_clock = clock_us, saved_turn = last_turn, saved_drift = last_drift;
    int saved_queued = queued_steps;
    extern uint64_t creds_last_step;
    uint64_t saved_credits_step = creds_last_step;
    uint32_t saved_dma[107];
    memcpy(saved_dma, dma, sizeof(dma));
    memset(out, 0, VENTILAGON_FRAME_BYTES);
    capture = out;
    last_turn = 0;
    last_drift = VENTILAGON_TURN_US * 2;
    queued_steps = 0;
    creds_last_step = VENTILAGON_TURN_US * 2;
    for (int col = 0; col < 256; col++) {
        capture_column = col;
        clock_us = (int64_t)col * VENTILAGON_TURN_US / 256;
        if (current_state == &credits_state) {
            extern void text_loop2(int64_t now);
            /* floor(column * period / 256) can round into the previous
             * column in text_loop2; choose ceil for its integer column index.
             */
            clock_us = ((int64_t)col * VENTILAGON_TURN_US + 255) / 256;
            creds_last_step = clock_us;
            text_loop2(clock_us);
        } else {
            last_column_drawn = (unsigned int)-1;
            display_tick(clock_us);
        }
    }
    capture = NULL;
    clock_us = saved_clock; last_turn = saved_turn; last_drift = saved_drift;
    queued_steps = saved_queued;
    creds_last_step = saved_credits_step;
    memcpy(dma, saved_dma, sizeof(dma));
}
#endif
