"""Standalone gamepad diagnostic for console/headless boxes (the Base).

Bypasses consoleengine.py/comms.py entirely -- talks to pyglet directly,
in the same shadow_window=False headless configuration console mode uses
-- to tell whether pyglet's Controller layer sees button/stick input on
this machine at all, independent of anything else in this project.

Run it, then press buttons / move sticks on the gamepad:
    python3 gamepad_debug.py
"""

import pyglet
pyglet.options['shadow_window'] = False

try:
    pyglet.input.controller.add_mappings_from_file("gamecontrollerdb.txt")
except OSError as error:
    print("gamecontrollerdb.txt not loaded:", error)

manager = pyglet.input.ControllerManager()
controllers = manager.get_controllers()
print("controllers found at startup:", controllers)

opened = []


def open_controller(ctrl):
    print("opening:", ctrl.device.name, "guid:", ctrl.guid)
    ctrl.open()
    opened.append(ctrl)

    @ctrl.event
    def on_button_press(controller, button):
        print("PRESS", button)

    @ctrl.event
    def on_button_release(controller, button):
        print("RELEASE", button)

    @ctrl.event
    def on_stick_motion(controller, stick, vector):
        print("STICK", stick, vector)

    @ctrl.event
    def on_dpad_motion(controller, vector):
        print("DPAD", vector)

    @ctrl.event
    def on_trigger_motion(controller, trigger, value):
        print("TRIGGER", trigger, value)


for c in controllers:
    open_controller(c)


@manager.event
def on_connect(ctrl):
    print("connected:", ctrl.device.name)
    open_controller(ctrl)


@manager.event
def on_disconnect(ctrl):
    print("disconnected:", ctrl.device.name)


def poll(dt):
    # Also print raw polled attribute values once a second, in case events
    # aren't dispatching but the underlying state is still updating.
    for ctrl in opened:
        print("poll:", ctrl.device.name, "a=", ctrl.a, "leftx=", ctrl.leftx,
              "lefty=", ctrl.lefty, "dpad=", ctrl.dpad)


if __name__ == '__main__':
    print("Press buttons / move sticks now. Ctrl+C to stop.")
    pyglet.clock.schedule_interval(poll, 1.0)
    pyglet.app.run()
