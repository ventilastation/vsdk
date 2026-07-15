import pyglet
from pyglet.window import key

import comms
from inputs_common import (
    keyboard_state, keyboard_v2_state, ota_shortcut_pressed, pack_controllers,
)
from pyglet2x.pygletdraw import window, help_label

keys = key.KeyStateHandler()

def init_inputs():
    window.push_handlers(keys)

controller_man = pyglet.input.ControllerManager()
controllers = []


def refresh_controllers():
    global controllers
    connected = list(controller_man.get_controllers())[:2]
    for ctrl in connected:
        if ctrl not in controllers:
            print(f"Controller connected: {ctrl.device.name}")
            ctrl.open()
    controllers = connected

def update_label():
    help_label.text = ("joy or " if controllers else "") + "keys: arrows/WASD Space O P Y PgUp/PgDn HJKL Z/X/C/V Home/End Ctrl/⌘-U Esc Q"

@controller_man.event
def on_connect(ctrl):
    refresh_controllers()
    update_label()

@controller_man.event
def on_disconnect(ctrl):
    print(f"Controller disconnected: {ctrl.device.name}")
    refresh_controllers()
    update_label()

print(controller_man.get_controllers())
refresh_controllers()
update_label()

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
    primary = controllers[0] if controllers else None
    secondary = controllers[1] if len(controllers) > 1 else None
    joy1, joy2, extra, home = pack_controllers(
        primary, secondary,
        (kb_left, kb_right, kb_up, kb_down, kb_boton, kb_accel, kb_decel),
        keyboard_v2_state(keys),
    )
    return joy1, joy2, extra, home or keys[key.ESCAPE]
