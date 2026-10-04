"""Model -> generated ``<name>_events.py`` mixin source, and the safe write
path.

**A mixin that explicitly extends ``vs2.Scene``, never instantiated on its
own.** It carries only ``on_enter(self)`` and ``update(self)``, meant to
sit first in a hand-written scene's bases
(``class Title(TitleSceneEvents, vs2.Scene):``) so its ``super().on_enter()``/
``super().update()`` calls reach the real ``vs2.Scene`` implementation.

**Why the mixin declares ``(vs2.Scene)`` instead of no base at all**
(confirmed directly against the real ``micropython`` unix binary, not
assumed): a zero-argument ``super()`` call inside ``TitleSceneEvents.on_enter``
needs to find "whatever comes after ``TitleSceneEvents``" in ``Title``'s
actual runtime MRO (``Title -> TitleSceneEvents -> vs2.Scene -> object``) --
that is how CPython resolves it, and it is what a class with no declared
base at all does under CPython. But MicroPython's ``super()`` does not walk
the runtime MRO of ``type(self)`` at all; it only looks at the class's own
declared base(s) at the point ``super()`` is written. A base-less mixin's
own base is ``object``, which has no ``on_enter``/``update``, so
MicroPython raises ``AttributeError: 'super' object has no attribute
'on_enter'`` immediately -- reproduced directly, and confirmed that even
the explicit two-argument ``super(TitleSceneEvents, self)`` form does not
help, since the limitation is in how MicroPython locates the *next* class,
not in which spelling of ``super()`` is used. Giving the mixin its own
explicit ``(vs2.Scene)`` base fixes this on both interpreters: it is a
harmless diamond (``Title(TitleSceneEvents, vs2.Scene)`` where
``TitleSceneEvents`` already is a ``vs2.Scene``), CPython's C3
linearization resolves it exactly as before, and MicroPython's simplified
``super()`` now finds ``vs2.Scene`` as literally the mixin's own declared
base. This is why the CPython-shim test suite never caught the original
bug: CPython's real MRO-walking ``super()`` papered right over it.

**Why ``goto_scene`` imports its target module lazily, inside the method
body, instead of at the top of the generated file.** Three scenes that
transition to each other in a cycle (title -> playing -> game-over ->
title, exactly this package's proving game) produce hand-written scene
modules that import each other in a cycle too, one hop later: if
``gameover_scene_events.py`` imported ``title_scene`` at module scope,
loading ``title_scene`` (which imports ``playing_scene``, which imports
generated ``playing_scene_events``, which would import ``gameover_scene``,
which imports ``gameover_scene_events``, which imports ``title_scene``
again -- still mid-import) breaks with a partially-initialized module.
Deferring the ``import ... as _scene`` line to the exact point inside
``on_enter``/``update`` where the target is actually constructed sidesteps
this entirely: by the time that line executes, the whole game has long
since finished importing, so there is nothing partial left to hit, and
Python's module cache makes the repeated ``import`` on every tick a cheap
dict lookup, not a re-execution. This is a standard, deliberate Python
idiom for breaking import cycles, not a workaround the model format
should have to know about.

**Why ``goto_scene`` propagates ``_vs_api_slug``/``_vs_declared_api``.**
``ventilastation.director.Director._enter_scene`` re-reads
``getattr(scene, "_vs_api_slug", None)`` and re-establishes the current-app
context via ``api_guard.begin_app(...)`` on *every* scene entry, including a
``Scene.switch()``. ``vs2.project`` variables are keyed to that same
current-app slug (``_Project._ensure_current_app``) and are wiped the
moment the slug changes. A freshly constructed target scene has neither
attribute set, so a naive ``self.switch(TargetScene())`` would read back as
"a different app just started" on the very next tick and silently drop
every project variable -- including the score this whole proving case
exists to carry across a transition. Copying both attributes from ``self``
onto the target before switching is therefore not a style choice: without
it, ``goto_scene`` breaks the one property (score survives a scene
transition) this package's proving game is built to demonstrate. Every
game in this repo that only ever pushes/switches within a single app never
hits this because ``app_loader.load_app`` sets the attributes once, on the
*first* scene only -- multi-scene VS2 games did not exist yet when that
codepath was written.

**Sequential same-tick evaluation.** Multiple ``on_tick`` entries compile,
in model order, into a straight-line sequence of ``if`` blocks inside one
``update()`` method -- not a dispatch table, not early-exit. A later
entry's action can and does observe an earlier entry's effect from the same
tick (see :mod:`model`'s docstring for why the proving game relies on
exactly this to fake "increment" without arithmetic).
"""

import operator

from tools.vs2_scene_gen.blob import encode_blob

from . import checksum
from . import model as model_module

INDENT = "        "  # inside a method body: 4 (class) + 4 (def) spaces

#: T17 Phase 3: the two render paths ``render_body``/``generate_source``
#: accept. "readable" (the default, and the only path this generator had
#: before this phase) renders every condition exactly as authored. "fast"
#: applies the one mechanical transform this schema's grammar actually has
#: a site for -- see ``render_condition``'s own docstring on why constant-
#: folding a literal-vs-literal ``compare`` is the *only* one of the three
#: permitted transforms (constant-fold / hoist / inline) that applies here
#: at all: there is no arithmetic expression to fold, no per-sprite loop
#: to hoist a repeated read out of (this generator has no sprites at all),
#: and no single-use local worth inlining (``goto_scene``'s own ``_target``
#: is read three times, never once). Reported honestly rather than
#: inventing a transform with no real site -- see this task's report.
BACKENDS = ("readable", "fast")

_COMPARE_FUNCS = {
    "==": operator.eq, "!=": operator.ne, "<": operator.lt,
    ">": operator.gt, "<=": operator.le, ">=": operator.ge,
}


class GeneratorError(ValueError):
    """Raised when a file exists on disk but is not safe to overwrite --
    see :func:`write_events_file`'s ``"hand_edited"`` status, the normal way
    this surfaces; this exception is for callers that want a hard failure
    instead."""


# ---------------------------------------------------------------------------
# Expression / condition / action rendering
# ---------------------------------------------------------------------------

def render_expr(expr, imports):
    """``expr`` (a value in :mod:`model`'s three-form expression grammar)
    -> Python source. Adds to ``imports`` (a set) any name the rendered
    source needs imported (currently only ``"randrange"``, for
    ``random``)."""
    kind = expr["kind"]
    if kind == "literal":
        return repr(expr["value"])
    if kind == "var":
        return "vs2.project.%s" % (expr["name"],)
    # kind == "random": inclusive both ends (the Blockly "random integer
    # from A to B" convention), via urandom.randrange's exclusive-stop
    # semantics -- randrange(a, b + 1).
    imports.add("randrange")
    a_src = render_expr(expr["a"], imports)
    b_src = render_expr(expr["b"], imports)
    return "randrange(%s, (%s) + 1)" % (a_src, b_src)


def _try_constant_fold_compare(condition):
    """``condition`` (a ``"compare"``-kind node) -> the folded Python
    ``bool`` if both operands are literals and the comparison can be
    evaluated at generate time, else ``None`` (leave it as a runtime
    expression). ``None`` also covers the case where the operator raises
    at generate time (e.g. ``<`` between a number and a string literal --
    exactly what the *unfolded* expression would also raise, at runtime,
    for the same nonsensical model): never fold what could behave
    differently from leaving the original expression to fail exactly
    where a hand-authored model told it to."""
    left, right = condition["left"], condition["right"]
    if left["kind"] != "literal" or right["kind"] != "literal":
        return None
    try:
        return _COMPARE_FUNCS[condition["op"]](left["value"], right["value"])
    except TypeError:
        return None


def render_condition(condition, imports, backend="readable"):
    """``condition`` -> a Python boolean expression source string.
    ``backend="fast"`` additionally constant-folds a ``"compare"`` whose
    both operands are literals into a plain ``True``/``False`` -- the only
    one of the three permitted fast-backend transforms (constant-fold /
    hoist / inline) this package's grammar has any site for at all, see
    :data:`BACKENDS`'s own docstring. Folding never removes the ``if``
    statement itself (that would be restructuring control flow, which the
    spec explicitly forbids); it only precomputes the condition's own
    value."""
    if condition["kind"] == "compare":
        if backend == "fast":
            folded = _try_constant_fold_compare(condition)
            if folded is not None:
                return repr(folded)
        left = render_expr(condition["left"], imports)
        right = render_expr(condition["right"], imports)
        return "%s %s %s" % (left, condition["op"], right)
    # kind == "timer_elapsed"
    return "self._vs2_events_ticks >= %d" % (condition["ticks"],)


def _with_block_comment(lines, block_id):
    """T17 Phase 3: append a trailing ``# block: <id>`` comment to every
    line in ``lines`` when ``block_id`` is present -- see this package's
    own ``linemap.py`` for why the comment is re-parsed rather than kept
    as a second structure. A no-op (returns ``lines`` unchanged) when
    ``block_id`` is falsy, so every call site below reads the same
    whether or not the originating model actually carried one."""
    if not block_id:
        return lines
    return [line + ("  # block: %s" % (block_id,)) for line in lines]


def render_action(action, indent, imports, backend="readable"):
    """``action`` -> a list of source lines, each already prefixed with
    ``indent`` and, when ``action`` carries a ``"block_id"``, suffixed
    with a trailing ``# block: <id>`` comment (every line this function
    returns belongs to the one action it renders, so every line gets the
    same comment). ``backend`` is accepted for symmetry with
    :func:`render_condition`/:func:`render_body` even though no action
    kind here has anything to fast-render differently -- see
    :data:`BACKENDS`'s docstring."""
    del backend  # no action kind has a fast-path transform; see docstring above
    kind = action["kind"]
    block_id = action.get("block_id")

    if kind == "set_variable":
        value_src = render_expr(action["value"], imports)
        return _with_block_comment(
            ["%svs2.project.%s = %s" % (indent, action["name"], value_src)], block_id)

    if kind == "set_label_text":
        text_src = render_expr(action["text"], imports)
        return _with_block_comment(
            ["%sself.%s.text = %s" % (indent, action["label_attr"], text_src)], block_id)

    # kind == "goto_scene": the import is local to this action's own block,
    # not module-level -- see this module's docstring for why.
    return _with_block_comment([
        "%simport %s as _scene" % (indent, action["module"]),
        "%s_target = _scene.%s()" % (indent, action["class_name"]),
        "%s_target._vs_api_slug = self._vs_api_slug" % (indent,),
        "%s_target._vs_declared_api = self._vs_declared_api" % (indent,),
        "%sself.switch(_target)" % (indent,),
    ], block_id)


# ---------------------------------------------------------------------------
# Pre-pass: every project variable this model ever sets, in first-seen order
# ---------------------------------------------------------------------------

def _collect_declared_vars(model):
    names = []
    seen = set()
    for event in model["events"]:
        for action in event.get("actions", []):
            if action["kind"] == "set_variable" and action["name"] not in seen:
                seen.add(action["name"])
                names.append(action["name"])
    return names


# ---------------------------------------------------------------------------
# Method-body assembly
# ---------------------------------------------------------------------------

def _render_event_block(event, imports, backend="readable"):
    conditions = event.get("conditions", [])
    if conditions:
        cond_src = " and ".join(render_condition(c, imports, backend) for c in conditions)
        lines = _with_block_comment(["%sif %s:" % (INDENT, cond_src)], event.get("block_id"))
        action_indent = INDENT + "    "
    else:
        lines = []
        action_indent = INDENT
    for action in event["actions"]:
        lines.extend(render_action(action, action_indent, imports, backend))
    return lines


def _render_on_enter(model, imports, declared_vars, backend="readable"):
    lines = ["%ssuper().on_enter()" % (INDENT,)]
    lines.append("%sself._vs2_events_ticks = 0" % (INDENT,))
    for name in declared_vars:
        lines.append("%svs2.project.var(%r, 0)" % (INDENT, name))
    for event in model["events"]:
        if event["kind"] == "on_start":
            lines.extend(_render_event_block(event, imports, backend))
    return lines


def _render_update(model, imports, backend="readable"):
    lines = ["%ssuper().update()" % (INDENT,)]
    lines.append("%sself._vs2_events_ticks += 1" % (INDENT,))
    for event in model["events"]:
        if event["kind"] == "on_tick":
            lines.extend(_render_event_block(event, imports, backend))
    return lines


def render_body(model, backend="readable"):
    """The generated file's body -- everything except the banner and the
    trailing blob line. Deterministic: the same model and the same
    ``backend`` always render the same body, byte for byte. ``goto_scene``
    needs no header-level import at all -- see this module's docstring for
    why its ``import`` line is local to the action's own block instead.
    ``backend`` is one of :data:`BACKENDS`; see its docstring for what
    ``"fast"`` actually changes here (very little -- constant-folding a
    literal-vs-literal compare, and nothing else, honestly)."""
    if backend not in BACKENDS:
        raise GeneratorError("backend: %r is not one of %s" % (backend, BACKENDS))
    imports = set()
    declared_vars = _collect_declared_vars(model)

    on_enter_lines = _render_on_enter(model, imports, declared_vars, backend)
    update_lines = _render_update(model, imports, backend)

    lines = ["import vs2"]
    if "randrange" in imports:
        lines.append("from urandom import randrange")
    lines.append("")
    lines.append("")
    lines.append("class %s(vs2.Scene):" % (model["class_name"],))
    lines.append("    def on_enter(self):")
    lines.extend(on_enter_lines)
    lines.append("")
    lines.append("    def update(self):")
    lines.extend(update_lines)
    return "\n".join(lines)


def generate_source(model, basename, backend="readable"):
    """The full generated file text: banner, body, blank line, blob.
    ``basename`` (e.g. ``"playing_scene_events.py"``) is recorded in the
    banner only -- it plays no role in the checksum or the blob.
    ``backend`` (:data:`BACKENDS`) is likewise not recorded anywhere in
    the file: the embedded blob always carries the same model regardless
    of which backend rendered it, so switching backends and regenerating
    is not a model change -- it changes only the body (and therefore the
    banner's body-sha, correctly)."""
    model_module.validate_model(model)
    body = render_body(model, backend)
    sha = checksum.body_sha(body)
    banner_line = checksum.make_banner(basename, sha)
    blob_line = checksum.make_blob_line(encode_blob(model))
    return checksum.join_generated_file(banner_line, body, blob_line)


class WriteResult:
    """Outcome of :func:`write_events_file`. ``status`` is one of
    ``"created"``, ``"updated"``, ``"unchanged"``, ``"hand_edited"`` or
    ``"detached"`` -- exactly the five outcomes
    ``tools.vs2_scene_gen.generator.WriteResult`` documents, applied to an
    event-sheet mixin file instead of a scene file."""

    def __init__(self, status, path, message):
        self.status = status
        self.path = path
        self.message = message

    def __repr__(self):
        return "WriteResult(%r, %r, %r)" % (self.status, str(self.path), self.message)


def write_events_file(model, output_path, backend="readable"):
    """Regenerate ``output_path`` from ``model`` if it is safe to do so.
    Never raises for any of the five normal outcomes above -- only a
    malformed ``model`` (a :class:`~model.ModelError`) or an unwritable
    path can raise. ``backend`` -- see :func:`generate_source`."""
    basename = output_path.name
    new_text = generate_source(model, basename, backend)

    if not output_path.exists():
        output_path.write_text(new_text)
        return WriteResult("created", output_path, "wrote new file")

    existing = output_path.read_text()
    parsed = checksum.split_generated_file(existing)
    if parsed is None:
        return WriteResult(
            "detached", output_path,
            "file exists but is not generator-managed (no banner+blob); left untouched")

    banner_line, body, _blob_line = parsed
    if checksum.recorded_sha(banner_line) != checksum.body_sha(body):
        return WriteResult(
            "hand_edited", output_path,
            "recorded body-sha does not match the file's actual body; "
            "refusing to overwrite a hand-edited generated file")

    if existing == new_text:
        return WriteResult("unchanged", output_path, "regenerated content is byte-identical")

    output_path.write_text(new_text)
    return WriteResult("updated", output_path, "model changed; file regenerated")
