#pragma once

// Brings up the hardware UART wired to the DUT's TX/RX pins, installs a
// driver on the console UART too, and starts a background task that copies
// bytes both ways between them. A 0xD3-prefixed host command is handled
// locally by the workbench for deterministic USB-only hardware testing; see
// serial_bridge.c and docs/internals/workbench.md.
void serial_bridge_begin(void);
