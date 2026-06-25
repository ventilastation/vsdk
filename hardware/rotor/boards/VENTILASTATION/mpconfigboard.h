#ifndef MICROPY_HW_BOARD_NAME
#define MICROPY_HW_BOARD_NAME               "Ventilastation"
#endif
#define MICROPY_HW_MCU_NAME                 "ESP32S3"

// Use the built-in USB Serial/JTAG link for REPL so flashing and filesystem
// deployment happen over the same cable on Ventilastation hardware.
#define MICROPY_HW_ENABLE_USBDEV            (0)
#define MICROPY_HW_ENABLE_UART_REPL         (0)

#define MICROPY_HW_I2C0_SCL                 (9)
#define MICROPY_HW_I2C0_SDA                 (8)
