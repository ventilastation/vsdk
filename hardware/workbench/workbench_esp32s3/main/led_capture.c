// Passive SPI-slave spy on the DUT's LED bus.
//
// The DUT drives this bus with no chip-select (see WORKBENCH.md), so the
// slave peripheral here is configured "always selected" (CS pin tied low
// via an internal pull-down, not wired to the DUT at all) and relies on
// each queued transaction's fixed length to bound a burst. This is the
// part of the design most likely to need hardware bring-up — see
// WORKBENCH.md's "LED bus capture (no chip-select)" section for the
// fallback plan if it doesn't sync reliably in practice.
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
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <string.h>

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

static void decode_burst(const uint8_t *buf) {
    uint32_t column = hall_sim_current_column();
    uint32_t mirror_column = (column + WB_COLUMNS / 2) % WB_COLUMNS;

    const uint8_t *arm0 = buf + START_FRAME_BYTES;                  // dma_pixels0
    const uint8_t *arm1 = buf + START_FRAME_BYTES + LED_FRAME_BYTES; // dma_pixels1

    xSemaphoreTake(s_frame_mutex, portMAX_DELAY);
    for (int n = 0; n < WB_NUM_LEDS; n++) {
        // word layout on the wire: [brightness, B, G, R]
        const uint8_t *w0 = arm0 + n * 4;
        uint8_t *out0 = frame_pixel(mirror_column, WB_NUM_LEDS - 1 - n);
        out0[0] = w0[3];  // R
        out0[1] = w0[2];  // G
        out0[2] = w0[1];  // B

        const uint8_t *w1 = arm1 + n * 4;
        uint8_t *out1 = frame_pixel(column, n);
        out1[0] = w1[3];
        out1[1] = w1[2];
        out1[2] = w1[1];
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

    while (1) {
        spi_slave_transaction_t *done = NULL;
        if (spi_slave_get_trans_result(SPI2_HOST, &done, portMAX_DELAY) == ESP_OK) {
            if (done->trans_len / 8 == BURST_BYTES) {
                decode_burst((const uint8_t *)done->rx_buffer);
            }
            spi_slave_queue_trans(SPI2_HOST, done, portMAX_DELAY);
        }
    }
}

void led_capture_begin(void) {
    s_frame_mutex = xSemaphoreCreateMutex();
    memset(s_frame, 0, sizeof(s_frame));

    // Not wired to the DUT: pulled low so the slave peripheral is always
    // "selected", since this bus has no real chip-select line.
    gpio_reset_pin(WB_SPI_CS_PIN);
    gpio_set_direction(WB_SPI_CS_PIN, GPIO_MODE_INPUT);
    gpio_set_pull_mode(WB_SPI_CS_PIN, GPIO_PULLDOWN_ONLY);

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
