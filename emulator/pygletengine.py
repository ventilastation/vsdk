import pyglet
import math
import random
from pyglet.gl import *
from struct import pack, unpack
from deepspace import deepspace

from inputs import *
from audio import init_sound, process_sound_queue

init_sound()

spritedata = bytearray( b"\0\0\0\xff\xff" * 100)
all_strips = {}


LED_DOT = 6
LED_SIZE = min(window.width, window.height) / 2
R_ALPHA = max(window.height, window.width)
ROWS = 256
COLUMNS = 256

TRANSPARENT = 0xFF

STARS = COLUMNS // 2
starfield = [(random.randrange(COLUMNS), random.randrange(ROWS)) for n in range(STARS)]

glLoadIdentity()
glEnable(GL_BLEND)
#glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
glBlendFunc(GL_SRC_ALPHA_SATURATE, GL_ONE)


def change_colors(colors):
    # byteswap all longs
    fmt_unpack = "<" + "L" * (len(colors)//4)
    fmt_pack = ">" + "L" * (len(colors)//4)
    b = unpack(fmt_unpack, colors)
    return pack(fmt_pack, *b)

def pack_colors(colors):
    fmt_pack = "<" + "L" * len(colors)
    return pack(fmt_pack, *colors)

def unpack_palette(pal):
    fmt_unpack = "<" + "L" * (len(pal)//4)
    return unpack(fmt_unpack, pal)

palette = []
upalette = []

def set_palettes(paldata):
    global palette, upalette
    palette = change_colors(paldata)
    upalette = unpack_palette(palette)

class PygletEngine():
    def __init__(self, led_count, comms_send, enable_display=True):
        self.led_count = led_count
        self.total_angle = 0
        self.last_sent = 0
        self.comms_send = comms_send
        led_step = (LED_SIZE / led_count)
        self.enable_display = enable_display
        self.help_label = pyglet.text.Label("←↕→ SPACE ESC Q", font_name="Arial", font_size=12, y=5, x=window.width-5, color=(128, 128, 128, 255), anchor_x="right")

        vertex_pos = []
        theta = (math.pi * 2 / COLUMNS)
        def arc_chord(r):
            return 2 * r * math.sin(theta / 2)

        x1, x2 = 0, 0
        for i in range(led_count):
            y1 = led_step * i - (led_step * .3)
            y2 = y1 + (led_step * 1)
            x3 = arc_chord(y2) * 0.7
            x4 = -x3
            vertex_pos.extend([x1, y1, x2, y1, x4, y2, x3, y2])
            x1, x2 = x3, x4

        vertex_colors = (0, 0, 0, 255) * led_count * 4
        texture_pos = (0,0, 1,0, 1,1, 0,1) * led_count

        self.vertex_list = pyglet.graphics.vertex_list(
            led_count * 4,
            ('v2f/static', vertex_pos),
            ('c4B/stream', vertex_colors),
            ('t2f/static', texture_pos))


        texture = pyglet.image.load("glow.png").get_texture(rectangle=True)


        def process_input():
            val = encode_input_val()

            if val != self.last_sent:
                self.comms_send(bytes([val]))
                self.last_sent = val

        self.i = 0
        def render_anim(column):
            self.i = (self.i+1) % (204*4)
            return palette[self.i:self.i+led_count*4]

        def get_visible_column(sprite_x, sprite_width, render_column):
            sprite_column = sprite_width - 1 - ((render_column - sprite_x + COLUMNS) % COLUMNS)
            if 0 <= sprite_column < sprite_width:
                return sprite_column
            else:
                return -1

        def step_starfield():
            for (n, (x, y)) in enumerate(starfield):
                y -= 1
                if y < 0:
                    y = ROWS - 1
                    x = random.randrange(COLUMNS)
                starfield[n] = (x, y)

        def render(column):
            pixels = [0x00000000] * led_count * 4

            for (x,y) in starfield:
                if x == column:
                    try:
                        px = deepspace[y] * 4
                        pixels[px:px+4] = [0xff404040] * 4
                    except:
                        print(y, deepspace)

            # el sprite 0 se dibuja arriba de todos los otros
            for n in range(99, -1, -1):
                x, y, image, frame, perspective = unpack("BBBBb", spritedata[n*5:n*5+5])
                if frame == 255:
                    continue

                strip = all_strips.get(image)
                if not strip:
                    continue
                w, h, total_frames, pal = unpack("BBBB", strip[0:4])
                pal_base = 256 * pal
                if w == 255: w = 256 # caso especial, para los planetas
                pixeldata = memoryview(strip)[4:]

                frame %= total_frames

                visible_column = get_visible_column(x, w, column)
                if visible_column != -1:
                    base = visible_column * h + (frame * w * h)
                    if perspective:
                        desde = max(y, 0)
                        hasta = min(y + h, ROWS - 1)
                        comienzo = max( -y, 0)
                        src = base + comienzo

                        for y in range(desde, hasta):
                            index = pixeldata[src]
                            src += 1
                            if index != TRANSPARENT:
                                color = upalette[index + pal_base]
                                if perspective == 1:
                                    y = deepspace[y]
                                else:
                                    y = led_count - 1 - y
                                px = y * 4
                                pixels[px:px+4] = [color] * 4
                    else:
                        zleds = deepspace[255-y]

                        for led in range(zleds):
                            src = led * led_count // zleds
                            if src >= h:
                                break
                            index = pixeldata[base + h - 1 - src]
                            if index != TRANSPARENT:
                                color = upalette[index + pal_base]
                                px = led * 4
                                pixels[px:px+4] = [color] * 4

            return pack_colors(pixels)

        @window.event
        def on_draw():
            if not self.enable_display:
                return
            window.clear()
            fps_display.draw()
            self.help_label.draw()

            angle = -(360.0 / 256.0)

            glTranslatef(window.width / 2, window.height / 2, 0)
            glRotatef(180, 0, 0, 1)
            glEnable(texture.target)
            glBindTexture(texture.target, texture.id)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            for column in range(256):
                limit = len(self.vertex_list.colors)
                try:
                    self.vertex_list.colors[:] = render(column)[0:limit]
                    self.vertex_list.draw(GL_QUADS)
                except:
                    pass
                glRotatef(angle, 0, 0, 1)
            glDisable(texture.target)
            glRotatef(180, 0, 0, 1)
            glTranslatef(-window.width / 2, -window.height / 2, 0)
            step_starfield()


        def animate(dt):
            process_input()
            process_sound_queue()
            return
            "FIXME"
            for n in range(6):
                val = spritedata[n*4 + 1] - n
                if (val > 127 and val < 200):
                    #val = 256 - 16
                    val = 127
                spritedata[n*4 + 1] = val % 256
                spritedata[n*4] = (spritedata[n*4] + n - 3) % 256

        pyglet.clock.schedule_interval(animate, 1/30.0)
        pyglet.app.run()

