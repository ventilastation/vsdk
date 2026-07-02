// Bridges the DUT's UART to the workbench's own USB-connected console
// UART, so a PC can watch and inject the same traffic the DUT would
// normally exchange with a neighboring rotor/base unit (see
// vsdk/apps/micropython/ventilastation/serialcomms.py).
//
// Diagnostic ESP_LOGx lines from this firmware share the same physical
// port (they still work: we install the driver with uart_vfs_dev_use_driver()
// so stdio keeps flowing through it), so raw DUT bytes and our own log
// lines are interleaved on that port. See WORKBENCH.md.

#include "serial_bridge.h"
#include "config.h"

#include "driver/uart.h"
#include "driver/uart_vfs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define DUT_UART_PORT UART_NUM_1
#define HOST_UART_PORT UART_NUM_0
#define BRIDGE_BUF_SIZE 256
#define UART_RING_BUF_SIZE (BRIDGE_BUF_SIZE * 4)

static void bridge_task(void *arg) {
    uint8_t buf[BRIDGE_BUF_SIZE];

    while (1) {
        int n = uart_read_bytes(DUT_UART_PORT, buf, sizeof(buf), pdMS_TO_TICKS(10));
        if (n > 0) {
            uart_write_bytes(HOST_UART_PORT, (const char *)buf, n);
        }

        n = uart_read_bytes(HOST_UART_PORT, buf, sizeof(buf), 0);
        if (n > 0) {
            uart_write_bytes(DUT_UART_PORT, (const char *)buf, n);
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

    // Take over the console UART with a real driver so we can read bytes
    // typed at the workbench's USB port, while keeping printf/ESP_LOGx
    // working through the same port via the VFS driver hookup.
    ESP_ERROR_CHECK(uart_driver_install(HOST_UART_PORT, UART_RING_BUF_SIZE, UART_RING_BUF_SIZE, 0, NULL, 0));
    uart_vfs_dev_use_driver(HOST_UART_PORT);

    xTaskCreate(bridge_task, "serial_bridge", 3072, NULL, 8, NULL);
}
