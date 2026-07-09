The Ventilastation workbench is a second ESP32-S3 board used to test a real
rotor board (the "DUT") as close to normal spinning operation as possible:
it resets the DUT, feeds it a simulated 600 RPM hall pulse, spies on its LED
SPI bus and re-streams the decoded frames to the desktop `vsdk/emulator`
over Wi-Fi, and bridges the DUT's UART to the workbench's USB port.

Firmware: [`workbench_esp32s3/`](workbench_esp32s3/).

Full design notes, pin connections, and the LED-bus wire protocol are in
[`../../docs/internals/workbench.md`](../../docs/internals/workbench.md).
