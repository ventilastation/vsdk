"""vs2_scene_gen: the T15 scene-model -> ``build()`` generator pipeline.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## Projects, scenes and
ownership`` (the generated-file shape, the embedded blob, ``Detach``,
``on_build()`` hooks) and ``### Round-trip: one embedded blob and one
one-way door`` / ``### Debugging generated code`` under ``## The block
editor`` (the checksum/Detach/line-map mechanics, which this module
applies at scene granularity rather than Blockly-workspace granularity).
Work-breakdown card: ``docs/vs2-behaviors-implementation.md`` T15.

This package is CPython-only build/editor tooling -- it never runs on the
board and is never imported by ``apps/micropython/``. It reads a plain
JSON **scene model** (see :mod:`model`) and turns it into a generated
``<Name>Scene.py`` file: a ``vs2.Scene`` subclass whose ``build()`` is a
flat, literal sequence of ``layer()``/``sprite()``/``sprite_pool()``/
``tilemap()``/``label()``/``var()``/``kinds()``/``behave()``/``family()``
calls -- exactly the shape the proposal describes: "nothing in ``build()``
branches or loops over game state".

Submodules:

- :mod:`model` -- the JSON schema and its validator.
- :mod:`values` -- renders one model "value" (literal / ``Var`` / a
  cross-reference / an event-hook reference) into Python source, and
  collects the imports a model needs.
- :mod:`checksum` -- the ``body-sha`` computation and the banner/blob
  line grammar that tells a generated file apart from a hand-edited or
  detached one.
- :mod:`blob` -- the trailing ``# scene-model: ...`` comment: base64+zlib
  over the canonical JSON model.
- :mod:`generator` -- model -> full file text, and the safe
  create/update/refuse-if-hand-edited write path.
- :mod:`detach` -- the one-way strip-the-banner-and-blob operation.
- :mod:`regenerate` -- the "regenerate everything" sweep CI can run, plus
  the on-creation-only companion-file stub helper.
- :mod:`payload` -- a pure-Python parser for ``vs2.export_scene_payload()``
  bytes (PAYLOAD_VERSION 3), used only by :mod:`recover`.
- :mod:`recover` -- runs a generated scene's ``build()`` under a real
  ``micropython`` unix-port process and reads back
  ``vs2.export_scene_payload()``, to verify the generator's output
  actually produces the scene the model describes.
"""
