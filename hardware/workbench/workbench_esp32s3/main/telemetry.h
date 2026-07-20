#pragma once

// Joins the Wi-Fi network configured in NVS (namespace WB_WIFI_NVS_NAMESPACE,
// same "ssid"/"password" blob keys the DUT itself reads), advertises the
// workbench over mDNS as WB_MDNS_HOSTNAME + ".local", and starts a
// background task running a UDP telemetry link on WB_TELEMETRY_PORT for the
// desktop vsdk/emulator (pyglet) -- UDP, not TCP, so one lost datagram
// leaves a few stale columns instead of stalling the whole stream. See
// telemetry.c for the wire format.
//
// Once a client has sent it a datagram (any line, including the periodic
// "hello\n" keepalive), streams chunked snapshots of the captured LED bus
// roughly every WB_TELEMETRY_FRAME_INTERVAL_MS, until WB_TELEMETRY_CLIENT_
// TIMEOUT_MS passes without hearing from that client again. Recognized
// client -> workbench lines:
//   "reset\n"     -> pulses the DUT's reset line (see reset_ctl.h)
//   "rpm <n>\n"   -> sets the simulated hall RPM (see hall_sim_set_rpm)
//   "hello\n"     -> no-op keepalive
void telemetry_begin(void);
