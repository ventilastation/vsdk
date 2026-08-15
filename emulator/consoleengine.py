"""Headless console-mode engine: gamepad + arcade-encoder keyboard + GPIO
buttons in, sound out, no window, no X11.

This backs the production Base (see emu.py's --no-display mode): a
Raspberry Pi with no monitor attached, where the spinning board's LEDs are
the only display. Getting here without X11 depends on pyglet's
shadow_window option being off *before anything in the process* touches
pyglet.window, pyglet.input, or pyglet.media -- importing any of those
modules otherwise creates an invisible 1x1 GL window as a housekeeping
side effect (pyglet/gl/__init__.py:_create_shadow_window), which needs a
live X11/EGL connection to succeed and simply crashes without one.
Disabling it is a documented pyglet option, not a workaround -- verified
empirically with $DISPLAY unset: ControllerManager, media.Player, and the
pyglet.app/clock loop all behave the same without it, since none of them
actually need a window, only pyglet's own import-time probing does.

emu.py sets that option first, before its own `import comms` (comms.py
imports audio/emu_audio, which import pyglet.media) -- by the time this
module is reached the option is already in effect. Set it again here too
(idempotent) so this module stays safe to import on its own, e.g. from a
test, without relying on emu.py having gone first.

Also applies pyglet_evdev_fix (see that module) before any Controller
gets constructed below -- without it, gamepad input silently never works
on a 32-bit userspace (pyglet's evdev backend miscomputes its event
struct size there and drops every real event).
"""

import pyglet
pyglet.options['shadow_window'] = False

import config
import pyglet_evdev_fix
from audio import sound_init, sound_process_queue
from emu_audio import emu_audio
from evdev_keys import MultiKeyState
from inputs_common import (
    keyboard_state, keyboard_v2_state, ota_shortcut_held, pack_controllers,
)
from pyglet.window import key

pyglet_evdev_fix.apply()


class ConsoleEngine:
    def __init__(self, comms_send):
        sound_init()
        self.comms_send = comms_send
        self.keys = MultiKeyState(config.KEYBOARD_DEVICE_NAME)

        pyglet.input.controller.add_mappings_from_file("gamecontrollerdb.txt")
        self.controller_manager = pyglet.input.ControllerManager()
        self.controllers = []
        # Event-driven, matching pyglet2x/inputs.py -- NOT re-derived every
        # tick. Controller.device.connected is just os.path.exists(path);
        # polling that 30x/sec turned any single-tick blip into a full
        # disconnect+reconnect, which called ctrl.open() on an
        # already-open device and corrupted its fd/poll registration --
        # that's why real button/stick events never arrived.
        self.controller_manager.push_handlers(
            on_connect=lambda ctrl: self._refresh_controllers(),
            on_disconnect=lambda ctrl: self._refresh_controllers(),
        )
        self._refresh_controllers()  # pick up whatever's already plugged in

        self.last_input_sent = (0, 0, 0)
        self.last_exit_pressed = False
        self.last_ota_pressed = False

    def _refresh_controllers(self):
        connected = list(self.controller_manager.get_controllers())[:2]
        for ctrl in connected:
            if ctrl not in self.controllers:
                print("Controller connected:", ctrl.device.name, "guid:", ctrl.guid)
                ctrl.open()
        for ctrl in self.controllers:
            if ctrl not in connected:
                print("Controller disconnected:", ctrl.device.name)
        self.controllers = connected

    def _encode_input(self):
        self.keys.poll()
        kb_left, kb_right, kb_up, kb_down, kb_a, kb_b, kb_x = keyboard_state(self.keys)
        primary = self.controllers[0] if self.controllers else None
        secondary = self.controllers[1] if len(self.controllers) > 1 else None
        joy1, joy2, extra, home = pack_controllers(
            primary, secondary,
            (kb_left, kb_right, kb_up, kb_down, kb_a, kb_b, kb_x),
            keyboard_v2_state(self.keys),
        )
        return joy1, joy2, extra, home or self.keys[key.ESCAPE]

    def _tick(self, dt):
        import comms
        joy1, joy2, extra, exit_pressed = self._encode_input()
        if (joy1, joy2, extra) != self.last_input_sent:
            comms.send_joystick(joy1, joy2, extra)
            self.last_input_sent = (joy1, joy2, extra)
        if exit_pressed and not self.last_exit_pressed:
            comms.send_command("exit")
        self.last_exit_pressed = exit_pressed
        # The windowed backends get this from on_key_press; with no window
        # there is no such event, so the chord is edge-detected off the same
        # polled state _encode_input() just refreshed.
        ota_pressed = ota_shortcut_held(self.keys)
        if ota_pressed and not self.last_ota_pressed:
            comms.trigger_ota()
        self.last_ota_pressed = ota_pressed
        sound_process_queue()
        emu_audio.process()  # drive emulator-audio player lifecycle (main thread)

    def run(self):
        pyglet.clock.schedule_interval(self._tick, 1 / 30.0)
        pyglet.app.run()
