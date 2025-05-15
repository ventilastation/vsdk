cd ..
. .venv/bin/activate
cd tools
python generate_roms.py
# python generate_images.py > ../tools/.workdir/imagenes.py
# python generate_strips.py  >> ../tools/.workdir/imagenes.py
# mpy-cross ../tools/.workdir/imagenes.py -o ../apps/micropython/ventilastation/imagenes.mpy
# echo "Updated apps/micropython/ventilastation/imagenes.mpy"
