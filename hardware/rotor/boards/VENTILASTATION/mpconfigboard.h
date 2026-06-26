#ifndef MICROPY_HW_BOARD_NAME
#define MICROPY_HW_BOARD_NAME               "Ventilastation"
#endif
#define MICROPY_HW_MCU_NAME                 "ESP32S3"

// UART REPL on UART0 (port 1, USB-UART bridge - always connected, survives resets).
// USB Serial/JTAG REPL on port 2 is also active automatically when USB_CDC=0.
// IDF primary console stays on UART0 (see sdkconfig.board) so boot messages
// appear on port 1 and the USB JTAG FIFO stays empty at boot, avoiding the
// terminal_connected=false race in usb_serial_jtag_tx_strn().
#define MICROPY_HW_ENABLE_USBDEV            (0)
#define MICROPY_HW_ENABLE_UART_REPL         (1)

#define MICROPY_HW_I2C0_SCL                 (9)
#define MICROPY_HW_I2C0_SDA                 (8)
