// Passive SPI-slave spy on the DUT's LED bus.
//
// The DUT's LED SPI master drives a real chip-select (GPIO17 -> WB_SPI_CS_PIN,
// GPIO14 on the workbench), asserted low for each 444-byte burst. That CS
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
#include "freertos/semphr.h"
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
static uint8_t s_frame[WB_FRAME_BYTES];
static SemaphoreHandle_t s_frame_mutex;

static inline uint8_t *frame_pixel(uint32_t column, uint32_t led) {
    return s_frame + (column * WB_NUM_LEDS + led) * 3;
}

// Each 4-byte LED frame on the wire is [brightness(0xe0|b5), B, G, R].
// Pass the colour bytes through as-is; intensity correction is deferred.
static inline void put_pixel(uint8_t *out, const uint8_t *w) {
    out[0] = w[3]; // R
    out[1] = w[2]; // G
    out[2] = w[1]; // B
}

static void decode_burst(const uint8_t *buf, uint32_t column) {
    uint32_t mirror_column = (column + WB_COLUMNS / 2) % WB_COLUMNS;

    // Buffer layout from povdisplay.c init_buffers(): dma_pixels0 = dma_buffer+1
    // (byte 4), dma_pixels1 = dma_buffer + PIXELS (byte 4 + (PIXELS-1)*4). The
    // two arms deliberately share one word (arm0's last LED == arm1's first);
    // computing arm1 as start+PIXELS*4 instead read one word past it -- into
    // the 0xff end frame -- which showed as a white line on the outer LED.
    const uint8_t *arm0 = buf + START_FRAME_BYTES;
    const uint8_t *arm1 = buf + START_FRAME_BYTES + (WB_NUM_LEDS - 1) * 4;

    xSemaphoreTake(s_frame_mutex, portMAX_DELAY);
    for (int n = 0; n < WB_NUM_LEDS; n++) {
        put_pixel(frame_pixel(mirror_column, WB_NUM_LEDS - 1 - n), arm0 + n * 4);
        put_pixel(frame_pixel(column, n), arm1 + n * 4);
    }
    xSemaphoreGive(s_frame_mutex);
}

static void capture_task(void *arg) {
    for (int i = 0; i < NUM_SLOTS; i++) {
        memset(&s_trans[i], 0, sizeof(s_trans[i]));
        s_trans[i].length = BURST_BYTES * 8;
        s_trans[i].rx_buffer = s_rx_buf[i];
        spi_slave_queue_trans(SPI2_HOST, &s_trans[i], portMAX_DELAY);
    }

    uint32_t good = 0, other = 0, last_len = 0;
    uint32_t column = 0;
    uint32_t last_turn = hall_sim_turn_count();
    int64_t last_report = esp_timer_get_time();

    while (1) {
        spi_slave_transaction_t *done = NULL;
        if (spi_slave_get_trans_result(SPI2_HOST, &done, pdMS_TO_TICKS(1000)) == ESP_OK) {
            last_len = done->trans_len / 8;
            if (last_len == BURST_BYTES) {
                good++;
                // The DUT emits exactly one burst per column, in order, starting
                // at column 0 after each hall pulse. Assign columns by counting
                // bursts and resetting each simulated revolution, rather than
                // recomputing from a clock at decode time (that jitters with
                // scheduling latency and makes the image unstable).
                uint32_t turn = hall_sim_turn_count();
                if (turn != last_turn) {
                    last_turn = turn;
                    column = 0;
                }
                decode_burst((const uint8_t *)done->rx_buffer, column);
                column = (column + 1) % WB_COLUMNS;
            } else {
                other++;
            }
            spi_slave_queue_trans(SPI2_HOST, done, portMAX_DELAY);
        }

        int64_t now = esp_timer_get_time();
        if (now - last_report >= 1000000) {
            ESP_LOGI(TAG, "bursts/s: good=%lu other=%lu last_len=%lu",
                     (unsigned long)good, (unsigned long)other, (unsigned long)last_len);
            good = 0; other = 0;
            last_report = now;
        }
    }
}

void led_capture_begin(void) {
    s_frame_mutex = xSemaphoreCreateMutex();
    memset(s_frame, 0, sizeof(s_frame));

    // WB_SPI_CS_PIN is wired to the DUT's LED-bus CS (GPIO17): the DUT master
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

    xTaskCreatePinnedToCore(capture_task, "led_capture", 4096, NULL, 10, NULL, 1);
}

void led_capture_snapshot(uint8_t *out) {
    xSemaphoreTake(s_frame_mutex, portMAX_DELAY);
    memcpy(out, s_frame, sizeof(s_frame));
    xSemaphoreGive(s_frame_mutex);
}
