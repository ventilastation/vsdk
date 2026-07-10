// Passive SPI-slave spy on the DUT's LED bus.
//
// The DUT's LED SPI master drives its configured led_cs pin (GPIO14 by
// default, wired to WB_SPI_CS_PIN), asserted low for each 444-byte burst. That CS
// frames the slave transactions: each queued receive completes on CS deassert
// with trans_len == BURST_BYTES. (An earlier "no chip-select / always
// selected" scheme did not work — the ESP32-S3 SPI slave needs CS edges to
// delimit transactions.)
//
// Each burst is a 444-byte APA102-style buffer built by
// hardware/rotor/modules/povdisplay/povdisplay.c:
//   [4-byte zero start frame]
//   [54 x 4-byte LED frame]   arm 0 (mirror column, LED order reversed)
//   [54 x 4-byte LED frame]   arm 1 (current column, direct order)
//   [8-byte end frame]
// where each LED frame is [brightness, B, G, R] (brightness is dropped).
//
// Real POV firmware (hardware/rotor/modules/povdisplay) only re-sends a
// burst when an LED's colour actually changes, relying on the physical LEDs
// to keep glowing their last-shifted-in colour as the rotor sweeps them
// through new angular positions in between. Ventilagon leans on this hard:
// it may emit as few as 9-10 bursts per revolution instead of one per
// column. So a burst's column can't be assigned by counting bursts (that
// assumes exactly one per column, in order) -- decode_task instead reads
// hall_sim_current_column() at capture time to get the actual column the
// burst landed on, and holds+repaints that colour forward through
// subsequent columns until a later burst supersedes it. See decode_task,
// hold_and_advance() and flush_hold().

#include "led_capture.h"
#include "config.h"
#include "hall_sim.h"

#include "driver/spi_slave.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "led_capture";

#define START_FRAME_BYTES 4
#define LED_FRAME_BYTES (WB_NUM_LEDS * 4)
#define END_FRAME_BYTES 8
#define BURST_BYTES (START_FRAME_BYTES + LED_FRAME_BYTES * 2 + END_FRAME_BYTES)  // 444
#define NUM_SLOTS 4

static uint8_t *s_rx_buf[NUM_SLOTS];
static spi_slave_transaction_t s_trans[NUM_SLOTS];

// capture_task (core 1) does nothing but SPI-slave plumbing: dequeue a
// completed DMA transaction, copy its raw bytes out, requeue immediately.
// Column bookkeeping and pixel decode used to happen inline in that same
// loop, but core 1 also had lwIP's TCPIP task (priority 18, "no affinity" by
// default) able to float onto it and preempt a mere-priority-10 capture_task
// whenever telemetry_task's TCP sends (or WiFi RX, mDNS, etc.) gave it work
// -- for long enough, occasionally, to miss the 4 pre-queued DMA slots and
// drop a burst. Pinning lwIP off core 1 (sdkconfig.defaults) addresses that
// directly, but moving everything not strictly SPI-related out of this task
// removes the rest of the doubt: core 1 now runs only this loop plus
// decode_task (also pinned here -- see led_capture_begin() for why it isn't
// on core 0), and whatever ISRs the SoC itself routes there.
#define CAPTURE_QUEUE_DEPTH 8

typedef struct {
    // Both captured at the moment the burst completes, not re-read later in
    // decode_task: hall_sim_turn_count()/hall_sim_current_column() must be
    // time-correlated with when the burst actually arrived, not with
    // whenever decode_task next gets scheduled to look at it (which, via a
    // queue, is decoupled from capture and would otherwise jitter with
    // decode_task's own scheduling latency instead of the DUT's real timing).
    uint32_t turn;
    uint32_t column;
    uint8_t raw[BURST_BYTES];
} capture_msg_t;

static QueueHandle_t s_capture_queue;

// Double-buffered instead of a single mutex-guarded frame: decode_task
// (via write_row(), on every burst it dequeues) writes into s_frame[s_write_buf];
// led_capture_snapshot() (telemetry_task, every WB_TELEMETRY_FRAME_INTERVAL_MS)
// reads s_frame[1 - s_write_buf]. decode_task flips s_write_buf once per
// revolution (see its turn-changed branch), so a snapshot's ~41KB memcpy
// never overlaps a write to the same buffer -- an earlier version shared a
// mutex between the two instead, which let telemetry's memcpy block
// whichever task served the SPI queue for its duration (worse, via priority
// inheritance, back when that was capture_task itself).
static uint8_t s_frame[2][WB_FRAME_BYTES];
static volatile uint8_t s_write_buf;

// One row (all WB_NUM_LEDS pixels, R,G,B each) -- contiguous, same layout as
// a column's slice of s_frame, so it can be memcpy'd straight in.
typedef uint8_t led_row_t[WB_NUM_LEDS][3];

static inline void write_row(uint32_t column, const led_row_t row) {
    memcpy(s_frame[s_write_buf] + column * WB_NUM_LEDS * 3, row, sizeof(led_row_t));
}

// Each 4-byte LED frame on the wire is [brightness(0xe0|b5), B, G, R].
// Pass the colour bytes through as-is; intensity correction is deferred.
static inline void put_pixel(uint8_t *out, const uint8_t *w) {
    out[0] = w[3]; // R
    out[1] = w[2]; // G
    out[2] = w[1]; // B
}

// Buffer layout from povdisplay.c init_buffers(): dma_pixels0 = dma_buffer+1
// (byte 4), dma_pixels1 = dma_buffer + PIXELS (byte 4 + (PIXELS-1)*4). The
// two arms deliberately share one word (arm0's last LED == arm1's first);
// computing arm1 as start+PIXELS*4 instead read one word past it -- into
// the 0xff end frame -- which showed as a white line on the outer LED.
static void extract_arm_rows(const uint8_t *buf, led_row_t arm0_row, led_row_t arm1_row) {
    const uint8_t *arm0 = buf + START_FRAME_BYTES;
    const uint8_t *arm1 = buf + START_FRAME_BYTES + (WB_NUM_LEDS - 1) * 4;

    for (int n = 0; n < WB_NUM_LEDS; n++) {
        put_pixel(arm0_row[WB_NUM_LEDS - 1 - n], arm0 + n * 4);
        put_pixel(arm1_row[n], arm1 + n * 4);
    }
}

// Paints `hold_row` into every column strictly between *last_unwrapped and
// new_unwrapped (exclusive/exclusive), then paints `new_row` at
// new_unwrapped itself and folds it into hold_row -- i.e. "whatever colour
// was active carries forward through the columns this burst skipped, and
// this burst's colour becomes what carries forward from here." Column
// indices are taken mod WB_COLUMNS, but the *_unwrapped counters themselves
// are not wrapped, so a caller can keep extending them across a pen's one
// wrap-around per revolution (see decode_task's arm0/mirror pen) without
// the comparisons here going backwards.
static void hold_and_advance(int32_t *last_unwrapped, uint32_t new_unwrapped,
                              led_row_t hold_row, const led_row_t new_row) {
    if ((int32_t)new_unwrapped < *last_unwrapped) {
        new_unwrapped = (uint32_t)*last_unwrapped;
    }
    for (int32_t u = *last_unwrapped + 1; u < (int32_t)new_unwrapped; u++) {
        write_row((uint32_t)u % WB_COLUMNS, hold_row);
    }
    write_row(new_unwrapped % WB_COLUMNS, new_row);
    memcpy(hold_row, new_row, sizeof(led_row_t));
    *last_unwrapped = (int32_t)new_unwrapped;
}

// Extends `hold_row` through the rest of the revolution (up to and
// including end_unwrapped), with no new burst to write -- used at
// turn-change to finish painting the buffer that's about to become the
// stable snapshot, since Ventilagon-style firmware may go the entire rest
// of a revolution without sending another burst.
static void flush_hold(int32_t *last_unwrapped, uint32_t end_unwrapped, const led_row_t hold_row) {
    for (int32_t u = *last_unwrapped + 1; u <= (int32_t)end_unwrapped; u++) {
        write_row((uint32_t)u % WB_COLUMNS, hold_row);
    }
    *last_unwrapped = (int32_t)end_unwrapped;
}

// Core 1: SPI-slave plumbing only. Dequeue a completed DMA transaction, copy
// its raw bytes out to the queue for decode_task, requeue immediately -- no
// column bookkeeping, no pixel decode, nothing that could take long enough
// to miss the next burst. xQueueSend uses a zero timeout: if decode_task
// somehow falls behind, we drop the message rather than ever block this loop.
static void capture_task(void *arg) {
    for (int i = 0; i < NUM_SLOTS; i++) {
        memset(&s_trans[i], 0, sizeof(s_trans[i]));
        s_trans[i].length = BURST_BYTES * 8;
        s_trans[i].rx_buffer = s_rx_buf[i];
        spi_slave_queue_trans(SPI2_HOST, &s_trans[i], portMAX_DELAY);
    }

    uint32_t good = 0, other = 0, drops = 0, last_len = 0;
    int64_t last_report = esp_timer_get_time();

    while (1) {
        spi_slave_transaction_t *done = NULL;
        if (spi_slave_get_trans_result(SPI2_HOST, &done, pdMS_TO_TICKS(1000)) == ESP_OK) {
            last_len = done->trans_len / 8;
            if (last_len == BURST_BYTES) {
                good++;
                capture_msg_t msg;
                msg.turn = hall_sim_turn_count();
                msg.column = hall_sim_current_column();
                memcpy(msg.raw, done->rx_buffer, BURST_BYTES);
                if (xQueueSend(s_capture_queue, &msg, 0) != pdTRUE) {
                    drops++;
                }
            } else {
                other++;
            }
            spi_slave_queue_trans(SPI2_HOST, done, portMAX_DELAY);
        }

        int64_t now = esp_timer_get_time();
        if (now - last_report >= 1000000) {
            ESP_LOGI(TAG, "bursts/s: good=%lu other=%lu drops=%lu last_len=%lu",
                     (unsigned long)good, (unsigned long)other, (unsigned long)drops, (unsigned long)last_len);
            good = 0; other = 0; drops = 0;
            last_report = now;
        }
    }
}

// Also core 1 (see led_capture_begin()), lower priority than capture_task.
// Everything that isn't strictly SPI plumbing: owns column bookkeeping and
// the actual pixel decode into s_frame.
//
// Each burst carries two rows -- arm0 (mirror column, LED order reversed)
// and arm1 (direct column) -- landing 180 degrees apart on the rotor. Each
// is tracked as its own independent "pen": last-known colour (arm0_row /
// arm1_row) plus how far it's painted so far this revolution
// (arm0_last_unwrapped / arm1_last_unwrapped, see hold_and_advance()). A
// pen's column only ever advances (or holds) as the revolution progresses;
// it never jumps backward within a turn, since msg.column comes from
// hall_sim_current_column() at capture time, which is monotonic within a
// revolution. arm0's target column is msg.column + WB_COLUMNS/2, which
// wraps exactly once per revolution -- tracking it unwrapped (never modulo
// until the actual s_frame write) keeps hold_and_advance()'s "did this pen
// move forward" check correct across that wrap.
static void decode_task(void *arg) {
    led_row_t arm0_row = {0};
    led_row_t arm1_row = {0};
    int32_t arm0_last_unwrapped = (int32_t)(WB_COLUMNS / 2) - 1;
    int32_t arm1_last_unwrapped = -1;
    uint32_t bursts_this_turn = 0, bursts_last_turn = 0;
    uint32_t last_turn = hall_sim_turn_count();
    int64_t last_report = esp_timer_get_time();
    capture_msg_t msg;

    while (1) {
        if (xQueueReceive(s_capture_queue, &msg, pdMS_TO_TICKS(1000)) == pdTRUE) {
            // Uses msg.turn (stamped by capture_task at capture time), not a
            // fresh hall_sim_turn_count() read here -- this task's own
            // scheduling latency is decoupled from when the burst actually
            // arrived, so re-reading the live counter here made almost every
            // dequeued message look like the start of a new revolution.
            if (msg.turn != last_turn) {
                last_turn = msg.turn;
                // A real burst-per-turn count, unlike the old "one burst per
                // column" assumption: Ventilagon-style firmware that only
                // sends a burst on colour change legitimately reports single
                // digits here -- that's not a dropped burst, it's compression.
                bursts_last_turn = bursts_this_turn;
                bursts_this_turn = 0;

                // Finish painting the buffer we're about to retire: extend
                // each pen's last colour through to the end of the
                // revolution, since with sparse bursts there may be no
                // further burst all the way to the next hall pulse.
                flush_hold(&arm1_last_unwrapped, WB_COLUMNS - 1, arm1_row);
                flush_hold(&arm0_last_unwrapped, WB_COLUMNS - 1 + WB_COLUMNS / 2, arm0_row);

                // The buffer we just finished now holds a complete
                // revolution and becomes the stable snapshot source; start
                // writing the new revolution into the other one.
                // led_capture_snapshot() always reads 1 - s_write_buf.
                s_write_buf ^= 1;
                arm1_last_unwrapped = -1;
                arm0_last_unwrapped = (int32_t)(WB_COLUMNS / 2) - 1;
            }

            led_row_t new_arm0_row, new_arm1_row;
            extract_arm_rows(msg.raw, new_arm0_row, new_arm1_row);

            hold_and_advance(&arm1_last_unwrapped, msg.column, arm1_row, new_arm1_row);
            hold_and_advance(&arm0_last_unwrapped, msg.column + WB_COLUMNS / 2, arm0_row, new_arm0_row);

            bursts_this_turn++;
        }

        int64_t now = esp_timer_get_time();
        if (now - last_report >= 1000000) {
            ESP_LOGI(TAG, "decode: bursts_last_turn=%lu", (unsigned long)bursts_last_turn);
            last_report = now;
        }
    }
}

void led_capture_begin(void) {
    s_write_buf = 0;
    memset(s_frame, 0, sizeof(s_frame));

    // WB_SPI_CS_PIN is wired to the DUT's configured LED-bus CS: the DUT master
    // now drives a real chip-select, asserting it low for each 444-byte burst,
    // which frames the slave transactions. Pull it up so it reads idle/
    // deasserted while the DUT isn't driving (e.g. before it boots).
    gpio_set_pull_mode(WB_SPI_CS_PIN, GPIO_PULLUP_ONLY);

    spi_bus_config_t buscfg = {
        .mosi_io_num = WB_SPI_MOSI_PIN,
        .miso_io_num = -1,
        .sclk_io_num = WB_SPI_SCLK_PIN,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
    };

    spi_slave_interface_config_t slvcfg = {
        .spics_io_num = WB_SPI_CS_PIN,
        .queue_size = NUM_SLOTS,
        .mode = 0,
    };

    ESP_ERROR_CHECK(spi_slave_initialize(SPI2_HOST, &buscfg, &slvcfg, SPI_DMA_CH_AUTO));

    for (int i = 0; i < NUM_SLOTS; i++) {
        s_rx_buf[i] = heap_caps_malloc(BURST_BYTES, MALLOC_CAP_DMA);
    }

    s_capture_queue = xQueueCreate(CAPTURE_QUEUE_DEPTH, sizeof(capture_msg_t));

    // Both on core 1: putting decode_task on core 0 alongside lwIP/WiFi
    // (priority 18/23) worked fine while telemetry_task was idle, but with
    // the emulator actually connected and streaming a ~41KB frame every
    // WB_TELEMETRY_FRAME_INTERVAL_MS, that's real sustained higher-priority
    // network activity that starved decode_task (priority 10) long enough to
    // overflow the queue. Core 1 has nothing on it that outranks either
    // task, so there's no equivalent starvation risk here. capture_task gets
    // a higher priority than decode_task so it always preempts it
    // immediately when a new SPI transaction completes, rather than the two
    // waiting on tick-based round-robin as they would at equal priority.
    xTaskCreatePinnedToCore(capture_task, "led_capture", 4096, NULL, 12, NULL, 1);
    xTaskCreatePinnedToCore(decode_task, "led_decode", 4096, NULL, 10, NULL, 1);
}

void led_capture_snapshot(uint8_t *out) {
    // Single-byte read of s_write_buf plus a memcpy from the *other* buffer,
    // no lock: decode_task never touches that buffer again until it flips
    // s_write_buf back to it a full revolution later (see decode_task),
    // which at any plausible RPM is far longer than this memcpy takes.
    uint8_t idx = 1 - s_write_buf;
    memcpy(out, s_frame[idx], sizeof(s_frame[idx]));
}
