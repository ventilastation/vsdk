# Native App Handoff Plan

This document describes how heavyweight native apps such as `voom` should be launched from the
MicroPython-based Ventilastation launcher.

## Current Reality

The rotor firmware in `vsdk` is built as:

- MicroPython ESP32 firmware
- plus linked user C modules from `hardware/rotor/modules/...`
- plus frozen Python code from `apps/micropython/manifest.py`

Relevant files:

- `hardware/rotor/build.sh`
- `hardware/rotor/modules/micropython.cmake`
- `hardware/rotor/modules/povdisplay/povdisplay.c`
- `apps/micropython/ventilastation/native_apps.py`

That originally suggested same-firmware native takeover as the cleanest design.

However, the working `voom` codebase is now tracked as the `apps/retro-go` submodule in `vsdk`.
It is a Retro-Go fork with:

- an `esp32s3-devkit-c` target
- a `prboom-go` app partition
- custom POV display projection code inside `components/retro-go/drivers/display/ventilastation_pov.c`

So there are now two valid models:

1. short term: use the launcher hook to switch into a flashed `voom` partition and reboot
2. long term: merge `voom` into the MicroPython firmware as a same-image native runtime

## Current Recommended Path

For `voom`, the pragmatic path is now:

1. keep MicroPython as the default launcher runtime
2. expose a tiny hardware module, `vshw_native_apps`
3. map `native.voom` to a flashed app partition labelled `prboom-go`
4. call `esp_ota_set_boot_partition(...)`
5. restart the ESP32

This keeps the Python launcher contract stable while matching the code that already exists.

## Python Contract

From Python, the launcher sees a native slug such as `native.voom`.

Current Python pieces:

- `apps/micropython/ventilastation/native_apps.py`
- `apps/micropython/ventilastation/app_loader.py`
- `apps/micropython/ventilastation/platforms/__init__.py`

The launcher persists intent in:

- `ventilastation/boot.json`

The hardware platform optionally exposes:

- `vshw_native_apps.launch(name)`
- `vshw_native_apps.available(name)`
- `vshw_native_apps.last_exit_reason()`

## Hardware Hook

The rotor firmware now includes:

- `hardware/rotor/modules/native_apps/native_apps.c`

Current behavior:

- `"voom"` maps to app partition `"prboom-go"`
- `available("voom")` checks whether that partition exists on flash
- `launch("voom")` switches the boot partition and restarts the chip

This is a direct launcher hook even though the actual app is still a separate firmware partition.

## Combined Image Build

`vsdk` now contains the combined-image pieces needed for this handoff:

- partition layout: `hardware/rotor/partitions-voom.csv`
- image builder: `hardware/rotor/build_voom_image.py`
- flash helper: `hardware/rotor/flash_voom_image.py`
- convenience entrypoint: `hardware/rotor/build.sh voom-image`
- convenience entrypoint: `hardware/rotor/build.sh voom-flash`

That image layout is:

- `nvs`
- `otadata`
- `phy_init`
- `factory` for the `vsdk` MicroPython firmware
- `prboom-go` for the Voom native app

The builder assumes the current local parent-folder layout:

- `../micropython`
- `apps/retro-go`
- `../esp-idf-5.4` for `vsdk` / MicroPython
- `../esp-idf` for `voom` / Retro-Go

and it:

1. builds the `vsdk` MicroPython firmware,
2. builds Retro-Go `launcher` and `prboom-go`,
3. generates a custom partition table,
4. packs a final flash image containing both apps.

The current output image path is:

- `hardware/rotor/build/vsdk-voom-esp32s3.bin`

The builder accepts separate SDK overrides:

```sh
python3 build_voom_image.py \
  --micropython-idf-path ../esp-idf-5.4 \
  --retro-go-idf-path ../esp-idf
```

To flash the already-built combined image:

```sh
cd hardware/rotor
python3 flash_voom_image.py --port /dev/cu.usbmodemXXXX
```

To rebuild and flash in one step:

```sh
cd hardware/rotor
python3 flash_voom_image.py --build --port /dev/cu.usbmodemXXXX
```

Or through the shell entrypoint:

```sh
cd hardware/rotor
./build.sh voom-flash --build --port /dev/cu.usbmodemXXXX
```

## Launcher Entry

The default launcher menu now includes:

- `native.voom`

That entry currently uses an existing bundled menu tile and routes through:

- `system/launcher/code/__init__.py`
- `apps/micropython/ventilastation/native_apps.py`

## Existing Voom Fork Facts

The current `voom` tree lives at:

- `apps/retro-go`

Board target is defined in:

- `components/retro-go/targets/esp32s3-devkit-c/config.h`
- `components/retro-go/targets/esp32s3-devkit-c/env.py`

That target sets:

- `RG_TARGET_NAME` = `ESP32S3-DEVKIT-C`
- `IDF_TARGET` = `esp32s3`
- `FW_FORMAT` = `none`

The relevant build image in that fork uses:

- `launcher`
- `prboom-go`

Build command:

```sh
./rg_tool.py --target=esp32s3-devkit-c build-img launcher prboom-go
```

The resulting partition layout in that fork is:

- `launcher`
- `prboom-go`

## How Voom Generates The LED Image

The POV display path in the working fork lives in:

- `apps/retro-go/components/retro-go/drivers/display/ventilastation_pov.c`

The flow is:

1. Doom renders a normal 320 x 240 framebuffer.
2. `I_FinishUpdate()` copies that framebuffer into `vs_data`.
3. `vs_setup_projection_table()` precomputes a 256 x 54 polar lookup table.
4. `project_angle()` samples the framebuffer for one rotation angle and converts palette entries
   into LED colors using `brillos` and `intensidades_por_led`.
5. `gpu_step()` uses hall-sensor timing to stream two projected columns over SPI.

There is also a debug helper in `../voom/hex2png.py` that turns logged
projected hex output into a 256 x 54 PNG.

## Why This Is Better Than Forcing A MicroPython Extension

`voom` is not a normal Python extension candidate. It wants to own:

- framebuffer timing
- hall-sensor timing
- LED SPI output
- audio
- large native buffers

So the right abstraction is still a tiny Python launch surface with native ownership underneath.

## Current Build Status

The combined image flow is currently working with split SDK versions:

- `vsdk` / MicroPython builds under `ESP-IDF 5.4`
- `voom` / Retro-Go builds under `ESP-IDF 5.0.4`

The produced combined image is:

- `hardware/rotor/build/vsdk-voom-esp32s3.bin`

## Long-Term Option

If we later want a tighter integration, we can still replace the partition switch with a
same-firmware `voom` runtime under:

- `hardware/rotor/modules/voom/...`

That future path would reuse the same Python slug and the same `vshw_native_apps` control surface.

## Implementation Order

1. Finish Python-side registry and launch contract
2. Add `vshw_native_apps`
3. Switch `native.voom` into a flashed `prboom-go` partition
4. Add return-to-MicroPython semantics from the Voom firmware
5. Optionally replace partition switching with same-firmware takeover later
