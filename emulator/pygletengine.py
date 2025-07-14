import platform
import config
import sys
import pyglet

pyglet.options['vsync'] = "--no-display" not in sys.argv

import math
import random
import os
from pyglet.gl import *
from pyglet.window import key
from struct import pack, unpack
from deepspace import deepspace

try:
    # Botones de la base de Super Ventilagon
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup([9,10], GPIO.IN, GPIO.PUD_UP)

    def base_button_left():
        return GPIO.input(9) == 0
    
    def base_button_right():
        return GPIO.input(10) == 0

except ImportError:
    def base_button_left():
        return False

    def base_button_right():
        return False

if platform.system() != "Windows":
    # Force using OpenAL since pulse crashes
    pyglet.options['audio'] = ('openal', 'silent')

# preload all sounds
sounds = {}
sound_queue = []

all_strips = {}

SOUNDS_FOLDER = "../apps/sounds"

def load_sounds():
    for dirpath, dirs, files in os.walk(SOUNDS_FOLDER):
        for fn in files:
            if fn.endswith(".mp3"):
                fullname = os.path.join(dirpath, fn)
                fn = fullname[len(SOUNDS_FOLDER)+1:-4].replace("\\", "/")
                try:
                    sound = pyglet.media.load(fullname + ".wav", streaming=False)
                    print(fullname + ".wav")
                except:
                    try:
                        sound = pyglet.media.load(fullname, streaming=False)
                        print(fullname)
                    except pyglet.media.codecs.wave.WAVEDecodeException:
                        print("WARNING: sound not found:", fullname)

                sounds[bytes(fn, "latin1")] = sound

    # startup sound
    sound_queue.append(("sound", bytes("ventilagon/audio/es/superventilagon", "latin1")))


import threading

threading.Thread(target=load_sounds, daemon=True).start()

def playsound(name):
    sound_queue.append(("sound", name))

def playnotes(folder, notes):
    sound_queue.append(("notes", folder, notes))

def playmusic(name):
    sound_queue.append(("music", name))


spritedata = bytearray( b"\0\0\0\xff\xff" * 100)

joysticks = pyglet.input.get_joysticks()
print(joysticks)
if joysticks:
    #import pdb
    #pdb.set_trace()
    joystick = joysticks[0]
    joystick.open()
else:
    joystick = None

window = pyglet.window.Window(config=Config(double_buffer=True), fullscreen=config.FULLSCREEN)
fps_display = pyglet.window.FPSDisplay(window)
keys = key.KeyStateHandler()


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

@window.event
def on_key_press(symbol, modifiers):
    if symbol == pyglet.window.key.ESCAPE:
        return pyglet.event.EVENT_HANDLED
    if symbol == pyglet.window.key.Q:
        pyglet.app.exit()


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
    def __init__(self, led_count, keyhandler, enable_display=True):
        self.led_count = led_count
        self.total_angle = 0
        self.last_sent = 0
        self.keyhandler = keyhandler
        led_step = (LED_SIZE / led_count)
        self.enable_display = enable_display
        self.music_player = None
        self.help_label = pyglet.text.Label("←↕→ SPACE ESC Q", font_name="Arial", font_size=12, y=5, x=window.width-5, color=(128, 128, 128, 255), anchor_x="right")

        vertex_pos = []
        theta = (math.pi * 2 / COLUMNS)
        def arc_chord(r):
            return 2 * r * math.sin(theta / 2)

        x1, x2 = 0, 0
        for i in range(led_count):
            y1 = led_step * i
            y2 = y1 + (led_step * 1)
            x3 = arc_chord(y2) * 0.7
            x4 = -x3
            vertex_pos.extend([x1, y1, x2, y1, x2, y2, x1, y2])
            x1, x2 = x3, x4

        vertex_colors = (0, 0, 0, 255) * led_count * 4
        texture_pos = (0,0, 1,0, 1,1, 0,1) * led_count

        self.vertex_list = pyglet.graphics.vertex_list(
            led_count * 4,
            ('v2f/static', vertex_pos),
            ('c4B/stream', vertex_colors),
            ('t2f/static', texture_pos))


        texture = pyglet.image.load("glow.png").get_texture(rectangle=True)


        def send_keys():
            reset = keys[key.ESCAPE]
            try:
                left = joystick.x < -0.5 or joystick.hat_x < -0.5 or joystick.buttons[4]
                right = joystick.x > 0.5 or joystick.hat_x > 0.5 or joystick.buttons[5]
                up = joystick.y < -0.5 or joystick.hat_y > 0.5
                down = joystick.y > 0.5 or joystick.hat_y < -0.5


                boton = joystick.buttons[0]  # or joystick.buttons[4] or joystick.buttons[5] or joystick.buttons[6]

                accel = joystick.z > 0 or keys[key.PAGEUP] or keys[key.P] or joystick.buttons[2]
                decel = joystick.rz > 0 or keys[key.PAGEDOWN] or keys[key.O] or joystick.buttons[3]

                try:
                    reset = reset or joystick.buttons[8] or joystick.buttons[1]
                except:
                    reset = reset or joystick.buttons[7] or joystick.buttons[1]
                left = left or keys[key.LEFT] or keys[key.A] or base_button_left()
                right = right or keys[key.RIGHT] or keys[key.D] or base_button_right()
                up = up or keys[key.UP] or keys[key.W]
                down = down or keys[key.DOWN] or keys[key.S]
                boton = boton or keys[key.SPACE]

            except Exception:
                left = keys[key.LEFT] or keys[key.A] or base_button_left()
                right = keys[key.RIGHT] or keys[key.D] or base_button_right()
                up = keys[key.UP] or keys[key.W]
                down = keys[key.DOWN] or keys[key.S]

                boton = keys[key.SPACE]
                accel = keys[key.PAGEUP] or keys[key.P]
                decel = keys[key.PAGEDOWN] or keys[key.O]

            val = (left << 0 | right << 1 | up << 2 | down << 3 | boton << 4 |
                    accel << 5 | decel << 6 | reset << 7)

            if val != self.last_sent:
                self.keyhandler(bytes([val]))
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
            send_keys()
            while sound_queue:
                command, *args = sound_queue.pop()
                if command == "sound":
                    name = args[0]
                    s = sounds.get(name)
                    if s:
                        s.play()
                    else:
                        print("WARNING: sound not found:", name)
                elif command == "music":
                    name = args[0]
                    if self.music_player:
                        self.music_player.pause()
                    if name != b"off":
                        s = sounds.get(name)
                        if s:
                            self.music_player = s.play()
                        else:
                            print("WARNING: music not found:", name)
                elif command == "notes":
                    folder, notes = args
                    to_play = []
                    for note in notes.split(b";"):
                        sound = sounds.get(folder + b"/" + note)
                        if sound:
                            to_play.append(sound)
                        else:
                            print("WARNING: note not found:", folder, note)

                    for s in to_play:
                        s.play()
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

window.push_handlers(keys)
