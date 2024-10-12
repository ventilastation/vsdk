cd ..
. .venv/bin/activate
cd tools
python generate_images.py > ../apps/micropython/libs/imagenes.py
python generate_strips.py  >> ../apps/micropython/libs/imagenes.py
echo "Created apps/micropython/libs/imagenes.py"
