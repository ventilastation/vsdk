# Remote physical-workbench access from the web emulator

Status: implementation and deployment runbook, reconciled with `main` at
`eb27744` on 2026-07-20.

Implementation status: the shared UDP receiver, incremental serial host parser,
gateway policy/WSS core, browser adapter, initial mobile controls, and focused
tests exist. Production uses an Oracle Always Free relay, frp reverse tunnel,
Caddy TLS terminator, and oauth2-proxy with Google sign-in. This avoids a
Cloudflare account and requires only an Oracle tenancy, a DNS A record, and a
Google OAuth web client owned by the board administrator.

This document specifies how a browser running the static web emulator from
GitHub Pages can, after an explicit Google sign-in, display and control the
physical Ventilastation board attached to the workbench on a developer
computer. It covers the local gateway, Internet transport, authentication,
authorization, control leasing, frame and audio delivery, input, deployment,
and verification.

The browser emulator remains fully usable without signing in. Remote access
is an optional mode entered with **Connect physical board**.

## Reconciliation with current main

[Pull request #137](https://github.com/ventilastation/vsdk/pull/137) has
landed the workbench's UDP telemetry implementation and its normative
documentation. This changes the starting point of the remote work:

- Chunked UDP `frame_apa102` is an implemented dependency, not a transport to
  design. Keep its `0xA1`/sequence/chunk-index wire format unchanged in the
  first remote release.
- `frame_apa102` is explicitly an exception to the byte-stream
  [host protocol](host-protocol.md). Only USB serial audio/system traffic uses
  the shared line-plus-binary-payload dispatcher.
- The desktop receiver already applies each fresh four-column chunk to a
  persistent raw APA102 buffer, rejects stale/reordered chunks per slot, and
  decodes the latest buffer at 30 Hz. The gateway should extract and reuse
  this latest-column behavior rather than wait for complete logical frames.
- The workbench sends one 64-datagram snapshot about every 33 ms, uses a 20 ms
  UDP send timeout, disables Wi-Fi modem sleep, and explicitly yields its
  telemetry task to avoid starving the watchdog. Remote compression and WSS
  fan-out must therefore remain entirely off the LAN receive loop.
- The workbench streams to whichever UDP address most recently sent a
  `hello`, `reset`, or `rpm` datagram. The desktop hardware emulator and remote
  gateway cannot be telemetry clients at the same time; the gateway becomes
  the sole subscriber while remote service is active.
- [workbench.md](workbench.md), [host-protocol.md](host-protocol.md), and
  [pov-color-pipeline.md](pov-color-pipeline.md) now describe the UDP path and
  are the source of truth. No documentation migration from TCP remains.

## Goals

- Keep the web emulator deployable as static files on GitHub Pages.
- Let a mobile browser connect without opening an inbound router port.
- Require Google authentication before a user can reach a physical board.
- Let the board owner decide who may view, control, or operate the board.
- Allow many viewers but at most one active controller.
- Deliver a useful mobile experience: a target of 20 displayed frames per
  second at 600 RPM, low-latency input, and browser audio.
- Fail safely: a lost or revoked controller must leave the DUT with neutral
  input, and remote users must never gain a generic path to the developer
  computer or workbench protocol.
- Reuse the existing browser renderer, audio host, input protocol, APA102
  decoder, colour profile, and host-command parser where practical.

## Non-goals

- Running the emulator backend on GitHub Pages. GitHub Pages is a static site
  host and cannot own a live board connection.
- Exposing workbench UDP port 5005 or the workbench USB serial device to the
  Internet.
- Remote firmware flashing, OTA, file access, a shell, or arbitrary host
  commands in the first release.
- Multi-controller input merging.
- Pixel-perfect, lossless delivery of every captured workbench frame. A live
  preview is a latest-state stream; freshness is more important than history.
- WebRTC in the first implementation. It is a measured fallback if WebSocket
  head-of-line blocking prevents the latency target from being met.

## Existing system and constraints

The relevant existing paths are:

- `web/`: source of truth for the GitHub Pages emulator.
- `emulator/comms.py`: desktop host connections and host-command dispatch.
- `emulator/apa102.py` and `emulator/color_profile.py`: captured APA102 to
  calibrated display-colour conversion.
- `hardware/workbench/workbench_esp32s3/`: workbench firmware.
- [host-protocol.md](host-protocol.md): DUT-to-host display, audio, and system
  messages.
- [input-protocol-v2.md](input-protocol-v2.md): host-to-DUT input messages.
- [workbench.md](workbench.md): physical workbench design.
- [web-emulator-architecture.md](web-emulator-architecture.md): browser host,
  adapter, worker, and renderer boundaries.

The current workbench has two local connections:

1. Wi-Fi UDP port 5005 sends 64 APA102 column-chunk datagrams for each
   256-by-54 capture. Each datagram is 870 bytes and contains a sequence
   number and four columns. The reverse direction accepts only `hello`,
   `reset`, and `rpm <n>` datagrams. The most recent sender becomes the single
   telemetry client. The desktop receiver sends `hello` once a second and the
   workbench expires the client after five seconds without a datagram.
2. USB serial bridges canonical joystick frames toward the DUT and carries
   audio/system host commands back from it.

One raw APA102 capture is 256 x 54 x 4 = 55,296 bytes. At the current 33 ms
capture interval the LAN stream is approximately 13.3 Mbit/s before UDP/IP
overhead. The Internet gateway must therefore convert and pace frames; it
must not proxy this UDP stream directly to the phone.

The current desktop path has been verified at 600 RPM with 2,560 clean
444-byte LED-bus bursts per second and no malformed captures. That is the
hardware baseline to preserve. Its `WorkbenchTelemetryConn` validates each
870-byte datagram, tracks the last sequence for all 64 chunk slots, updates a
persistent APA102 buffer, and triggers one full-buffer decode every 1/30
second. These behaviors should move into shared headless code without changing
the desktop preview first.

The web renderer already accepts `frame_rgb`, and the web host already plays
asset-backed `sound`, `music`, `musicstop`, and `notes` events. The adapter
boundary is the correct place to add a remote runtime without coupling the
renderer to WebSocket state.

### Mobile input prerequisite

The current touch D button uses `BUTTON_D` (`0x80`) in `touchButtons`, while
`BrowserHostApp.syncButtons()` masks `touchButtons` with `0x7f`. The press is
therefore discarded. Before remote control ships, touch buttons must produce
the same structured `{joy1, joy2, extra}` representation used by keyboard and
gamepad input. D/Y maps to `INPUT_EXTRA.JOY1_Y`; mobile Start and Back map to
their protocol-v2 `extra` bits. Exit remains a distinct edge-triggered action
that the gateway converts to the canonical `exit\n` command rather than an
input bit. Tests must cover every mobile control through the four-byte `*`,
joy1, joy2, extra state frame plus the separate Exit command.

## Target architecture

```text
 https://ventilastation.protocultura.net/  (GitHub Pages)
 +-----------------------------------------------------+
 | BrowserHostApp                                     |
 |  local mode: WASM adapter                          |
 |  remote mode: RemoteWorkbenchAdapter               |
 |  touch/gamepad -> input       frames/audio <-      |
 +-------------------------+---------------------------+
                           | TLS WebSocket
                           v
 https://ventilastation-board.protocultura.net/
 +-------------------------+---------------------------+
 | Oracle VM: Caddy + oauth2-proxy + frps             |
 |  /auth/*: Google login and verified proxy headers  |
 |  /ws: gateway-issued ticket required               |
 +-------------------------+---------------------------+
                           | outbound tunnel
                           v
 Developer computer, loopback only
 +-----------------------------------------------------+
 | remote_gateway.py                                  |
 | auth/ACL | lease | protocol | frame/audio/input    |
 +----------------------+------------------------------+
                        |                    |
             UDP :5005 |                    | USB serial
                        v                    v
             +-----------------------------------------+
             | Workbench ESP32-S3 -> physical DUT     |
             +-----------------------------------------+
```

The frp client tunnel is outbound from this computer. The router has no port
forward, the gateway listens only on loopback, and the workbench remains
reachable only on the LAN and over local USB. Oracle's `frps` binds the
gateway's returned port to its own loopback; Caddy is therefore the sole
Internet-facing process and obtains the TLS certificate for the board hostname.

## Trust boundaries

There are four separate decisions; none may be implied by another:

1. **Google identity** proves who signed in.
2. **oauth2-proxy/Google sign-in** determines who may complete the login flow.
3. **Gateway ACL** gives an allowed identity a role for a particular board.
4. **Controller lease** determines which eligible identity may send input at
   this instant.

The self-hosted edge protects the public entry and the gateway remains
authoritative for board roles and live sessions. Identity fields sent by
browser messages are never trusted. Once a socket is open, its identity and
role come only from the ticket accepted during that socket's upgrade.

## Authentication and connection flow

Browser WebSockets cannot attach an arbitrary `Authorization` header, and a
cross-origin login cookie is too brittle to make the application protocol
depend on it. Authentication therefore has two stages: oauth2-proxy validates
Google identity, then the gateway exchanges that verified identity for a
short-lived, one-use WebSocket ticket.

1. The user opens the GitHub Pages emulator. Local WASM mode starts normally
   and requires no account.
2. The user presses **Connect physical board**. This user gesture also enables
   browser audio.
3. The page opens a popup at
   `https://ventilastation-board.protocultura.net/auth/start`.
4. Caddy delegates the popup to oauth2-proxy, which redirects to Google. The
   Google OAuth consent screen should list the test users explicitly until the
   application is published.
5. On success, oauth2-proxy returns verified user/email response headers.
   Caddy deletes browser-supplied `X-Remote-*` headers and copies those values
   to the proxied `/auth/start` request. The gateway accepts this mode only
   while bound to loopback behind the private frp port.
6. The gateway extracts the stable subject and normalized email, checks the
   local board ACL, and issues a signed ticket containing `sub`, `email`,
   `role`, `board`, `aud`, `iat`, `exp`, and random `jti` claims.
7. The popup returns the ticket to the exact GitHub Pages origin with
   `window.opener.postMessage`. If the browser severs the opener relationship,
   it redirects to the Pages URL with the ticket in the URL fragment. The page
   consumes the fragment and immediately removes it with `history.replaceState`.
8. The page opens
   `wss://ventilastation-board.protocultura.net/ws?ticket=<ticket>`.
9. Before sending HTTP 101, the gateway verifies the ticket signature,
   audience, board, and 30-to-60-second expiry, then atomically consumes the
   `jti`. Reuse fails. Query strings and tickets must be redacted from every
   access and application log.
10. The gateway also requires an exact allowed `Origin` header. The origin
    check is defense in depth, not the primary credential.

Configure exactly three public edge paths:

- `/oauth2/*` reaches oauth2-proxy without a pre-check so login callbacks work.
- `/auth/*` gets a Caddy `forward_auth` check and can mint a ticket only after
  Google sign-in.
- `/ws` is login-bypassed because it accepts only a gateway-signed, one-use
  ticket. It is not anonymously usable.

The gateway's `trusted-proxy` authentication mode is not safe on a public
listener. Caddy must strip client copies of the identity headers and frps must
set `proxyBindAddr = "127.0.0.1"`. Rate limits should apply to failed ticket
upgrades and login endpoints.

### Ticket signing and secret storage

For one gateway process, HMAC-SHA-256 with a randomly generated 32-byte key is
sufficient. Store the key outside the repository with owner-only permissions,
for example under `~/.config/vsdk/remote-workbench/`. Support a current and
previous key identifier during rotation. Never put OAuth credentials, tunnel
credentials, tickets, email allowlists, or signing keys in the repository or
GitHub Pages bundle.

The gateway must use constant-time signature checks and an atomic
consume-if-unused operation for `jti`. A small SQLite database is appropriate
for tickets, ACL records, leases, and audit metadata. Expired ticket rows can
be removed periodically.

## Authorization and board ownership

The gateway ACL is default-deny and assigns one role per `(identity, board)`:

| Role | Capabilities |
|---|---|
| `viewer` | Receive status, frames, and audio. Cannot send DUT input. |
| `controller` | Viewer capabilities and eligibility to acquire the exclusive input lease. |
| `operator` | Controller capabilities plus reset and RPM control while holding the lease. |
| `admin` | Operator capabilities plus local ACL/session administration and force revoke. |

The first admin is bootstrapped locally. Initial management should be a
loopback CLI rather than a public admin page, for example:

```text
python -m emulator.remote_gateway acl grant person@example.com controller --board workbench-1
python -m emulator.remote_gateway acl revoke person@example.com --board workbench-1
python -m emulator.remote_gateway sessions list
python -m emulator.remote_gateway sessions disconnect person@example.com
```

These command names define the intended operator interface; exact argparse
spelling can change during implementation. A later admin UI may call the same
service layer, but it must not be required to ship remote play.

Changing the oauth2-proxy/Google test-user policy prevents the next login but does not
close an existing WebSocket. Immediate revocation therefore updates the local
ACL and causes the gateway to close every matching active socket, neutralize
its input if necessary, and release its lease.

## Exclusive controller lease

Any number of authorized viewers may connect, subject to configured resource
limits. Exactly one socket may hold the board's controller lease.

```text
eligible session --request--> waiting/denied --grant--> lease holder
       ^                                      heartbeat |
       | disconnect, expiry, revoke, release            |
       +------------------------------------------------+
```

- A `controller`, `operator`, or `admin` may request the lease.
- The initial implementation may use first-come-first-served with an admin
  force-grant. A visible queue can be added without changing the wire model.
- Default lease duration is 10 minutes and can be renewed while the session
  and ACL remain valid.
- The controller sends a heartbeat every five seconds. Ten seconds without a
  heartbeat, a socket close, page hide timeout, role revocation, or maximum
  session expiry releases the lease.
- On every release path the gateway writes neutral `{joy1:0, joy2:0,
  extra:0}` input immediately, writes it again on the next two input ticks,
  and only then grants another controller.
- Input from viewers, queued users, old lease generations, and non-current
  sockets is ignored and counted as a security metric.
- Reset and RPM changes require both `operator` (or `admin`) role and the
  current lease. RPM is clamped to the workbench firmware's supported range.

Each grant carries a monotonically increasing `lease_generation`. Every input
message includes that generation, which prevents delayed packets from a prior
controller from taking effect after reassignment.

## Local gateway

Add a standalone, headless gateway, proposed as
`emulator/remote_gateway.py`. It must not import Pyglet or create a desktop
window. Run it as an explicit command; remote access is off unless both the
gateway and frp client tunnel are running.

The gateway owns these tasks:

- listen on a loopback HTTP/WebSocket port for the private tunnel;
- validate the edge-injected identity and mint/consume tickets;
- maintain the ACL, sessions, roles, lease, and audit log;
- be the single UDP telemetry client of the workbench;
- own the workbench USB serial device;
- maintain and snapshot the latest-column APA102 capture buffer, then decode
  it outside the UDP receive loop;
- parse serial host commands and expose only allowlisted typed browser events;
- accept canonical input from the current lease holder and write canonical
  input-protocol-v2 frames to serial;
- send only allowlisted `hello`, `reset`, and bounded `rpm` commands over UDP;
- bound every queue and disconnect slow or abusive clients.

Do not duplicate the desktop protocol logic. Extract the byte-stream host
parser and typed event representation from `emulator/comms.py` into a pure
module such as `emulator/host_protocol.py`, then use it from both the desktop
emulator and gateway. Separately extract `WorkbenchTelemetryConn`'s constants,
wrap-safe sequence comparison, packet validation, per-chunk sequence table,
persistent APA102 buffer, one-second keepalive, and 30 Hz snapshot/decode
pacing into a Pyglet-free module. `frame_apa102` must not be routed through the
serial host parser. Preserve the current desktop behavior with fixtures and
tests before switching it to the shared code.

During the shared-module extraction, add a cross-platform advisory ownership
lock keyed by board identity. Both `emu.py --remote` and the gateway acquire it
before starting their `hello` loop; the second local process fails with a clear
message instead of making the stream oscillate between UDP source ports. The
operator runbook must still say to stop `emu.py --remote` before starting
public service. This lock coordinates processes on one computer only; it does
not authenticate the workbench UDP service or prevent another LAN host from
taking over, so unexpected chunk starvation/source changes remain an
operational alert.

The service binds to `127.0.0.1`, not `0.0.0.0`. `frpc` forwards the Oracle
VM's private returned port to that loopback address. Startup must fail closed
if the signing key, trusted-proxy headers, allowed Pages origin, board ACL,
serial device, or board identifier is absent or ambiguous.

## Browser integration

Add `web/remote-adapter.js` implementing the existing runtime adapter shape.
Remote mode should therefore feed the same `BrowserHostApp` renderer and audio
host as WASM mode rather than introducing a second UI.

The remote adapter is responsible for:

- popup authentication and exact-origin `postMessage` validation;
- WebSocket lifecycle, binary parsing, keepalive, and reconnect UI;
- emitting `frame_rgb` data through the existing frame stream;
- converting allowlisted remote audio events into existing host events;
- sending structured input at a fixed rate only while the lease is held;
- reporting identity, board, role, lease holder, latency, and connection state;
- sending a final neutral input on page hide and socket close when possible.

When switching to remote mode, pause or terminate the local WASM worker so it
does not continue consuming CPU/audio behind the physical stream. On remote
disconnect the user may explicitly return to a freshly booted local runtime.
Do not silently merge the local emulated state with the physical board state.

The mobile UI needs Connect/Disconnect, Request/Release control, controller
identity, a read-only indicator, Start, Back, and Exit. Reset and RPM controls
are shown only for an operator/admin with an active lease. A lost connection
must visibly disable controls before reconnect begins.

After changing `web/`, rebuild the runtime bundle and publish through the
normal process in [deploying-web-emulator.md](deploying-web-emulator.md),
including JavaScript cache-version bumps. The generated website copy is not a
source file.

## Version 1 WebSocket protocol

All WebSocket application messages are binary. Sparse control payloads use
UTF-8 JSON inside the binary envelope; frame and audio payloads remain binary.
Integer fields are little-endian.

Every message begins with this 20-byte header:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | ASCII magic `VSRW` |
| 4 | 1 | protocol version, initially `1` |
| 5 | 1 | message type |
| 6 | 2 | type-specific flags |
| 8 | 4 | sequence number |
| 12 | 4 | sender monotonic timestamp in milliseconds, wrapping naturally |
| 16 | 4 | payload byte length |

The receiver rejects a bad magic, unsupported version, declared length
mismatch, message over its type-specific limit, invalid JSON schema, or
unknown client message. Server capabilities in `HELLO` permit additive
message types in later versions.

### Server-to-browser messages

| Type | Name | Payload |
|---:|---|---|
| `0x01` | `HELLO` | JSON: protocol capabilities, board, authenticated role, session expiry, display dimensions, frame codecs, and current lease state. |
| `0x02` | `FRAME_RGB` | 8-byte metadata (`width:u16`, `height:u16`, `format:u8`, `codec:u8`, `reserved:u16`) followed by RGB888 bytes, raw or deflate-compressed. |
| `0x03` | `HOST_EVENT` | Allowlisted typed event name and arguments followed by its optional bounded binary payload. |
| `0x04` | `STATUS` | JSON: connection, frame loss, lease, RTT, and workbench state changes. |
| `0x05` | `ERROR` | JSON: stable error code and user-safe message. No secrets or raw assertions. |
| `0x06` | `LEASE` | JSON: holder display identity, generation, expiry, and queue position. |

`HOST_EVENT` does not carry arbitrary host-protocol text. The gateway parser
maps only the supported events to a stable typed schema. The initial allowlist
is asset audio (`sound`, `music`, `musicstop`, `notes`), read-only `base`
display state, and bounded `info`/`traceback` diagnostics; chip-audio events
are added in the audio phase. Unknown commands are logged locally at a bounded
rate and omitted from the browser stream.

### Browser-to-server messages

| Type | Name | Payload |
|---:|---|---|
| `0x10` | `INPUT` | `joy1:u8`, `joy2:u8`, `extra:u8`, `flags:u8`, `lease_generation:u32`. Only the low seven bits of each input byte are accepted. Exit is a defined edge bit in `flags`. |
| `0x11` | `FRAME_ACK` | `frame_seq:u32`, `receive_to_display_ms:u32`, used with the gateway's recorded send time for lag measurement and adaptive pacing. |
| `0x12` | `HEARTBEAT` | `lease_generation:u32`, `last_server_seq:u32`. |
| `0x13` | `LEASE_REQUEST` | JSON request/release action. |
| `0x14` | `OPERATOR_COMMAND` | Strict JSON union of `reset` or integer `rpm`; role and lease are checked again server-side. |

The gateway converts the state portion of `INPUT` into one canonical four-byte
input frame: `0x2a`, `joy1 & 0x7f`, `joy2 & 0x7f`, `extra & 0x7f`. A valid Exit
rising-edge flag additionally enqueues the canonical ASCII `exit\n` command
through the same serialized USB writer; it is never represented as an eighth
joystick bit. De-duplicate the edge per socket and lease generation. Browser
input normally travels at 30 Hz, with an immediate message on state change.
Repeated identical state may be suppressed only while heartbeat and
neutralization guarantees remain intact.

Sequence counters are independent in each direction. Monotonic timestamps are
useful for intervals reported by the same peer; clocks from the browser and
gateway are never subtracted directly. Gateway send-to-ACK time and explicit
ping echoes provide cross-peer latency/RTT measurements.

## Latest-column capture, conversion, and backpressure

Mirror the receiver now on `main`: the gateway owns one persistent
55,296-byte APA102 buffer plus `last_seq[64]`. A valid datagram whose wrap-safe
sequence is at least as new as that chunk slot replaces its four columns
immediately. A stale datagram is dropped. There is no complete-frame wait,
assembly deadline, retransmission, or FIFO; a lost datagram deliberately leaves
those columns at their last received values until a later snapshot refreshes
them.

At a paced maximum of 30 Hz, take a consistent copy of that persistent buffer
under a short lock and decode the copy outside the UDP receive loop. Record the
newest source `frame_seq` and each slot's distance/age from it so status can
report stale chunks and sequence gaps without delaying display. The WSS frame
header uses its own gateway output sequence; source workbench sequence and
staleness are diagnostic metadata, not ordering for browser messages.

The APA102 snapshot is converted on this computer with the existing
brightness and colour-profile behavior, then serialized as 256 x 54 RGB888.
An uncompressed RGB frame is 41,472 bytes, or about 6.64 Mbit/s at 20 FPS.
Version 1 supports:

- `raw-rgb888`, required as a compatibility fallback;
- `deflate-rgb888`, preferred when the browser supports
  `DecompressionStream("deflate")`.

Compression ratio is content-dependent and must be measured on real games;
the design does not assume a particular saving. Compression runs off the UDP
receive path and may be skipped when it cannot keep pace.

There is one pending outbound frame slot per browser. A new frame replaces an
unsent frame; frames never form a FIFO backlog. If `WebSocket.bufferedAmount`
exceeds a configured ceiling, the gateway/browser stop adding frames until it
falls, while control/status continues. The browser discards stale frame
sequences and acknowledges only frames actually displayed. The gateway uses
ACK lag to adapt each client's frame rate, initially within 10 to 20 FPS.
Slow viewers may receive fewer frames without affecting the controller.

If testing shows that converting every client independently is expensive,
compress each source frame once per negotiated codec and share that immutable
payload among clients. Bound the number of viewers and total outbound bitrate.

If WSS still exhibits unacceptable head-of-line stalls on real mobile
networks, add WebRTC as protocol version 2: unordered, non-retransmitting frame
data; reliable ordered input/audio/control; signaling through the authenticated
gateway; and TURN for networks that require relay. Do this only after the WSS
latency measurements justify the operational cost.

## Audio

Ship audio in two steps.

### Phase A: asset-backed audio

Forward typed `sound`, `music`, `musicstop`, and `notes` events. The browser
uses its existing published game assets and `BrowserAudioHost`; audio files do
not traverse the WebSocket. `music off` is normalized to `musicstop`. Asset
paths are validated and must remain within the published asset index.

The Connect gesture calls `audio.enable()` to satisfy mobile autoplay rules.
An unavailable asset is a visible diagnostic but must not stop frames or
input.

### Phase B: console chip audio

Support `achip`, `aframe`, `amap`, and `astop` after Phase A is stable. Compile
the existing `emulator/chipsynth` cores to WASM and drive them from an
AudioWorklet with a bounded ring buffer. Start with 50-to-80 ms of audio
jitter buffer and adjust from underrun metrics. Do not decode chip audio on
the UI thread.

The NES DMC ROM dependency requires an explicit implementation decision:
either transfer an allowlisted session ROM bank to the browser after
authorization, or synthesize PCM on the gateway and transport audio frames.
It must not be silently ignored.

The workbench diagnostic console and DUT host-command byte stream currently
share USB-side plumbing. Before binary `aframe` forwarding is enabled, prove
that there is exactly one serialized writer and that diagnostic logging cannot
be inserted into host-protocol headers or payloads. Route logs to a separate
endpoint or disable them on that data channel. The parser must recover from
unknown complete commands, but cannot recover reliably from bytes inserted in
the middle of a declared binary payload.

The workbench's host-to-DUT RESYNC detector begins with a newline, which is
also the terminator of `exit\n` and every other text command. Its partial-match
buffer must have a short bounded flush (the current pending implementation uses
5 ms), otherwise a command-ending newline can be held until another input
write arrives. Phase 0 must verify one Exit press is sufficient and measure
this delay; remote correctness must not depend on the next 30 Hz joystick
frame incidentally flushing it.

## Failure handling

- **Browser network loss:** disable UI input immediately, let the server lease
  heartbeat expire, neutralize DUT input, and reconnect only with an unexpired
  authenticated session. A consumed ticket is never reused; obtain a new one.
- **Gateway-to-workbench UDP loss:** retain the affected columns in the
  persistent latest-column buffer, expose per-slot loss/staleness metrics, and
  continue the one-second `hello` keepalive. Never wait for a missing chunk.
- **USB serial loss:** neutralization may not reach the DUT, so close remote
  control immediately, mark the board unavailable, and retry local discovery
  without accepting another lease.
- **Gateway restart:** all sockets and leases vanish. Send neutral input as
  soon as serial reconnects before accepting a controller.
- **Tunnel loss:** local gateway continues safely but cannot be reached. Do not
  fall back to a public LAN listener.
- **OAuth proxy failure:** new authentication exchanges fail closed; already
  issued short-lived tickets still expire and active sessions remain subject to
  ACL revocation.
- **Browser backgrounding:** send neutral input and voluntarily release the
  lease after a short grace period. Mobile timer throttling makes client-only
  heartbeat enforcement unsafe, so the server deadline remains authoritative.

## Security requirements

- TLS terminates at Caddy on the Oracle VM; the frp tunnel is the only path to
  the local gateway.
- The gateway binds loopback and the workbench stays on private UDP/USB links.
- Exact trusted identity-header names and exact Pages origins are configured; no
  wildcard origin or email-domain fallback is allowed by default.
- ACL, role, active board, lease generation, command allowlist, numeric bounds,
  and message size are checked for every privileged message.
- No WebSocket message can request a shell, filesystem path, serial bytes,
  arbitrary workbench line, OTA action, or arbitrary host command.
- Tickets expire in 30-to-60 seconds and are single use. OAuth sessions should
  be 15-to-60 minutes; WebSocket sessions should have a 30-to-60-minute
  maximum and require fresh authentication after expiry.
- Authentication, upgrade, connection, and operator-command rate limits are
  enforced. Invalid clients are disconnected rather than allowed to consume
  unbounded parsing or compression work.
- Logs never contain identity assertions, tickets, cookie values, query strings, raw
  input history, serial binary payloads, or signing keys.
- Dependencies for JWT, HTTP, WebSocket, and compression handling are pinned
  and included in the normal update review process.

## Observability and audit

Expose a loopback-only health/status endpoint and structured logs. Useful
metrics include:

- auth successes/failures by reason, ticket issue/consume/reuse rejection;
- connected viewers, current controller, queue depth, lease expiry/revocation;
- LAN chunk loss, per-slot sequence lag/age, stale columns, snapshot and
  decoded frame rate;
- per-client frames sent/dropped/displayed, compression ratio,
  `bufferedAmount`, ACK lag, and estimated RTT;
- serial reconnects, parser errors, audio events, AudioWorklet underruns;
- ignored unauthorized input/operator messages and rate-limit actions.

The audit log records timestamp, normalized email, subject identifier, board,
role, connect/disconnect, lease grant/release/revoke, reset, RPM change, and
admin ACL action. It does not record tokens or the user's raw button stream.
Give audit data a bounded retention policy.

## Repository changes

The expected change set is:

| Path | Change |
|---|---|
| `emulator/host_protocol.py` | Pure incremental host-command parser and typed events extracted from `comms.py`. |
| `emulator/workbench_telemetry.py` | Extracted UDP constants, packet validation, wrap-safe per-chunk latest-column buffer, keepalive, local ownership lock, snapshot pacing, and bounded workbench commands. |
| `emulator/remote_gateway.py` | Headless HTTP/WSS service, auth exchange, ACL, lease, routing, metrics, and CLI entry point. |
| `emulator/comms.py` | Use shared serial-parser/UDP-telemetry modules while preserving `WorkbenchTelemetryConn` behavior. |
| `emulator/povrender.py` | Consume shared APA102 snapshots/decoder without owning the UDP buffer implementation. |
| `web/remote-adapter.js` | Ticket flow and versioned WSS adapter. |
| `web/app.js` | Runtime-mode switching, remote state/lease UI integration, and structured touch input. |
| `web/app-support.js` | Shared structured touch mappings and remote protocol helpers as appropriate. |
| `web/index.html`, `web/styles.css` | Connect, identity, lease, Start/Back/Exit, operator controls, and mobile states. |
| `web/audio-host.js` | Phase A typed remote event handling; later chip-audio AudioWorklet integration. |
| `tests/` | Parser, auth, ACL, ticket, lease, protocol, frame, input, and failure tests. |
| `tools/` or service templates | Example frp, Caddy, oauth2-proxy, and local service configuration with placeholders only. |

Keep deploy-time configuration and secrets outside `web/`: anything in the
Pages bundle is public.

No workbench firmware or UDP wire-format change is required for version 1.
Add firmware metrics only if baseline measurements show that gateway operation
cannot be diagnosed from the receiver; do not add acknowledgements or
retransmission to the workbench stream.

## Implementation phases

### Phase 0: baseline and shared protocol extraction

1. Capture current local workbench FPS, LAN chunk loss, input latency, and
   serial audio behavior for representative MicroPython and native games.
2. Fix structured mobile D/Y, Start, Back, and Exit input with tests.
3. Land and verify the bounded workbench RESYNC-candidate flush so a lone
   `exit\n` reaches the DUT without a second input write.
4. Extract the Pyglet-free serial host parser and the existing UDP
   latest-column receiver; run the current desktop emulator through them
   without visual/audio behavior changes.
5. Add recorded UDP and serial fixtures, including missing/reordered chunks,
   sequence wrap, split headers, binary payloads, and unknown commands.

Exit criterion: local desktop hardware mode remains stable for 30 minutes with
no regression from the established 2,560 clean bursts/second hardware
baseline, unbounded queue, watchdog reset, or parser desynchronization.

### Phase 1: local gateway and remote frames/input

1. Implement the headless gateway, version 1 envelope, frame conversion,
   deflate/raw negotiation, one-frame queues, input neutralization, and lease.
2. Implement the remote browser adapter and mode UI.
3. Test first over loopback, then over LAN, then through a temporary tunnel.
4. Keep reset/RPM disabled until role checks and audit logging exist.

Exit criterion: one mobile client can view and control the DUT safely through
WSS, including reconnect and forced disconnect.

### Phase 2: Google authentication and owner ACL

1. Create the Oracle relay, DNS route, frp tunnel, and Caddy TLS endpoint.
2. Configure Google OAuth, oauth2-proxy, `/auth/*` forward authentication,
   `/ws` ticket bypass routing, session duration, and edge rate limits.
3. Implement trusted-proxy identity validation, one-use tickets, SQLite ACL, owner CLI,
   session revocation, and audit.
4. Enable operator-only reset/RPM after adversarial authorization tests.

Exit criterion: an unlisted Google identity, ticket replay, wrong origin,
viewer input, stale lease input, and revoked active user all fail closed.

### Phase 3: audio

1. Forward and verify asset-backed audio events.
2. Make the USB host-command path byte-clean under concurrent logs.
3. Add chip-synth WASM/AudioWorklet support and resolve NES DMC data handling.

Exit criterion: audio remains synchronized and input/frame targets continue to
pass under the extra traffic.

### Phase 4: hardening and optional WebRTC

Run mobile-network soak tests, tune compression and per-client pacing, test
key rotation and recovery, document service operations, and add WebRTC only if
measured WSS stalls fail the acceptance criteria.

## Test plan

### Unit and property tests

- Trusted-proxy missing/malformed identity-header cases, and optional legacy
  Access JWT issuer, audience, signature, expiry, missing-claim, and key
  rotation cases using local test keys.
- Ticket expiry, audience/board mismatch, tamper, atomic one-use under
  concurrent upgrades, and redacted logging.
- ACL default deny, every role boundary, live revoke, and board scoping.
- Lease request, renew, timeout, generation rollover, disconnect, force grant,
  and neutralization on every exit path.
- WebSocket header and payload length fuzzing with strict size limits.
- UDP missing, duplicate, reordered, malformed, old, and wrapped sequences.
- Persistent-column behavior when one or more of the 64 chunks are absent for
  several source snapshots; decoding must continue without a complete frame.
- Deflate/raw negotiation, decompression failure, stale frame rejection, and
  latest-frame queue replacement.
- Every keyboard, gamepad, and touch control mapped through protocol v2,
  especially D/Y, Start, Back, Exit, and simultaneous direction/action input.
- A single Exit edge emits one `exit\n`, its newline passes the workbench
  RESYNC filter within the bound, and held/replayed browser input cannot emit a
  second Exit command.
- Host parser fragmentation and every supported binary audio payload.

### Integration tests

- Local fake workbench UDP/serial peers drive the gateway and a headless
  browser; verify pixels, typed audio events, input bytes, reset/RPM bounds,
  and neutral disconnect.
- Browser popup success, rejected identity, cancelled login, opener-less
  fragment fallback, expired session, ticket replay, and exact-origin checks.
- Two browsers contend for control while both continue receiving frames.
- A second local desktop/gateway process fails the shared ownership lock
  without sending `hello`; a deliberate second-LAN-host test demonstrates and
  documents the workbench's latest-sender takeover and resulting alert.
- Slow viewer and deliberately lossy connection do not increase controller
  latency or memory use.
- Tunnel restart, gateway restart, USB unplug/replug, workbench Wi-Fi loss,
  laptop sleep/wake, and phone background/foreground.

### Hardware and mobile soak

Test at least iOS Safari and Android Chrome over local Wi-Fi and a real mobile
data path. Use representative static, animation-heavy, MicroPython, and native
console workloads. Run a 30-minute soak plus a longer unattended viewer soak.

## Acceptance criteria

- At least 15 displayed FPS over mobile data; target 20 FPS at 600 RPM.
- Gateway capture-to-browser-display latency below 100 ms p95 where the mobile
  network RTT makes that achievable; report network RTT separately.
- Browser input-to-gateway below 80 ms p95.
- Input-to-visible-board-response below 200 ms p95 on the reference mobile
  test path.
- Asset-audio event reaches the browser below 100 ms p95.
- Neutral input is written within 250 ms of a detected disconnect/revoke and
  within the server heartbeat deadline for an undetectable half-open network.
- No unbounded queue or monotonic memory growth in a 30-minute run.
- No workbench SPI capture drops attributable to gateway telemetry load.
- LAN receive/decode behavior matches the current latest-column semantics:
  missing chunks make only their columns stale and never stall publication.
- A slow viewer cannot degrade controller input latency beyond the agreed
  target.
- All authentication and authorization negative tests fail before privileged
  state changes, with secrets absent from logs.

Latency measurements must name their endpoints and include p50, p95, p99,
sample count, mobile network RTT, displayed FPS, and loss. Do not combine
gateway processing time and unpredictable carrier RTT into one unexplained
number.

## Deployment and operations

1. Create an Oracle Always Free VM and assign its reserved public IP.
2. Create an A record for `ventilastation-board.protocultura.net` pointing at
   that address; wait for it to resolve before starting Caddy.
3. Install `frps`, Caddy, and oauth2-proxy on the VM. Set `proxyBindAddr` to
   loopback, firewall the returned gateway port, and allow only 22, 80, 443,
   and the authenticated frp control port as needed.
4. Create a Google OAuth web client with the exact callback
   `https://ventilastation-board.protocultura.net/oauth2/callback`; configure
   oauth2-proxy's client and cookie secrets outside the repository.
5. Install `frpc` on the workbench computer and configure its local target as
   the gateway's `127.0.0.1:8765`. Store the frp token outside the repository.
6. Generate the ticket key and initialize the local ACL database; grant the
   owner admin access locally.
7. Start the gateway as a user service with restart-on-failure, bounded logs,
   a fixed serial selector, and no broad filesystem permissions.
8. Ensure the desktop hardware emulator is stopped; start the gateway and let
   its one-second `hello` loop become the workbench's sole UDP subscriber.
9. Start frpc only after the gateway health check succeeds.
10. Deploy the web adapter and UI through the existing GitHub Pages build.
11. Run the public authentication, ticket replay, lease, neutralization, and
   latency smoke tests after every gateway or Pages deployment.

The operational runbook must include granting/revoking a user, disconnecting
an active user, rotating signing and tunnel credentials, identifying the
current controller, stopping public access immediately, finding safe audit
records, and recovering from USB/tunnel failures.

## Open decisions

- DNS-zone credentials for the board hostname and the Oracle home region.
- Personal-Google exact-email policy versus Google Workspace group policy.
- Maximum viewer count and outbound bitrate for this computer/uplink.
- Whether the first controller policy is immediate first-come-first-served or
  owner approval from the local CLI.
- SQLite state location and audit retention period.
- `HOST_EVENT` binary sub-layout after the shared typed-event model is
  extracted.
- Whether console chip audio sends register events to browser WASM or PCM from
  the gateway, especially for NES DMC.
- Whether WSS meets the measured mobile latency target before adding WebRTC.

None of these decisions changes the main trust model: Google/oauth2-proxy identifies
the person, the gateway ACL authorizes the board role, and the exclusive lease
authorizes live input.

## External references

- [What is GitHub Pages?](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)
- [frp configuration](https://gofrp.org/en/docs/features/common/configure/)
- [Caddy forward authentication](https://caddyserver.com/docs/caddyfile/directives/forward_auth)
- [oauth2-proxy Caddy integration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/integration/)
- [MDN `DecompressionStream`](https://developer.mozilla.org/en-US/docs/Web/API/DecompressionStream/DecompressionStream)
- [MDN WebSocket client guidance](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications)
