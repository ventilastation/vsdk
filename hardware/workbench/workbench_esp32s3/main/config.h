#pragma once

// Workbench pin assignments and tunables.
// See ../../../docs/internals/workbench.md for the full pinout table and design rationale.
//
// These are all *workbench-side* GPIOs, chosen to avoid ESP32-S3 strapping
// pins (0, 3, 45, 46), the native USB pins (19, 20), and the octal-PSRAM
// pins used on N16R8-style modules (35-37). Change freely to match
// whatever dev board is on hand.

// ---- DUT reset (EN) ----
#define WB_RESET_PIN        4   // -> DUT EN/reset. Open-drain style: LOW to assert, INPUT to release.
#define WB_RESET_PULSE_MS   150

// ---- Hall sensor simulation ----
#define WB_HALL_PIN             7     // -> DUT hall_gpio
#define WB_HALL_RPM_DEFAULT     600
#define WB_HALL_RPM_MAX         700   // matches the pyglet UI's RPM slider range (0-700)
#define WB_HALL_PULSE_WIDTH_US  1000  // low-pulse width per simulated revolution

// ---- LED SPI bus capture (workbench acts as SPI slave, input only) ----
#define WB_SPI_SCLK_PIN  12  // <- DUT led_clk
#define WB_SPI_MOSI_PIN  13  // <- DUT led_mosi
#define WB_SPI_CS_PIN    14  // <- DUT LED-bus CS (`vs_board` led_cs; 14 by default). Frames each burst.

#define WB_NUM_LEDS   54     // must match PIXELS in hardware/rotor/modules/povdisplay/gpu.c
#define WB_COLUMNS    256
// Reassembled LED telemetry keeps each complete on-wire APA102 LED frame:
// [0xe0 | global brightness, B, G, R]. The workbench is a passive observer;
// it must not discard global brightness or reinterpret the colour data.
#define WB_APA102_LED_FRAME_BYTES 4
#define WB_FRAME_BYTES (WB_COLUMNS * WB_NUM_LEDS * WB_APA102_LED_FRAME_BYTES)

// ---- UDP telemetry chunking (see telemetry.c) ----
// Each datagram carries WB_COLUMNS_PER_CHUNK columns' worth of raw APA102
// data, well under any realistic MTU: 4 divides WB_COLUMNS evenly (no
// ragged final chunk) and keeps each packet's payload at 4*54*4=864 bytes
// (870 with the header), far under the ~1470-byte usable payload of a
// standard 1500-byte-MTU link -- deliberately small enough that IP never
// has to fragment a datagram, since a lost IP fragment takes the whole
// datagram with it.
#define WB_COLUMNS_PER_CHUNK    4
#define WB_NUM_CHUNKS           (WB_COLUMNS / WB_COLUMNS_PER_CHUNK)
#define WB_CHUNK_PAYLOAD_BYTES  (WB_COLUMNS_PER_CHUNK * WB_NUM_LEDS * WB_APA102_LED_FRAME_BYTES)

// ---- DUT UART bridge ----
#define WB_UART_TX_PIN  6   // -> DUT serial_rx
#define WB_UART_RX_PIN  5   // <- DUT serial_tx
#define WB_UART_BAUD    115200

// ---- Wi-Fi station + mDNS ----
// The workbench joins an existing network (so the PC running the pyglet
// emulator keeps normal internet access on the same Wi-Fi) instead of
// running its own AP. Credentials come from NVS namespace "devel_wifi" —
// the same namespace/keys the DUT itself reads in
// apps/micropython/ventilastation/updater.py — provisioned with
// `make workbench-wifi-provision` (see docs/internals/workbench.md).
#define WB_WIFI_NVS_NAMESPACE  "devel_wifi"
// Pre-rename namespace, still read as a fallback so workbenches provisioned
// before the "devel_wifi" rename keep connecting without re-provisioning.
#define WB_WIFI_NVS_NAMESPACE_LEGACY  "voom_wifi"
#define WB_WIFI_CONNECT_RETRY_DELAY_MS  2000

// Advertised as "<hostname>.local" via mDNS so the pyglet emulator can find
// the workbench without knowing its DHCP-assigned IP.
#define WB_MDNS_HOSTNAME      "ventilastation-workbench"
#define WB_MDNS_INSTANCE_NAME "Ventilastation Workbench"
#define WB_MDNS_SERVICE_TYPE  "_ventilastation-wb"
#define WB_MDNS_SERVICE_PROTO "_udp"

// ---- Wi-Fi telemetry link (pyglet emulator) ----
// UDP, not TCP: frame_apa102 is a live "latest wins" preview, and TCP's
// in-order/retransmit guarantees actively hurt that -- one lost segment
// stalls delivery of everything queued behind it (head-of-line blocking)
// until it's retransmitted, turning a single dropped packet into a visible
// freeze instead of a few stale columns. See telemetry.c.
#define WB_TELEMETRY_PORT               5005
#define WB_TELEMETRY_FRAME_INTERVAL_MS  33
// How long without any datagram from the client (hello/reset/rpm) before
// the workbench stops streaming to it -- avoids blasting UDP frames at a
// vanished/crashed emulator forever.
#define WB_TELEMETRY_CLIENT_TIMEOUT_MS  5000
