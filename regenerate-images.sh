cd tools
python generate_images.py > ../micropython/libs/imagenes.py
python generate_strips.py  >> ../micropython/libs/imagenes.py
echo "Created micropython/libs/imagenes.py"
