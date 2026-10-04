"""vs2_behavior_gen: T17 Phase 1 -- the Blockly-for-Behaviors generator and
the offline Action/Behavior catalog.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The block editor`` (tier 5:
the Action palette, generated from parameter declarations; the two-zone
tick skeleton) and ``### Round-trip...``. Work-breakdown card:
``docs/vs2-behaviors-implementation.md`` T17.

**Phase 1 scope, exactly.** Built here: the generated palette's data source
(:mod:`catalog`), a block-program schema for one Behavior authored as the
proposal's two-zone tick skeleton (:mod:`model`), a generator producing a
real ``Behavior`` subclass ``.py`` file from that schema (:mod:`generator`),
its checksum/blob/``Detach`` mechanics (:mod:`checksum`, :mod:`detach`), and
``Projectile`` re-authored as the proving case. **Explicitly deferred to a
later phase** (see the T17 dispatch card and
``docs/vs2-behaviors-handoff.md``): state hats and ``StateMachine`` block
support, ``Damageable`` (not a real shipped Behavior at all yet), the
debugger line-map, and the "fast" codegen backend (only the readable one
exists).

This package is CPython-only build/editor tooling, exactly like
:mod:`tools.vs2_scene_gen` (T15) and :mod:`tools.vs2_event_gen` (T16)
beside it -- it never runs on the board and is never imported by
``apps/micropython/``. :mod:`catalog` is the one submodule that *does*
import the real ``vs2.actions``/``vs2.behaviors`` modules (safe under plain
CPython -- see its own docstring); every other submodule is pure Python
with no ``vs2`` dependency, matching its siblings' convention of not
needing the real package just to validate or render a model.

**Comment prefix: ``# behavior-blocks:``, a third distinct prefix.** See
:mod:`checksum`'s docstring for the full naming-collision story: the
proposal's own text and ``vs2_scene_gen/blob.py``'s reservation both
pointed at ``# blocks:``, and T16 (a *different* Blockly-based generator,
the event sheet) claimed it first. This package needed a third prefix and
picked ``# behavior-blocks:``.

This package reuses ``tools.vs2_scene_gen.blob``'s ``encode_blob``/
``decode_blob`` directly (already fully generic over any JSON-able dict)
rather than forking them, matching T16's own precedent.

Submodules:

- :mod:`catalog` -- walks the fixed Phase-1 Action/Behavior class list via
  ``vs2.params.introspect()``, plus each Behavior's subject-kind
  constraint; :func:`catalog.write_catalog` produces
  ``web/vs2-behavior-catalog.json``.
- :mod:`generate_catalog` -- the standalone CLI wrapping the above.
- :mod:`model` -- the block-program JSON schema (one Behavior: params,
  state, declared Actions, the apply-to-all list, the per-sprite decision
  tree) and its validator.
- :mod:`checksum` -- the ``body-sha`` computation and the banner/blob line
  grammar, using the ``# behavior-blocks: ...`` prefix.
- :mod:`generator` -- model -> full file text (banner + body + blob), and
  the safe create/update/refuse-if-hand-edited write path.
- :mod:`detach` -- the one-way strip-the-banner-and-blob operation.
"""
