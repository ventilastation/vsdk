#pragma once

// Brings up the Wi-Fi access point and starts a background task running a
// TCP server on WB_TELEMETRY_PORT for the desktop vsdk/emulator (pyglet)
// to connect to, matching vsdk/emulator/comms.py's ConnIP client. Once
// connected, streams "frame_rgb" snapshots of the captured LED bus roughly
// every WB_TELEMETRY_FRAME_INTERVAL_MS.
void telemetry_begin(void);
