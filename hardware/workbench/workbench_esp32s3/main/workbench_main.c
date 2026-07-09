// Ventilastation hardware workbench firmware.
//
// Runs on a second ESP32-S3, wired to a real Ventilastation rotor board
// (the "DUT") to exercise it as close to normal spinning operation as
// possible: resets the DUT, feeds it a simulated 600 RPM hall pulse, spies
// on its LED SPI bus and re-streams the decoded frames to the desktop
// vsdk/emulator over Wi-Fi, and bridges the DUT's UART to this board's USB
// port.
//
// See ../../docs/internals/workbench.md for the full design, pinout, and known risks.
// The DUT's firmware is not modified in any way.

#include "config.h"
#include "reset_ctl.h"
#include "hall_sim.h"
#include "led_capture.h"
#include "serial_bridge.h"
#include "telemetry.h"

#include "esp_log.h"

static const char *TAG = "workbench";

void app_main(void) {
    ESP_LOGI(TAG, "Ventilastation workbench starting");

    reset_ctl_begin();
    serial_bridge_begin();
    led_capture_begin();
    telemetry_begin();

    ESP_LOGI(TAG, "pulsing DUT reset");
    reset_ctl_pulse(WB_RESET_PULSE_MS);

    ESP_LOGI(TAG, "starting hall pulse simulation at %d RPM", WB_HALL_RPM_DEFAULT);
    hall_sim_begin();
}
