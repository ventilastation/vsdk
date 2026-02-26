# This module is used by the emulator.
# For the time being, Super Ventilagon is only implemented on real hardware

from ventilastation.director import director, stripes
from ventilastation.sprites import Sprite

work = None

def enter():
    global work
    work = Sprite()
    work.set_strip(stripes["menatwork.png"])
    work.set_perspective(0)
    work.set_x(0)
    work.set_y(0)
    work.set_y(255)
    work.set_frame(0)
    director.music_play(b"ventilagon/music/superventilagon-track")

def sending():
    pass

def exit():
    pass

def received(_):
    pass

def is_idle():
    return True
