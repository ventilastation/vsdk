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
"""

import pyglet
pyglet.options['shadow_window'] = False

import config
from audio import sound_init, sound_process_queue
from emu_audio import emu_audio
from evdev_keys import open_keyboard
from inputs_common import keyboard_state, keyboard_v2_state, pack_controllers
from pyglet.window import key


class ConsoleEngine:
    def __init__(self, comms_send):
        sound_init()
        self.comms_send = comms_send
        self.keys = open_keyboard(config.KEYBOARD_DEVICE_NAME)

        pyglet.input.controller.add_mappings_from_file("gamecontrollerdb.txt")
        self.controller_manager = pyglet.input.ControllerManager()
        self.controllers = []

        self.last_input_sent = (0, 0, 0)
        self.last_exit_pressed = False

    def _refresh_controllers(self):
        connected = list(self.controller_manager.get_controllers())[:2]
        for ctrl in connected:
            if ctrl not in self.controllers:
                print("Controller connected:", ctrl.device.name)
                ctrl.open()
        self.controllers = connected

    def _encode_input(self):
        self._refresh_controllers()
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
        sound_process_queue()
        emu_audio.process()  # drive emulator-audio player lifecycle (main thread)

    def run(self):
        pyglet.clock.schedule_interval(self._tick, 1 / 30.0)
        pyglet.app.run()
