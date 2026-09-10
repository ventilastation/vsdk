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
  -> APA102 global-brightness + RGB PWM solver (dark white balance applies here)
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

The canonical profile is the 325-byte little-endian `PCAL` v2 payload stored
in NVS as `voom_pov` / `color_v1` (the key name predates the schema version
living inside the payload). `col_offset` remains a separate i32 key. It is
understood by the MicroPython renderer, Retro-Go POV driver, and desktop
emulator.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | magic `PCAL` |
| 4 | 1 | schema version (`2`) |
| 5 | 1 | flags, currently zero |
| 6 | 2 | total payload length (`325`) |
| 8 | 4 | monotonically increasing generation |
| 12 | 21 | source transfer/gamma, master, white balance, dark white balance, radial exponent, GB floor/ceiling |
| 33 | 18 | LED-to-preview 3×3 matrix, signed Q12 |
| 51 | 108 | 54 LED gain trims, Q10 |
| 159 | 64 | 32 APA102 global-brightness response values, Q15 |
| 223 | 102 | three 17-knot PWM response curves, Q15 |

v2 adds the three dark white balance values; everything else keeps its v1
meaning. A board still holding a 319-byte v1 blob is migrated in place on the
next load, with the new field neutral, so its measured curves and hand-tuned
gains survive the upgrade instead of resetting to factory.

The profile persists calibration *parameters and measured response knots*, not
render LUTs. C builds source-decode, radial, and inverse PWM tables when a new
profile is applied. Two preallocated pipeline states are used: the inactive
state is built completely, then an atomic index swap makes it visible to the
render task. Thus a `povcal set` takes effect on the next rendered column
without a reboot or partial LUT.

The current profile supports source transfer, master brightness, RGB white
balance, dark white balance, radial exponent, per-LED gain, and APA102
global-brightness bounds. The desktop workbench panel initializes its
master/radial/dark-green sliders from the acknowledged profile and provides
Save/Revert/Factory controls. The response
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

Current rotors carry NS107S LEDs rather than APA102s. They share the wire
format, so the encoding above is unchanged, but their global-brightness stage
is a per-channel current gain whose three channels do not track each other
exactly as the level drops. A single shared `global_response` curve therefore
mispredicts two of the three channels in the dark, which shows up as a tint on
tones dim enough to use global-brightness modulation -- greenish dark greys on
the measured rotor.

## Dark white balance

`dark_white` describes that per-channel drift. It is a milli-gain per channel
in the same direction as the ordinary white balance: 1000 is neutral and
smaller means dimmer. It applies with a weight that is zero at `gb_ceiling`,
where the ordinary white balance already holds and bright tones are already
correct, and reaches full strength at `gb_floor`. Only tones the solver
actually pushes below the ceiling are affected.

The pipeline folds it into a per-channel effective global-brightness curve:

```text
effective_global[channel][level] = global_response[level] * 1000 / gain
gain = 1000 + (dark_white[channel] - 1000) * weight / 1000
weight = 0 at gb_ceiling, 1000 at gb_floor, linear in level between
```

Dividing is what makes the trim read as a brightness. Declaring a channel
dimmer down here means telling the solver that channel's global stage emits
more light per PWM count than the shared curve says, which the solver answers
with less PWM -- so the rendered tone loses that channel.

The correction is evaluated only while building the render LUTs, into tables
the encoder already consults (`dark_pwm_lut` is indexed by channel and
brightness already). The per-LED render path is unchanged and costs nothing
extra.

To trim a rotor by eye, put up a controlled dark stimulus, adjust, and persist:

```text
povcal test gray 24
povcal set dark_white 1000 960 1000
povcal commit
povcal test off
```

`povcal test gray` is deliberately a dark level here: the trim has no effect on
a stimulus bright enough to render at the ceiling. The desktop workbench panel
carries a "Dark green" slider over a narrow band around neutral, since green is
the axis that drifts on the measured rotor; red and blue keep the values the
board last acknowledged and are reachable through the command above.

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
povcal set dark_white 1000 960 1000
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

## Handoff and Paint performance

`povperf` profiles the ESP32-S3 GPU task only when explicitly enabled. The
double-buffered renderer reports two paths separately. **Handoff** is
physical-column service: waiting for and queueing APA102 DMA plus copying the
published framebuffer row before the next SPI transfer. It is the per-column
hard deadline that protects a steady image. **Paint** is background projection:
producing rendered columns and complete 256-column rotations. It determines
how much visual work fits in a frame. Game-logic **Step** timing is separate
from this GPU profiler and must be measured by the scene/behavior profiler.
It does not print from the render task or persist any setting.

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
`povperf_timing` reports mean and maximum Handoff/Paint/DMA-wait/copy time in
microseconds. `deadline_us` is the Handoff budget: the measured revolution
period divided by 256. A Handoff overrun occurs when `total_us` exceeds that
budget. `skipped` is the number of physical angular updates the GPU task
passed within a revolution before it could service them. An accepted hall edge
begins a new measurement epoch, so its intentional phase correction is not
misreported as a near-full-revolution skip. `frames`,
`avg_frame_render_us` and `max_frame_render_us` measure Paint across complete
256-column rotations against `frame_deadline_us`. `complete=1` means both
physical and full-frame samples were collected; the numeric skip and overrun
fields remain independent so acceptance tools can enforce their own limits.
Zero Handoff overruns, positive Handoff slack, zero Paint frame overruns and a
bounded skip rate show that the output and projection paths are healthy.
`worst_slack_us` is the minimum Handoff slack, `deadline_us - total_us`; it
should remain positive.

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
- MicroPython `povcal` command lifecycle, persistence boundary, and the
  v1-to-v2 profile upgrade;
- dark white balance: neutral at the ceiling, trimming only the named channel
  once global-brightness modulation engages, and rejected outside its range;
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
   photodiode/colorimeter to measure the installed rotor. The dark white
   balance models the NS107S per-channel global-brightness drift as one scalar
   per channel with a linear ramp. If a measured sweep shows the drift is not
   linear in the level, the next step is three measured `global_response`
   curves rather than one curve plus a tilt; the render path already indexes
   its tables per channel, so that change stays inside profile parsing and LUT
   construction.
2. Expose response-knot and preview-matrix editing/import in the desktop tool.
3. Add the same profile-aware decoder to the web emulator.
4. Build and exercise MicroPython and Retro-Go images on a real rotor, then
   tune the factory/default profile from measured data.
