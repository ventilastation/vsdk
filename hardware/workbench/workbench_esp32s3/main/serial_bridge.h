#pragma once

// Brings up the hardware UART wired to the DUT's TX/RX pins, installs a
// driver on the console UART too, and starts a background task that
// copies bytes both ways between them (see docs/internals/workbench.md "UART bridge").
void serial_bridge_begin(void);
