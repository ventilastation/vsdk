#pragma once

// Workbench pin assignments and tunables.
// See ../../../WORKBENCH.md for the full pinout table and design rationale.
//
// These are all *workbench-side* GPIOs, chosen to avoid ESP32-S3 strapping
// pins (0, 3, 45, 46), the native USB pins (19, 20), and the octal-PSRAM
// pins used on N16R8-style modules (35-37). Change freely to match
// whatever dev board is on hand.

// ---- DUT reset (EN) ----
#define WB_RESET_PIN        5   // -> DUT EN/reset. Open-drain style: LOW to assert, INPUT to release.
#define WB_RESET_PULSE_MS   150

// ---- Hall sensor simulation ----
#define WB_HALL_PIN             4     // -> DUT hall_gpio
#define WB_HALL_RPM             600
#define WB_HALL_PULSE_WIDTH_US  1000  // low-pulse width per simulated revolution

// ---- LED SPI bus capture (workbench acts as SPI slave, input only) ----
#define WB_SPI_SCLK_PIN  12  // <- DUT led_clk
#define WB_SPI_MOSI_PIN  13  // <- DUT led_mosi
#define WB_SPI_CS_PIN    14  // internal only: NOT wired to the DUT, held low via pull-down

#define WB_NUM_LEDS   54     // must match PIXELS in hardware/rotor/modules/povdisplay/gpu.c
#define WB_COLUMNS    256
#define WB_FRAME_BYTES (WB_COLUMNS * WB_NUM_LEDS * 3)

// ---- DUT UART bridge ----
#define WB_UART_TX_PIN  17   // -> DUT serial_rx
#define WB_UART_RX_PIN  18   // <- DUT serial_tx
#define WB_UART_BAUD    115200

// ---- Wi-Fi telemetry link (pyglet emulator) ----
#define WB_WIFI_AP_SSID                 "ventilastation-workbench"
#define WB_WIFI_AP_PASSWORD             "workbench123"
#define WB_TELEMETRY_PORT               5005
#define WB_TELEMETRY_FRAME_INTERVAL_MS  33
