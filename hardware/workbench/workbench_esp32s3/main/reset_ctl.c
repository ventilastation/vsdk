#include "reset_ctl.h"
#include "config.h"

#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void reset_ctl_begin(void) {
    // Hi-Z: never drive the line high ourselves, let the DUT's own pull-up do it.
    gpio_reset_pin(WB_RESET_PIN);
    gpio_set_direction(WB_RESET_PIN, GPIO_MODE_INPUT);
}

void reset_ctl_pulse(uint32_t low_ms) {
    gpio_set_direction(WB_RESET_PIN, GPIO_MODE_OUTPUT);
    gpio_set_level(WB_RESET_PIN, 0);
    vTaskDelay(pdMS_TO_TICKS(low_ms));
    gpio_set_direction(WB_RESET_PIN, GPIO_MODE_INPUT);
}
