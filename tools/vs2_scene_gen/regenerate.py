"""The "regenerate everything" sweep, and the on-creation-only companion
stub helper.

Spec (``## What has to change under the hood``): "``tools/``: a headless
generator so CI can regenerate every in-tree generated file and assert it
is byte-identical."

**Model/output pairing convention.** A scene model lives beside the file
it generates, as ``<stem>.vs2model.json`` next to ``<stem>.py`` (e.g.
``vixeous_scene.vs2model.json`` -> ``vixeous_scene.py``) -- co-located so
``git mv``-ing a game's ``code/`` folder carries both together, and
discoverable with one glob, no separate registry file to keep in sync
with the tree.

**Never touches a companion (hand-written game-logic) file.** Only this
convention's own ``.py`` siblings are regenerated. A companion file like
``vixeous.py`` (the ``update()``/event-handler file next to a generated
``vixeous_scene.py``) has no ``.vs2model.json`` of its own and is never
looked at by :func:`regenerate_all` -- see :func:`ensure_companion_stub`
for the one, narrowly-scoped exception (creating a *missing* companion
file, once).
"""

import json
from pathlib import Path

from . import generator

MODEL_SUFFIX = ".vs2model.json"


def discover_models(root):
    """Every scene-model file under ``root``, sorted for deterministic
    reporting order."""
    root = Path(root)
    return sorted(root.rglob("*" + MODEL_SUFFIX))


def output_path_for(model_path):
    """The generated ``.py`` file a model path is paired with, per this
    module's naming convention."""
    model_path = Path(model_path)
    stem = model_path.name[: -len(MODEL_SUFFIX)]
    return model_path.with_name(stem + ".py")


def regenerate_all(root):
    """Regenerate every discovered model under ``root``. Returns the list
    of :class:`generator.WriteResult`, one per model, in the same order
    as :func:`discover_models`. Never raises on a hand-edited or detached
    target -- those are ordinary statuses in the result list, not
    exceptions; a caller that wants CI to fail on either should inspect
    the statuses (see this module's ``main`` for the convention)."""
    results = []
    for model_path in discover_models(root):
        model = json.loads(Path(model_path).read_text())
        results.append(generator.write_scene_file(model, output_path_for(model_path)))
    return results


# ---------------------------------------------------------------------------
# Companion stub: "on a detached file it offers a Python stub instead, on
# creation only, never on regeneration."
# ---------------------------------------------------------------------------

class CompanionResult:
    """``status`` is ``"created"`` (the companion file did not exist; a
    stub subclass plus one stub method per handler reference was written)
    or ``"left_alone"`` (the companion file already existed -- per the
    spec, this tool never edits it again, regardless of what handler
    references the model gains or loses afterwards)."""

    def __init__(self, status, path, handlers):
        self.status = status
        self.path = path
        self.handlers = handlers

    def __repr__(self):
        return "CompanionResult(%r, %r, %r)" % (self.status, str(self.path), self.handlers)


def _collect_handlers(model):
    handlers = set()

    def walk_params(params):
        for value in params.values():
            if isinstance(value, dict) and set(value.keys()) == {"handler"}:
                handlers.add(value["handler"])

    for behavior in model.get("scene_behaviors", []):
        walk_params(behavior.get("params", {}))
    for layer in model["layers"]:
        for drawable in layer.get("drawables", []):
            for behavior in drawable.get("behaviors", []):
                walk_params(behavior.get("params", {}))
    return sorted(handlers)


def ensure_companion_stub(model, scene_module, generated_class_name, subclass_name,
                           companion_path):
    """If ``companion_path`` does not exist, create it: a ``subclass_name``
    subclass of ``generated_class_name`` (imported from ``scene_module``,
    a plain dotted or relative module name written verbatim into the
    ``import`` line), with one stub method per ``{"handler": ...}``
    reference the model contains -- each a ``pass``-bodied ``# TODO``, so
    the file compiles and the scene builds even before anyone fills them
    in -- plus a ``main()`` returning an instance.

    If ``companion_path`` already exists, this does **nothing** and
    returns ``"left_alone"`` -- per the spec, "on a detached file it
    offers a Python stub instead, on creation only, never on
    regeneration": once a companion file exists, it is the author's
    forever, exactly like a ``Detach``-ed scene file, and this function
    must never re-open it to add a handler a later model change
    introduces. (The block-hat mechanism that would let the *block*
    editor wire a fresh reference into an already-detached file is T17's
    job -- see this package's report.)
    """
    handlers = _collect_handlers(model)
    if companion_path.exists():
        return CompanionResult("left_alone", companion_path, handlers)

    lines = [
        '"""%s: hand-written game logic.' % (subclass_name,),
        "",
        "Created once by tools/vs2_scene_gen.regenerate.ensure_companion_stub --",
        "never touched by a later regenerate_all() pass. Edit this file freely;",
        "it is yours from the moment it is created.",
        '"""',
        "import %s" % (scene_module,),
        "",
        "",
        "class %s(%s.%s):" % (subclass_name, scene_module, generated_class_name),
    ]
    if handlers:
        for handler in handlers:
            lines.append("    def %s(self, *args):" % (handler,))
            lines.append("        pass  # TODO: implement")
            lines.append("")
    else:
        lines.append("    pass")
        lines.append("")
    lines.append("")
    lines.append("def main():")
    lines.append("    return %s()" % (subclass_name,))
    lines.append("")

    companion_path.write_text("\n".join(lines))
    return CompanionResult("created", companion_path, handlers)


def main(argv=None):
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]) if args else Path(".")
    results = regenerate_all(root)
    ok = True
    for result in results:
        print("%s %s -- %s" % (result.status, result.path, result.message))
        if result.status == "hand_edited":
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
