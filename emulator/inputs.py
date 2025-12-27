import pyglet
from pyglet.window import key

from pygletdraw import window

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

fps_display = pyglet.window.FPSDisplay(window)
keys = key.KeyStateHandler()

def init_inputs():
    window.push_handlers(keys)

joysticks = pyglet.input.get_joysticks()
print(joysticks)
if joysticks:
    joystick = joysticks[0]
    joystick.open()
else:
    joystick = None

@window.event
def on_key_press(symbol, modifiers):
    if symbol == pyglet.window.key.ESCAPE:
        return pyglet.event.EVENT_HANDLED
    if symbol == pyglet.window.key.Q:
        pyglet.app.exit()

def encode_input_val():
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
    return val