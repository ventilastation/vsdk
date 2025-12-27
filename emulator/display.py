import pyglet
from pyglet.gl import Config
import sys
import config


pyglet.options['vsync'] = "--no-display" not in sys.argv

window = pyglet.window.Window(config=Config(double_buffer=True), fullscreen=config.FULLSCREEN)
logo = pyglet.image.load("logo.png")
window.set_icon(logo)
window.set_caption("Ventilastation Emulator")
