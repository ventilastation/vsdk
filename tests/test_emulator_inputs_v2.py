"""Pure controller-routing checks without requiring the pyglet package."""

import sys
import types


fake_pyglet = types.ModuleType("pyglet")
fake_window = types.ModuleType("pyglet.window")
fake_window.key = types.SimpleNamespace()
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


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("emulator inputs v2: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
