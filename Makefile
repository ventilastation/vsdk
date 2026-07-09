.PHONY: micropython-webassembly web-runtime-bundle web-emulator-bundle vsdk flash-vsdk voom flash-voom launcher flash-launcher retro-core flash-retro-core voom-emulator flash-voom-emulator run-emulator voom-sounds flash-all generate-roms build-fs deploy-fs dev-deploy dev-emulator workbench-build workbench-flash workbench-monitor workbench-wifi-provision list-boards

PORT ?=
BAUD ?= 2000000

# --- Stable board selection (avoid /dev/ttyACM* number swaps) ---
# ESP32-S3 USB-Serial-JTAG boards re-enumerate on every reset, so with two
# boards attached their /dev/ttyACM* numbers can swap mid-session -- flashing
# PORT=/dev/ttyACMx then silently hits the WRONG chip. The /dev/serial/by-id/
# symlink instead always follows a given chip. Pass MAC=aa:bb:cc:dd:ee:ff to
# target a board by its USB-JTAG serial (the chip's MAC); it resolves to the
# matching by-id path regardless of the board's current ttyACM number:
#   make flash-vsdk    MAC=3C:84:27:C8:5E:58
#   make workbench-flash MAC=3C:84:27:C9:5D:24
# `make list-boards` prints the MAC <-> ttyACM mapping of attached boards.
# (Matching is case-insensitive and ignores colons, so it also works while a
# board is still showing its pre-flash USB-CDC descriptor.)
ifdef MAC
PORT := $(shell w=$$(printf %s "$(MAC)" | tr -d : | tr A-Z a-z); for f in /dev/serial/by-id/*; do [ -e "$$f" ] || continue; n=$$(printf %s "$$f" | tr -d : | tr A-Z a-z); if printf %s "$$n" | grep -qiF -- "$$w"; then printf %s "$$f"; break; fi; done)
ifeq ($(strip $(PORT)),)
$(error No attached board matches MAC=$(MAC); run 'make list-boards' to see attached boards)
endif
endif

SERIAL_LOCK_FILE ?= /tmp/vsdk-serial.lock

# ESP-IDF checkouts. MicroPython and Retro-Go need different IDF versions;
# see docs/internals/building.md. Override these when your SDKs live elsewhere, e.g.:
#   make vsdk VSDK_IDF_PATH=~/esp/esp-idf-5.5
VSDK_IDF_PATH ?= ../../esp-idf/esp-5.5.2
RETRO_GO_IDF_PATH ?= ../../esp-idf/esp-5.0.4
# Backward-compatible aliases (the old variable names):
VOOM_MICROPYTHON_IDF_PATH ?= $(VSDK_IDF_PATH)
VOOM_RETRO_GO_IDF_PATH ?= $(RETRO_GO_IDF_PATH)

VSDK_BOARD ?= VENTILASTATION
VSDK_BOARD_VARIANT ?= SPIRAM_OCT
VSDK_BOARD_DIR := $(abspath ./hardware/rotor/boards/VENTILASTATION)
VSDK_MODULES := $(abspath ./hardware/rotor/modules/micropython.cmake)
VSDK_FROZEN_MANIFEST := $(abspath ./apps/micropython/manifest.py)
MICROPYTHON_ROOT ?= ./hardware/rotor/micropython
MICROPYTHON_PORT_DIR := $(abspath $(MICROPYTHON_ROOT)/ports/esp32)
RETRO_GO_DIR := ./apps/retro-go

# POV firmware output mode for prboom-go / launcher (see RG_VS_ENABLE_TCP_BRIDGE):
#   0 = drive the spinning LED strip over SPI (real hardware) -- the default
#   1 = stream frames to the desktop emulator over TCP/WiFi (development)
# The *-emulator targets below set this to 1; override manually with VOOM_TCP_BRIDGE=1.
VOOM_TCP_BRIDGE ?= 0
RG_TOOL_EXTRA_DEFINES = -DRG_VS_ENABLE_TCP_BRIDGE=$(VOOM_TCP_BRIDGE)
export RG_TOOL_EXTRA_DEFINES

# The board's USB-CDC serial port re-enumerates on reset, so concurrent flash
# commands can interrupt each other mid-transfer. Use a host-side lock to
# serialize any target that talks to the board over the flashing port.
# macOS ships lockf; Linux ships flock (same "<tool> <file> <cmd...>" form).
# Fall back to no locking rather than failing if neither is present.
SERIAL_LOCK := $(shell if command -v lockf >/dev/null 2>&1; then echo lockf $(SERIAL_LOCK_FILE); elif command -v flock >/dev/null 2>&1; then echo flock $(SERIAL_LOCK_FILE); fi)

# Run $(2) inside the ESP-IDF environment at $(1). A login shell so that
# export.sh sees the user's usual PATH (python3, git) even from GUI contexts;
# bash is available on both Linux and macOS (override IDF_SHELL if needed).
IDF_SHELL ?= bash -lc
idf-env = $(IDF_SHELL) 'source "$(1)/export.sh" >/dev/null && $(2)'

# Build/flash one Retro-Go app ($(1) = app name, e.g. prboom-go).
rg-build = $(call idf-env,$(RETRO_GO_IDF_PATH),cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation build $(1))
rg-flash = $(SERIAL_LOCK) $(call idf-env,$(RETRO_GO_IDF_PATH),cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation --port="$(PORT)" --baud="$(BAUD)" flash $(1))

# Targets that talk to a board need PORT (or MAC, resolved above); targets
# that provision WiFi also need credentials. Checked at parse time so the
# failure is instant even under parallel make.
PORT_TARGETS := flash-vsdk flash-voom flash-launcher flash-retro-core flash-voom-emulator flash-all deploy-fs workbench-flash workbench-monitor workbench-wifi-provision
WIFI_TARGETS := dev-deploy workbench-wifi-provision
ifneq ($(filter $(PORT_TARGETS),$(MAKECMDGOALS)),)
ifeq ($(strip $(PORT)),)
$(error Set PORT=/dev/cu.usbmodemXXXX (or MAC=aa:bb:...; run 'make list-boards'))
endif
endif
ifneq ($(filter $(WIFI_TARGETS),$(MAKECMDGOALS)),)
ifeq ($(strip $(WIFI_SSID)),)
$(error Set WIFI_SSID=... WIFI_PASS=...)
endif
endif

# List attached ESP boards as their stable by-id name -> current /dev/ttyACM*,
# so you can grab a MAC for MAC= (see the "Stable board selection" note above).
# On macOS there is no /dev/serial/by-id; list the /dev/cu.usbmodem* ports
# instead (macOS names already stay stable per chip serial).
list-boards:
	@if ls /dev/serial/by-id/* >/dev/null 2>&1; then \
		for f in /dev/serial/by-id/*; do printf '  %-72s -> %s\n' "$$(basename "$$f")" "$$(readlink -f "$$f")"; done; \
	elif ls /dev/cu.usbmodem* >/dev/null 2>&1; then \
		ls -1 /dev/cu.usbmodem* | sed 's/^/  /'; \
	else \
		echo "no boards attached (looked for /dev/serial/by-id/* and /dev/cu.usbmodem*)"; \
	fi

micropython-webassembly:
	./tools/build-micropython-webassembly.sh

web-runtime-bundle:
	python3 ./tools/generate_web_runtime_bundle.py

web-emulator-bundle:
	./tools/build-web-emulator-bundle.sh

vsdk:
	$(call idf-env,$(VSDK_IDF_PATH),$(MAKE) -C "$(MICROPYTHON_PORT_DIR)" V=1 BOARD="$(VSDK_BOARD)" BOARD_DIR="$(VSDK_BOARD_DIR)" BOARD_VARIANT="$(VSDK_BOARD_VARIANT)" USER_C_MODULES="$(VSDK_MODULES)" FROZEN_MANIFEST="$(VSDK_FROZEN_MANIFEST)" all)

# flash-vsdk writes MicroPython to both the factory slot and the micropython
# (ota_2) slot. On first boot, comms.py migrates from factory to ota_2
# automatically.
flash-vsdk: vsdk
	$(SERIAL_LOCK) python3 ./hardware/rotor/flash_vsdk_image.py --port "$(PORT)" --baud "$(BAUD)" --idf-path "$(VSDK_IDF_PATH)" --board "$(VSDK_BOARD)" --board-variant "$(VSDK_BOARD_VARIANT)"

voom:
	$(call rg-build,prboom-go)

flash-voom: voom
	$(call rg-flash,prboom-go)

launcher:
	$(call rg-build,launcher)

flash-launcher: launcher
	$(call rg-flash,launcher)

retro-core:
	$(call rg-build,retro-core)

flash-retro-core: retro-core
	$(call rg-flash,retro-core)

# --- Voom desktop emulator dev loop ---
# Build/flash prboom-go configured to stream POV frames to the desktop emulator
# (RG_VS_ENABLE_TCP_BRIDGE=1), then run the emulator pointed at the board to display them.
# Usage:
#   make flash-voom-emulator PORT=/dev/ttyACM0     # build + flash emulator firmware
#   make run-emulator BOARD_IP=192.168.1.42        # render the stream on the desktop
# The board needs WiFi creds in NVS "voom_wifi" (provisioned via the MicroPython side
# or `make dev-deploy`). After reset it prints its IP over USB serial.
voom-emulator flash-voom-emulator: VOOM_TCP_BRIDGE = 1

voom-emulator: voom

flash-voom-emulator: flash-voom

run-emulator:
	cd emulator && python emu.py $(BOARD_IP) --remote

# --- Voom sound assets ---
# Pre-render Doom's WAD audio into system/voom/sounds/*.mp3 so the emulator (TCP)
# and the hardware host (serial) can play the triggers Voom sends. SFX need only
# ffmpeg; music needs a MIDI synth + soundfont (one-time: sudo apt install fluidsynth).
# Re-run whenever the WAD changes.
voom-sounds:
	cd emulator && python build_voom_sounds.py

flash-all: flash-vsdk flash-voom flash-retro-core deploy-fs

generate-roms:
	python3 tools/generate_roms.py

build-fs:
	python3 hardware/rotor/build_micropython_fs.py

deploy-fs:
	$(SERIAL_LOCK) python3 hardware/rotor/deploy_micropython_fs.py --port "$(PORT)" --baud "$(BAUD)"

# Hardware WiFi dev loop
# Usage:
#   make dev-deploy PORT=/dev/ttyACM0 WIFI_SSID=mywifi WIFI_PASS=mypassword
#   make dev-emulator BOARD_IP=192.168.1.42
#
# After dev-deploy: reset the board — it will print its IP over USB serial.
# Run dev-emulator in one terminal, `mpremote connect PORT` in another for console.
WIFI_SSID ?=
WIFI_PASS ?=
BOARD_IP ?= 192.168.1.1

dev-deploy:
	python3 ./tools/dev_deploy.py \
		$(if $(PORT),--port $(PORT),) \
		--wifi-ssid "$(WIFI_SSID)" \
		--wifi-password "$(WIFI_PASS)"

dev-emulator:
	cd emulator && python emu.py $(BOARD_IP) --no-display

# --- Hardware workbench (second ESP32-S3 board that exercises a real DUT) ---
# See docs/internals/workbench.md for the full design.
# Usage:
#   make workbench-build
#   make workbench-flash PORT=/dev/cu.usbmodemXXXX
#   make workbench-wifi-provision PORT=/dev/cu.usbmodemXXXX WIFI_SSID=mywifi WIFI_PASS=mypassword
#   make workbench-monitor PORT=/dev/cu.usbmodemXXXX
#
# wifi-provision writes credentials straight into the workbench's NVS
# partition (namespace "voom_wifi", same as the DUT reads in
# apps/micropython/ventilastation/comms.py) without rebuilding or
# reflashing firmware. Reset the workbench afterwards — it logs its IP and
# mDNS name over its USB port.
WORKBENCH_DIR := hardware/workbench/workbench_esp32s3
WORKBENCH_IDF_PATH ?= $(VSDK_IDF_PATH)

workbench-build:
	$(call idf-env,$(WORKBENCH_IDF_PATH),cd "$(WORKBENCH_DIR)" && idf.py build)

workbench-flash: workbench-build
	$(SERIAL_LOCK) $(call idf-env,$(WORKBENCH_IDF_PATH),cd "$(WORKBENCH_DIR)" && idf.py -p "$(PORT)" -b "$(BAUD)" flash)

workbench-monitor:
	$(call idf-env,$(WORKBENCH_IDF_PATH),cd "$(WORKBENCH_DIR)" && idf.py -p "$(PORT)" monitor)

workbench-wifi-provision:
	$(SERIAL_LOCK) $(call idf-env,$(WORKBENCH_IDF_PATH),python3 "$(WORKBENCH_DIR)/tools/provision_wifi.py" --port "$(PORT)" --wifi-ssid "$(WIFI_SSID)" --wifi-password "$(WIFI_PASS)")
