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

keys = key.KeyStateHandler()

def init_inputs():
    window.push_handlers(keys)

def init_controller(ctrl):
    global controller
    controller = ctrl
    print(f"Controller connected: {ctrl.device.name}")
    controller.open()
    # @controller.event
    # def on_button_press(controller, button_name):
    #     print(f"Button {button_name} pressed")

    # @controller.event
    # def on_button_release(controller, button_name):
    #     print(f"Button {button_name} released")

    # @controller.event
    # def on_dpad_motion(controller, vector):
    #     print(f"DPad moved to ({vector.x}, {vector.y})")

controller_man = pyglet.input.ControllerManager()

@controller_man.event
def on_connect(ctrl):
    init_controller(ctrl)

@controller_man.event
def on_disconnect(ctrl):
    print(f"Controller disconnected: {ctrl.device.name}")
    global controller
    controller = None

initial_controllers = controller_man.get_controllers()
print(initial_controllers)
if initial_controllers:
    init_controller(initial_controllers[0])
else:
    controller = None


@window.event
def on_key_press(symbol, modifiers):
    if symbol == pyglet.window.key.ESCAPE:
        return pyglet.event.EVENT_HANDLED
    if symbol == pyglet.window.key.Q:
        pyglet.app.exit()

def encode_input_val():
    THR = 0.5
    reset = keys[key.ESCAPE]
    try:
        left = controller.leftx < -THR or controller.dpad.x < -THR # or controller.leftshoulder
        right = controller.leftx > THR or controller.dpad.x > THR # or controller.rightshoulder
        up = controller.lefty < -THR or controller.dpad.y > THR
        down = controller.lefty > THR or controller.dpad.y < -THR

        boton = controller.a

        accel = controller.lefttrigger > 0 or keys[key.PAGEUP] or keys[key.P] or controller.x
        decel = controller.righttrigger > 0 or keys[key.PAGEDOWN] or keys[key.O] or controller.y

        reset = reset or controller.b or controller.guide or controller.back
        left = left or keys[key.LEFT] or keys[key.A] or base_button_left()
        right = right or keys[key.RIGHT] or keys[key.D] or base_button_right()
        up = up or keys[key.UP] or keys[key.W]
        down = down or keys[key.DOWN] or keys[key.S]
        boton = boton or keys[key.SPACE]

    except Exception as e:
        # print(f"Joystick read error: {e}")
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
