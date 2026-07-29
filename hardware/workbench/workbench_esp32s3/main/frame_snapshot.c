#include "frame_snapshot.h"

#include "config.h"
#include "led_capture.h"

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static uint8_t s_frame_buf[WB_FRAME_BYTES];
static SemaphoreHandle_t s_frame_mutex;

void frame_snapshot_begin(void) {
    s_frame_mutex = xSemaphoreCreateMutex();
}

const uint8_t *frame_snapshot_acquire(void) {
    xSemaphoreTake(s_frame_mutex, portMAX_DELAY);
    led_capture_snapshot(s_frame_buf);
    return s_frame_buf;
}

void frame_snapshot_release(void) {
    xSemaphoreGive(s_frame_mutex);
}
