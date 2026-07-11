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

Voom uses the local player's `damagecount` and `armorpoints`:

- while `damagecount > 0`, the base strip uses entry 0 (black) of the active
  Doom damage palette; this preserves the palette-derived red rather than
  synthesizing a fixed red;
- otherwise the strip is blue at `clamp(armorpoints, 0, 200) / 200` brightness;
- damage red overrides shield blue because the strip is uniformly one colour;
- the servo receives `damagecount` normalized from `0..100` to `0..255`.

## Emulator preview

Both emulators present a compact, read-only preview at the stage's bottom
right: a 16-LED strip, a generic 0–255 servo dial (never mechanical degrees),
and two blinking button indicators. The preview consumes the same host command
state as the Arduino forwarder; it does not independently inspect Doom or VS2.
