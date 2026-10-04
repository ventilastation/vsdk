"""Recovering the *true* built scene from a real MicroPython process, and
comparing it back against a scene model.

Spec (``## The block editor``): "the editor recovers the true scene ...
by reading ``vs2.export_scene_payload()``" -- not by re-reading the model
or the generated source, both of which describe *intent*; the payload is
the one artifact that describes what ``build()`` actually did.

**Why shell out to a real ``micropython`` unix binary, not the CPython-shim
pattern ``tests/test_vixeous_vs2.py`` uses.** That test (and several
others in this package's neighbourhood) run ``apps/micropython/vs2``
directly under CPython, with a couple of module shims (``uos``, ``utime``,
...) standing in for MicroPython built-ins -- fast, and fine for exercising
game logic. But CPython's ``dict`` preserves insertion order; MicroPython's
does not (its dict iteration order is hash-based). Anything in the vs2/
ventilastation stack that walks a dict without sorting it first --
directly, or two frames removed, in library code this package doesn't
own -- can silently produce a *different* answer under the CPython shim
than it would on a real device or the real desktop emulator. Recovery
exists precisely to catch "the model and the built scene disagree";
running it against a CPython approximation would defeat that purpose by
construction. So :func:`capture_scene_payload` always launches the real
``micropython`` unix port as a subprocess and reads back what *it*
actually built.

**Draw-order index, not attribute names.** As :mod:`payload` documents,
a payload has no idea a sprite is called ``self.enemies`` -- only
``(kind, index-into-that-kind's-own-list)``, in draw order.
:func:`compare_payload_to_model` therefore never tries to resolve a model
attribute name against a payload record by name; it walks both sequences
in lockstep, in the same layer-then-position order :mod:`generator`
itself emits ``on_build_N()`` hooks in (flattening a ``sprite_pool`` of
``count`` sprites into ``count`` consecutive draw-order entries, since
that is what :meth:`vs2.Layer.sprite_pool` itself does at build time --
see that method's docstring: "All ``count`` sprites are allocated here").

**Image identity is a heuristic, not a name lookup.** A payload sprite/
tilemap record carries a ``strip`` integer, not the string a model
declares as ``image``. Recovering the *name* would require the same
asset-manifest resolution the running scene itself did (a ROM's own
stripe table), which this module deliberately does not re-implement or
re-load -- see :mod:`payload`'s own docstring on this exact boundary.
What *is* checkable without that: the same declared image name must
always resolve to the same ``strip`` everywhere it is used in one scene
(recovered images are cached per name -- see ``Scene.image``), and two
different declared names should not collapse onto the same ``strip``.
Both directions are checked; neither is proof of a specific name, only of
internal consistency -- "where derivable," per this task's own framing.
A single-occurrence swap of two same-shaped, never-repeated images is
provably invisible to this heuristic (nothing about it is inconsistent);
that is a known, accepted gap, not an oversight.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import model as model_module
from . import payload as payload_module

#: The child process's own view of what "draw-order kind" a model drawable
#: kind expands to (per :mod:`generator`'s emitted call and
#: :mod:`payload`'s ``DRAW_SPRITE``/``DRAW_TILEMAP`` tagging): a ``sprite``
#: or ``sprite_pool`` always create :class:`vs2.Sprite` drawables; a
#: ``tilemap`` or ``label`` always create :class:`vs2.Tilemap` drawables
#: (``Label`` is a ``Tilemap`` subclass -- see ``apps/micropython/vs2/
#: __init__.py``).
_SPRITE_MODEL_KINDS = ("sprite", "sprite_pool")
_TILEMAP_MODEL_KINDS = ("tilemap", "label")

# Position/frame comparisons tolerate this much slack, matching the
# payload's own 8.8 fixed-point quantization (one part in 256) -- a
# literal model value can never round-trip to *more* error than that.
_POSITION_TOLERANCE = 1.0 / 256


class RecoverError(RuntimeError):
    """Raised for genuine tool misuse -- the ``micropython`` unix binary is
    not on ``PATH``, the driver subprocess exited non-zero, or it printed
    something that is not the hex payload it was told to print. Never
    raised for a model/payload *disagreement*; that is
    :func:`compare_payload_to_model`'s job, and it reports those as data
    (a list of strings), not exceptions -- see its own docstring."""


_DRIVER_SCRIPT = '''\
import sys

sys.path.insert(0, "apps/micropython")

from ventilastation.director import configure_runtime
from ventilastation.app_loader import load_app
import vs2

configure_runtime("headless")
scene = load_app({slug!r})
payload = vs2.export_scene_payload(scene)
sys.stdout.write(bytes(payload).hex())
sys.stdout.write("\\n")
'''


def _write_driver_script(slug):
    """A temporary driver script that builds and seals ``slug`` under a
    headless runtime, then prints its ``export_scene_payload()`` bytes to
    stdout as hex (not raw bytes -- ``subprocess`` text-mode capture is
    not byte-safe, and a payload's raw bytes are not valid UTF-8 in
    general).

    Only ``sys.path.insert(0, "apps/micropython")`` is added here: the
    repo root itself does *not* need to be added by hand.
    ``app_loader.import_app_module`` -> ``ensure_project_root_on_path``
    already appends it (as ``""``, since the driver runs with the repo
    root as its current working directory, where ``os.stat("games")``
    succeeds) the first time it is called, and adding it twice would be
    redundant, not wrong, but this module follows the "don't duplicate
    what callee already does" rule the rest of this package's docstrings
    call out.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", suffix="_vs2_recover_driver.py", delete=False)
    try:
        handle.write(_DRIVER_SCRIPT.format(slug=slug))
    finally:
        handle.close()
    return Path(handle.name)


def capture_scene_payload(slug, repo_root):
    """Build ``slug`` (a dotted app slug, e.g. ``"alecu.vixeous"``) under a
    real, real MicroPython unix-port process and return the parsed
    ``export_scene_payload()`` dict (see :func:`payload.parse_scene_payload`
    for its shape).

    This is the one place this package shells out to the real interpreter
    instead of running pure CPython -- see this module's own docstring
    for why (dict-order fidelity, not speed).

    Args:
        slug: A dotted app slug, resolved by
            ``ventilastation.app_loader.load_app`` exactly as the real
            launcher would.
        repo_root: Path to the repository root. The driver subprocess
            runs with this as its current working directory (so
            ``games/...`` resolves the same way ``app_loader`` itself
            resolves it on a real desktop-emulator invocation).

    Returns:
        dict: The parsed scene payload -- see
        :func:`payload.parse_scene_payload`.

    Raises:
        RecoverError: If ``micropython`` is not on ``PATH``, the driver
            subprocess exits non-zero (bad slug, an app that raises while
            building, ...), or it does not print the hex payload it was
            told to.
        payload.PayloadError: If the bytes it did print do not parse as a
            well-formed, supported-version scene payload.
    """
    micropython = shutil.which("micropython")
    if micropython is None:
        raise RecoverError(
            "the 'micropython' unix-port binary is not on PATH; cannot "
            "recover a real build for %r" % (slug,))

    repo_root = Path(repo_root)
    driver_path = _write_driver_script(slug)
    try:
        result = subprocess.run(
            [micropython, str(driver_path)], cwd=str(repo_root),
            capture_output=True, text=True, check=False)
    finally:
        driver_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RecoverError(
            "micropython driver failed for slug %r (exit %d):\\n%s"
            % (slug, result.returncode, result.stderr))

    hex_text = result.stdout.strip()
    try:
        raw = bytes.fromhex(hex_text)
    except ValueError as exc:
        raise RecoverError(
            "micropython driver for slug %r did not print a hex payload; "
            "stdout was %r, stderr was %r" % (slug, result.stdout, result.stderr)) from exc

    return payload_module.parse_scene_payload(raw)


# ---------------------------------------------------------------------------
# Model <-> payload comparison
# ---------------------------------------------------------------------------

def _flatten_model_drawables(model):
    """Every draw-order slot the model's ``layers``/``drawables`` expand
    to, in the same order :mod:`generator` emits them in, as
    ``(layer_index, layer, drawable, pool_slot)`` tuples -- ``pool_slot``
    is ``None`` for anything but a ``sprite_pool`` slot, else the slot's
    ``0``-based index within that pool (for messages only; every slot of
    one pool is otherwise identical -- same image, same literal frame,
    hidden, at the origin, per ``Layer.sprite_pool``)."""
    flattened = []
    for layer_index, layer in enumerate(model["layers"]):
        for drawable in layer.get("drawables", []):
            if drawable["kind"] == "sprite_pool":
                for slot in range(drawable["count"]):
                    flattened.append((layer_index, layer, drawable, slot))
            else:
                flattened.append((layer_index, layer, drawable, None))
    return flattened


def _describe(layer, drawable, pool_slot):
    where = "%s.%s" % (layer["attr"], drawable["attr"])
    if pool_slot is not None:
        where += "[%d]" % (pool_slot,)
    return where


def _is_literal(value):
    return value is None or isinstance(value, (bool, int, float, str))


def compare_payload_to_model(model, parsed_payload):
    """Walk ``model``'s ``layers[].drawables[]`` and
    ``parsed_payload["drawables"]`` in lockstep (both already in draw
    order -- see this module's own docstring) and report every
    disagreement found as a human-readable string. An empty list means
    they agree on everything this function knows how to check.

    Never raises for a mismatch -- that is the normal, expected result a
    caller reports, possibly several at once; see :class:`RecoverError`
    for what *is* worth raising.

    Args:
        model: A scene model already accepted by
            :func:`model.validate_model` (raises :class:`model.ModelError`
            otherwise -- a malformed model is a caller mistake, not a
            model/payload disagreement).
        parsed_payload: The dict :func:`payload.parse_scene_payload` (or
            :func:`capture_scene_payload`) returned.

    Returns:
        list[str]: Mismatch descriptions, empty if none.
    """
    model_module.validate_model(model)

    mismatches = []

    if len(parsed_payload.get("layers", ())) != len(model["layers"]):
        mismatches.append(
            "layer count: model declares %d, payload has %d"
            % (len(model["layers"]), len(parsed_payload.get("layers", ()))))

    expected = _flatten_model_drawables(model)
    payload_drawables = parsed_payload.get("drawables", [])
    payload_sprites = parsed_payload.get("sprites", [])
    payload_tilemaps = parsed_payload.get("tilemaps", [])

    if len(expected) != len(payload_drawables):
        mismatches.append(
            "drawable count: model's draw order has %d entries "
            "(sprite_pool expanded to its count), payload has %d"
            % (len(expected), len(payload_drawables)))

    strip_by_image = {}

    for position in range(min(len(expected), len(payload_drawables))):
        layer_index, layer, drawable, pool_slot = expected[position]
        ref = payload_drawables[position]
        where = "drawables[%d] (%s)" % (position, _describe(layer, drawable, pool_slot))

        kind = drawable["kind"]
        expected_payload_kind = "sprite" if kind in _SPRITE_MODEL_KINDS else "tilemap"
        if ref["kind"] != expected_payload_kind:
            mismatches.append(
                "%s: expected a %s draw-order entry, payload has a %s"
                % (where, expected_payload_kind, ref["kind"]))
            continue

        records = payload_sprites if ref["kind"] == "sprite" else payload_tilemaps
        if ref["index"] >= len(records):
            mismatches.append(
                "%s: payload references %s index %d, but only %d exist"
                % (where, ref["kind"], ref["index"], len(records)))
            continue
        record = records[ref["index"]]

        if record["layer_index"] != layer_index:
            mismatches.append(
                "%s: payload layer_index %d != model layer index %d"
                % (where, record["layer_index"], layer_index))

        image_name = drawable["image"]
        observed_strip = record["strip"]
        if image_name in strip_by_image:
            if strip_by_image[image_name] != observed_strip:
                mismatches.append(
                    "%s: image %r resolved to strip %d here, but strip %d "
                    "elsewhere in the same scene"
                    % (where, image_name, observed_strip, strip_by_image[image_name]))
        else:
            for other_name in sorted(strip_by_image):
                if strip_by_image[other_name] == observed_strip:
                    mismatches.append(
                        "%s: image %r resolved to strip %d, which image %r "
                        "already claimed elsewhere in this scene"
                        % (where, image_name, observed_strip, other_name))
                    break
            strip_by_image[image_name] = observed_strip

        if kind != "sprite_pool":
            if "frame" in drawable and _is_literal(drawable["frame"]):
                if record.get("frame") != drawable["frame"]:
                    mismatches.append(
                        "%s: model frame %r, payload frame %r"
                        % (where, drawable["frame"], record.get("frame")))
            if "visible" in drawable and _is_literal(drawable["visible"]):
                if record.get("visible") != drawable["visible"]:
                    mismatches.append(
                        "%s: model visible %r, payload visible %r"
                        % (where, drawable["visible"], record.get("visible")))
            for axis in ("x", "y"):
                if axis in drawable and _is_literal(drawable[axis]):
                    expected_value = float(drawable[axis])
                    actual_value = float(record.get(axis, 0.0))
                    if abs(actual_value - expected_value) > _POSITION_TOLERANCE:
                        mismatches.append(
                            "%s: model %s=%r, payload %s=%r"
                            % (where, axis, drawable[axis], axis, actual_value))
        else:
            # Every sprite_pool slot is allocated hidden, at the origin, on
            # its declared literal frame (never a Var/ref -- the schema
            # allows one only), per Layer.sprite_pool.
            if record.get("visible") is not False:
                mismatches.append(
                    "%s: sprite_pool slot should start hidden, payload visible=%r"
                    % (where, record.get("visible")))
            if "frame" in drawable and record.get("frame") != drawable["frame"]:
                mismatches.append(
                    "%s: model frame %r, payload frame %r"
                    % (where, drawable["frame"], record.get("frame")))

    return mismatches
