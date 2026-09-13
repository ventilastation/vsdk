"""Standalone CLI: one ``.vs2behavior.json`` in, one generated ``<name>.py``
out.

Usage::

    python3 tools/vs2_behavior_gen/build_behavior.py path/to/enemy_states.vs2behavior.json

Writes (or safely refuses to overwrite) ``path/to/enemy_states.py`` via
:func:`tools.vs2_behavior_gen.generator.write_behavior_file`. Mirrors
``tools/vs2_event_gen/build_events.py``'s own CLI shape exactly (same
``output_path_for``/``build_one``/``main`` split, same error handling), one
deliberate difference in the naming rule: **the suffix is substituted in
place** (``<name>.vs2behavior.json`` -> ``<name>.py``), not appended, because
this generator's output is a whole, drop-in ``Behavior``/``StateMachine``
subclass -- exactly ``tools/vs2_scene_gen``'s own ``<name>.vs2model.json`` ->
``<name>.py`` rule, not ``vs2_event_gen``'s "companion mixin beside a
same-named hand-written scene" one (see that module's own docstring for why
*its* rule differs).

This is what ``games/vs2_examples/vasura_states_demo``'s own
``code/enemy_states.vs2behavior.json`` -> ``code/enemy_states.py`` is built
with (see that game's ``code/build_enemy_states.py``, which constructs the
model dict this CLI's ``build_one`` then validates and generates from --
Phase 2 has no Blockly panel support for state hats yet, so "authoring the
block program" is that one small Python script instead of the browser
panel, the same stand-in T16's own event-sheet models used before a panel
existed for those either).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.vs2_behavior_gen import generator, model  # noqa: E402


class BuildError(ValueError):
    """Raised for a usage error this CLI's own ``main()`` reports and turns
    into a clean non-zero exit, rather than a traceback."""


MODEL_SUFFIX = ".vs2behavior.json"


def output_path_for(model_path):
    """``<name>.vs2behavior.json`` -> ``<name>.py``, sitting beside it."""
    model_path = Path(model_path)
    name = model_path.name
    if not name.endswith(MODEL_SUFFIX):
        raise BuildError("%s: expected a name ending in %r" % (model_path, MODEL_SUFFIX))
    stem = name[: -len(MODEL_SUFFIX)]
    return model_path.with_name(stem + ".py")


def build_one(model_path):
    """Validate and (safely) generate the ``.py`` for one
    ``.vs2behavior.json``. Returns the :class:`generator.WriteResult`."""
    model_path = Path(model_path)
    data = json.loads(model_path.read_text())
    model.validate_model(data)
    output_path = output_path_for(model_path)
    return generator.write_behavior_file(data, output_path)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: build_behavior.py <name>.vs2behavior.json", file=sys.stderr)
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
