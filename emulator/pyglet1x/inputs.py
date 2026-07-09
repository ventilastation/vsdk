import pyglet
from pyglet.window import key

from inputs_common import keyboard_state, pack_input
from pyglet1x.pygletdraw import window

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
    kb_left, kb_right, kb_up, kb_down, kb_boton, kb_accel, kb_decel = keyboard_state(keys)
    reset = keys[key.ESCAPE]
    try:
        left = joystick.x < -0.5 or joystick.hat_x < -0.5 or joystick.buttons[4]
        right = joystick.x > 0.5 or joystick.hat_x > 0.5 or joystick.buttons[5]
        up = joystick.y < -0.5 or joystick.hat_y > 0.5
        down = joystick.y > 0.5 or joystick.hat_y < -0.5

        boton = joystick.buttons[0]

        accel = joystick.z > 0 or joystick.buttons[2]
        decel = joystick.rz > 0 or joystick.buttons[3]

        try:
            reset = reset or joystick.buttons[8] or joystick.buttons[1]
        except IndexError:
            reset = reset or joystick.buttons[7] or joystick.buttons[1]
    except Exception:
        left = right = up = down = boton = accel = decel = False

    return pack_input(left or kb_left, right or kb_right, up or kb_up, down or kb_down,
                      boton or kb_boton, accel or kb_accel, decel or kb_decel, reset)
