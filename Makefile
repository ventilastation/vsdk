.PHONY: micropython-webassembly web-runtime-bundle web-emulator-bundle remote-workbench-setup remote-workbench-doctor remote-workbench-run remote-workbench-smoke vsdk initial-flash flash-recovery voom launcher flash-launcher retro-core fmsx run-emulator voom-sounds generate-roms build-fs configure-board configure-board-v2 configure-board-eu wifi-provision workbench-build workbench-flash workbench-monitor workbench-wifi-provision base-monitor list-boards register-rotor register-workbench register-base

PORT ?=
MAC ?=
BAUD ?= 2000000

# --- Board selection ---
# Both boards use identical ESP32-S3 USB descriptors. The detector performs a
# firmware-level probe and returns the unique board of the type required by
# the target. An explicit PORT always wins, which is useful when several
# boards of one type are attached or when a particular board must be forced.
PYTHON ?= python3
BOARD_DETECTOR := $(abspath tools/find_board.py)
ROTOR_PORT_TARGETS := initial-flash flash-recovery flash-launcher configure-board configure-board-v2 configure-board-eu wifi-provision
WORKBENCH_PORT_TARGETS := workbench-flash workbench-monitor workbench-wifi-provision
BASE_PORT_TARGETS := base-monitor
PORT_TARGETS := $(ROTOR_PORT_TARGETS) $(WORKBENCH_PORT_TARGETS) $(BASE_PORT_TARGETS)
ROTOR_GOALS := $(filter $(ROTOR_PORT_TARGETS),$(MAKECMDGOALS))
WORKBENCH_GOALS := $(filter $(WORKBENCH_PORT_TARGETS),$(MAKECMDGOALS))
BASE_GOALS := $(filter $(BASE_PORT_TARGETS),$(MAKECMDGOALS))

ifneq ($(strip $(ROTOR_GOALS)),)
ifneq ($(strip $(WORKBENCH_GOALS)),)
ifeq ($(strip $(PORT)),)
$(error Targets for both board types need separate invocations or an explicit PORT=...)
endif
endif
endif
ifneq ($(strip $(ROTOR_GOALS)),)
ifneq ($(strip $(BASE_GOALS)),)
ifeq ($(strip $(PORT)),)
$(error Targets for both board types need separate invocations or an explicit PORT=...)
endif
endif
endif
ifneq ($(strip $(WORKBENCH_GOALS)),)
ifneq ($(strip $(BASE_GOALS)),)
ifeq ($(strip $(PORT)),)
$(error Targets for both board types need separate invocations or an explicit PORT=...)
endif
endif
endif

BOARD_KIND :=
ifneq ($(strip $(ROTOR_GOALS)),)
BOARD_KIND := ventilastation
endif
ifneq ($(strip $(WORKBENCH_GOALS)),)
BOARD_KIND := workbench
endif
ifneq ($(strip $(BASE_GOALS)),)
BOARD_KIND := base
endif

ifneq ($(strip $(BOARD_KIND)),)
ifeq ($(strip $(PORT)),)
PORT := $(shell $(PYTHON) "$(BOARD_DETECTOR)" --board "$(BOARD_KIND)" $(if $(MAC),--mac "$(MAC)",))
endif
ifeq ($(strip $(PORT)),)
$(error Could not select a $(BOARD_KIND) board; run 'make list-boards' or pass PORT=...)
endif
endif

SERIAL_LOCK_FILE ?= /tmp/vsdk-serial.lock

VSDK_BOARD ?= VENTILASTATION
VSDK_BOARD_VARIANT ?= SPIRAM_OCT
VSDK_BOARD_DIR := $(abspath ./hardware/rotor/boards/VENTILASTATION)
VSDK_MODULES := $(abspath ./hardware/rotor/modules/micropython.cmake)
VSDK_FROZEN_MANIFEST := $(abspath ./apps/micropython/manifest.py)
MICROPYTHON_ROOT ?= ./hardware/rotor/micropython
MICROPYTHON_PORT_DIR := $(abspath $(MICROPYTHON_ROOT)/ports/esp32)
RETRO_GO_DIR := ./apps/retro-go

# The board's USB-CDC serial port re-enumerates on reset, so concurrent flash
# commands can interrupt each other mid-transfer. Use a host-side lock to
# serialize any target that talks to the board over the flashing port.
# macOS ships lockf; Linux ships flock (same "<tool> <file> <cmd...>" form).
# Fall back to no locking rather than failing if neither is present.
SERIAL_LOCK := $(shell if command -v lockf >/dev/null 2>&1; then echo lockf $(SERIAL_LOCK_FILE); elif command -v flock >/dev/null 2>&1; then echo flock $(SERIAL_LOCK_FILE); fi)

# ESP-IDF: MicroPython, Retro-Go and the workbench all build against one
# version now. The Makefile does NOT source export.sh for you -- that used to
# happen per target (via a wrapping login shell) and added seconds to every
# single step. Instead, source it once yourself before running make; it
# stays active for the rest of the shell session. See docs/internals/building.md.
IDF_SOURCE_HINT := source ../../esp-idf/esp-5.5.2/export.sh
NO_IDF_TARGETS := list-boards register-rotor register-workbench register-base micropython-webassembly web-runtime-bundle web-emulator-bundle remote-workbench-setup remote-workbench-doctor remote-workbench-run remote-workbench-smoke run-emulator voom-sounds generate-roms build-fs base-monitor
IDF_GOALS := $(filter-out $(NO_IDF_TARGETS),$(MAKECMDGOALS))
ifneq ($(strip $(IDF_GOALS)),)
ifeq ($(strip $(IDF_PATH)),)
$(error ESP-IDF environment not active in this shell. Run '$(IDF_SOURCE_HINT)' once per session (see docs/internals/building.md) before make $(firstword $(IDF_GOALS)))
endif
endif

# The port drops and re-enumerates for a couple of seconds after every
# flash's hard reset, so a target that runs right after another one (e.g.
# initial-flash followed by configure-board) must wait for the port to come
# back before opening it. The serial lock alone can't help: it serializes
# access but the previous holder exits while the board is still
# re-enumerating.
WAIT_FOR_PORT := $(abspath tools/wait_for_port.py)
wait-port = python3 "$(WAIT_FOR_PORT)" --port "$(PORT)"

# Build/flash one Retro-Go app ($(1) = app name, e.g. prboom-go).
rg-build = cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation build $(1)
rg-flash = $(SERIAL_LOCK) bash -c '$(wait-port) && cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation --port="$(PORT)" --baud="$(BAUD)" flash $(1)'

# Targets that talk to a board need PORT (auto-selected above); targets that
# provision WiFi also need credentials. Checked at parse time so the failure
# is instant even under parallel make.
WIFI_TARGETS := wifi-provision workbench-wifi-provision
ifneq ($(filter $(PORT_TARGETS),$(MAKECMDGOALS)),)
ifeq ($(strip $(PORT)),)
$(error Set PORT=/dev/cu.usbmodemXXXX (or run 'make list-boards'))
endif
endif
ifneq ($(filter $(WIFI_TARGETS),$(MAKECMDGOALS)),)
ifeq ($(strip $(WIFI_SSID)),)
$(error Set WIFI_SSID=... WIFI_PASS=...)
endif
endif

list-boards:
	$(PYTHON) "$(BOARD_DETECTOR)" --list

# Remember which USB id is which board, so every other target can select it
# by a plain, instant descriptor lookup instead of the multi-second RESYNC
# probe (see tools/find_board.py). One-time per board (its id survives
# reflashing -- it's the factory MAC, not anything stored on the board).
# With only one board attached, no PORT is needed; with several, pass
# PORT=... to say which one you mean.
register-rotor:
	$(PYTHON) "$(BOARD_DETECTOR)" --register ventilastation $(if $(PORT),--port "$(PORT)",)

register-workbench:
	$(PYTHON) "$(BOARD_DETECTOR)" --register workbench $(if $(PORT),--port "$(PORT)",)

register-base:
	$(PYTHON) "$(BOARD_DETECTOR)" --register base $(if $(PORT),--port "$(PORT)",)

micropython-webassembly:
	./tools/build-micropython-webassembly.sh

web-runtime-bundle:
	python3 ./tools/generate_web_runtime_bundle.py

web-emulator-bundle:
	./tools/build-web-emulator-bundle.sh

# Remote workbench operator path. Setup is the only command needing options;
# run and smoke reuse the private config under ~/.config/vsdk/remote-workbench.
EMAIL ?=
REMOTE_WORKBENCH_SERIAL ?= auto
REMOTE_WORKBENCH_HOST ?= 192.168.1.100

remote-workbench-setup:
	@if [ -z "$(EMAIL)" ]; then echo "Set EMAIL=you@example.com" >&2; exit 2; fi
	python3 ./tools/remote_workbench.py setup --email "$(EMAIL)" --serial-port "$(REMOTE_WORKBENCH_SERIAL)" --telemetry-host "$(REMOTE_WORKBENCH_HOST)"

remote-workbench-doctor:
	python3 ./tools/remote_workbench.py doctor

remote-workbench-run:
	python3 ./tools/remote_workbench.py run

remote-workbench-smoke:
	python3 ./tools/remote_workbench.py smoke

vsdk:
	$(MAKE) -C "$(MICROPYTHON_PORT_DIR)" V=1 BOARD="$(VSDK_BOARD)" BOARD_DIR="$(VSDK_BOARD_DIR)" BOARD_VARIANT="$(VSDK_BOARD_VARIANT)" USER_C_MODULES="$(VSDK_MODULES)" FROZEN_MANIFEST="$(VSDK_FROZEN_MANIFEST)" all

# initial-flash is a bench-dev convenience: it writes MicroPython to both the
# factory slot and the micropython (ota_2) slot over USB, plus an empty
# formatted LittleFS image to the vfs partition, for fast local iteration
# without waiting on WiFi/OTA. It is NOT the bring-up procedure for a new
# board -- use flash-recovery for that (see docs/internals/ota.md).
initial-flash: vsdk
	$(SERIAL_LOCK) bash -c '$(wait-port) && python3 ./hardware/rotor/flash_vsdk_image.py --port "$(PORT)" --baud "$(BAUD)" --board "$(VSDK_BOARD)" --board-variant "$(VSDK_BOARD_VARIANT)"'

# flash-recovery is the bring-up procedure for a new (or fully-erased) board:
# USB-flashes only the `factory` partition (the permanent recovery
# environment) + NVS, read-first so re-running this doesn't clobber an
# already-provisioned board (pass FORCE=1 to overwrite). Everything else --
# vfs, native apps, and the real ota_2 micropython copy -- installs over WiFi
# via recovery's own OTA loop once it boots. Pass WIFI_SSID=/WIFI_PASS= to
# also provision devel_wifi in the same step.
FORCE ?=
flash-recovery: vsdk
	$(SERIAL_LOCK) bash -c '$(wait-port) && python3 ./hardware/rotor/flash_recovery_image.py --port "$(PORT)" --baud "$(BAUD)" --board "$(VSDK_BOARD)" --board-variant "$(VSDK_BOARD_VARIANT)" $(if $(FORCE),--force,) $(if $(WIFI_SSID),--wifi-ssid "$(WIFI_SSID)" --wifi-password "$(WIFI_PASS)",)'

voom:
	$(call rg-build,prboom-go)

launcher:
	$(call rg-build,launcher)

flash-launcher: launcher
	$(call rg-flash,launcher)

retro-core:
	$(call rg-build,retro-core)

fmsx:
	$(call rg-build,fmsx)

# --- Hardware dev loop via the workbench ---
# The workbench captures the DUT's real LED SPI bus and streams the frames to
# the desktop emulator over Wi-Fi (see docs/internals/workbench.md). BOARD_IP
# defaults to the workbench's mDNS name when omitted.
run-emulator:
	cd emulator && python emu.py $(BOARD_IP) --remote

# --- Voom sound assets ---
# Pre-render Doom's WAD audio into system/voom/sounds/*.mp3 so the host that
# plays audio (the desktop emulator, or the base over serial) has the files
# for the triggers Voom sends. SFX need only
# ffmpeg; music needs a MIDI synth + soundfont (one-time: sudo apt install fluidsynth).
# Re-run whenever the WAD changes.
voom-sounds:
	cd emulator && python build_voom_sounds.py

generate-roms:
	python3 tools/generate_roms.py

build-fs:
	python3 hardware/rotor/build_micropython_fs.py

# --- Main-board wiring configuration ---
# The physical wiring is stored in NVS namespace "vs_board", shared by
# MicroPython and every native Retro-Go app. The default values are for a
# Ventilastation III. Re-run after changing a board's wiring; it survives every
# firmware and filesystem reflash.
HALL_GPIO ?= 7
IRDIODE_GPIO ?= 7
LED_SPI_HOST ?= 2
LED_CLK ?= 12
LED_MOSI ?= 13
LED_CS ?= 14
LED_FREQ ?= 20000000
SERIAL_UART ?= 2
SERIAL_TX ?= 5
SERIAL_RX ?= 6
SERIAL_BAUD ?= 115200

configure-board:
	$(SERIAL_LOCK) bash -c '$(wait-port) && python3 ./tools/provision_board.py --port "$(PORT)" \
		--hall-gpio "$(HALL_GPIO)" --irdiode-gpio "$(IRDIODE_GPIO)" \
		--led-spi-host "$(LED_SPI_HOST)" --led-clk "$(LED_CLK)" \
		--led-mosi "$(LED_MOSI)" --led-cs "$(LED_CS)" --led-freq "$(LED_FREQ)" \
		--serial-uart "$(SERIAL_UART)" --serial-tx "$(SERIAL_TX)" \
		--serial-rx "$(SERIAL_RX)" --serial-baud "$(SERIAL_BAUD)"'

# The legacy boards use the original LED/UART wiring. The European Edition
# differs only in the Hall sensor pin.
configure-board-v2:
	$(MAKE) configure-board HALL_GPIO=6 IRDIODE_GPIO=6 LED_CLK=15 LED_MOSI=16 LED_CS=14 SERIAL_TX=10 SERIAL_RX=9

configure-board-eu:
	$(MAKE) configure-board HALL_GPIO=4 IRDIODE_GPIO=6 LED_CLK=15 LED_MOSI=16 LED_CS=14 SERIAL_TX=10 SERIAL_RX=9

# --- Board WiFi provisioning (for OTA upgrades) ---
# Writes credentials to the main board's NVS (namespace "devel_wifi").
# The board only joins WiFi when an OTA upgrade is requested over serial;
# see docs/internals/ota.md. One-time per board:
#   make wifi-provision WIFI_SSID=mywifi WIFI_PASS=mypassword
WIFI_SSID ?=
WIFI_PASS ?=
BOARD_IP ?=

wifi-provision:
	$(SERIAL_LOCK) bash -c '$(wait-port) && python3 ./tools/provision_wifi.py \
		--port "$(PORT)" \
		--wifi-ssid "$(WIFI_SSID)" \
		--wifi-password "$(WIFI_PASS)"'

# --- Hardware workbench (second ESP32-S3 board that exercises a real DUT) ---
# See docs/internals/workbench.md for the full design.
# Usage:
#   make workbench-build
#   make workbench-flash
#   make workbench-wifi-provision WIFI_SSID=mywifi WIFI_PASS=mypassword
#   make workbench-monitor
#
# workbench-wifi-provision writes credentials straight into the workbench's
# NVS partition (namespace "devel_wifi", same as the DUT reads in
# apps/micropython/ventilastation/updater.py) without rebuilding or
# reflashing firmware. Reset the workbench afterwards — it logs its IP and
# mDNS name over its USB port.
WORKBENCH_DIR := hardware/workbench/workbench_esp32s3

workbench-build:
	cd "$(WORKBENCH_DIR)" && idf.py build

workbench-flash: workbench-build
	$(SERIAL_LOCK) bash -c 'cd "$(WORKBENCH_DIR)" && idf.py -p "$(PORT)" -b "$(BAUD)" flash'

workbench-monitor:
	cd "$(WORKBENCH_DIR)" && idf.py -p "$(PORT)" monitor

workbench-wifi-provision:
	$(SERIAL_LOCK) python3 "$(WORKBENCH_DIR)/tools/provision_wifi.py" --port "$(PORT)" --wifi-ssid "$(WIFI_SSID)" --wifi-password "$(WIFI_PASS)"

# --- Base Arduino (buttons/servo/dial relay; see docs/internals/base-control-api.md) ---
# Not an ESP-IDF project, so there's no build/flash target here (use the
# Arduino IDE/arduino-cli directly) -- just a serial monitor, since
# find_board.py can now identify it the same way it identifies the rotor and
# workbench (see docs/internals/input-protocol-v2.md#resync--device-identification).
# Usage:
#   make base-monitor
base-monitor:
	$(PYTHON) -m serial.tools.miniterm "$(PORT)" 57600
