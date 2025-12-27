import pyglet
from pyglet.gl import Config
from pyglet.gl import *
import sys
import config


pyglet.options['vsync'] = "--no-display" not in sys.argv

window = pyglet.window.Window(config=Config(double_buffer=True), fullscreen=config.FULLSCREEN)
logo = pyglet.image.load("logo.png")
window.set_icon(logo)
window.set_caption("Ventilastation Emulator")

LED_SIZE = min(window.width, window.height) / 2

def init_display():
    glLoadIdentity()
    glEnable(GL_BLEND)
    #glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glBlendFunc(GL_SRC_ALPHA_SATURATE, GL_ONE)

def resize_display():
    global LED_SIZE
    LED_SIZE = min(window.width, window.height) / 2
    led_step = (LED_SIZE / led_count)

