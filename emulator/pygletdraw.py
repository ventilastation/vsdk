import math
import sys
import traceback

import pyglet
from pyglet.gl import Config
from pyglet.gl import *

import config
from vsdk import COLUMNS, pack_colors, repeated, render


pyglet.options['vsync'] = "--no-display" not in sys.argv

window = pyglet.window.Window(config=Config(double_buffer=True), fullscreen=config.FULLSCREEN)
logo = pyglet.image.load("logo.png")
window.set_icon(logo)
window.set_caption("Ventilastation Emulator")
fps_display = pyglet.window.FPSDisplay(window)
help_label = pyglet.text.Label("←↕→ SPACE ESC Q", font_name="Arial", font_size=12, y=5, x=window.width-5, color=(128, 128, 128, 255), anchor_x="right")

LED_SIZE = min(window.width, window.height) / 2
vertex_list = None
texture = None

def display_init(led_count):
    glLoadIdentity()
    glEnable(GL_BLEND)
    #glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glBlendFunc(GL_SRC_ALPHA_SATURATE, GL_ONE)


    led_step = (LED_SIZE / led_count)
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

    global vertex_list
    vertex_list = pyglet.graphics.vertex_list(
        led_count * 4,
        ('v2f/static', vertex_pos),
        ('c4B/stream', vertex_colors),
        ('t2f/static', texture_pos))

    global texture
    texture = pyglet.image.load("glow.png").get_texture(rectangle=True)


def display_resize():
    global LED_SIZE
    LED_SIZE = min(window.width, window.height) / 2
    led_step = (LED_SIZE / led_count)

def display_draw():
    window.clear()
    fps_display.draw()
    help_label.draw()

    angle = -(360.0 / 256.0)

    glTranslatef(window.width / 2, window.height / 2, 0)
    glRotatef(180, 0, 0, 1)
    glEnable(texture.target)
    glBindTexture(texture.target, texture.id)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    for column in range(256):
        limit = len(vertex_list.colors)
        try:
            pixels = render(column)[0:limit]
            vertex_list.colors[:] = pack_colors(list(repeated(4, pixels)))
            vertex_list.draw(GL_QUADS)
        except Exception as e:
            traceback.print_exc()
            pass
        glRotatef(angle, 0, 0, 1)
    glDisable(texture.target)
    glRotatef(180, 0, 0, 1)
    glTranslatef(-window.width / 2, -window.height / 2, 0)
