import pyglet
from pyglet.gl import *

from inputs import *
from audio import sound_init, sound_process_queue
from pygletdraw import *
from vsdk import *

sound_init()

class PygletEngine():
    def __init__(self, led_count, comms_send, enable_display=True):
        display_init(led_count)
        self.last_byte_sent = 0
        self.comms_send = comms_send
        self.enable_display = enable_display

        def process_input():
            val = encode_input_val()

            if val != self.last_byte_sent:
                self.comms_send(bytes([val]))
                self.last_byte_sent = val

        @window.event
        def on_draw():
            if not self.enable_display:
                return
            display_draw()

        def animate(dt):
            process_input()
            sound_process_queue()
            step_starfield()

        init_inputs()
        pyglet.clock.schedule_interval(animate, 1/30.0)
        pyglet.app.run()

