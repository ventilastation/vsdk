import pyglet
from audio import sound_init, sound_process_queue
from emu_audio import emu_audio

if pyglet.version >= "2.0":
    from pyglet2x.inputs import *
    from pyglet2x.pygletdraw import *
else:
    from pyglet1x.inputs import *
    from pyglet1x.pygletdraw import *
from povrender import step_starfield


class PygletEngine():
    def __init__(self, led_count, comms_send, enable_display=True):
        sound_init()
        display_init(led_count)
        self.last_input_sent = (0, 0, 0)
        self.last_exit_pressed = False
        self.comms_send = comms_send
        self.enable_display = enable_display

        def process_input():
            import comms
            joy1, joy2, extra, exit_pressed = encode_input_val()

            if (joy1, joy2, extra) != self.last_input_sent:
                comms.send_joystick(joy1, joy2, extra)
                self.last_input_sent = (joy1, joy2, extra)
            if exit_pressed and not self.last_exit_pressed:
                comms.send_command("exit")
            self.last_exit_pressed = exit_pressed

        @window.event
        def on_draw():
            if not self.enable_display:
                return
            display_draw()

        def animate(dt):
            process_input()
            sound_process_queue()
            emu_audio.process()  # drive emulator-audio player lifecycle (main thread)
            if self.enable_display:
                step_starfield()

        init_inputs()
        pyglet.clock.schedule_interval(animate, 1/30.0)
        pyglet.app.run()
