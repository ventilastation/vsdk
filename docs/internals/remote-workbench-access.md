# Remote physical-workbench access from the web emulator

Status: WebRTC/H.264 implementation on `codex/remote-workbench`, updated from
`main` on 2026-07-20.

This document describes the implemented path from the static GitHub Pages
emulator to a physical Ventilastation board connected by USB to a developer
workbench. It is intended for a remote mobile browser with Google sign-in,
default-deny board access, high-frame-rate color display, audio host commands,
and emulated input returned to the board.

## Quick deployment and smoke test

The day-to-day operator path is two commands. Private configuration and tunnel
credentials stay under `~/.config/vsdk/remote-workbench`; nothing secret is
written into the repository.

```text
# Terminal 1: start and supervise both the gateway and FRP tunnel:
make remote-workbench-run

# Terminal 2: print the phone URL and watch the five end-to-end checks:
make remote-workbench-smoke
```

`remote-workbench-run` auto-selects FRP when `frpc.toml` and `bin/frpc` exist,
otherwise it falls back to ngrok. The deployed FRP path uses the stable gateway
`https://ventilastation-board.protocultura.net`; the Pages emulator therefore
needs only `?remote=1`. On the phone, sign in, request control, move the
joystick, and change a menu item. The smoke command passes after observing
login, connected H.264 video, a control lease, joystick input, and an audio
command in the gateway audit database.

One-time setup on a new workbench computer is:

```text
make remote-workbench-setup EMAIL=allowed-google-account@example.com
# Copy the private frpc.toml, frp.token and bin/frpc into the printed config dir.
```

The USB board is optional at gateway startup. If it is absent, the same smoke
path uses the synthetic disconnected display described below. `doctor` reports
a warning instead of failing, and the gateway keeps retrying the configured
serial device until it appears.

Useful variants:

```text
make remote-workbench-doctor
make remote-workbench-setup EMAIL=user@example.com REMOTE_WORKBENCH_SERIAL=/dev/cu.usbmodem123
python3 tools/remote_workbench.py smoke --open --timeout 300
python3 tools/remote_workbench.py run --transport ngrok  # emergency fallback
```

Rerunning setup is safe: it reuses existing private configuration. Pass
`--force` directly to the Python tool only when intentionally regenerating the
email policy or endpoint settings. Logs live beside the private configuration
in `~/.config/vsdk/remote-workbench/logs/`.

## Outcome and constraints

- GitHub Pages hosts the existing static client at
  `https://ventilastation.protocultura.net/emulator/?remote=1`.
- The workbench gateway owns USB serial and is the sole UDP telemetry client
  for the board on port 5005.
- A small Google Cloud VPS terminates HTTPS and Google OAuth. FRP exposes only
  the loopback gateway on `127.0.0.1:8765` through an authenticated TLS tunnel.
  It carries ticket exchange, WebRTC signaling, input, leases, status, and
  audio commands.
- Display media uses a peer-to-peer WebRTC H.264 track. It does not traverse
  the VPS tunnel when a direct ICE candidate pair succeeds, which keeps the
  high-volume frame stream off the relay.
- If direct ICE fails, a configured TURN server relays media. That consumes
  TURN bandwidth, not ngrok bandwidth.
- The local emulator remains available without sign-in. Authentication is
  requested only when the visitor chooses **Connect physical board**.

## Architecture

```text
GitHub Pages emulator (phone or desktop)
       | HTTPS/WSS: login, ticket, SDP, input, audio, status
       v
Google Cloud VPS: Caddy TLS + oauth2-proxy Google login
       | authenticated FRP tunnel to a loopback-only service
       v
remote_gateway.py (127.0.0.1:8765) ---- USB serial ---- physical DUT
       |                                      ^
       +---- UDP 5005 APA102 telemetry -------+
       |
       +==== WebRTC H.264 / DTLS-SRTP ===== browser
             direct ICE, or optional TURN
```

The gateway continuously assembles the newest complete APA102 capture but
publishes frames only while at least one authenticated WebRTC peer exists. A
per-peer video track waits for the newest snapshot; stale frames are replaced,
not queued. WebRTC supplies congestion control, packet loss recovery, pacing,
and keyframes. The browser schedules rendering from decoded-frame callbacks,
so it does not redraw an old frame merely because `requestAnimationFrame`
fired.

When the page becomes hidden, the adapter sends `VIDEO_STOP` and closes the
peer connection. It renegotiates when the emulator loop resumes. This prevents
background tabs from consuming video bandwidth.

## USB disconnect fallback

USB serial is hot-pluggable. Startup and runtime I/O failures switch the
gateway to a synthetic frame source; a reconnect switches it back to the most
recent real UDP capture without restarting the gateway, tunnel, or browser.

The fallback draws **board unplugged** directly in the native 256-column by
54-LED polar framebuffer. It uses the MicroPython ROM-selection menu's exact
4x6 `tinyfont_menu.png` glyphs, three lit columns plus a one-column gap, and
the same hardware-confirmed mirrored angle/radius placement used by retro-go's
native Ventilastation dialogs. The red warning sits in the readable bottom
wedge near the outer rim and moves one LED inward/outward every 500 ms.

Only two frames per second are published while disconnected. After 60 seconds
the gateway publishes one final warning starting at the outermost LED and stops
producing video frames. The cached error stays visible without continuing media
bandwidth. Reconnecting immediately restores real captures. A later disconnect
starts a fresh one minute warning window.

Control remains available for end-to-end testing while unplugged: input is
validated and audited but not claimed as delivered to hardware. A non-neutral
input emits the ROM menu's normal movement sound, allowing the automated smoke
test to cover video, lease, input, and browser audio without a board.

## Authentication and authorization

Authentication is deliberately separate from media transport:

1. The visitor selects **Connect physical board**. The static client opens
   `<gateway>/auth/start` in a popup.
2. oauth2-proxy on the VPS performs Google OAuth and applies its email
   allowlist before the request reaches the workbench.
3. The edge removes caller-supplied identity headers and injects the verified
   Google email as `X-Remote-Email`.
4. The loopback gateway checks its local board ACL and mints a signed,
   one-use, 30--60 second ticket. The popup returns it to the exact configured
   Pages origin with `postMessage`.
5. The client opens `wss://<gateway>/ws?ticket=...`. The gateway verifies the
   signature, audience, origin, expiry, unused ticket ID, and current ACL role.
6. Only after the authenticated WebSocket is established does the gateway
   advertise ICE configuration and accept a `VIDEO_OFFER`. The offer and
   resulting H.264 peer are bound to that authenticated browser session.
7. WebRTC authenticates the negotiated media channel with the DTLS
   fingerprints in the signed signaling exchange and encrypts media with
   DTLS-SRTP.
8. A controller must acquire the exclusive board lease before input is
   forwarded. Disconnect, lease expiry, release, or ACL revocation sends
   neutral input before another user can control the board.

Browser WebSockets do not reliably carry a cross-site OAuth cookie, which is
why the flow uses a one-use query ticket. Tunnel/access logs must redact query
strings. The ticket contains no reusable Google credential and is atomically
consumed.

The gateway ACL is default-deny:

| Role | Permission |
| --- | --- |
| `viewer` | View display/status and receive audio commands. |
| `controller` | Viewer access plus eligibility for the exclusive input lease. |
| `operator` | Controller access plus approved reset/RPM operations. |
| `admin` | Operator access plus local ACL/session administration. |

Manage it locally, never through the public endpoint:

```text
python -m emulator.remote_gateway acl grant person@example.com controller
python -m emulator.remote_gateway acl revoke person@example.com
python -m emulator.remote_gateway sessions list
```

Removing an email from oauth2-proxy's allowlist blocks future login. Revoking
the local ACL is authoritative for existing sessions: the lease loop notices
the role change, closes the socket, and neutralizes input.

## Video format and color fidelity

The logical display is **256 rotor columns by 54 LEDs**. In framebuffer byte
order it is naturally 54 texels wide by 256 rows high. The capture and render
rate is 30 frames per second.

Sending a literal 54×256 RGB picture through browser-compatible H.264 would
not preserve the LEDs' colors: H.264 Baseline uses 4:2:0 chroma, so neighbouring
one-pixel red/green/blue values are averaged. The implemented wire picture is
therefore 162×256:

```text
logical LED 0         logical LED 1
  R0  G0  B0            R1  G1  B1        (162 luma samples per row)
```

Each component value is encoded as a neutral-grey RGB sample. All information
then lives in the full-resolution luma plane, while the subsampled chroma
planes remain neutral. A regression test encodes and decodes an adversarial
saturated pattern through the same H.264 Baseline settings; at 1 Mbit/s it
requires mean channel error below 0.5 and maximum error no greater than 3.

The browser uploads the decoded `HTMLVideoElement` directly into a 162×256
WebGL texture with `texSubImage2D`. The ring fragment shader samples the three
luma positions and reconstructs one RGB LED. There is no canvas, `ImageData`,
JavaScript RGBA copy, palette, RGB555 conversion, or browser CPU transpose.
The logical geometry remains exactly 54×256.

The H.264 sender starts at aiortc's 1 Mbit/s target and WebRTC adapts between
its congestion-control bounds. Inter-frame compression makes normal menu/game
content substantially smaller than independently deflated RGB frames, while
30 fps and RGB888 semantics are retained.

## Signaling and control protocol

All WebSocket messages keep the fixed 20-byte `VSRW` version-1 binary header.
JSON control payloads are bounded to 128 KiB so complete non-trickle SDP can
carry several ICE candidates.

| Type | Direction | Purpose |
| --- | --- | --- |
| `HELLO` | gateway → browser | Role, lease state, H.264 format, ICE servers. |
| `VIDEO_OFFER` (`0x20`) | browser → gateway | H.264-only WebRTC offer after full ICE gathering. |
| `VIDEO_ANSWER` (`0x21`) | gateway → browser | H.264 answer and confirmed packed dimensions. |
| `VIDEO_STATUS` (`0x22`) | both/status | ICE/peer state and transport statistics. |
| `VIDEO_STOP` (`0x23`) | browser → gateway | Stop media when hidden or disconnected. |
| `HOST_EVENT` | gateway → browser | Safe sound/music/notes and emulator host events. |
| `LEASE_REQUEST` / `LEASE` | both | Exclusive controller arbitration. |
| `INPUT` | browser → gateway | Canonical joystick state plus exit edge. |
| `HEARTBEAT` | browser → gateway | Renew the currently held lease. |

`HOST_EVENT` permits only the existing browser commands `sound`, `music`,
`musicstop`, `notes`, `base`, `info`, `traceback`, `achip`, `aframe`, `amap`,
and `astop`. The public protocol exposes no shell, filesystem, firmware flash,
arbitrary serial write, or raw UDP command.

## ICE, STUN, and TURN

The default is a public STUN server:

```text
REMOTE_WORKBENCH_ICE_SERVERS_JSON='[{"urls":["stun:stun.l.google.com:19302"]}]'
```

STUN discovers public candidate addresses but does not relay media. It usually
allows a direct UDP path even though both peers are behind NAT. Symmetric NAT,
some mobile carriers, corporate firewalls, or UDP blocking may require TURN:

```text
REMOTE_WORKBENCH_ICE_SERVERS_JSON='[
  {"urls":["stun:stun.l.google.com:19302"]},
  {"urls":["turns:relay.example.net:5349"],
   "username":"short-lived-user","credential":"short-lived-secret"}
]'
```

ICE configuration is not embedded in GitHub Pages. It is sent in `HELLO` only
after ticket authentication and ACL approval. Prefer short-lived TURN REST
credentials. A static TURN password is exposed to every authorized viewer and
should be used only for a tightly controlled smoke environment. An empty or
invalid ICE configuration fails gateway startup rather than silently disabling
connectivity.

## ngrok edge policy

The checked-in example is
`tools/remote-workbench-ngrok-policy.example.yml`. The deployed policy must:

1. apply Google OAuth to every HTTP path except `/ws`;
2. deny identities outside the explicit Google email allowlist;
3. remove caller-controlled `X-Remote-Email` and `X-Remote-Subject` headers;
4. add `X-Remote-Email` from ngrok's verified OAuth identity.

`/ws` skips the cookie-based OAuth action because it is authenticated with the
gateway's one-use ticket. The gateway must remain loopback-only; trusted-proxy
mode is unsafe if another network path can reach it.

The free ngrok domain and OAuth quota are suitable for private testing. After
this WebRTC change, only small signaling/control/audio messages count against
ngrok network bandwidth. A TURN relay, if needed, needs a separate bandwidth
budget.

## Manual configuration and operation

The commands in the quick deployment section automate this section. Use the
manual procedure only for debugging or a customized installation.

Store live secrets in an owner-only directory outside the repository, for
example `~/.config/vsdk/remote-workbench/`:

- `gateway.env`: endpoints, serial device, trusted headers, and ICE servers;
- `ticket.key`: at least 32 random bytes;
- `ngrok-authtoken`, `ngrok.yml`, and `ngrok-policy.yml`;
- TURN credentials, if used.

Never commit passwords, personal email allowlists, OAuth credentials, tunnel
tokens, ticket keys, tickets, or TURN secrets.

Install and verify the gateway environment:

```text
python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements.txt
set -a; source ~/.config/vsdk/remote-workbench/gateway.env; set +a
.venv312/bin/python -m emulator.remote_gateway serve --check-config
```

Run the loopback gateway and tunnel in separate supervised processes:

```text
set -a; source ~/.config/vsdk/remote-workbench/gateway.env; set +a
.venv312/bin/python -m emulator.remote_gateway serve

ngrok http 127.0.0.1:8765 \
  --config ~/.config/vsdk/remote-workbench/ngrok.yml \
  --traffic-policy-file ~/.config/vsdk/remote-workbench/ngrok-policy.yml
```

The generated test link passes the assigned public endpoint in the `gateway`
query parameter. A custom host page may instead set
`window.VENTILASTATION_REMOTE_GATEWAY` before importing the adapter.

## Detailed verification

`make remote-workbench-smoke` automates the normal acceptance path. The checks
below remain useful for regression testing and deeper diagnosis.

Automated regression tests:

```text
.venv312/bin/python tests/test_remote_video.py
.venv312/bin/python tests/test_remote_gateway.py
.venv312/bin/python tests/test_workbench_telemetry.py
node tests/test_remote_adapter.mjs
```

End-to-end smoke test:

1. Confirm the board serial device exists and UDP telemetry receives complete
   captures.
2. Start the gateway and ngrok. Confirm an unauthenticated `/auth/start`
   request is redirected to Google and a direct spoofed identity header is
   discarded by the edge.
3. Open the deployed Pages emulator with `?remote=1`, sign in using an
   allowlisted test Google identity, and confirm the role shown by `HELLO`.
4. Confirm WebRTC reaches `connected`, negotiated codec is H.264, decoded FPS
   approaches 30, frames advance, and `bytesReceived` increases without a
   matching high-volume transfer through ngrok.
5. Compare an asymmetric saturated board pattern with the physical display to
   verify orientation and the RGB-luma shader reconstruction.
6. Acquire the controller lease, move through a menu, and verify joystick
   input changes the physical board state.
7. Verify a resulting `sound`, `music`, or `notes` host event is audible in the
   browser.
8. Hide the page and verify `VIDEO_STOP`; restore it and verify a new peer is
   negotiated.
9. Connect a second viewer and confirm it can see/hear but cannot send input
   while another session holds the lease.
10. Disconnect or revoke the controller and confirm neutral USB input is
    written immediately.
11. Unplug USB and confirm the red compact-font warning moves every 500 ms,
    then settles at the outermost LED and stops sending new frames after one
    minute.
12. Reconnect USB during and after that minute and confirm real capture and
    input resume without restarting any process.

Record only non-secret evidence: endpoint hostname, login result, role, codec,
ICE candidate type (`host`, `srflx`, or `relay`), decoded FPS, frame count,
input acknowledgement, and host-event type. Never record OAuth cookies,
tickets, SDP, TURN passwords, tunnel tokens, or account passwords.

## Known deployment limits

- A STUN-only deployment cannot guarantee connectivity across every NAT or
  firewall. Configure TURN when the smoke test reports `failed` ICE state.
- TURN changes the bandwidth cost location; it does not eliminate relay cost.
- H.264 browser decode and WebGL are mandatory in remote mode. The remote path
  intentionally has no low-fidelity canvas fallback.
- The current free ngrok quota must allow the small OAuth and signaling
  exchange before any public test can begin. An exhausted quota still blocks
  authentication even though WebRTC would carry the display afterward.
