"""Headless coverage for games/vs2_examples/event_sheet_demo -- the T16
"event sheet" proving case: a small, original three-scene game (title,
playable, game over) authored through tools/vs2_event_gen, driven end to
end via director.step_once() the same way
tests/test_vixeous_vs2_examples.py drives the T15 proving case.

What this actually proves, tick by tick:

- Title's on_start (generated) sets the "PRESS A" label; pressing A
  (hand-written escape hatch -- title_scene.py) transitions to Playing.
- Playing's on_start/on_tick (entirely generated) stage a score up via
  successive timer_elapsed thresholds and switch to Game Over once a
  compare condition on that score is met.
- The score is a vs2.project variable, so it survives the Playing ->
  GameOver Scene.switch() -- the acceptance line's "a score surviving
  the transition" -- and Game Over's on_start (generated) reads it back
  and displays it.
- Game Over's on_tick (generated) switches back to Title after a
  timer_elapsed wait, completing the loop.
"""

import os
import random
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, ROOT)
sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", random)
if "utime" not in sys.modules:
    class _Utime:
        @staticmethod
        def ticks_ms():
            return int(time.time() * 1000)

        @staticmethod
        def ticks_add(value, delta):
            return value + delta

        @staticmethod
        def ticks_diff(end, start):
            return end - start

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime

import vs2
from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes
from vs2.controls import A

FONT_STRIP = "font.png"


class EventSheetDemoTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            stripes[FONT_STRIP] = 0
            runtime_director.platform.sprites.stripes[0] = {
                "width": 4,
                "height": 6,
                "frames": 20,
                "palette": 0,
                "glyphs": " 0123456789AEGMOPRSV",
            }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step(self, buttons=0):
        director.platform.comms.push_input(bytes([buttons]))
        try:
            director.step_once()
        except StopIteration:
            pass

    def step_many(self, count, buttons=0):
        for _ in range(count):
            self.step(buttons)

    # -- Title ------------------------------------------------------------

    def test_title_shows_press_a(self):
        scene = load_app("vs2_examples.event_sheet_demo")
        self.assertEqual(scene.title_label.text, "PRESS A")

    def test_pressing_a_transitions_title_to_playing(self):
        from games.vs2_examples.event_sheet_demo.code.playing_scene import Playing

        load_app("vs2_examples.event_sheet_demo")
        self.step(buttons=A)
        self.assertIsInstance(director.scene_stack[-1], Playing)

    def test_a_does_nothing_before_it_is_pressed(self):
        from games.vs2_examples.event_sheet_demo.code.title_scene import Title

        load_app("vs2_examples.event_sheet_demo")
        self.step_many(5, buttons=0)
        self.assertIsInstance(director.scene_stack[-1], Title)

    # -- Playing / score staging -------------------------------------------

    def test_score_starts_at_zero_on_entry(self):
        load_app("vs2_examples.event_sheet_demo")
        self.step(buttons=A)  # Title -> Playing; Playing.on_enter runs
        self.assertEqual(vs2.project.score, 0)

    def test_score_steps_up_via_timer_elapsed_thresholds(self):
        load_app("vs2_examples.event_sheet_demo")
        self.step(buttons=A)  # tick 0 in Playing: on_enter only

        self.step_many(19)  # ticks 1..19: _vs2_events_ticks reaches 19
        self.assertEqual(vs2.project.score, 0)

        self.step()  # tick 20: timer_elapsed(20) fires
        self.assertEqual(vs2.project.score, 10)

    # -- Playing -> GameOver, score survives the transition ----------------

    def test_score_survives_the_playing_to_gameover_transition(self):
        from games.vs2_examples.event_sheet_demo.code.gameover_scene import GameOver

        load_app("vs2_examples.event_sheet_demo")
        self.step(buttons=A)  # -> Playing

        # timer_elapsed(60) sets score to random(25, 35); the very same
        # tick's compare(score >= 25) then fires and switches to GameOver
        # -- see playing_scene.vs2events.json / the generator's sequential
        # same-tick evaluation.
        self.step_many(60)

        self.assertIsInstance(director.scene_stack[-1], GameOver)
        score = vs2.project.score
        self.assertGreaterEqual(score, 25)
        self.assertLessEqual(score, 35)
        # The whole point: GameOver's on_start (generated) read the same
        # vs2.project.score value Playing just set, across the switch().
        self.assertEqual(director.scene_stack[-1].score_label.text, str(score))
        self.assertEqual(director.scene_stack[-1].title_label.text, "GAME OVER")

    # -- GameOver -> Title, completing the loop ----------------------------

    def test_gameover_returns_to_title_after_its_wait(self):
        from games.vs2_examples.event_sheet_demo.code.title_scene import Title

        load_app("vs2_examples.event_sheet_demo")
        self.step(buttons=A)      # -> Playing
        self.step_many(60)        # -> GameOver
        self.step_many(89)        # ticks 1..89 in GameOver: not yet
        self.assertNotIsInstance(director.scene_stack[-1], Title)

        self.step()               # tick 90: timer_elapsed(90) fires
        self.assertIsInstance(director.scene_stack[-1], Title)
        # Back on the title screen, ready to play again.
        self.assertEqual(director.scene_stack[-1].title_label.text, "PRESS A")

    def test_full_loop_runs_many_times_without_crashing(self):
        # A coarse "does the whole thing hold together" smoke test: cycle
        # through all three scenes twice.
        load_app("vs2_examples.event_sheet_demo")
        for _ in range(2):
            self.step(buttons=A)  # Title -> Playing
            self.step_many(60)    # Playing -> GameOver
            self.step_many(90)    # GameOver -> Title


if __name__ == "__main__":
    unittest.main()
