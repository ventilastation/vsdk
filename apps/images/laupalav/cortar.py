from PIL import Image

files = [
    ("frente.png", 12),
    ("fondo.png", 24),
]

for filename, splits in files:
    img = Image.open(filename)
    w = img.width
    h = img.height

    canvas = Image.new(img.mode, (w + w, h))
    canvas.paste(img, (0, 0))
    canvas.paste(img, (w, 0))
    canvas.show()

    name, ext = filename.split(".")
    fn_template = name + "%02d." + ext

    step = img.width // splits
    for n in range(splits):
        frame = canvas.crop((step * n, 0, step * n + h, h))
        frame.save(fn_template % n)
        print(fn_template % n)
    frame.show()
        

