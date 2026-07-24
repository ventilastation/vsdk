# Base control API

`base` provides a reusable, application-neutral control path for base hardware:

```text
main board app --UART--> headless base emulator --UART--> Arduino
```

The Arduino controls all 16 RGB strip LEDs, two button LEDs, and the servo. It
accepts newline-delimited `base` commands specified in
[host-protocol.md](host-protocol.md). The Raspberry Pi emulator validates a
line before forwarding its canonical form to the Arduino. Desktop and browser
emulators show the exact same normalized state in a bottom-right base preview.

## Safety boundary

The public servo value is always a byte (`0..255`). The Arduino maps it to its
private, measured-safe end points (`106` at rest and `13` at full travel for
the current base). No VS2 caller, native app, or Raspberry Pi process sends a
degree, PWM value, pin number, or calibration value.

Malformed/out-of-range commands are ignored. The Arduino starts safely with
the strip and button LEDs off and the servo at rest.

## VS2 API

```python
from vs2 import base

base.leds.set_all(255, 0, 0)
base.leds.off()
base.servo.set(128)
base.buttons.set(mask=base.BUTTON_LED_ALL, blink_ms=250)
base.buttons.off()
```

`base.BUTTON_LED_1`, `base.BUTTON_LED_2`, and `base.BUTTON_LED_ALL` select the
two button lights. All APIs reject values outside their documented ranges and
deduplicate unchanged state. They are safe no-ops on an emulator without an
Arduino.

## Voom mapping

Voom uses entry 0 of the active Doom palette and the local player's armor.
Let `armor_blue = clamp(armorpoints, 0, 200) * 255 / 200`; read `(r, g, b)`
from palette entry 0 after Doom's own Gamma Boost has been applied.

- `(0, 0, 0)` means the player is okay: send `(0, 0, armor_blue)`.
- Otherwise, when `max(r, g) <= 63`, preserve the weak red/green palette
  colour and blend it with armor: `blue = min(255, b + armor_blue *
  (63 - max(r, g)) / 63)`.
- When either red or green exceeds 63, send the palette colour unchanged:
  `(r, g, b)`. This includes strong damage and acid/radiation effects.
- The servo independently receives player health normalized from `0..100` to
  `0..255`; Doom health above 100 holds the healthy endpoint.

The blend intentionally happens before gamma correction, so the 63 threshold
and the game-state relationship remain in Doom palette space.

## Base strip gamma

The Arduino applies one 256-entry, 2.2 gamma lookup table to each final RGB
channel before writing the NeoPixels. The desktop and web previews apply the
same curve. This compensates for Doom palette values targeting a gamma-corrected
monitor while the strip receives near-linear PWM values.

The POV renderer is related but cannot be copied directly: its
`intensidades[54][256]` lookup has a distinct response for every radial LED,
combining gamma with physical LED-position compensation. The base's identical
strip LEDs use one common curve. Future measured calibration may replace the
2.2 table and add per-channel gains, but that remains Arduino-local and does
not change the public byte API.

## Device identification (RESYNC)

The Arduino also watches its incoming byte stream for the RESYNC marker
(see
[input-protocol-v2.md](input-protocol-v2.md#resync--device-identification)),
independent of the `base ...` command parser. On match it reinitializes its
state (strip off, servo at rest, button LEDs off — the same defaults
`setup()` establishes) and prints
`VENTILASTATION BASE <version> <githash>`. The Arduino has no reset
facility and nothing in its simple poll loop can wedge, so this
reinitialization is the full RESYNC response — there is no separate "hard
reset" path. `<githash>` is `unknown`: the Arduino build has no git-hash
injection today, unlike the ESP-IDF firmwares.

## Legacy Super Ventilagon relay

The Arduino also still answers Super Ventilagon's older relay protocol
(`arduino <cmd>` in [host-protocol.md](host-protocol.md), forwarded to the
Arduino as `ventilagon start`/`stop`/`reset`/`attract` — the same
newline-terminated "`<domain> <verb>`" shape as `base ...` above, just
without arguments). This drives a self-contained, on-device light-and-servo
show (fixed color/duration sections, ending in the strip off) timed entirely
on the Arduino; the host only starts, stops, or resets it. It shares the
servo and button-LED state with the `base ...` protocol above, but paints
the strip with its own untouched colors rather than through the gamma
table, to keep matching the original show.

## Emulator preview

Both emulators present a compact, read-only preview at the stage's bottom
right: a 16-LED strip, a generic 0–255 servo dial (never mechanical degrees),
and two blinking button indicators. The preview consumes the same host command
state as the Arduino forwarder; it does not independently inspect Doom or VS2.
