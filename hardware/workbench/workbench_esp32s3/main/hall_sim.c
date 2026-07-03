#include "hall_sim.h"
#include "config.h"

#include "driver/gpio.h"
#include "esp_timer.h"
#include <stdbool.h>

static esp_timer_handle_t s_period_timer;
static esp_timer_handle_t s_pulse_end_timer;
static volatile int64_t s_last_turn_us;
static volatile int64_t s_rotation_period_us;
static volatile uint32_t s_rpm;
static volatile bool s_running;
static volatile uint32_t s_turn_count;

static void pulse_end_cb(void *arg) {
    gpio_set_level(WB_HALL_PIN, 1);
}

static void period_cb(void *arg) {
    s_last_turn_us = esp_timer_get_time();
    s_turn_count++;
    gpio_set_level(WB_HALL_PIN, 0);
    esp_timer_start_once(s_pulse_end_timer, WB_HALL_PULSE_WIDTH_US);
}

uint32_t hall_sim_turn_count(void) {
    return s_turn_count;
}

static void apply_rpm(uint32_t rpm) {
    if (esp_timer_is_active(s_period_timer)) {
        esp_timer_stop(s_period_timer);
    }

    s_rpm = rpm;
    if (rpm == 0) {
        s_running = false;
        gpio_set_level(WB_HALL_PIN, 1);
        return;
    }

    s_rotation_period_us = 60000000LL / rpm;
    s_last_turn_us = esp_timer_get_time();
    s_running = true;
    esp_timer_start_periodic(s_period_timer, s_rotation_period_us);
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

    apply_rpm(WB_HALL_RPM_DEFAULT);
}

void hall_sim_set_rpm(uint32_t rpm) {
    if (rpm > WB_HALL_RPM_MAX) {
        rpm = WB_HALL_RPM_MAX;
    }
    apply_rpm(rpm);
}

uint32_t hall_sim_get_rpm(void) {
    return s_rpm;
}

uint32_t hall_sim_current_column(void) {
    if (!s_running) {
        return 0;
    }
    int64_t now = esp_timer_get_time();
    int64_t elapsed = now - s_last_turn_us;
    if (elapsed < 0) {
        elapsed = 0;
    }
    return (uint32_t)((elapsed * WB_COLUMNS) / s_rotation_period_us) % WB_COLUMNS;
}
