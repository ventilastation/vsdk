import pyglet
import math
import traceback
from pyglet.gl import *

from inputs import *
from audio import init_sound, process_sound_queue
from pygletdraw import *
from vsdk import *

init_sound()
init_display()

class PygletEngine():
    def __init__(self, led_count, comms_send, enable_display=True):
        self.last_byte_sent = 0
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

            if val != self.last_byte_sent:
                self.comms_send(bytes([val]))
                self.last_byte_sent = val



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
                    pixels = render(column)[0:limit]
                    self.vertex_list.colors[:] = pack_colors(list(repeated(4, pixels)))
                    self.vertex_list.draw(GL_QUADS)
                except Exception as e:
                    traceback.print_exc()
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

        init_inputs()
        pyglet.clock.schedule_interval(animate, 1/30.0)
        pyglet.app.run()

