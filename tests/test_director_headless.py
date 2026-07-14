"""Director/scene lifecycle tests on the headless platform.

Runs under the MicroPython unix port (plain asserts, no unittest):

    micropython tests/test_director_headless.py
"""

import sys

sys.path.insert(0, "apps/micropython")

from ventilastation.director import configure_runtime, director, reset_runtime
from ventilastation.scene import Scene


def fresh_runtime():
    reset_runtime()
    return configure_runtime("headless")


def test_scene_lifecycle():
    runtime = fresh_runtime()
    events = []

    class Probe(Scene):
        def on_enter(self):
            events.append("enter")

        def on_exit(self):
            events.append("exit")

        def step(self):
            events.append("step")

    scene = Probe()
    director.push(scene)
    director.step_once()
    assert events == ["enter", "step"], events
    director.pop()
    assert events == ["enter", "step", "exit"], events
    assert not runtime.scene_stack


def test_button_edges():
    runtime = fresh_runtime()
    edges = []

    class Probe(Scene):
        def step(self):
            edges.append((
                director.is_pressed(director.BUTTON_A),
                director.was_pressed(director.BUTTON_A),
                director.was_released(director.BUTTON_A),
            ))

    director.push(Probe())
    director.step_once()                                   # idle frame
    runtime.platform.comms.push_input(bytes([0x10]))
    director.step_once()                                   # press frame
    director.step_once()                                   # held frame
    runtime.platform.comms.push_input(bytes([0x00]))
    director.step_once()                                   # release frame
    assert edges == [
        (False, False, False),
        (True, True, False),
        (True, False, False),
        (False, False, True),
    ], edges


def test_joy2_and_exit_return_to_root_scene():
    runtime = fresh_runtime()
    comms = runtime.platform.comms
    joy2 = [0]
    extra = [0]
    commands = []
    comms.next_joy2 = lambda: joy2[0]
    comms.next_extra = lambda: extra[0]
    comms.next_command = lambda: commands.pop(0) if commands else None
    events = []

    class Menu(Scene):
        def on_enter(self):
            events.append("menu-enter")

        def step(self):
            events.append("menu-step")

    class Game(Scene):
        def on_exit(self):
            events.append("game-exit")

        def step(self):
            events.append("game-step")

    menu = Menu()
    director.push(menu)
    director.push(Game())
    comms.push_input(bytes([director.BUTTON_A]))
    joy2[0] = director.BUTTON2_A | director.BUTTON2_C
    extra[0] = director.EXTRA_JOY1_Y | director.EXTRA_JOY2_Y
    director.step_once()
    assert director.is_pressed(director.BUTTON_Y)
    assert director.is_pressed2(director.BUTTON2_A | director.BUTTON2_X)
    assert director.is_pressed2(director.BUTTON2_Y)

    commands.append("exit")
    director.step_once()
    assert runtime.scene_stack == [menu]
    assert events[-3:] == ["game-exit", "menu-enter", "menu-step"], events
    assert director.buttons == 0
    assert director.buttons2 == 0


def test_push_rollback_on_failing_enter():
    fresh_runtime()

    class Good(Scene):
        def step(self):
            pass

    class Bad(Scene):
        def on_enter(self):
            raise ValueError("boom")

    good = Good()
    director.push(good)
    try:
        director.push(Bad())
    except ValueError:
        pass
    else:
        raise AssertionError("Bad.on_enter should have propagated")
    assert director.scene_stack[-1] is good
    # The failing enter must be reported to the host as a traceback.
    sent = [line for line, _data in director.platform.comms.sent]
    assert any(line.startswith(b"traceback") for line in sent), sent
    director.step_once()  # the surviving scene still runs


def test_call_later_ordering():
    fresh_runtime()
    calls = []

    class Timers(Scene):
        def on_enter(self):
            super().on_enter()
            self.call_later(0, lambda: calls.append("now"))
            self.call_later(10000, lambda: calls.append("later"))

        def step(self):
            pass

    director.push(Timers())
    director.step_once()
    assert calls == ["now"], calls


def test_runtime_reset():
    fresh_runtime()
    reset_runtime()
    try:
        director.step_once()
    except RuntimeError:
        pass
    else:
        raise AssertionError("director should be unusable after reset_runtime")


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("director headless: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
