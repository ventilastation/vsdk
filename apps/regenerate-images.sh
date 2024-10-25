cd ..
. .venv/bin/activate
cd tools
python generate_images.py > ../emulator/imagenes.py
python generate_strips.py  >> ../emulator/imagenes.py
mpy-cross ../emulator/imagenes.py -o ../apps/micropython/ventilastation/imagenes.mpy
echo "Updated emulator/imagenes.py and apps/micropython/ventilastation/imagenes.mpy"
