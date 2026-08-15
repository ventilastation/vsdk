"""Headless (--no-display) OTA shortcut.

Console mode never creates a window, so the Ctrl-U handler that pyglet1x and
pyglet2x hang off ``on_key_press`` never runs there -- consoleengine.py has to
edge-detect the chord from polled evdev state instead. These checks cover that
path end to end without needing pyglet, evdev, or an audio stack.
"""

import sys
import types


fake_key = types.SimpleNamespace(
    LEFT=1, RIGHT=2, UP=3, DOWN=4, A=5, D=6, W=7, S=8, SPACE=9, O=10, P=11,
    H=12, J=13, K=14, L=15, Z=16, X=17, C=18, V=19, Y=20,
    PAGEUP=21, PAGEDOWN=22, HOME=23, END=24, ESCAPE=25,
    U=26, LCTRL=27, RCTRL=28, LCOMMAND=29, RCOMMAND=30, LMETA=31, RMETA=32,
    MOD_CTRL=0x100, MOD_COMMAND=0x200,
)

_KEY_NAMES = [
    "KEY_LEFT", "KEY_RIGHT", "KEY_UP", "KEY_DOWN", "KEY_A", "KEY_D", "KEY_W",
    "KEY_S", "KEY_SPACE", "KEY_O", "KEY_P", "KEY_H", "KEY_J", "KEY_K", "KEY_L",
    "KEY_Z", "KEY_X", "KEY_C", "KEY_V", "KEY_Y", "KEY_PAGEUP", "KEY_PAGEDOWN",
    "KEY_HOME", "KEY_END", "KEY_ESC",
    "KEY_U", "KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTMETA", "KEY_RIGHTMETA",
]
# Real evdev keeps KEY_* below BTN_JOYSTICK (0x120); preserve that ordering so
# evdev_keys._is_joystick_like() keeps its real meaning under the stub.
fake_ecodes = types.SimpleNamespace(
    EV_KEY=1, EV_ABS=3, BTN_JOYSTICK=0x120,
    **{name: index + 1 for index, name in enumerate(_KEY_NAMES)}
)

EV_KEY, _UP, _DOWN = fake_ecodes.EV_KEY, 0, 1


def _install_stubs():
    fake_pyglet = types.ModuleType("pyglet")
    fake_pyglet.options = {}
    fake_window = types.ModuleType("pyglet.window")
    fake_window.key = fake_key
    fake_pyglet.window = fake_window

    fake_evdev = types.ModuleType("evdev")
    fake_evdev.ecodes = fake_ecodes
    fake_evdev.list_devices = lambda: []
    fake_evdev.InputDevice = lambda path: None
    fake_ecodes_module = types.ModuleType("evdev.ecodes")

    fake_fix = types.ModuleType("pyglet_evdev_fix")
    fake_fix.apply = lambda: None

    fake_audio = types.ModuleType("audio")
    fake_audio.sound_init = lambda: None
    fake_audio.sound_process_queue = lambda: None

    fake_emu_audio = types.ModuleType("emu_audio")
    fake_emu_audio.emu_audio = types.SimpleNamespace(process=lambda: None)

    for name, module in (
        ("pyglet", fake_pyglet), ("pyglet.window", fake_window),
        ("evdev", fake_evdev), ("evdev.ecodes", fake_ecodes_module),
        ("pyglet_evdev_fix", fake_fix),
        ("audio", fake_audio), ("emu_audio", fake_emu_audio),
    ):
        sys.modules.setdefault(name, module)
    sys.path.insert(0, "emulator")


_install_stubs()

from evdev_keys import _DETECTION_KEYS, _EVDEV_TO_PYGLET, MultiKeyState  # noqa: E402
from inputs_common import ota_shortcut_held  # noqa: E402


class FakeEvent:
    def __init__(self, code, value):
        self.type, self.code, self.value = EV_KEY, code, value


class FakeDevice:
    name = "fake arcade encoder"

    def __init__(self):
        self.pending = []

    def read(self):
        events, self.pending = self.pending, []
        return events


def _keyboard_with(device):
    keys = MultiKeyState()
    keys._devices["/dev/input/fake"] = (device, set())
    return keys


def test_evdev_table_translates_the_ota_chord():
    assert _EVDEV_TO_PYGLET[fake_ecodes.KEY_U] == fake_key.U
    assert _EVDEV_TO_PYGLET[fake_ecodes.KEY_LEFTCTRL] == fake_key.LCTRL
    assert _EVDEV_TO_PYGLET[fake_ecodes.KEY_RIGHTCTRL] == fake_key.RCTRL


def test_ota_chord_does_not_loosen_keyboard_detection():
    # Modifiers show up on plenty of HID devices that are not the arcade
    # panel's encoder, so they must not count toward _MIN_MATCHING_KEYS.
    for code in (fake_ecodes.KEY_U, fake_ecodes.KEY_LEFTCTRL,
                 fake_ecodes.KEY_RIGHTCTRL, fake_ecodes.KEY_LEFTMETA,
                 fake_ecodes.KEY_RIGHTMETA):
        assert code not in _DETECTION_KEYS
    assert fake_ecodes.KEY_LEFT in _DETECTION_KEYS
    assert fake_ecodes.KEY_ESC in _DETECTION_KEYS


def test_held_ctrl_u_reaches_the_shortcut_through_evdev():
    device = FakeDevice()
    keys = _keyboard_with(device)

    device.pending = [FakeEvent(fake_ecodes.KEY_LEFTCTRL, _DOWN)]
    keys.poll()
    assert not ota_shortcut_held(keys)

    device.pending = [FakeEvent(fake_ecodes.KEY_U, _DOWN)]
    keys.poll()
    assert ota_shortcut_held(keys)

    device.pending = [FakeEvent(fake_ecodes.KEY_U, _UP)]
    keys.poll()
    assert not ota_shortcut_held(keys)


def test_console_tick_triggers_ota_once_per_press():
    from consoleengine import ConsoleEngine

    triggered = []
    fake_comms = types.ModuleType("comms")
    fake_comms.trigger_ota = lambda: triggered.append(1)
    fake_comms.send_joystick = lambda *args: None
    fake_comms.send_command = lambda *args: None
    sys.modules["comms"] = fake_comms

    device = FakeDevice()
    engine = object.__new__(ConsoleEngine)  # __init__ opens audio and controllers
    engine.keys = _keyboard_with(device)
    engine.controllers = []
    engine.last_input_sent = (0, 0, 0)
    engine.last_exit_pressed = False
    engine.last_ota_pressed = False

    engine._tick(0)
    assert triggered == []

    device.pending = [FakeEvent(fake_ecodes.KEY_LEFTCTRL, _DOWN),
                      FakeEvent(fake_ecodes.KEY_U, _DOWN)]
    engine._tick(0)
    assert triggered == [1]

    # Held across further ticks: one OTA per press, not one per frame.
    engine._tick(0)
    engine._tick(0)
    assert triggered == [1]

    device.pending = [FakeEvent(fake_ecodes.KEY_U, _UP)]
    engine._tick(0)
    device.pending = [FakeEvent(fake_ecodes.KEY_U, _DOWN)]
    engine._tick(0)
    assert triggered == [1, 1]


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("console OTA shortcut: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
