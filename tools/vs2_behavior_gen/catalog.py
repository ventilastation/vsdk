"""The static, offline Action/Behavior catalog: ``vs2.params.introspect()``
walked over a fixed class list, plus each Behavior's subject-kind
constraint, written out as one JSON-able dict.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The block editor`` -- "Only
tier 5 is generated from parameter declarations ... a new Action appears in
palette, panel, protocol and reference docs at once" -- and
``apps/micropython/vs2/params.py``'s own ``introspect()`` docstring, which
names "the Blockly field generator" as one of its four consumers by name.
Work-breakdown card: ``docs/vs2-behaviors-implementation.md`` T17, Phase 1.

**Why this needs to exist at all, separate from the live ``vs2beh``
protocol.** ``apps/micropython/ventilastation/behavior_control.py`` (T11)
already reports parameter declarations over the wire, but only for
Behaviors *currently attached to a running scene* -- there is nothing to
list with no board or emulator connected. The block editor's palette needs
every Action and Behavior that *could* be attached, at authoring time, with
nothing running at all. Hence a small CPython tool that imports the real
``vs2.actions``/``vs2.behaviors`` modules directly (safe under plain
CPython -- confirmed directly: importing them needs no
``configure_runtime()``, no display/audio hardware, nothing beyond the
``uos``/``utime`` shims every CPython-side ``vs2`` test already carries;
see :func:`_import_vs2`) and walks :func:`vs2.params.introspect` the same
way the panel and the wire protocol do, then serialises the result to a
plain JSON file the browser ``fetch()``s -- exactly
``web/runtime-manifest.json``'s own established pattern (a build-time-
generated file, no server logic).

**A real spec-vs-shipped-catalog mismatch, found while writing this.** The
spec's own worked example (``## Behaviors``) writes ``Collide(self.hits)``
as though ``targets`` were a declared parameter like any other, and "One
declaration, four consumers" implies every Action field renders from
``vs2.params.introspect()`` alone. It does not, for two of the four Phase-1
Actions:

- :class:`vs2.actions.Collide`'s constructor is
  ``__init__(self, targets, radius=None, space="world", subject=None)`` --
  plain Python keyword arguments, not ``vs2.params.Parameter`` class
  attributes. ``introspect(Collide)`` yields **zero** entries (confirmed
  directly). A Blockly block generated purely from that introspection would
  have no fields at all -- unusable for the one Action Phase 1's proving
  case (``Projectile``) actually needs.
- :class:`vs2.actions.Animate`'s ``field=`` (which attribute it writes,
  defaulting to ``"frame"``) is likewise a plain constructor keyword, not a
  declared parameter.

So this module's :data:`EXTRA_ACTION_FIELDS` hand-lists the constructor
fields ``vs2.params.introspect()`` cannot see, and every action entry in the
catalog carries both an introspected ``params`` list (possibly empty, as
for ``Collide``) and an ``extra_fields`` list (possibly empty, as for
``Move``/``MoveTo``) -- kept visibly separate in the JSON rather than
merged into one list, so a consumer (the palette generator, a future docs
generator) can tell "declared by the parameter system" apart from
"hand-added because the class predates/bypasses it" instead of the mismatch
being silently papered over. ``tools/vs2_behavior_gen/model.py``'s
``ACTION_FIELDS``/``ACTION_REQUIRED_FIELDS`` duplicate the *field names*
half of this (deliberately, to avoid that module importing real ``vs2`` --
see its own docstring) but this module is the one place the *values*
(types, defaults, required-ness) are recorded.

**Behaviors are catalog-listed for reference, not for composition.** Every
Behavior in :data:`BEHAVIOR_CLASSES` is walked the same way, including its
subject-kind constraint (:func:`_subject_kinds`, mirroring exactly how
``apps/micropython/vs2/__init__.py``'s ``_behavior_kind_mismatch`` decides
it: whichever of ``step``/``step_one``/``step_scene`` the class defines
*directly* -- inherited-from-``Behavior``-base is never true, since
``Behavior`` defines none of the three). This phase's block *generator*
only ever produces a **new** Behavior authored from Actions via the
two-zone skeleton (see ``tools/vs2_behavior_gen/model.py``); it does not
let a block program embed an *existing* catalog Behavior as a sub-unit --
nothing in the proposal describes that shape, and ``Behavior`` has no
``run``/``run_one`` contract an embedding could call the way an Action's
does. So the 16 catalog Behaviors appear in this JSON as a browsable
reference (what already exists, its knobs, what subject it needs) -- the
same job ``docs/vs2/reference/behaviors.md`` will eventually do from this
same introspection, per the proposal's own "## What has to change under the
hood" list -- not as new block types an author drags into a program. This
is a judgment call, not a mandate the spec states outright; flagged here so
a later phase can revisit it deliberately rather than rediscover the
question.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MICROPYTHON_ROOT = REPO_ROOT / "apps" / "micropython"

CATALOG_VERSION = 1

#: The exact Phase-1 catalog -- see this package's docstring and the T17
#: dispatch card for why these classes, and only these.
ACTION_CLASSES = ("Move", "MoveTo", "Animate", "Collide")

BEHAVIOR_CLASSES = (
    "Projectile", "Transient", "Lifetime", "DespawnBeyond", "Recycling",
    "Blinking", "Pinned", "Shaking", "Animated", "Moving", "Patrolling",
    "PathFollowing", "Pilotable", "Aiming", "Chasing", "Orbiting", "Laned",
)

#: Constructor-level fields ``vs2.params.introspect()`` cannot see -- see
#: this module's docstring. ``(type_name, default, required)`` per field,
#: using the same ``type_name`` vocabulary ``vs2.params.Parameter`` types
#: use (``"pool"``, ``"number"``, ``"choice"``, plus a plain ``"string"``
#: this module adds for ``Animate.field``, which no ``Parameter`` subclass
#: models -- it is a bare attribute name, not a tunable value).
EXTRA_ACTION_FIELDS = {
    "Move": {},
    "MoveTo": {},
    "Animate": {
        "field": {"type": "string", "default": "frame", "required": False},
    },
    "Collide": {
        "targets": {"type": "pool", "default": None, "required": True},
        "radius": {"type": "number", "default": None, "required": False},
        "space": {"type": "choice", "default": "world",
                   "options": ["world", "screen"], "required": False},
    },
}


def _import_vs2():
    """Import the real ``vs2.actions``/``vs2.behaviors`` modules under
    plain CPython, installing the same minimal ``uos``/``utime`` shims
    every CPython-side ``vs2`` test in this repo already carries (see
    ``tests/test_vs2_behaviors.py``'s header) -- needed transitively by
    ``vs2/__init__.py``'s own imports, not by anything this module does
    directly. No ``configure_runtime()`` call: pure class introspection
    touches no hardware-backed singleton (confirmed directly against this
    exact import sequence)."""
    import os

    if str(MICROPYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(MICROPYTHON_ROOT))

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

    from vs2 import actions, behaviors
    return actions, behaviors


def _jsonable(value):
    if isinstance(value, tuple):
        return list(value)
    return value


def _param_entries(cls):
    from vs2.params import introspect

    entries = []
    for name, type_name, default, metadata in introspect(cls):
        entry = {"name": name, "type": type_name, "default": _jsonable(default)}
        for key in ("min", "max", "step", "label", "unit", "options"):
            value = metadata.get(key)
            if value is not None:
                entry[key] = _jsonable(value)
        entries.append(entry)
    return entries


def _extra_field_entries(action_class_name):
    fields = EXTRA_ACTION_FIELDS.get(action_class_name, {})
    entries = []
    for name in sorted(fields):
        spec = fields[name]
        entry = {"name": name, "type": spec["type"], "default": _jsonable(spec["default"]),
                  "required": spec["required"]}
        if "options" in spec:
            entry["options"] = list(spec["options"])
        entries.append(entry)
    return entries


def _subject_kinds(cls):
    """Which of ``pool``/``sprite``/``scene`` ``cls`` may be attached to,
    determined the same way ``apps/micropython/vs2/__init__.py``'s
    ``_behavior_kind_mismatch`` determines it at build time: whichever of
    ``step``/``step_one``/``step_scene`` the class itself defines. A
    Behavior defining none of the three (a passive, ``attached()``-only
    one) is attachable to anything -- reported here as an empty list, not
    guessed at."""
    kinds = []
    if getattr(cls, "step", None) is not None:
        kinds.append("pool")
    if getattr(cls, "step_one", None) is not None:
        kinds.append("sprite")
    if getattr(cls, "step_scene", None) is not None:
        kinds.append("scene")
    return kinds


def _doc_summary(cls):
    doc = cls.__doc__ or ""
    first_line = doc.strip().split("\n", 1)[0].strip()
    return first_line


def build_catalog():
    """The full catalog dict: ``{"version", "actions": [...], "behaviors":
    [...]}``. Deterministic -- classes are walked in the fixed order of
    :data:`ACTION_CLASSES`/:data:`BEHAVIOR_CLASSES`, and every nested list
    (``introspect()``'s own output) is already name-sorted."""
    actions_module, behaviors_module = _import_vs2()

    action_entries = []
    for name in ACTION_CLASSES:
        cls = getattr(actions_module, name)
        action_entries.append({
            "name": name,
            "doc": _doc_summary(cls),
            "params": _param_entries(cls),
            "extra_fields": _extra_field_entries(name),
        })

    behavior_entries = []
    for name in BEHAVIOR_CLASSES:
        cls = getattr(behaviors_module, name)
        behavior_entries.append({
            "name": name,
            "doc": _doc_summary(cls),
            "params": _param_entries(cls),
            "state": list(cls.state),
            "subject_kinds": _subject_kinds(cls),
        })

    return {
        "version": CATALOG_VERSION,
        "actions": action_entries,
        "behaviors": behavior_entries,
    }


def write_catalog(output_path):
    """Write :func:`build_catalog`'s result to ``output_path`` as
    indented, deterministic JSON (sorted keys are unnecessary -- every dict
    above is already built key-by-key in a fixed order -- but ``indent=2``
    keeps a diff of this committed file readable)."""
    catalog = build_catalog()
    output_path.write_text(json.dumps(catalog, indent=2) + "\n")
    return catalog
