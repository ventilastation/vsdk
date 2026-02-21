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
        # self.must_profile = False
        # # schedule the profile after 5 seconds
        # pyglet.clock.schedule_once(lambda dt: setattr(self, 'must_profile', True), 5.0)

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
            # if self.must_profile:
            #     from cProfile import Profile
            #     from pstats import Stats
            #     profiler = Profile()
            #     profiler.enable()
            #     display_draw()
            #     profiler.disable()
            #     stats = Stats(profiler).sort_stats('cumulative')
            #     stats.print_stats(100)
            #     self.must_profile = False

        def animate(dt):
            process_input()
            sound_process_queue()
            step_starfield()

        init_inputs()
        pyglet.clock.schedule_interval(animate, 1/30.0)
        pyglet.app.run()

