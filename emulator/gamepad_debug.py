"""Standalone gamepad diagnostic for console/headless boxes (the Base).

Bypasses consoleengine.py/comms.py entirely -- talks to pyglet directly,
in the same shadow_window=False headless configuration console mode uses
-- to tell whether pyglet's Controller layer sees button/stick input on
this machine at all, independent of anything else in this project.

Run it, then press buttons / move sticks on the gamepad:
    python3 gamepad_debug.py

`python3 -m evdev.evtest` reading the same /dev/input/eventN showed a
perfect, continuous stream of real events while pyglet's Controller
stayed frozen -- so the break is inside pyglet, between that fd and
Controller state. One real difference: a device with rumble support
(pyglet.input.linux.evdev.FFController, which this F310 qualifies for)
uploads force-feedback effects via EVIOCSFF ioctls right after opening;
evtest never touches FF at all. --no-ff patches those ioctls out to test
whether that upload is what's disrupting the normal input stream on this
kernel/driver:
    python3 gamepad_debug.py --no-ff

--no-ff ruled that out too: state stayed frozen either way. --trace goes
one level deeper, instrumenting pyglet's own EvdevDevice.poll/select (the
methods that are supposed to notice the fd is readable and read it) plus
a raw select.select() on the same fd done entirely outside pyglet, so we
can see exactly which side of that boundary stops seeing the device:
    python3 gamepad_debug.py --trace

--trace showed EvdevDevice.select() DOES fire repeatedly, tracking real
input activity -- so pyglet's event loop is noticing the fd and calling
the read method. State still never updates. --trace2 goes one level
deeper still, instrumenting the actual os.readv() call inside select()
(how many bytes it reads per firing) and Control.value's setter (the
step that should trigger on_change -> Controller.leftx/.a updates), to
tell whether reads are silently coming back empty or something breaks
after a real read:
    python3 gamepad_debug.py --trace2
"""

import select
import sys

NO_FF = "--no-ff" in sys.argv[1:]
TRACE = "--trace" in sys.argv[1:]
TRACE2 = "--trace2" in sys.argv[1:]

import pyglet
pyglet.options['shadow_window'] = False

if NO_FF:
    import pyglet.input.linux.evdev as evdev_backend
    evdev_backend.EVIOCSFF = lambda fileno, effect: None
    print("Patched out EVIOCSFF (force-feedback effect upload) for this run.")

if TRACE:
    import pyglet.input.linux.evdev as evdev_backend

    _counts = {"poll_calls": 0, "poll_true": 0, "select_calls": 0}
    _orig_poll = evdev_backend.EvdevDevice.poll
    _orig_select = evdev_backend.EvdevDevice.select

    def _traced_poll(self):
        _counts["poll_calls"] += 1
        ready = _orig_poll(self)
        if ready:
            _counts["poll_true"] += 1
        return ready

    def _traced_select(self):
        _counts["select_calls"] += 1
        print("EvdevDevice.select() FIRED for", self.name)
        return _orig_select(self)

    evdev_backend.EvdevDevice.poll = _traced_poll
    evdev_backend.EvdevDevice.select = _traced_select

if TRACE2:
    import pyglet.input.linux.evdev as evdev_backend
    from pyglet.input.base import Control

    _counts2 = {
        "readv_calls": 0, "readv_bytes_total": 0, "readv_zero": 0,
        "control_value_sets": 0,
    }
    _last_sets = []  # rolling log of the most recent Control.value assignments

    _orig_readv = evdev_backend._readv

    def _traced_readv(fd, buffers):
        n = _orig_readv(fd, buffers)
        _counts2["readv_calls"] += 1
        _counts2["readv_bytes_total"] += n
        if n == 0:
            _counts2["readv_zero"] += 1
        return n

    _orig_value_setter = Control.value.fset

    def _traced_value_setter(self, newvalue):
        _counts2["control_value_sets"] += 1
        _last_sets.append((getattr(self, "name", "?"), getattr(self, "event_code", "?"), newvalue))
        del _last_sets[:-5]
        _orig_value_setter(self, newvalue)

    evdev_backend._readv = _traced_readv
    Control.value = property(Control.value.fget, _traced_value_setter)

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

    if TRACE:
        registered = ctrl.device in pyglet.app.platform_event_loop.select_devices
        print("device.fileno() =", ctrl.device.fileno(),
              "| registered in platform_event_loop.select_devices:", registered)

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

    if TRACE:
        print("trace counters:", dict(_counts))
        for ctrl in opened:
            fd = ctrl.device.fileno()
            # A raw select() on the exact same fd, done entirely outside
            # pyglet, to see whether the OS reports it readable right now
            # (it should, if you're actively moving the stick) even though
            # EvdevDevice.select() above never fires.
            ready, _, _ = select.select([fd], [], [], 0)
            print("raw select() on fd", fd, "-> ready:", bool(ready))

    if TRACE2:
        print("trace2 counters:", dict(_counts2))
        print("last Control.value sets (name, event_code, value):", _last_sets)


if __name__ == '__main__':
    print("Press buttons / move sticks now. Ctrl+C to stop.")
    pyglet.clock.schedule_interval(poll, 1.0)
    pyglet.app.run()
