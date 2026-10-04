"""vs2_event_gen: the T16 event-sheet -> ``on_enter()``/``update()`` generator.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The block editor`` (tiers 1-4:
events/conditions, expressions, variables, system actions -- tier 5, the
sprite-Action catalog, is T17's job) and ``### Round-trip: one embedded blob
and one one-way door`` (the checksum/blob/``Detach`` mechanics, applied here
at event-sheet granularity). Work-breakdown card:
``docs/vs2-behaviors-implementation.md`` T16.

**This is a deliberately minimal first pass**, scoped down the same way T15
cut "scene editor" to "no drag-and-drop canvas, just the generator
pipeline". Built here: exactly two events (``on_start``, ``on_tick``), two
conditions (``compare``, ``timer_elapsed``), three expressions (literal,
variable-read, ``random``), and three system actions (``set_variable``,
``goto_scene``, ``set_label_text``). Not built here, on purpose: the
sprite/pool Action-catalog tier (T17), state hats/``StateMachine`` blocks
(T17), the debugger line-map, and the "fast" codegen backend -- only the
readable backend exists.

This package is CPython-only build/editor tooling, exactly like
:mod:`tools.vs2_scene_gen` beside it -- it never runs on the board and is
never imported by ``apps/micropython/``. It reads a plain JSON **event-sheet
model** (see :mod:`model`) and turns it into a generated
``<name>_events.py`` file: not a full ``vs2.Scene`` subclass (this pass does
not generate scene graphs -- that is :mod:`tools.vs2_scene_gen`'s job), but a
plain mixin class carrying ``on_enter(self)`` and ``update(self)``, meant to
be combined with a hand-written scene class::

    class Title(title_scene_events.TitleSceneEvents, vs2.Scene):
        def build(self):
            ...

``super().on_enter()``/``super().update()`` calls inside the generated
methods rely on this mixin-first MRO to reach the real ``vs2.Scene``
methods -- the same cooperative-mixin shape as every hand-written
``on_enter`` override elsewhere in this repo (``def on_enter(self):
super().on_enter(); ...``).

**Comment prefix: ``# blocks:``, not ``# scene-model:``.** See
:mod:`checksum`'s docstring -- this is the prefix
``tools/vs2_scene_gen/blob.py`` reserved for exactly this package, so a
generated file's own trailing comment says at a glance which generator
produced it.

Submodules:

- :mod:`model` -- the JSON event-sheet schema and its validator.
- :mod:`checksum` -- the ``body-sha`` computation and the banner/blob line
  grammar, using the ``# blocks: ...`` prefix (a small parallel of
  ``vs2_scene_gen.checksum``, which hardcodes the other prefix).
- :mod:`generator` -- model -> full file text (banner + body + blob), and
  the safe create/update/refuse-if-hand-edited write path.
- :mod:`detach` -- the one-way strip-the-banner-and-blob operation.
- :mod:`build_events` -- the standalone CLI: one ``.vs2events.json`` in,
  one generated companion file out. No ``regenerate.py`` sweep in this
  pass -- see :mod:`build_events`'s docstring for why that is a deliberate
  omission, not an oversight.

This package reuses ``tools.vs2_scene_gen.blob``'s ``encode_blob``/
``decode_blob`` directly (they are already fully generic over any JSON-able
dict) rather than forking them.
"""
