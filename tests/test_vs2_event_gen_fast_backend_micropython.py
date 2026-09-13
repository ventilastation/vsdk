"""T17 Phase 3: real-MicroPython parity between tools/vs2_event_gen's
readable and fast backends.

Deliberately small: tools/vs2_event_gen/generator.py's own module
docstring (:data:`BACKENDS`) is honest that this generator's grammar has
exactly one fast-backend site at all (constant-folding a literal-vs-
literal ``compare`` into a plain ``True``/``False``) -- no per-sprite
loop to hoist across (event sheets have no sprites), no single-use local
worth inlining. This file exists to prove that one real transform is
behaviorally inert on real MicroPython too, not just "looks right" from
reading the rendered text (tests/test_vs2_event_gen.py's own
``FastBackendTests`` already covers that CPython side).

Fixtures (not generated at test time, matching every other
real-MicroPython test in this effort -- see
tests/test_vs2_behavior_gen_micropython.py's own docstring for why):
tests/fixtures/fold_demo_scene_events_fixture.py (readable) and
tests/fixtures/fold_demo_scene_events_fast_fixture.py (fast), both for the
same tiny synthetic model (one always-true and one always-false
literal-vs-literal compare -- see this file's own generation script in
this task's report). No CPython-side drift guard exists for these two
(unlike the three vs2_behavior_gen fixture pairs) since this model is a
one-off built only for this test, not exercised anywhere else.

Run: ``micropython tests/test_vs2_event_gen_fast_backend_micropython.py``
"""

import sys

sys.path.insert(0, "apps/micropython")
sys.path.insert(0, "tests/fixtures")

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime
import vs2

from fold_demo_scene_events_fixture import FoldDemoSceneEvents as Readable
from fold_demo_scene_events_fast_fixture import FoldDemoSceneEvents as Fast


def _run(scene_cls):
    reset_runtime()
    api_guard.reset()
    configure_runtime("headless")
    api_guard.begin_app("games.test_vs2_event_gen_fast_backend", "vs2")

    scene = scene_cls()
    scene.idle_timeout = None
    scene.back_button = False
    director.push(scene)

    snapshots = []
    for _ in range(5):
        scene.update()
        snapshots.append(vs2.project.score)
    return snapshots


def test_readable_and_fast_produce_identical_score_history():
    readable = _run(Readable)
    fast = _run(Fast)
    assert readable == fast, (readable, fast)
    # Sanity: the always-true branch actually ran every tick (score reset
    # to 1 each time via the folded `random(1, 1)`), and the always-false
    # one never did (score would be 999 otherwise) -- confirms this
    # comparison isn't vacuously trivial.
    assert readable == [1, 1, 1, 1, 1], readable


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("vs2 event gen fast backend (micropython): %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
