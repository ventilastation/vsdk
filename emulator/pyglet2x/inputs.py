import pyglet
from pyglet.window import key

import comms
from inputs_common import keyboard_state, pack_input
from pyglet2x.pygletdraw import window, help_label

keys = key.KeyStateHandler()

def init_inputs():
    window.push_handlers(keys)

def init_controller(ctrl):
    global controller
    controller = ctrl
    print(f"Controller connected: {ctrl.device.name}")
    controller.open()

controller_man = pyglet.input.ControllerManager()

def update_label():
    help_label.text = ("joy or " if controller else "") + "keys: ←↕→ SPACE ESC Q"

@controller_man.event
def on_connect(ctrl):
    init_controller(ctrl)
    update_label()

@controller_man.event
def on_disconnect(ctrl):
    print(f"Controller disconnected: {ctrl.device.name}")
    global controller
    controller = None
    update_label()

initial_controllers = controller_man.get_controllers()
print(initial_controllers)
if initial_controllers:
    init_controller(initial_controllers[0])
else:
    controller = None
update_label()

@window.event
def on_key_press(symbol, modifiers):
    if symbol == pyglet.window.key.ESCAPE:
        return pyglet.event.EVENT_HANDLED
    if symbol == pyglet.window.key.Q:
        pyglet.app.exit()
    if symbol == pyglet.window.key.U:
        comms.trigger_ota()

def encode_input_val():
    THR = 0.5
    kb_left, kb_right, kb_up, kb_down, kb_boton, kb_accel, kb_decel = keyboard_state(keys)
    reset = keys[key.ESCAPE]
    try:
        left = controller.leftx < -THR or controller.dpad.x < -THR
        right = controller.leftx > THR or controller.dpad.x > THR
        up = controller.lefty < -THR or controller.dpad.y > THR
        down = controller.lefty > THR or controller.dpad.y < -THR

        boton = controller.a

        accel = controller.lefttrigger > 0 or controller.x
        decel = controller.righttrigger > 0 or controller.y

        reset = reset or controller.b or controller.guide or controller.back
    except Exception:
        left = right = up = down = boton = accel = decel = False

    return pack_input(left or kb_left, right or kb_right, up or kb_up, down or kb_down,
                      boton or kb_boton, accel or kb_accel, decel or kb_decel, reset)
