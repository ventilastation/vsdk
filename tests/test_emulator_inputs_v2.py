"""Pure controller-routing checks without requiring the pyglet package."""

import sys
import types


fake_pyglet = types.ModuleType("pyglet")
fake_window = types.ModuleType("pyglet.window")
fake_window.key = types.SimpleNamespace(
    LEFT="LEFT", RIGHT="RIGHT", UP="UP", DOWN="DOWN",
    A="A", D="D", W="W", S="S", SPACE="SPACE", O="O", P="P", U="U", Y="Y",
    H="H", J="J", K="K", L="L", Z="Z", X="X", C="C", V="V",
    PAGEUP="PAGEUP", PAGEDOWN="PAGEDOWN", HOME="HOME", END="END",
    LCTRL="LCTRL", RCTRL="RCTRL", LCOMMAND="LCOMMAND", RCOMMAND="RCOMMAND",
    LMETA="LMETA", RMETA="RMETA",
    MOD_CTRL=0x100, MOD_COMMAND=0x200,
    B="B", N="N", M="M", _1="_1", _2="_2",
    NUM_0="NUM_0", NUM_1="NUM_1", NUM_2="NUM_2", NUM_3="NUM_3",
    NUM_ADD="NUM_ADD", NUM_ENTER="NUM_ENTER", NUM_INSERT="NUM_INSERT",
    NUM_END="NUM_END", NUM_DOWN="NUM_DOWN", NUM_NEXT="NUM_NEXT",
)
fake_pyglet.window = fake_window
sys.modules.setdefault("pyglet", fake_pyglet)
sys.modules.setdefault("pyglet.window", fake_window)
sys.path.insert(0, "emulator")

from inputs_common import (  # noqa: E402
    EXTRA_JOY1_BACK,
    EXTRA_JOY1_START,
    EXTRA_JOY1_Y,
    EXTRA_JOY2_BACK,
    EXTRA_JOY2_START,
    EXTRA_JOY2_Y,
    keyboard_state,
    keyboard_v2_state,
    KeyboardHelpGate,
    ota_shortcut_held,
    ota_shortcut_pressed,
    pack_controllers,
)


class Controller:
    def __init__(self, **values):
        self.__dict__.update(values)


def controller(**values):
    values.setdefault("leftx", 0)
    values.setdefault("lefty", 0)
    values.setdefault("rightx", 0)
    values.setdefault("righty", 0)
    values.setdefault("dpad", types.SimpleNamespace(x=0, y=0))
    values.setdefault("a", False)
    values.setdefault("b", False)
    values.setdefault("x", False)
    values.setdefault("y", False)
    values.setdefault("start", False)
    values.setdefault("back", False)
    values.setdefault("guide", False)
    values.setdefault("leftshoulder", False)
    values.setdefault("lefttrigger", 0)
    values.setdefault("rightshoulder", False)
    values.setdefault("righttrigger", 0)
    return Controller(**values)


def test_one_controller_uses_right_stick_for_joy2():
    primary = controller(
        leftx=-1, lefty=1,
        rightx=1, righty=-1,
        a=True, b=True, x=True, y=True, start=True, back=True, guide=True,
    )
    joy1, joy2, extra, home = pack_controllers(primary)
    assert joy1 == 0x79, hex(joy1)  # left, down, A/B/X
    assert joy2 == 0x06, hex(joy2)  # right stick: right, up
    assert extra == (EXTRA_JOY1_Y | EXTRA_JOY1_START | EXTRA_JOY1_BACK)
    assert home


def test_one_controller_uses_shoulder_and_trigger_for_joy2_abxy():
    primary = controller(
        leftshoulder=True, lefttrigger=1,
        rightshoulder=True, righttrigger=1,
    )
    joy1, joy2, extra, home = pack_controllers(primary)
    assert joy1 == 0
    assert joy2 == 0x70, hex(joy2)
    assert extra == EXTRA_JOY2_Y
    assert not home


def test_two_controllers_give_joy2_its_own_dpad_and_faces():
    primary = controller(rightx=-1, righty=1, a=True)
    secondary = controller(
        leftx=1, lefty=1,
        dpad=types.SimpleNamespace(x=-1, y=1),
        a=True, b=True, x=True, y=True, start=True, back=True,
    )
    joy1, joy2, extra, home = pack_controllers(primary, secondary)
    assert joy1 == 0x10, hex(joy1)
    # Controller 1's right stick is ignored.  Joy2 combines controller 2's
    # stick/D-pad and keeps its independent A/B/X/Y, Start, and Back values.
    assert joy2 == 0x7F, hex(joy2)
    assert extra == (EXTRA_JOY2_Y | EXTRA_JOY2_START | EXTRA_JOY2_BACK)
    assert not home


def test_keyboard_maps_all_protocol_v2_controls():
    expected = {
        "W": (0, 4, 0), "S": (0, 8, 0), "A": (0, 1, 0), "D": (0, 2, 0),
        "SPACE": (0, 16, 0), "B": (0, 32, 0), "N": (0, 64, 0), "M": (0, 0, 2),
        "_1": (0, 0, 32), "_2": (0, 0, 16),
        "UP": (4, 0, 0), "DOWN": (8, 0, 0), "LEFT": (1, 0, 0), "RIGHT": (2, 0, 0),
        "NUM_0": (16, 0, 0), "NUM_1": (32, 0, 0), "NUM_2": (64, 0, 0), "NUM_3": (0, 0, 1),
        "NUM_ADD": (0, 0, 8), "NUM_ENTER": (0, 0, 4),
        "NUM_INSERT": (16, 0, 0), "NUM_END": (32, 0, 0),
        "NUM_DOWN": (64, 0, 0), "NUM_NEXT": (0, 0, 1),
    }
    class Keys:
        pressed = set()
        def __getitem__(self, symbol):
            return symbol in self.pressed
    keys = Keys()
    for symbol, wanted in expected.items():
        keys.pressed = {symbol}
        joy2, extra = keyboard_v2_state(keys)
        assert pack_controllers(None, keyboard=keyboard_state(keys), keyboard_v2=(joy2, extra))[:3] == wanted, symbol
    keys.pressed = set(expected)
    assert pack_controllers(None, keyboard=keyboard_state(keys), keyboard_v2=keyboard_v2_state(keys))[:3] == (127, 127, 63)
    keys.pressed = {"O", "P", "Y", "PAGEUP", "PAGEDOWN", "H", "J", "K", "L", "Z", "X", "C", "V", "HOME", "END"}
    assert pack_controllers(None, keyboard=keyboard_state(keys), keyboard_v2=keyboard_v2_state(keys))[:3] == (0, 0, 0)


def test_help_preview_does_not_leak_held_keys_into_gameplay():
    class Keys:
        pressed = {"SPACE", "NUM_ADD"}
        def __getitem__(self, symbol):
            return symbol in self.pressed
    keys = Keys()
    gate = KeyboardHelpGate()
    assert gate.read(keys, True) == ((False,) * 7, (0, 0))
    assert gate.read(keys, False) == ((False,) * 7, (0, 0))
    keys.pressed = set()
    gate.read(keys, False)
    keys.pressed = {"SPACE", "NUM_ADD"}
    keyboard, v2 = gate.read(keys, False)
    assert pack_controllers(None, keyboard=keyboard, keyboard_v2=v2)[:3] == (0, 16, 8)


def test_ota_shortcut_requires_ctrl_or_command():
    assert ota_shortcut_pressed("U", 0x100)
    assert ota_shortcut_pressed("U", 0x200)
    assert not ota_shortcut_pressed("U", 0)
    assert not ota_shortcut_pressed("Y", 0x100)


def test_ota_shortcut_held_reads_polled_state():
    # Console mode has no key-press events, so the same chord has to be
    # recognizable from held keys alone (see consoleengine.py).
    held = lambda *pressed: {symbol: symbol in pressed for symbol in (
        "U", "Y", "LCTRL", "RCTRL", "LCOMMAND", "RCOMMAND", "LMETA", "RMETA")}

    assert ota_shortcut_held(held("U", "LCTRL"))
    assert ota_shortcut_held(held("U", "RCTRL"))
    assert ota_shortcut_held(held("U", "LCOMMAND"))
    assert ota_shortcut_held(held("U", "RMETA"))
    assert not ota_shortcut_held(held("U"))
    assert not ota_shortcut_held(held("LCTRL"))
    assert not ota_shortcut_held(held("Y", "LCTRL"))
    assert not ota_shortcut_held(held())


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("emulator inputs v2: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
