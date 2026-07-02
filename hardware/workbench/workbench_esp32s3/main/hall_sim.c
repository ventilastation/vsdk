#include "hall_sim.h"
#include "config.h"

#include "driver/gpio.h"
#include "esp_timer.h"

static const int64_t kRotationPeriodUs = 60000000LL / WB_HALL_RPM;

static esp_timer_handle_t s_period_timer;
static esp_timer_handle_t s_pulse_end_timer;
static volatile int64_t s_last_turn_us;

static void pulse_end_cb(void *arg) {
    gpio_set_level(WB_HALL_PIN, 1);
}

static void period_cb(void *arg) {
    s_last_turn_us = esp_timer_get_time();
    gpio_set_level(WB_HALL_PIN, 0);
    esp_timer_start_once(s_pulse_end_timer, WB_HALL_PULSE_WIDTH_US);
}

void hall_sim_begin(void) {
    gpio_reset_pin(WB_HALL_PIN);
    gpio_set_direction(WB_HALL_PIN, GPIO_MODE_OUTPUT);
    gpio_set_level(WB_HALL_PIN, 1);

    const esp_timer_create_args_t pulse_args = {
        .callback = &pulse_end_cb,
        .name = "hall_pulse_end",
    };
    esp_timer_create(&pulse_args, &s_pulse_end_timer);

    const esp_timer_create_args_t period_args = {
        .callback = &period_cb,
        .name = "hall_period",
    };
    esp_timer_create(&period_args, &s_period_timer);

    s_last_turn_us = esp_timer_get_time();
    esp_timer_start_periodic(s_period_timer, kRotationPeriodUs);
}

uint32_t hall_sim_current_column(void) {
    int64_t now = esp_timer_get_time();
    int64_t elapsed = now - s_last_turn_us;
    if (elapsed < 0) {
        elapsed = 0;
    }
    return (uint32_t)((elapsed * WB_COLUMNS) / kRotationPeriodUs) % WB_COLUMNS;
}
