. .venv/bin/activate
cd tools
python generate_roms.py
cd ..
cd emulator
python emu.py
pkill micropython