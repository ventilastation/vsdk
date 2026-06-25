.PHONY: micropython-webassembly web-runtime-bundle web-emulator-bundle vsdk flash-vsdk voom flash-voom flash-all

PORT ?=
BAUD ?= 2000000
VOOM_WAIT ?= 15
VOOM_MICROPYTHON_IDF_PATH ?= ../../esp-idf-5.4
VOOM_RETRO_GO_IDF_PATH ?= ../../esp-idf
VSDK_BOARD ?= VENTILASTATION
VSDK_BOARD_VARIANT ?= SPIRAM_OCT
VSDK_BOARD_DIR := $(abspath ./hardware/rotor/boards/VENTILASTATION)
VSDK_MODULES := $(abspath ./hardware/rotor/modules/micropython.cmake)
VSDK_FROZEN_MANIFEST := $(abspath ./apps/micropython/manifest.py)
MICROPYTHON_PORT_DIR := ./../../micropython/ports/esp32
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

flash-all: flash-vsdk flash-voom
ifndef PORT
	$(error Set PORT=/dev/cu.usbmodemXXXX)
endif
	/bin/zsh -lc 'source "$(VOOM_MICROPYTHON_IDF_PATH)/export.sh" >/dev/null && python3 ./hardware/rotor/deploy_micropython_fs.py --port "$(PORT)" --baud "$(BAUD)" --wait "$(VOOM_WAIT)"'
