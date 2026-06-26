.PHONY: micropython-webassembly web-runtime-bundle web-emulator-bundle vsdk flash-vsdk voom flash-voom launcher flash-launcher flash-all generate-roms build-fs deploy-fs dev-deploy dev-emulator

PORT ?=
BAUD ?= 2000000
VOOM_WAIT ?= 15
VOOM_MICROPYTHON_IDF_PATH ?= ../../esp-idf/esp-5.5.2
VOOM_RETRO_GO_IDF_PATH ?= ../../esp-idf/esp-5.0.4
VSDK_BOARD ?= VENTILASTATION
VSDK_BOARD_VARIANT ?= SPIRAM_OCT
VSDK_BOARD_DIR := $(abspath ./hardware/rotor/boards/VENTILASTATION)
VSDK_MODULES := $(abspath ./hardware/rotor/modules/micropython.cmake)
VSDK_FROZEN_MANIFEST := $(abspath ./apps/micropython/manifest.py)
MICROPYTHON_ROOT ?= ./hardware/rotor/micropython
MICROPYTHON_PORT_DIR := $(abspath $(MICROPYTHON_ROOT)/ports/esp32)
RETRO_GO_DIR := ./apps/retro-go

micropython-webassembly:
	./tools/build-micropython-webassembly.sh

web-runtime-bundle:
	python3 ./tools/generate_web_runtime_bundle.py

web-emulator-bundle:
	./tools/build-web-emulator-bundle.sh

vsdk:
	/bin/zsh -lc 'source "$(VOOM_MICROPYTHON_IDF_PATH)/export.sh" >/dev/null && $(MAKE) -C "$(MICROPYTHON_PORT_DIR)" V=1 BOARD="$(VSDK_BOARD)" BOARD_DIR="$(VSDK_BOARD_DIR)" BOARD_VARIANT="$(VSDK_BOARD_VARIANT)" USER_C_MODULES="$(VSDK_MODULES)" FROZEN_MANIFEST="$(VSDK_FROZEN_MANIFEST)" all'

flash-vsdk: vsdk
ifndef PORT
	$(error Set PORT=/dev/cu.usbmodemXXXX)
endif
	python3 ./hardware/rotor/flash_vsdk_image.py --port "$(PORT)" --baud "$(BAUD)" --idf-path "$(VOOM_MICROPYTHON_IDF_PATH)" --board "$(VSDK_BOARD)" --board-variant "$(VSDK_BOARD_VARIANT)"

voom:
	/bin/zsh -lc 'source "$(VOOM_RETRO_GO_IDF_PATH)/export.sh" >/dev/null && cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation build prboom-go'

flash-voom: voom
ifndef PORT
	$(error Set PORT=/dev/cu.usbmodemXXXX)
endif
	/bin/zsh -lc 'source "$(VOOM_RETRO_GO_IDF_PATH)/export.sh" >/dev/null && cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation --port="$(PORT)" --baud="$(BAUD)" flash prboom-go'

launcher:
	/bin/zsh -lc 'source "$(VOOM_RETRO_GO_IDF_PATH)/export.sh" >/dev/null && cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation build launcher'

flash-launcher: launcher
ifndef PORT
	$(error Set PORT=/dev/cu.usbmodemXXXX)
endif
	/bin/zsh -lc 'source "$(VOOM_RETRO_GO_IDF_PATH)/export.sh" >/dev/null && cd "$(RETRO_GO_DIR)" && python3 rg_tool.py --target=ventilastation --port="$(PORT)" --baud="$(BAUD)" flash launcher'

flash-all: flash-vsdk flash-voom flash-launcher deploy-fs

generate-roms:
	python3 tools/generate_roms.py

build-fs:
	python3 hardware/rotor/build_micropython_fs.py

deploy-fs:
ifndef PORT
	$(error Set PORT=/dev/cu.usbmodemXXXX)
endif
	python3 hardware/rotor/deploy_micropython_fs.py --port "$(PORT)" --baud "$(BAUD)"

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
	@test -n "$(WIFI_SSID)" || (echo "Usage: make dev-deploy PORT=... WIFI_SSID=... WIFI_PASS=..."; exit 1)
	python3 ./tools/dev_deploy.py \
		$(if $(PORT),--port $(PORT),) \
		--wifi-ssid "$(WIFI_SSID)" \
		--wifi-password "$(WIFI_PASS)"

dev-emulator:
	cd emulator && python emu.py $(BOARD_IP) --no-display
