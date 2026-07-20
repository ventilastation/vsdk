# Remote physical-workbench access from the web emulator

Status: implemented runbook, reconciled with `main` on 2026-07-20.

This document defines the production path from the static GitHub Pages
emulator to a physical Ventilastation board attached by USB to a developer
workbench. It is designed for a remote mobile browser: Google sign-in happens
at the public edge, the browser receives paced display frames and audio host
commands, and only an authorised controller can send emulated input.

The current deployment uses an ngrok HTTPS endpoint. It replaces the earlier
Oracle/frp/Caddy proposal: it has no inbound router port, no VPS, and no
Cloudflare account. The public endpoint is an ngrok free development domain,
so this deployment is deliberately a test/small-private-group service rather
than a general public product.

## Scope and constraints

- GitHub Pages hosts only the existing static emulator at
  `https://ventilastation.protocultura.net/emulator/?remote=1`.
- The workbench computer owns USB serial and is the sole UDP telemetry client
  for the board on port 5005.
- The public tunnel forwards solely to `127.0.0.1:8765`; the gateway does not
  listen on a LAN or public interface.
- Google authentication is required before either `/auth/start` or `/ws` can
  reach the gateway. The gateway then verifies role and controller lease.
- The normal browser emulator remains available without a login.

## Architecture

```text
GitHub Pages emulator (phone or desktop)
          |  HTTPS / WSS
          v
ngrok edge: Google OAuth + email allowlist + verified identity header
          |  HTTPS, loopback target only
          v
remote_gateway.py on the workbench computer (127.0.0.1:8765)
   | UDP 5005 telemetry       | USB serial input / host events
   v                          v
workbench ESP32-S3        physical DUT
```

The workbench's 64 UDP APA102 chunks are not proxied directly. The gateway
maintains the freshest capture, decodes it, compresses/paces RGB frames for
the WebSocket client, and forwards sound/music/notes commands as structured
host events. This prevents the mobile connection from carrying the roughly
13 Mbit/s raw LAN stream and favours current frames over backlog.

## Trust model and access control

There are three independent decisions:

1. ngrok's Google OAuth identifies the visitor and enforces a small email
   allowlist before traffic reaches the workbench.
2. The gateway issues a one-use, short-lived WebSocket ticket only from the
   edge-injected verified email. The browser cannot set this identity.
3. The gateway ACL assigns a board role. A controller must also acquire the
   exclusive lease before input is forwarded.

Roles are default-deny:

| Role | Permission |
| --- | --- |
| `viewer` | See status, frames, and audio commands. |
| `controller` | Viewer permissions and eligibility for the input lease. |
| `operator` | Controller permissions plus authorised workbench operations. |
| `admin` | Operator permissions plus ACL/session administration. |

The initial ACL is managed locally, not from the public endpoint:

```text
python -m emulator.remote_gateway acl grant person@example.com controller --board workbench-1
python -m emulator.remote_gateway acl revoke person@example.com --board workbench-1
python -m emulator.remote_gateway sessions list
```

Revoking a controller releases its lease and sends neutral input immediately.
Removing an email from the ngrok policy blocks future sign-ins; remove its
gateway ACL entry or disconnect its session when immediate loss of access is
required.

## Authentication and WebSocket flow

1. A user opens the Pages emulator and chooses **Connect physical board**.
2. The adapter opens `<gateway>/auth/start` in a popup. ngrok requires Google
   sign-in and accepts only the listed emails.
3. ngrok removes caller-supplied `X-Remote-Email`/`X-Remote-Subject` headers,
   then injects `X-Remote-Email` from its verified OAuth identity.
4. The loopback gateway checks its ACL and returns a signed, 30--60 second,
   one-use ticket to the opener with `postMessage`.
5. The adapter opens `wss://<gateway>/ws?ticket=...`. The gateway validates
   ticket signature, audience, origin, expiry, and unused ticket identifier
   before accepting the socket.
6. The browser requests the exclusive controller lease before it sends input.
   On disconnect/expiry/revocation, the gateway sends neutral input to USB.

WebSocket query tickets are unavoidable in this browser flow, so access logs
must redact them. Tickets contain no reusable Google credential and are
consumed atomically.

## ngrok traffic policy

Keep the live token and policy outside the repository. The installed policy
must have these operations in this order:

```yaml
on_http_request:
  - actions:
      - type: oauth
        config:
          provider: google
          auth_id: vsdk-remote-workbench
          idle_session_timeout: 15m
          max_session_duration: 1h
  - expressions:
      - "!(actions.ngrok.oauth.identity.email in ['allowed@example.com'])"
    actions:
      - type: deny
  - actions:
      - type: remove-headers
        config:
          headers: [X-Remote-Email, X-Remote-Subject]
      - type: add-headers
        config:
          headers:
            X-Remote-Email: "${actions.ngrok.oauth.identity.email}"
```

The remove-then-add sequence is mandatory. It prevents a visitor from
smuggling a conflicting identity header to the gateway. This trusted-proxy
mode is safe only while the gateway is loopback-only and ngrok is its only
public path.

ngrok free endpoints use an assigned `*.ngrok-free.dev` development domain
and have a small monthly OAuth identity limit. A team/shared deployment should
use a paid static domain or a self-hosted tunnel/identity-provider edge before
expanding the allowlist.

## Local configuration and operation

Store all secrets in an owner-only directory outside the repository, for
example `~/.config/vsdk/remote-workbench/`:

- `gateway.env`: board address, serial device, trusted-proxy mode, ACL seed.
- `ticket.key`: 32-byte ticket-signing key.
- `ngrok-authtoken` and `ngrok.yml`: ngrok account credential/configuration.
- `ngrok-policy.yml`: Google OAuth, allowlist, and header sanitisation policy.

Never commit any of these files, OAuth credentials, tickets, passwords, or
personal email lists.

Start the gateway with its owner-only environment file and bind it to
loopback:

```text
set -a; source ~/.config/vsdk/remote-workbench/gateway.env; set +a
REMOTE_WORKBENCH_AUTH_MODE=trusted-proxy \
  python -m emulator.remote_gateway serve
```

Start ngrok in a separate supervised terminal:

```text
ngrok http 127.0.0.1:8765 \
  --config ~/.config/vsdk/remote-workbench/ngrok.yml \
  --traffic-policy-file ~/.config/vsdk/remote-workbench/ngrok-policy.yml
```

Set `web/remote-adapter.js` to the assigned HTTPS endpoint and deploy the
updated static emulator. A temporary staging endpoint can instead set
`window.VENTILASTATION_REMOTE_GATEWAY` before the page loads.

## Protocol and performance targets

The remote binary protocol has a fixed `VSRW`/versioned header. The useful
message classes are `FRAME_RGB`, `HOST_EVENT`, `STATUS`, `LEASE`, `INPUT`,
`FRAME_ACK`, `HEARTBEAT`, and operator commands. The initial target is 20
displayed frames per second at 600 RPM. Frames are independently compressed,
bounded in flight, and replaced by newer frames when a mobile client is slow.

`HOST_EVENT` carries only the existing safe browser host commands: `sound`,
`music`, `musicstop`, and `notes`. No shell, filesystem, flashing, arbitrary
serial, or raw UDP command is exposed. `INPUT` carries canonical controller
state plus a distinct exit edge; the gateway validates length/rate, enforces
the lease, and converts it to the existing USB input protocol.

## Deployment verification

1. Confirm the board is connected and the gateway reports USB and UDP ready.
2. Start ngrok. An unauthenticated request to its endpoint must redirect to
   ngrok Google OAuth rather than reach the gateway.
3. Load the deployed Pages emulator with `?remote=1`; choose **Connect
   physical board** and sign in with an allowlisted test identity.
4. Verify a fresh physical frame appears, then move through a menu with mobile
   or keyboard controls. Verify the board changes and the browser receives a
   sound event.
5. Attempt a second non-controller user: viewing may work if the ACL permits,
   but input must be denied while the controller lease is held.
6. Disconnect the controller and verify the gateway writes neutral input.

Focused regression tests are:

```text
python tests/test_remote_gateway.py
python tests/test_workbench_telemetry.py
node tests/test_remote_adapter.mjs
```

Record only non-secret smoke-test evidence: endpoint domain, login result,
connected role, frame count, input acknowledgement, and received host-event
type. Do not record tunnel tokens, tickets, cookies, OAuth tokens, or
passwords.
