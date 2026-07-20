# POV colour pipeline and calibration

Ventilastation converts game RGB into APA102 LED values through one calibrated
pipeline shared by MicroPython and native Retro-Go games. This replaces the
old fixed intensity tables when a valid profile is active, while retaining
those tables as a boot-time fallback for an invalid or missing profile.

## Signal path

```text
game RGB code
  -> source-transfer decode (sRGB or configured power gamma)
  -> linear target light
  -> master, white balance, radial, and per-LED adjustments
  -> APA102 global-brightness + RGB PWM solver
  -> [0xe0 | GB, B, G, R] LED frame
  -> workbench capture (four bytes preserved verbatim)
  -> desktop emulator profile decoder
  -> monitor sRGB preview
```

For a fixed angular column, an outer LED covers a longer arc than an inner
one. The profile's radial term compensates the corresponding lower light per
display area. The initial model uses `(led + 1) / 54` as radius and applies
`radius ^ radial_exponent`; a per-LED gain then corrects the remaining strip,
optical, and supply variation.

Rotation speed is a timing-health concern, not a normal brightness multiplier:
at a fixed angular resolution, a slower turn also gives each angular sample
proportionally more illumination time.

## Profile format and NVS

The canonical profile is the 319-byte little-endian `PCAL` v1 payload stored
in NVS as `voom_pov` / `color_v1`. `col_offset` remains a separate i32 key.
It is understood by the MicroPython renderer, Retro-Go POV driver, and desktop
emulator.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | magic `PCAL` |
| 4 | 1 | schema version (`1`) |
| 5 | 1 | flags, currently zero |
| 6 | 2 | total payload length (`319`) |
| 8 | 4 | monotonically increasing generation |
| 12 | 15 | source transfer/gamma, master, white balance, radial exponent, GB floor/ceiling |
| 27 | 18 | LED-to-preview 3×3 matrix, signed Q12 |
| 45 | 108 | 54 LED gain trims, Q10 |
| 153 | 64 | 32 APA102 global-brightness response values, Q15 |
| 217 | 102 | three 17-knot PWM response curves, Q15 |

The profile persists calibration *parameters and measured response knots*, not
render LUTs. C builds source-decode, radial, and inverse PWM tables when a new
profile is applied. Two preallocated pipeline states are used: the inactive
state is built completely, then an atomic index swap makes it visible to the
render task. Thus a `povcal set` takes effect on the next rendered column
without a reboot or partial LUT.

The current profile supports source transfer, master brightness, RGB white
balance, radial exponent, per-LED gain, and APA102 global-brightness bounds.
The desktop workbench panel initializes its master/radial sliders from the
acknowledged profile and provides Save/Revert/Factory controls. The response
curves and preview matrix are already part of the stable payload; curve and
matrix editing are the next calibration-tool addition.

## APA102 encoding

An APA102 has three 8-bit channel PWMs and a shared 5-bit global-brightness
control. Its global-brightness PWM is about 582 Hz, which can produce visible
blinking on a spinning rotor. For every LED the encoder therefore starts at
the highest permitted global level and uses RGB PWM for normal dimming. It
lowers global brightness only when the brightest channel would otherwise fall
below RGB code 32, retaining useful channel resolution for very dark tones.
The calibrated inverse response curves still determine the three PWM values.

The real-time encoder does not perform divisions or curve searches per LED.
Applying a profile builds active and inactive sets atomically. The common path
uses compact internal-RAM per-LED/channel scales, a brightness-choice table,
and the PWM table for the highest permitted global brightness; it needs three
integer multiply-and-shifts and no PSRAM reads. Only dark pixels that must use
APA102 global-brightness modulation consult the PSRAM inverse-PWM fallback.
The two sets use about 186 KiB of PSRAM and 16 KiB of internal RAM, and are
rebuilt only after a valid `povcal set`, `revert`, or `factory` update.

The encoded 32-bit value is laid out in memory exactly as the LED bus expects:

```text
[0xe0 | global_brightness, blue_pwm, green_pwm, red_pwm]
```

## Calibration commands

Commands use the existing host-to-board newline stream. A successful command
replies with the full canonical profile:

```text
povcal_state <schema> <generation> <nbytes>\n<payload>
```

Errors reply with `povcal_error <generation> <code>`.

```text
povcal get
povcal set source_eotf srgb
povcal set source_eotf power 2200
povcal set master 700
povcal set white 1000 960 900
povcal set radial_exponent 1000
povcal set led_gain 17 1025
povcal set gb_floor 2
povcal set gb_ceiling 31
povcal test gray 96
povcal test radial 200
povcal test off
povcal commit
povcal revert
povcal factory
```

`set` updates RAM and the active renderer only. `commit` persists the profile,
so repeatedly dragging a calibration control does not wear NVS. `revert`
reloads the committed NVS blob. `factory` creates the canonical default in RAM
and can itself be committed.

MicroPython handles these commands through `color_calibration.py`. Native
Retro-Go handles the same commands in `vs_host_bridge.c`, so a running console
game updates immediately instead of waiting for a return to the menu.

`povcal test` is deliberately RAM-only. It substitutes a gray, primary, white,
or centre-to-edge radial stimulus inside the shared encoder, after game pixels
are produced but before APA102 values are calculated. This makes a measurement
pattern identical in MicroPython and native games, without altering the saved
profile. Use `povcal test off` before returning to normal content.

## Render-performance comparison

`povperf` profiles the ESP32-S3 GPU task only when explicitly enabled. It
times one physical angular update: queueing the previous APA102 DMA buffer,
rendering both arms, waiting for DMA only when rendering did not hide its
transfer time, and copying both finished arm buffers. It does not print from
the render task or persist any setting.

Run the same steady rotor speed and the same scene twice:

```text
povperf mode legacy
povperf start
# let at least several complete rotations pass
povperf status
povperf stop

povperf mode calibrated
povperf start
# same duration and scene
povperf status
povperf stop
```

Use a busy VS2 scene such as `vixeous` or `mapdemo`; `povperf_state` records
whether VS2 was active and its current layer, sprite, and tilemap slot counts.
`povperf_timing` reports mean and maximum total/render/DMA-wait/copy time in
microseconds. `deadline_us` is the measured revolution period divided by 256;
an update is an overrun when `max_total_us` exceeds that budget. `skipped` is
the number of angular updates the GPU task observed it had passed before it
could render, so `complete=1`, zero overruns, and zero skipped updates are the
evidence that every scheduled column was prepared in time. `worst_slack_us`
is the minimum `deadline_us - total_us`; it should remain comfortably positive.

The profiler is for the MicroPython GPU/VS2 renderer. Native Retro-Go has its
own display loop and is not represented by these counters.

## Workbench and emulator

The workbench reassembles the two physical arms into a spatial image, but does
not interpret LED values. Conceptually it's a 256 × 54 × 4 byte, column-major
buffer of `[GB, B, G, R]` values -- on the wire it's chunked over UDP rather
than sent as one contiguous `frame_apa102` payload (see
[workbench.md#why-udp-not-tcp](workbench.md#why-udp-not-tcp)), but the
emulator reassembles it back into exactly that buffer before anything below
touches it.

This differs from the legacy `frame_rgb` full-frame format, which has only
three RGB bytes and remains available for synthetic renderers. The workbench
must preserve every captured APA102 LED datum byte; it may only reverse arm 0,
place the arms in their correct angular columns, and carry a row forward over
columns for which the rotor sent no SPI update.

When the emulator connects to the workbench UART bridge, it sends `povcal get`.
It validates the reply and uses the profile's APA102 response curves and
LED-to-preview matrix to decode raw capture into relative linear LED light,
then encodes monitor RGB as sRGB. It does not apply source gamma, radial gain,
or white balance a second time: those are already embodied in captured APA102
values.

A desktop monitor is not a calibrated substitute for the LEDs' absolute
luminance or gamut. The preview is intended to preserve the calibrated
relative light and chromaticity. Its future view-exposure control must remain
display-only and never change board calibration.

## Verification

`python3 tests/run_tests.py` covers:

- binary profile parsing, profile generation, and emulator preview decoding;
- MicroPython `povcal` command lifecycle and persistence boundary;
- native C profile validation, atomic active state, radial/global-brightness
  quantization, and APA102 frame packing;
- raw four-byte APA102 desktop preview input;
- existing VS2 renderer parity tests with the pipeline inactive.

The Retro-Go component includes the same C implementation through a tiny
wrapper, rather than copying the encoder. The normal host test suite compiles
that wrapper; a full Retro-Go firmware build and real rotor measurement remain
required before considering a profile production-calibrated.

## Remaining calibration work

1. Use the controlled gray, primary, white, and radial patterns with a
   photodiode/colorimeter to measure the installed rotor.
2. Expose response-knot and preview-matrix editing/import in the desktop tool.
3. Add the same profile-aware decoder to the web emulator.
4. Build and exercise MicroPython and Retro-Go images on a real rotor, then
   tune the factory/default profile from measured data.
