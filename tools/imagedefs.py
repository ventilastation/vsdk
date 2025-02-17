import os

def image_group(folder=None, stripes={}):
    d = {}
    for n, s in stripes:
        d[os.path.join(folder, n)] = s
    return d

def strip(filename, frames=1, palette=0):
    return filename, dict(frames=frames, palette=palette)

def fullscreen(filename, radius=54, palette=0):
    return filename, dict(frames=1, radius=radius, palette=palette, process="reproject")

# width, height, frames, palette
vyruss_images = image_group(
    folder = "vyruss",
    stripes = [
        strip("disparo.png", frames=2),
        strip("explosion.png", frames=5),
        strip("explosion_nave.png", frames=4),
        strip("galaga.png", frames=12),
        strip("ll9.png", frames=4),
        strip("gameover.png"),
        strip("numerals.png", frames=12),

        fullscreen("tierra.png", radius=25, palette=2),
        fullscreen("marte.png", radius=25, palette=3),
        fullscreen("jupiter.png", radius=25, palette=4),
        fullscreen("saturno.png", radius=50, palette=5),
    ]
)

vladfarty_images = image_group(
    folder = "vladfarty",
    stripes = [
        strip("vga_cp437.png", frames=256),
        strip("rainbow437.png", frames=256),
        strip("vga_pc734.png", frames=256),
        strip("ready.png", frames=2),
        strip("copyright.png", frames=1),
        strip("reset.png", frames=5),

        fullscreen("vladfartylogo.png", radius=30),
        #fullscreen("vlad_farting.png"),
        fullscreen("farty_lion.png", palette=7),
        fullscreen("farty_lionhead.png", palette=7),
        fullscreen("bg64.png"),
        fullscreen("bgspeccy.png"),
        fullscreen("chanime01.png", palette=6),
        fullscreen("chanime02.png", palette=6),
        fullscreen("chanime03.png", palette=6),
        fullscreen("chanime04.png", palette=6),
        fullscreen("chanime05.png", palette=6),
        fullscreen("chanime06.png", palette=6),
        fullscreen("chanime07.png", palette=6),
        fullscreen("salto01.png", palette=6),
        fullscreen("salto02.png", palette=6),
        fullscreen("salto03.png", palette=6),
        fullscreen("salto04.png", palette=6),
        fullscreen("salto05.png", palette=6),
        fullscreen("salto06.png", palette=6),
    ]
)

other_images = image_group(
    folder = "other",
    stripes = [
        strip("menu.png", frames=5),
        strip("credits.png", frames=32),
        strip("pollitos.png", frames=5, palette=1),
        strip("debug_arxels.png", frames=7),
        fullscreen("tecno_estructuras.png"),
        fullscreen("ventilastation.png"),
        fullscreen("doom.png", palette=8),
        fullscreen("sves.png"),
        fullscreen("bembi.png", palette=1)
    ]
)

laupalav_images = image_group(
    folder = "laupalav",
    stripes = [
        fullscreen("bambi01.png", palette=9),
        fullscreen("bambi02.png", palette=9),
        fullscreen("bambi03.png", palette=9),
        fullscreen("fondo00.png", palette=9),
        fullscreen("fondo01.png", palette=9),
        fullscreen("fondo02.png", palette=9),
        fullscreen("fondo03.png", palette=9),
        fullscreen("fondo04.png", palette=9),
        fullscreen("fondo05.png", palette=9),
        fullscreen("fondo06.png", palette=9),
        fullscreen("fondo07.png", palette=9),
        fullscreen("fondo08.png", palette=9),
        fullscreen("fondo09.png", palette=9),
        fullscreen("fondo10.png", palette=9),
        fullscreen("fondo11.png", palette=9),
        fullscreen("fondo12.png", palette=9),
        fullscreen("fondo13.png", palette=9),
        fullscreen("fondo14.png", palette=9),
        fullscreen("fondo15.png", palette=9),
        fullscreen("fondo16.png", palette=9),
        fullscreen("fondo17.png", palette=9),
        fullscreen("fondo18.png", palette=9),
        fullscreen("fondo19.png", palette=9),
        fullscreen("fondo20.png", palette=9),
        fullscreen("fondo21.png", palette=9),
        fullscreen("fondo22.png", palette=9),
        fullscreen("fondo23.png", palette=9),
        fullscreen("frente00.png", palette=9),
        fullscreen("frente01.png", palette=9),
        fullscreen("frente02.png", palette=9),
        fullscreen("frente03.png", palette=9),
        fullscreen("frente04.png", palette=9),
        fullscreen("frente05.png", palette=9),
        fullscreen("frente06.png", palette=9),
        fullscreen("frente07.png", palette=9),
        fullscreen("frente08.png", palette=9),
        fullscreen("frente09.png", palette=9),
        fullscreen("frente10.png", palette=9),
        fullscreen("frente11.png", palette=9),
        fullscreen("bambi_test.png", palette=9),
        fullscreen("rose_black_00.png", palette=9),
        fullscreen("rose_black_01.png", palette=9),
        fullscreen("rose_green_00.png", palette=9),
        fullscreen("rose_green_01.png", palette=9),
    ]
)

unused_images = image_group(
    folder = "unused",
    stripes = [
        strip("00_galaga.png", frames=28),
        strip("01_captured.png", frames=28),
        strip("02_greenboss.png", frames=28),
        strip("03_blueboss.png", frames=28),
        strip("04_redmoth.png", frames=28),
        strip("05_bluebee.png", frames=28),
        strip("06_galaxian.png", frames=28),
        strip("07_skorpion.png", frames=28),
        strip("08_greenshit.png", frames=28),
        strip("09_dumbbug.png", frames=28),
        strip("10_newsat.png", frames=28),
        strip("11_spock.png", frames=28),
        strip("crawling.png"),

        fullscreen("yourgame.png"),
        fullscreen("menatwork.png", radius=40),
    ]
)

all_images = {}
all_images.update(vyruss_images)
all_images.update(vladfarty_images)
all_images.update(other_images)
all_images.update(laupalav_images)
#all_images.update(unused_images)


def debug():
    from pprint import pprint
    pprint(all_images)

    for filename, params in all_images.items():
        print(filename, os.stat("../images/" + filename))

#debug()
