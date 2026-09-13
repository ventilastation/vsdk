"""Tests for tools/vs2_behavior_gen/generator.py -- model -> generated
``Behavior`` subclass source, the checksum/hand-edit/Detach round-trip, and
-- the real acceptance bar this task's dispatch card sets -- building
``Projectile`` from blocks, generating its ``.py``, and running it through
the *exact same* behavioral checks ``tests/test_vs2_behaviors.py`` already
runs against the real, hand-written ``Projectile``: the hoisted ``Move``,
despawn past ``range``, and despawn on a ``Collide`` hit.

Two test classes:

- ``RoundTripTests`` -- pure text-level generator mechanics, pure CPython,
  no ``vs2`` import, mirroring ``tests/test_vs2_scene_gen_generator.py``/
  ``tests/test_vs2_event_gen.py``'s own structure.
- ``GeneratedProjectileBehaviorTests`` -- imports the real ``vs2`` package
  (the same ``uos``/``utime`` CPython shims ``tests/test_vs2_behaviors.py``
  installs), writes the generated source to a real temp file, imports it
  with ``importlib``, and runs it through a real ``vs2.Scene``. Not
  byte-identical to the hand-written ``Projectile`` (different authoring
  path, different local variable names inside the generated ``if``/``else``
  -- see ``generator.py``'s own docstring on why the loop shape is copied
  verbatim while the per-sprite body is generated) -- proven *behaviorally*
  equivalent instead, which is what the dispatch card actually asks for.

Run: ``python3 tests/test_vs2_behavior_gen_generator.py``
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_behavior_gen import checksum, detach, generator
from tools.vs2_behavior_gen.model import ModelError


def _param(name, type_="number", default=0, **extra):
    entry = {"name": name, "type": type_, "default": default}
    entry.update(extra)
    return entry


def _param_ref(name):
    return {"kind": "param", "name": name}


def _state_ref(name):
    return {"kind": "state", "name": name}


def projectile_model():
    """The block-program model for ``Projectile``, expressed exactly the
    way an author composing the two-zone tick skeleton in the block editor
    would produce it (see ``model.py``'s own module docstring, which shows
    this identical model as its worked example)."""
    return {
        "version": 1,
        "class_name": "GeneratedProjectile",
        "subject_kind": "pool",
        "params": [
            _param("speed_x", "angle", 0, min=-32, max=32, step=0.25,
                   label="Angular speed", unit="col/tick"),
            _param("speed_y", "number", 8, min=-32, max=32, step=0.25,
                   label="Radial speed", unit="led/tick"),
            _param("range", "number", 180, min=1, max=255, step=1,
                   label="Range", unit="led"),
            _param("hits", "pool", None, label="Hits what"),
        ],
        "state": ["shot_flown"],
        "actions": [
            {"bind": "move", "action_class": "Move",
             "args": {"speed_x": _param_ref("speed_x"), "speed_y": _param_ref("speed_y")}},
            {"bind": "hit", "action_class": "Collide",
             "args": {"targets": _param_ref("hits")}},
        ],
        "apply_to_all": ["move"],
        "per_sprite": [
            {"kind": "accumulate", "state": "shot_flown", "amount": _param_ref("speed_y")},
            {"kind": "if_else",
             "condition": {"kind": "compare", "op": ">",
                            "left": _state_ref("shot_flown"), "right": _param_ref("range")},
             "then": [{"kind": "despawn"}],
             "else": [{"kind": "if_action", "bind": "hit",
                        "then": [{"kind": "despawn_hit"}, {"kind": "despawn"}], "else": []}]},
        ],
    }


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="vs2_behavior_gen_test_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_source_has_the_banner_body_blob_shape(self):
        text = generator.generate_source(projectile_model(), "generated_projectile.py")
        parsed = checksum.split_generated_file(text)
        self.assertIsNotNone(parsed)
        banner_line, body, blob_line = parsed
        self.assertEqual(checksum.recorded_sha(banner_line), checksum.body_sha(body))
        self.assertIn("class GeneratedProjectile(Behavior):", body)
        self.assertIn("def step(self, sprites):", body)
        self.assertTrue(blob_line.startswith("# behavior-blocks: "))

    def test_uses_its_own_third_blob_prefix_not_the_other_two_generators(self):
        text = generator.generate_source(projectile_model(), "x.py")
        self.assertIn("# behavior-blocks: ", text)
        self.assertNotIn("\n# scene-model: ", text)
        self.assertNotIn("\n# blocks: ", text)

    def test_regenerating_an_unchanged_model_is_byte_identical(self):
        model = projectile_model()
        first = generator.generate_source(model, "x.py")
        second = generator.generate_source(model, "x.py")
        self.assertEqual(first, second)

    def test_blob_round_trips_the_exact_model(self):
        from tools.vs2_scene_gen.blob import decode_blob
        model = projectile_model()
        text = generator.generate_source(model, "x.py")
        _banner, _body, blob_line = checksum.split_generated_file(text)
        decoded = decode_blob(checksum.blob_data(blob_line))
        self.assertEqual(decoded, model)

    def test_invalid_model_raises_model_error(self):
        model = projectile_model()
        model["subject_kind"] = "nonsense"
        with self.assertRaises(ModelError):
            generator.generate_source(model, "x.py")

    def test_write_behavior_file_created_then_unchanged(self):
        path = self.tmpdir / "generated_projectile.py"
        first = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(first.status, "created")
        second = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(second.status, "unchanged")

    def test_write_behavior_file_updates_on_a_model_change(self):
        path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(projectile_model(), path)
        changed = projectile_model()
        changed["params"][2]["default"] = 220  # range
        result = generator.write_behavior_file(changed, path)
        self.assertEqual(result.status, "updated")
        self.assertIn("range = Number(220", path.read_text())

    def test_write_behavior_file_detects_hand_edit(self):
        path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(projectile_model(), path)
        text = path.read_text()
        path.write_text(text.replace("range", "distance"))
        result = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(result.status, "hand_edited")
        # and the file on disk was left untouched by the refused write
        self.assertIn("distance", path.read_text())

    def test_write_behavior_file_reports_detached_file_as_not_ours(self):
        path = self.tmpdir / "generated_projectile.py"
        path.write_text("class GeneratedProjectile:\n    pass\n")
        result = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(result.status, "detached")
        # left untouched
        self.assertEqual(path.read_text(), "class GeneratedProjectile:\n    pass\n")

    def test_detach_strips_banner_and_blob_one_way(self):
        path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(projectile_model(), path)
        detached_text = detach.detach_file(path)
        self.assertNotIn("behavior-blocks", detached_text)
        self.assertNotIn("generated, do not edit", detached_text)
        self.assertTrue(detach.is_generated(path.read_text()) is False)
        # regenerating no longer touches this file's shape at all -- it's
        # not generator-managed any more.
        result = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(result.status, "detached")

    def test_sprite_subject_kind_generates_step_one_with_no_loop(self):
        model = projectile_model()
        model["subject_kind"] = "sprite"
        text = generator.generate_source(model, "x.py")
        self.assertIn("def step_one(self, sprite):", text)
        self.assertNotIn("sprites._live", text)
        self.assertIn("self.move.run_one(sprite)", text)


# ---------------------------------------------------------------------------
# The real acceptance bar: import the real vs2 package, build a scene, run
# the GENERATED Projectile through the exact same assertions
# tests/test_vs2_behaviors.py runs against the HAND-WRITTEN one.
# ---------------------------------------------------------------------------

MICROPYTHON_ROOT = str(Path(ROOT) / "apps" / "micropython")
if MICROPYTHON_ROOT not in sys.path:
    sys.path.insert(0, MICROPYTHON_ROOT)

sys.modules.setdefault("uos", os)
try:
    import utime  # noqa: F401
except ImportError:
    import time as _time

    class _Utime:
        @staticmethod
        def ticks_ms():
            return int(_time.time() * 1000)

        @staticmethod
        def ticks_us():
            return int(_time.time() * 1000000)

        @staticmethod
        def ticks_add(value, delta):
            return value + delta

        @staticmethod
        def ticks_diff(end, start):
            return end - start
    sys.modules["utime"] = _Utime

import gc  # noqa: E402

import vs2  # noqa: E402
from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402


def _load_generated_class(model, tmpdir, basename="generated_projectile.py"):
    """Write ``model``'s generated source to a real file under ``tmpdir``
    and import it with ``importlib`` -- proving the generator's *actual
    file output* runs, not merely the in-memory ``render_body()`` string."""
    path = Path(tmpdir) / basename
    generator.write_behavior_file(model, path)
    module_name = "vs2_behavior_gen_test_" + basename[:-3]
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, model["class_name"])


class GeneratedProjectileBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vs2_behavior_gen_exec_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["ship.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 4, "height": 4, "frames": 4, "palette": 0,
        }
        api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")
        self.GeneratedProjectile = _load_generated_class(projectile_model(), self.tmpdir)

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_scene(self, build_fn):
        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                build_fn(self)

            def update(self):
                pass

        game = Game()
        director.push(game)
        return game

    def test_generated_class_is_a_real_behavior_subclass(self):
        from vs2.behaviors import Behavior
        self.assertTrue(issubclass(self.GeneratedProjectile, Behavior))

    def test_moves_via_the_hoisted_move_action(self):
        """Mirrors tests/test_vs2_behaviors.py's
        test_projectile_moves_via_the_hoisted_move_action exactly, against
        the generated class instead of the hand-written one."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=2)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=1, speed_y=2, range=200, hits=scene.targets))
            scene.shots.spawn(10, 10)

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        behavior.step(game.shots)
        sprite = game.shots._live[0]
        self.assertEqual(sprite.dx, 1)
        self.assertEqual(sprite.dy, 2)
        self.assertEqual(sprite.shot_flown, 2)

    def test_despawns_past_its_range(self):
        """Mirrors test_projectile_despawns_past_its_range."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=10, range=25, hits=scene.targets))
            scene.shots.spawn(0, 0)

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        for _ in range(3):
            behavior.step(game.shots)
        self.assertEqual(len(game.shots), 0)

    def test_despawns_both_sprites_on_a_hit(self):
        """Mirrors test_projectile_despawns_both_sprites_on_a_hit."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=0, range=200, hits=scene.targets))
            scene.shots.spawn(10, 10)
            scene.targets.spawn(10, 10)  # exactly overlapping

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        behavior.step(game.shots)
        self.assertEqual(len(game.shots), 0)
        self.assertEqual(len(game.targets), 0)

    def test_does_not_despawn_or_hit_when_neither_condition_is_met(self):
        """A case the three mirrored tests above don't cover on their own:
        proves the if/else split is real (the Collide branch is only
        reached when the range branch is NOT taken), not an artifact of
        each test only ever exercising one arm."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=1, range=200, hits=scene.targets))
            scene.shots.spawn(0, 0)
            scene.targets.spawn(100, 100)  # far away: never hit

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        for _ in range(5):
            behavior.step(game.shots)
        self.assertEqual(len(game.shots), 1)
        self.assertEqual(len(game.targets), 1)
        self.assertEqual(game.shots._live[0].shot_flown, 5)

    def test_zero_allocation_over_1000_steps(self):
        """The same allocation-regression shape every Behavior test in this
        repo uses (tests/test_vs2_behaviors.py's own
        test_scene_with_projectile_over_100_sprites_..., trimmed to one
        sprite + one target since this is a generator smoke test, not a
        fresh benchmark)."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=-0.25, range=255, hits=scene.targets))
            scene.shots.spawn(0, 0)
            scene.targets.spawn(250, 250)  # far away: Collide never hits

        game = self._build_scene(build)
        for _ in range(50):
            game.scene_step()  # warm up any one-time caches

        try:
            gc.mem_free()
        except AttributeError:
            self.skipTest("gc.mem_free() unavailable (this is CPython, not MicroPython)")

        gc.collect()
        before = gc.mem_free()
        for _ in range(1000):
            game.scene_step()
        gc.collect()
        after = gc.mem_free()
        self.assertGreaterEqual(after, before - 4096)


if __name__ == "__main__":
    unittest.main()
