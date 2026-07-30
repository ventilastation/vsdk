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
#include "frame_snapshot.h"
#include "hall_sim.h"

#include "driver/uart.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

// Bytes sent by the emulator/button protocol are seven-bit values. 0xD3 is
// therefore an unambiguous escape into a small command channel that is
// consumed by the workbench and never forwarded to the DUT:
//
//   0xD3 "rpm <n>\n" -> "wb_ok rpm=<clamped-n>\n"
//   0xD3 "capture\n" -> "wb_frame <bytes> <crc32>\n" + raw frame bytes
//
// A CRC covers the binary payload so a host test cannot accidentally accept
// a truncated or interleaved capture as a rendering result.
#define WB_USB_CONTROL_ESCAPE 0xD3
#define WB_USB_COMMAND_BYTES 48
#define WB_USB_WRITE_CHUNK_BYTES 512

static bool usb_write_all(const void *data, size_t len) {
    const uint8_t *cursor = data;
    int64_t deadline_us = esp_timer_get_time() + 3000000;
    while (len > 0 && esp_timer_get_time() < deadline_us) {
        size_t chunk = len > WB_USB_WRITE_CHUNK_BYTES ? WB_USB_WRITE_CHUNK_BYTES : len;
        int written = usb_serial_jtag_write_bytes(cursor, chunk, pdMS_TO_TICKS(100));
        if (written > 0) {
            cursor += written;
            len -= (size_t)written;
        }
    }
    return len == 0;
}

static uint32_t crc32_bytes(const uint8_t *data, size_t len) {
    uint32_t crc = 0xffffffffU;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1) ^ (0xedb88320U & mask);
        }
    }
    return ~crc;
}

static void usb_reply_line(const char *line) {
    usb_write_all(line, strlen(line));
}

static void handle_workbench_command(char *command) {
    if (strncmp(command, "rpm ", 4) == 0) {
        char *end = NULL;
        long rpm = strtol(command + 4, &end, 10);
        if (end == command + 4 || *end != '\0' || rpm < 0) {
            usb_reply_line("wb_error invalid_rpm\n");
            return;
        }
        hall_sim_set_rpm((uint32_t)rpm);
        char response[40];
        snprintf(response, sizeof(response), "wb_ok rpm=%lu\n",
                 (unsigned long)hall_sim_get_rpm());
        usb_reply_line(response);
        return;
    }

    if (strcmp(command, "capture") == 0) {
        const uint8_t *frame = frame_snapshot_acquire();
        uint32_t crc = crc32_bytes(frame, WB_FRAME_BYTES);
        char header[48];
        snprintf(header, sizeof(header), "wb_frame %u %08lx\n",
                 (unsigned)WB_FRAME_BYTES, (unsigned long)crc);

        // Stop diagnostics from entering the USB transmit ring between the
        // framing line and binary payload. DUT UART forwarding also pauses
        // because this command executes synchronously in bridge_task.
        esp_log_level_t old_level = esp_log_level_get("*");
        esp_log_level_set("*", ESP_LOG_NONE);
        bool ok = usb_write_all(header, strlen(header));
        if (ok) {
            ok = usb_write_all(frame, WB_FRAME_BYTES);
        }
        usb_serial_jtag_wait_tx_done(pdMS_TO_TICKS(3000));
        esp_log_level_set("*", old_level);
        frame_snapshot_release();
        if (!ok) {
            usb_reply_line("wb_error capture_timeout\n");
        }
        return;
    }

    usb_reply_line("wb_error unknown_command\n");
}

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

// A byte that's part of a still-possible RESYNC match can't be forwarded
// immediately -- unlike input_parser.py's equivalent tracking on the DUT
// side, which can freely feed a not-yet-disproven byte through its own
// internal state machine because that's reversible (an abandoned partial
// command just gets discarded from a buffer), forwarding to the DUT's UART
// is a real, external, irreversible side effect. So a byte matching
// RESYNC_SEQUENCE[candidate_len] has to sit in `candidate` until something
// either completes the match (and it's correctly discarded, per this
// function's whole purpose) or disproves it (and it's flushed to the DUT
// exactly as received).
//
// RESYNC_SEQUENCE starts with '\n' -- the same byte that terminates every
// ordinary text command this bridge carries ("exit\n", "reset\n",
// "rpm <n>\n") -- so that disproving byte is not guaranteed to arrive
// promptly: if the command's trailing '\n' is the last byte in its USB
// write and nothing else arrives on this link for a while, the DUT's
// command parser (which needs to see that '\n' before it'll act at all)
// just doesn't -- until whatever byte arrives next, e.g. the *next*
// button/joystick event, incidentally disproves the stale match and
// flushes it. That's exactly what caused the reported "ESC needs pressing
// twice" bug: the first "exit\n"'s terminator sat here until the second
// "exit\n" attempt's leading 'e' flushed it.
//
// flush_stale_candidate(), called from bridge_task()'s loop, bounds this:
// a genuine RESYNC burst is one atomic write from a well-behaved prober and
// completes over USB in far less than CANDIDATE_FLUSH_TIMEOUT_US regardless
// of baud rate, so the timeout can't misidentify a real resync attempt as
// stale traffic.
static uint8_t s_candidate[sizeof(RESYNC_SEQUENCE)];
static size_t s_candidate_len;
static int64_t s_candidate_started_us;
static char s_workbench_command[WB_USB_COMMAND_BYTES];
static size_t s_workbench_command_len;
static bool s_in_workbench_command;
static bool s_workbench_command_overflow;

#define CANDIDATE_FLUSH_TIMEOUT_US 5000

static void flush_stale_candidate(void) {
    if (s_candidate_len > 0 && esp_timer_get_time() - s_candidate_started_us > CANDIDATE_FLUSH_TIMEOUT_US) {
        forward_to_dut(s_candidate, s_candidate_len);
        s_candidate_len = 0;
    }
}

static void handle_host_bytes(const uint8_t *buf, size_t len) {
    for (size_t i = 0; i < len; i++) {
        uint8_t byte = buf[i];

        if (s_in_workbench_command) {
            if (byte == '\n') {
                if (s_workbench_command_len > 0 &&
                    s_workbench_command[s_workbench_command_len - 1] == '\r') {
                    s_workbench_command_len--;
                }
                s_workbench_command[s_workbench_command_len] = '\0';
                if (s_workbench_command_overflow) {
                    usb_reply_line("wb_error command_too_long\n");
                } else {
                    handle_workbench_command(s_workbench_command);
                }
                s_in_workbench_command = false;
                s_workbench_command_len = 0;
                s_workbench_command_overflow = false;
            } else if (!s_workbench_command_overflow) {
                if (s_workbench_command_len + 1 < sizeof(s_workbench_command)) {
                    s_workbench_command[s_workbench_command_len++] = (char)byte;
                } else {
                    s_workbench_command_overflow = true;
                }
            }
            continue;
        }

        if (byte == WB_USB_CONTROL_ESCAPE) {
            forward_to_dut(s_candidate, s_candidate_len);
            s_candidate_len = 0;
            s_in_workbench_command = true;
            s_workbench_command_len = 0;
            s_workbench_command_overflow = false;
            continue;
        }

        if (byte == RESYNC_SEQUENCE[s_candidate_len]) {
            if (s_candidate_len == 0) {
                s_candidate_started_us = esp_timer_get_time();
            }
            s_candidate[s_candidate_len++] = byte;
            if (s_candidate_len == sizeof(RESYNC_SEQUENCE)) {
                // esp_restart() never returns in practice (immediate
                // reboot); resetting candidate_len first is just defensive
                // in case that assumption ever changes, matching the same
                // precaution in vs_host_bridge.c.
                s_candidate_len = 0;
                esp_restart(); // identification banner is printed on next boot
            }
            continue;
        }

        forward_to_dut(s_candidate, s_candidate_len);
        s_candidate_len = 0;
        if (byte == RESYNC_SEQUENCE[0]) {
            s_candidate[s_candidate_len++] = byte;
            s_candidate_started_us = esp_timer_get_time();
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

        // Bounds how long a partial RESYNC match (see handle_host_bytes())
        // can withhold bytes from the DUT when nothing further arrives to
        // confirm or disprove it -- also covers the case where this whole
        // iteration's usb_serial_jtag_read_bytes() returned nothing at all.
        flush_stale_candidate();
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
