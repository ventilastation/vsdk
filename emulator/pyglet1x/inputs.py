import pyglet
from pyglet.window import key

import comms
from inputs_common import (
    keyboard_state, keyboard_v2_state, ota_shortcut_pressed, pack_directions,
)
from pyglet1x.pygletdraw import window

keys = key.KeyStateHandler()

def init_inputs():
    window.push_handlers(keys)

joysticks = pyglet.input.get_joysticks()
print(joysticks)
for joystick in joysticks[:2]:
    joystick.open()

@window.event
def on_key_press(symbol, modifiers):
    if symbol == pyglet.window.key.ESCAPE:
        return pyglet.event.EVENT_HANDLED
    if symbol == pyglet.window.key.Q:
        pyglet.app.exit()
    if ota_shortcut_pressed(symbol, modifiers):
        comms.trigger_ota()
        return pyglet.event.EVENT_HANDLED

def encode_input_val():
    kb_left, kb_right, kb_up, kb_down, kb_boton, kb_accel, kb_decel = keyboard_state(keys)
    kb_joy2, kb_extra = keyboard_v2_state(keys)
    def pressed(joystick, number):
        try:
            return bool(joystick.buttons[number])
        except (AttributeError, IndexError):
            return False

    def directions(joystick, x_name="x", y_name="y", dpad=False):
        if joystick is None:
            return 0
        x = getattr(joystick, x_name, 0)
        y = getattr(joystick, y_name, 0)
        hat_x = getattr(joystick, "hat_x", 0) if dpad else 0
        hat_y = getattr(joystick, "hat_y", 0) if dpad else 0
        return pack_directions(x < -0.5 or hat_x < -0.5,
                               x > 0.5 or hat_x > 0.5,
                               y < -0.5 or hat_y > 0.5,
                               y > 0.5 or hat_y < -0.5)

    primary = joysticks[0] if joysticks else None
    secondary = joysticks[1] if len(joysticks) > 1 else None
    joy1 = directions(primary, dpad=True) | pack_directions(kb_left, kb_right, kb_up, kb_down)
    extra = 0
    if primary:
        joy1 |= pressed(primary, 0) << 4 | pressed(primary, 1) << 5 | pressed(primary, 2) << 6
        extra |= pressed(primary, 3) << 0 | pressed(primary, 7) << 2 | pressed(primary, 6) << 3
    joy1 |= bool(kb_boton) << 4 | bool(kb_accel) << 5 | bool(kb_decel) << 6
    if secondary:
        joy2 = directions(secondary, dpad=True)
        joy2 |= pressed(secondary, 0) << 4 | pressed(secondary, 1) << 5 | pressed(secondary, 2) << 6
        extra |= pressed(secondary, 3) << 1 | pressed(secondary, 7) << 4 | pressed(secondary, 6) << 5
        home = pressed(primary, 8) or pressed(secondary, 8)
    else:
        joy2 = directions(primary, "rx", "ry")
        # Pyglet 1.x exposes the standard gamepad shoulders as buttons 4/5
        # and commonly reports its triggers on z/rz.  Those otherwise-unused
        # controls supply the single pad's Joy2 ABXY buttons.
        left_trigger = getattr(primary, "z", 0) > 0.5 if primary else False
        right_trigger = getattr(primary, "rz", 0) > 0.5 if primary else False
        joy2 |= pressed(primary, 4) << 4 | left_trigger << 5 | pressed(primary, 5) << 6
        extra |= right_trigger << 1
        home = pressed(primary, 8)
    joy2 |= kb_joy2
    extra |= kb_extra
    return joy1, joy2, extra, home or keys[key.ESCAPE]
