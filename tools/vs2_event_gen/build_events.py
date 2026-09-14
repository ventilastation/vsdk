"""Standalone CLI: one ``.vs2events.json`` in, one generated
``<name>_events.py`` companion out.

Usage::

    python3 tools/vs2_event_gen/build_events.py path/to/title_scene.vs2events.json

Writes (or safely refuses to overwrite) ``path/to/title_scene_events.py``
via :func:`tools.vs2_event_gen.generator.write_events_file`. This is what
this task's proving game (``games/vs2_examples/event_sheet_demo``) is built
with, and what CI/tests call for it -- see ``tests/test_vs2_event_gen.py``.

**No ``regenerate.py`` sweep in this pass.** ``tools/vs2_scene_gen`` has one
(``regenerate_all``, walking a whole tree of ``.vs2model.json`` files) plus
an on-creation-only companion-stub helper. This package skips both: a
single hand-invoked file is enough for one proving game with three event
sheets, and there is no companion-stub need here because the hand-written
scene class already exists before the event sheet is authored (the model
does not invent new attribute names the way ``vs2_scene_gen``'s ``handler``
value tag does). Judgment call, not a hard rule -- once a second game
authors event sheets through the web panel described in this task, a sweep
that walks every ``*.vs2events.json`` under ``games/`` the way
``regenerate_all`` walks ``*.vs2model.json`` is the obvious next step, and
should probably land before this generator is used for anything beyond the
one proving game.

Naming convention, exactly: ``<name>.vs2events.json`` -> ``<name>_events.py``
(mirrors T15's ``<name>.vs2model.json`` -> ``<name>.py``, except the suffix
is appended rather than substituted in place, because the generated file
here is a *companion mixin* beside a same-named hand-written scene module,
not a drop-in replacement for one -- ``title_scene.py`` is the hand-written
class; ``title_scene_events.py`` is what this module writes).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.vs2_event_gen import generator, model  # noqa: E402


class BuildError(ValueError):
    """Raised for a usage error this CLI's own ``main()`` reports and
    turns into a clean non-zero exit, rather than a traceback."""


MODEL_SUFFIX = ".vs2events.json"


def output_path_for(model_path):
    """``<name>.vs2events.json`` -> ``<name>_events.py``, sitting beside
    it."""
    model_path = Path(model_path)
    name = model_path.name
    if not name.endswith(MODEL_SUFFIX):
        raise BuildError("%s: expected a name ending in %r" % (model_path, MODEL_SUFFIX))
    stem = name[: -len(MODEL_SUFFIX)]
    return model_path.with_name(stem + "_events.py")


def build_one(model_path):
    """Validate and (safely) generate the companion file for one
    ``.vs2events.json``. Returns the :class:`generator.WriteResult`."""
    model_path = Path(model_path)
    data = json.loads(model_path.read_text())
    model.validate_model(data)
    output_path = output_path_for(model_path)
    return generator.write_events_file(data, output_path)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: build_events.py <name>.vs2events.json", file=sys.stderr)
        return 2
    try:
        result = build_one(argv[0])
    except (BuildError, model.ModelError, OSError) as error:
        print("error: %s" % (error,), file=sys.stderr)
        return 1
    print("%s: %s (%s)" % (result.status, result.path, result.message))
    return 0 if result.status != "hand_edited" else 1


if __name__ == "__main__":
    sys.exit(main())
