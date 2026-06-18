.PHONY: micropython-webassembly web-runtime-bundle web-emulator-bundle

micropython-webassembly:
	./tools/build-micropython-webassembly.sh

web-runtime-bundle:
	python3 ./tools/generate_web_runtime_bundle.py

web-emulator-bundle:
	./tools/build-web-emulator-bundle.sh
