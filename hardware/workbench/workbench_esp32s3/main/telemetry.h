#pragma once

// Joins the Wi-Fi network configured in NVS (namespace WB_WIFI_NVS_NAMESPACE,
// same "ssid"/"password" blob keys the DUT itself reads), advertises the
// workbench over mDNS as WB_MDNS_HOSTNAME + ".local", and starts a
// background task running a TCP server on WB_TELEMETRY_PORT for the
// desktop vsdk/emulator (pyglet) to connect to.
//
// Once connected, streams "frame_apa102" snapshots of the captured LED bus
// roughly every WB_TELEMETRY_FRAME_INTERVAL_MS, and accepts simple line
// commands from the client:
//   "reset\n"     -> pulses the DUT's reset line (see reset_ctl.h)
//   "rpm <n>\n"   -> sets the simulated hall RPM (see hall_sim_set_rpm)
void telemetry_begin(void);
