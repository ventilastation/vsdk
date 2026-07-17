// Bridges the DUT's UART to the workbench's USB port, so the PC running the
// emulator can exchange the same traffic the DUT would normally swap with a
// neighbouring rotor/base unit over UART (button state in, sound/music
// requests out -- see vsdk/apps/micropython/ventilastation/serialcomms.py and
// the emulator's workbench_conn in vsdk/emulator/comms.py).
//
// The "host" side is the ESP32-S3 *native USB-Serial-JTAG* -- the interface
// the PC actually opens as /dev/ttyACM* (Linux) or /dev/cu.usbmodem* (macOS).
// It is NOT UART0 (GPIO43/44): an earlier version bridged to UART_NUM_0, whose
// pins go to a header that isn't connected over USB, so button/sound bytes
// never reached the PC. The console is set to USB-Serial-JTAG in
// sdkconfig.defaults; we install its driver and route stdio through it, so
// diagnostic ESP_LOGx lines stay visible on the same port, interleaved with
// the raw bridge bytes. See docs/internals/workbench.md.

#include "serial_bridge.h"
#include "config.h"

#include "driver/uart.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define DUT_UART_PORT UART_NUM_1
#define BRIDGE_BUF_SIZE 256
#define UART_RING_BUF_SIZE (BRIDGE_BUF_SIZE * 4)

// WB_GIT_HASH is defined by CMakeLists.txt from ESP-IDF's own PROJECT_VER
// (git-describe-based); this fallback only applies to a build that doesn't
// define it.
#ifndef WB_GIT_HASH
#define WB_GIT_HASH "unknown"
#endif
#define WB_VERSION "v1.0"

// RESYNC / device identification (see
// docs/internals/input-protocol-v2.md#resync--device-identification).
// Replaces the older VSDK_BOARD_PROBE literal-match probe: RESYNC is
// recognized by all three Ventilastation devices the same way, not just the
// workbench, and works even when whatever's on the other end is wedged.
static const uint8_t RESYNC_SEQUENCE[] = { '\n', '\n', 0xD2, 'E', 'S', 'Y', 'N', 'C', '\n' };

static void forward_to_dut(const uint8_t *buf, size_t len) {
    if (len > 0) {
        uart_write_bytes(DUT_UART_PORT, (const char *)buf, len);
    }
}

// Keep the RESYNC marker out of the DUT UART. All other bytes remain
// byte-for-byte transparent for the emulator's normal bridge traffic -- a
// partial/failed match is replayed to the DUT exactly as received, so this
// never eats bytes the DUT was supposed to see.
static void handle_host_bytes(const uint8_t *buf, size_t len) {
    static uint8_t candidate[sizeof(RESYNC_SEQUENCE)];
    static size_t candidate_len;

    for (size_t i = 0; i < len; i++) {
        uint8_t byte = buf[i];
        if (byte == RESYNC_SEQUENCE[candidate_len]) {
            candidate[candidate_len++] = byte;
            if (candidate_len == sizeof(RESYNC_SEQUENCE)) {
                // esp_restart() never returns in practice (immediate
                // reboot); resetting candidate_len first is just defensive
                // in case that assumption ever changes, matching the same
                // precaution in vs_host_bridge.c.
                candidate_len = 0;
                esp_restart(); // identification banner is printed on next boot
            }
            continue;
        }

        forward_to_dut(candidate, candidate_len);
        candidate_len = 0;
        if (byte == RESYNC_SEQUENCE[0]) {
            candidate[candidate_len++] = byte;
        } else {
            forward_to_dut(&byte, 1);
        }
    }
}

static void bridge_task(void *arg) {
    uint8_t buf[BRIDGE_BUF_SIZE];

    while (1) {
        // DUT -> PC: forward the DUT's UART TX out over USB-Serial-JTAG.
        int n = uart_read_bytes(DUT_UART_PORT, buf, sizeof(buf), pdMS_TO_TICKS(10));
        if (n > 0) {
            // Bounded timeout so a disconnected/idle PC can't stall the bridge.
            usb_serial_jtag_write_bytes(buf, n, pdMS_TO_TICKS(20));
        }

        // PC -> DUT: forward bytes the emulator writes to our USB into the
        // DUT's UART RX (button state, etc.).
        n = usb_serial_jtag_read_bytes(buf, sizeof(buf), 0);
        if (n > 0) {
            handle_host_bytes(buf, n);
        }
    }
}

void serial_bridge_begin(void) {
    const uart_config_t dut_cfg = {
        .baud_rate = WB_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(DUT_UART_PORT, UART_RING_BUF_SIZE, UART_RING_BUF_SIZE, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(DUT_UART_PORT, &dut_cfg));
    ESP_ERROR_CHECK(uart_set_pin(DUT_UART_PORT, WB_UART_TX_PIN, WB_UART_RX_PIN,
                                  UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    // Bring up the native USB-Serial-JTAG driver for the host side and route
    // stdio through it so ESP_LOGx keeps flowing to the PC's serial console
    // while the same USB endpoint also carries raw DUT bridge bytes.
    if (!usb_serial_jtag_is_driver_installed()) {
        usb_serial_jtag_driver_config_t usj_cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
        usj_cfg.tx_buffer_size = UART_RING_BUF_SIZE;
        usj_cfg.rx_buffer_size = UART_RING_BUF_SIZE;
        ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usj_cfg));
    }
    usb_serial_jtag_vfs_use_driver();

    // RESYNC identification banner (see
    // docs/internals/input-protocol-v2.md#resync--device-identification):
    // the first thing this board puts on the wire, raw -- not routed through
    // ESP_LOGx, whose prefix/timestamp would make the line unrecognizable to
    // a RESYNC prober.
    static const char banner[] = "VENTILASTATION WORKBENCH " WB_VERSION " " WB_GIT_HASH "\n";
    usb_serial_jtag_write_bytes(banner, sizeof(banner) - 1, pdMS_TO_TICKS(20));

    // Core 1 is reserved for led_capture.c's tasks (SPI-slave capture +
    // decode); keep everything else, including this bridge, on core 0.
    xTaskCreatePinnedToCore(bridge_task, "serial_bridge", 3072, NULL, 8, NULL, 0);
}
