"""Model -> generated ``Behavior`` subclass source, and the safe write path.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The block editor`` and ``###
Round-trip: one embedded blob and one one-way door``, applied at
Behavior-file granularity (one generated ``.py`` per custom Behavior, per
the proposal's own file tree: ``code/behaviors/chasing.py GENERATED from
blocks. One file per custom behavior.``).

**A whole class, not a mixin.** T16's event-sheet generator emits a mixin
because a scene already has a hand-written base to combine with. A
``Behavior`` has no such counterpart -- every hand-written entry in
``apps/micropython/vs2/behaviors.py`` (``Projectile`` included) *is* the
whole class, subclassing ``Behavior`` directly. So this generator emits a
complete ``Behavior`` subclass: parameter declarations, ``state = (...)``,
``attached()`` composing the declared Actions, and ``step()``/``step_one()``
(chosen by ``subject_kind`` -- see :mod:`model`) carrying the two-zone
tick body.

**The pool-shaped loop is copied verbatim from the real ``Projectile``,
deliberately.** ``apps/micropython/vs2/behaviors.py``'s ``Projectile.step()``
walks ``sprites._live`` with a downward indexed ``while`` specifically so a
``despawn()`` mid-loop (which swaps the freed slot's sprite in from the
tail -- see that class's own comments) never skips or double-visits a
sprite. Inventing a different loop shape here -- even one that "looks"
equivalent -- would risk exactly the despawn-safety bug the real class's
comments exist to prevent, for a generator whose whole job is producing
code indistinguishable in *behavior* from what a careful author would
write by hand. So :func:`_render_step_pool` emits that exact shape,
statement for statement, and only the per-sprite body inside it varies by
model.

**Why every rendered expression is a plain string, not a value type.**
Matching ``tools/vs2_event_gen/generator.py``'s own ``render_expr``: the
generator's whole job is producing readable Python text, so there is
nothing to gain from a richer intermediate representation the way a real
compiler would want one.

**Phase 2: state hats emit a ``StateMachine`` subclass, not a mixin.**
When ``model["state_machine"]`` is present, the generated class subclasses
:class:`~vs2.behaviors.StateMachine` directly (a real, already-existing
base -- not a bare mixin), and does **not** override ``step``/``step_one``/
``attached`` unless the model actually needs to (only ``attached``, and
only when the model declares Actions to compose -- see
:func:`_render_state_machine_attached`): every other bit of dispatch
machinery (the despawn-safe per-sprite loop, ``hold()``, the ``enter_``/
``exit_`` hook lookup, ``fsm_state``/``fsm_hold``/``fsm_then`` priming) is
inherited unchanged from the real class. This sidesteps the exact
MicroPython ``super()`` gotcha ``tools/vs2_event_gen/generator.py``'s own
docstring documents (a mixin with no declared base, whose
``super().on_enter()`` call crashes on real MicroPython because its
``super()`` only walks the class's *own declared base*, not
``type(self).__mro__`` the way CPython's does): there is no bare mixin
here to begin with, and the one place this generator's own output calls
into its base class explicitly (:func:`_render_state_machine_attached`,
when a model declares Actions) spells that call as the real class's own
docstring instructs -- ``StateMachine.attached(self, subject)``, the
unbound-call form, never ``super().attached(subject)`` -- which works
identically on both interpreters regardless of MRO-walking differences,
so this is not merely "avoided by accident".
"""

import operator

from tools.vs2_scene_gen.blob import encode_blob

from . import checksum
from . import model as model_module

INDENT = "        "  # inside a method body: 4 (class) + 4 (def) spaces

#: T17 Phase 3: the two render paths ``render_body``/``generate_source``
#: accept -- see ``docs/vs2-behaviors-proposal.md``, "### Two backends:
#: readable by default, fast on request": "the fast backend is a
#: mechanical transform of the readable one -- hoisting, inlining and
#: constant folding only, never reordering or restructuring." This
#: package's grammar has a real site for all three (unlike
#: ``tools/vs2_event_gen``'s, which only has one -- see that package's own
#: ``generator.py`` docstring for the honest accounting of why):
#:
#: - **constant-fold**: an ``if_else`` node's ``"compare"`` condition, when
#:   both operands are literals, folds to a plain ``True``/``False`` --
#:   see :func:`_try_constant_fold_compare`. The *only* site: this
#:   grammar's expression kinds are ``literal``/``param``/``state``, none
#:   of them a binary arithmetic op, so there is no "two literal operands
#:   under an accumulate" to fold the way the spec's own example phrase
#:   suggests -- an ``accumulate`` node's ``amount`` is always already a
#:   single leaf expression, nothing to combine.
#: - **hoist**: a ``"param"`` expression (``self.<name>``) read anywhere
#:   inside a pool-subject's per-sprite ``while`` loop is read once per
#:   live sprite every tick even though it names the same value each time
#:   (params never change mid-``step()``) -- hoisted to a local assigned
#:   once before the loop. See :func:`_collect_hoistable_params`. Deliberately
#:   *not* applied inside a state-hat's own per-state method or a
#:   ``step_one()`` body: neither has an explicit loop in the *generated*
#:   code to hoist above (a state method is called once per sprite by the
#:   base class's own dispatcher, and ``step_one`` has no loop at all --
#:   see model.py's own "sprite" subject_kind), so there is nowhere
#:   syntactically earlier to hoist a read *to*.
#: - **inline**: an ``if_action`` node's own ``_<bind>_result`` local
#:   exists only so a nested ``despawn_hit`` can reuse the Action's
#:   ``run_one()`` result -- when nothing in the node's own ``then``/
#:   ``else`` actually references it (no ``despawn_hit`` in scope), it is
#:   a single-use local and the assignment is inlined straight into the
#:   ``if`` condition. See :func:`_references_hit_var`. Every *other*
#:   generator-introduced local (``_cb_<name>``, ``_spawn_<name>``,
#:   ``_sound_<name>``) is deliberately left alone: each exists
#:   specifically to read a mutable ``self.<attr>`` exactly once before
#:   both testing it for ``None`` and using it (see e.g. ``call_callback``'s
#:   own rendering comment, "read into a local first (never twice)") --
#:   inlining those would reintroduce the double-read the readable
#:   backend's own comments explain is deliberately avoided, which is a
#:   correctness regression, not a speedup.
BACKENDS = ("readable", "fast")

_COMPARE_FUNCS = {
    "==": operator.eq, "!=": operator.ne, "<": operator.lt,
    ">": operator.gt, "<=": operator.le, ">=": operator.ge,
}


class GeneratorError(ValueError):
    """Raised when a file exists on disk but is not safe to overwrite --
    see :func:`write_behavior_file`'s ``"hand_edited"`` status, the normal
    way this surfaces; this exception is for callers that want a hard
    failure instead."""


# ---------------------------------------------------------------------------
# Parameter declarations
# ---------------------------------------------------------------------------

#: model param "type" -> (vs2.params class name, constructor kwargs this
#: generator sets explicitly). Every ``vs2.params.Parameter`` subclass
#: accepts ``default`` positionally and ``label``/``unit`` by keyword;
#: ``Number``/``Angle`` additionally take ``min``/``max``/``step``;
#: ``Choice`` takes ``options`` instead. See
#: ``apps/micropython/vs2/params.py`` for the real signatures this mirrors.
_PARAM_CLASS_BY_TYPE = {
    "number": "Number", "angle": "Angle", "flag": "Flag", "choice": "Choice",
    "frames": "Frames", "sound": "Sound", "image": "Image", "pool": "PoolRef",
    "points": "Points", "callback": "Callback",
}

_NUMERIC_KWARGS = ("min", "max", "step")
_COMMON_KWARGS = ("label", "unit")


def _render_param_decl(param):
    """One ``name = ParamClass(default, ...)`` line's right-hand side,
    given one ``model.params[i]`` entry."""
    param_class = _PARAM_CLASS_BY_TYPE[param["type"]]
    args = [repr(param["default"])]
    if param["type"] == "choice":
        args.append("options=%r" % (tuple(param.get("options") or ()),))
    else:
        for key in _NUMERIC_KWARGS:
            if key in param:
                args.append("%s=%r" % (key, param[key]))
    for key in _COMMON_KWARGS:
        if key in param:
            args.append("%s=%r" % (key, param[key]))
    return param_class, "%s(%s)" % (param_class, ", ".join(args))


# ---------------------------------------------------------------------------
# Expression / condition rendering (pure: no side effects, always inline-able)
# ---------------------------------------------------------------------------

def render_expr(expr, hoisted=None):
    """``expr`` -> Python source. ``hoisted`` (see
    :func:`_collect_hoistable_params`) is the fast backend's own
    ``{param_name: local_name}`` map -- when ``expr`` is a ``"param"``
    read whose name is a key in it, this renders the hoisted local
    (``_h_<name>``) instead of ``self.<name>``. ``None`` (the default,
    always used for the readable backend and for every call site that is
    not inside a pool-subject's per-sprite loop -- ``attached()``'s own
    Action-construction calls included, since those run once at attach
    time and reading ``self.<param>`` there is already correct) renders
    every ``"param"`` the old, un-hoisted way."""
    kind = expr["kind"]
    if kind == "literal":
        return repr(expr["value"])
    if kind == "param":
        if hoisted and expr["name"] in hoisted:
            return hoisted[expr["name"]]
        return "self.%s" % (expr["name"],)
    if kind == "state":
        return "sprite.%s" % (expr["name"],)
    # kind == "binary_op". Not constant-folded (unlike a "compare"
    # condition's two literals -- see _try_constant_fold_compare below):
    # a binary_op tree only ever shows up inside a per-sprite amount/value,
    # never a condition, so there is no boolean branch decision at
    # generate time to fold away, only an arithmetic expression that is
    # just as cheap to evaluate on the board as it would be to fold here.
    # min/max render as plain Python builtins -- both exist natively on
    # MicroPython, no runtime helper needed.
    left = render_expr(expr["left"], hoisted)
    right = render_expr(expr["right"], hoisted)
    op = expr["op"]
    if op in ("min", "max"):
        return "%s(%s, %s)" % (op, left, right)
    return "(%s %s %s)" % (left, op, right)


def _try_constant_fold_compare(condition):
    """``condition`` -> the folded Python ``bool`` if both operands are
    literals and the comparison evaluates cleanly at generate time, else
    ``None``. Mirrors ``tools.vs2_event_gen.generator``'s identical
    helper -- see its own docstring for why a ``TypeError`` at fold time
    (e.g. ``<`` between a number and a string literal) means "leave it
    unfolded", not "crash the generator": the unfolded expression would
    raise the exact same error, at runtime, for the same nonsensical
    model."""
    left, right = condition["left"], condition["right"]
    if left["kind"] != "literal" or right["kind"] != "literal":
        return None
    try:
        return _COMPARE_FUNCS[condition["op"]](left["value"], right["value"])
    except TypeError:
        return None


def render_condition(condition, backend="readable", hoisted=None):
    # kind == "compare" (the only condition kind Phase 1 supports)
    if backend == "fast":
        folded = _try_constant_fold_compare(condition)
        if folded is not None:
            return repr(folded)
    return "%s %s %s" % (render_expr(condition["left"], hoisted), condition["op"],
                          render_expr(condition["right"], hoisted))


def _with_block_comment(lines, block_id):
    """T17 Phase 3: append a trailing ``# block: <id>`` comment to every
    line in ``lines`` when ``block_id`` is present. Every line a single
    node/action directly emits gets the same comment; lines produced by a
    *nested* node (a compound node's own ``then``/``else`` body) are not
    touched here -- they carry their own id via their own recursive call
    instead. See ``linemap.py`` for why the comment is re-parsed rather
    than kept as a second structure."""
    if not block_id:
        return lines
    return [line + ("  # block: %s" % (block_id,)) for line in lines]


def _iter_exprs_in_node(node):
    """Every expression a per-sprite (or state-body) node directly holds
    -- used by :func:`_collect_hoistable_params` to find every
    ``"param"`` name read anywhere in a per-sprite tree. ``despawn``/
    ``despawn_hit``/``goto_state`` hold no expression of their own;
    ``if_action``'s "is not None" check is not a stored expression
    either."""
    kind = node["kind"]
    if kind == "accumulate":
        yield node["amount"]
    elif kind == "set_state":
        yield node["value"]
    elif kind == "spawn":
        yield node["x"]
        yield node["y"]
    elif kind == "hold":
        yield node["ticks"]
    elif kind == "call_callback":
        for arg in node.get("args", []):
            yield arg
    elif kind == "if_else":
        yield node["condition"]["left"]
        yield node["condition"]["right"]


# ---------------------------------------------------------------------------
# Action declarations (attached()) and apply-to-all (step's uniform prologue)
# ---------------------------------------------------------------------------

def _render_action_call(action_decl):
    # Action-construction args are read exactly once, at attach time (not
    # per-tick), so this never passes a `hoisted` map -- see render_expr's
    # own docstring on why that is correct, not merely an oversight.
    action_class = action_decl["action_class"]
    args = action_decl.get("args", {})
    parts = ["%s=%s" % (name, render_expr(args[name])) for name in sorted(args)]
    return "actions.%s(%s)" % (action_class, ", ".join(parts))


def _render_attached(model):
    lines = ["%sdef attached(self, subject):" % (INDENT[:4],)]
    actions = model.get("actions", [])
    if not actions:
        lines.append("%spass" % (INDENT,))
        return lines
    for action_decl in actions:
        line = "%sself.%s = self.action(%s)" % (
            INDENT, action_decl["bind"], _render_action_call(action_decl))
        lines.extend(_with_block_comment([line], action_decl.get("block_id")))
    return lines


def _render_apply_to_all(model, sprites_expr, indent, actions_by_bind):
    """The uniform prologue's lines, calling ``run(sprites)`` for a pool
    subject or ``run_one(sprite)`` for a lone-sprite subject -- see
    :mod:`model`'s docstring on why ``subject_kind`` decides this. Each
    line's trailing block-id comment (when any) is the *same* Action
    declaration's block id ``_render_attached``/
    ``_render_state_machine_attached`` already used for that bind's own
    ``self.<bind> = self.action(...)`` line -- one Blockly block (the
    "do"-flavor Action placed in the "apply to all" zone) produces both
    lines, see ``web/vs2-behavior-blocks.js``'s own ``serializeApplyToAll``."""
    method = "run" if model["subject_kind"] == "pool" else "run_one"
    lines = []
    for bind in model.get("apply_to_all", []):
        line = "%sself.%s.%s(%s)" % (indent, bind, method, sprites_expr)
        block_id = actions_by_bind.get(bind, {}).get("block_id")
        lines.extend(_with_block_comment([line], block_id))
    return lines


# ---------------------------------------------------------------------------
# Per-sprite statement rendering (recursive; runs inside the per-sprite loop
# for a pool subject, or directly against ``sprite`` for a lone-sprite one).
# ---------------------------------------------------------------------------

def _references_hit_var(nodes):
    """True if a ``despawn_hit`` node inside ``nodes`` refers to the
    *current* ``hit_var`` scope -- descends into an ``if_else``'s own
    ``then``/``else`` (same scope: ``_render_per_sprite_node`` passes
    ``hit_var`` through unchanged there) but *not* into a nested
    ``if_action``'s (a fresh ``hit_var`` takes over for that subtree; a
    ``despawn_hit`` inside it refers to that nested result, not this
    one). Used only by the fast backend, to decide whether an
    ``if_action``'s own ``_<bind>_result`` local is single-use (see
    :data:`BACKENDS`'s docstring's "inline" bullet) and can be inlined
    away."""
    for node in nodes:
        kind = node["kind"]
        if kind == "despawn_hit":
            return True
        if kind == "if_else":
            if (_references_hit_var(node.get("then", []))
                    or _references_hit_var(node.get("else", []))):
                return True
        # if_action starts a fresh hit_var scope of its own; not descended
        # into here for that reason (see docstring above).
    return False


def _render_per_sprite_list(nodes, indent, hit_var, backend="readable", hoisted=None):
    lines = []
    for node in nodes:
        lines.extend(_render_per_sprite_node(node, indent, hit_var, backend, hoisted))
    if not lines:
        lines.append("%spass" % (indent,))
    return lines


def _render_per_sprite_node(node, indent, hit_var, backend="readable", hoisted=None):
    kind = node["kind"]
    block_id = node.get("block_id")

    if kind == "accumulate":
        line = "%ssprite.%s += %s" % (
            indent, node["state"], render_expr(node["amount"], hoisted))
        return _with_block_comment([line], block_id)

    if kind == "despawn":
        return _with_block_comment(["%ssprite.despawn()" % (indent,)], block_id)

    if kind == "despawn_hit":
        # Only reachable inside an "if_action" node's own then/else stack --
        # see model.py's PER_SPRITE_KINDS docstring and this function's
        # "if_action" branch below, which is the only place `hit_var` is
        # ever set to anything but None.
        if hit_var is None:
            raise GeneratorError(
                "despawn_hit used outside an if_action's then/else stack")
        return _with_block_comment(["%s%s.despawn()" % (indent, hit_var)], block_id)

    if kind == "set_state":
        # accumulate's non-accumulating sibling: a plain assignment, for
        # e.g. resetting an invulnerability countdown to its configured
        # length on a fresh hit rather than adding to whatever was left.
        line = "%ssprite.%s = %s" % (indent, node["state"], render_expr(node["value"], hoisted))
        return _with_block_comment([line], block_id)

    if kind == "call_callback":
        # Every existing Callback in apps/micropython/vs2/behaviors.py
        # (Transient.on_end, Lifetime.on_expire, Blinking.on_end) calls its
        # callback as `cb(sprite)` -- read into a local first (never twice)
        # so a game that passes a Callback once and swaps it never sees a
        # torn read. `args` extends that with more positional arguments
        # after `sprite` -- e.g. Damageable.on_death's own points argument,
        # see this task's report for why that one Callback's contract is
        # richer than every other one in the catalog. NOT inlined by the
        # fast backend even though `local` is read exactly twice below:
        # inlining would read the mutable `self.<name>` attribute a second
        # time instead of reusing the first read, which is precisely the
        # torn-read hazard this comment already explains is deliberately
        # avoided -- see BACKENDS's own docstring.
        name = node["name"]
        local = "_cb_" + name
        call_args = ["sprite"] + [render_expr(arg, hoisted) for arg in node.get("args", [])]
        return _with_block_comment([
            "%s%s = self.%s" % (indent, local, name),
            "%sif %s is not None:" % (indent, local),
            "%s    %s(%s)" % (indent, local, ", ".join(call_args)),
        ], block_id)

    if kind == "spawn":
        # Spawns into a declared PoolRef parameter (e.g. an explosion
        # pool) -- guarded the same way every PoolRef consumer in this
        # codebase guards a full pool's spawn() returning None (see
        # games/vs2_examples/vixeous/code/vixeous.py's own burst()). Not
        # inlined by the fast backend, for the same never-read-twice
        # reason as call_callback above.
        pool_name = node["pool"]
        local = "_spawn_" + pool_name
        return _with_block_comment([
            "%s%s = self.%s" % (indent, local, pool_name),
            "%sif %s is not None:" % (indent, local),
            "%s    %s.spawn(%s, %s)" % (
                indent, local, render_expr(node["x"], hoisted), render_expr(node["y"], hoisted)),
        ], block_id)

    if kind == "play_sound":
        # _choose_sound picks one name when the declared Sound parameter
        # is a tuple (vs2.params.Sound's own "tuple of names picked from
        # at random" contract) -- see Transient._expire's identical idiom.
        # Not inlined by the fast backend, for the same reason as above.
        name = node["name"]
        local = "_sound_" + name
        return _with_block_comment([
            "%s%s = self.%s" % (indent, local, name),
            "%sif %s is not None:" % (indent, local),
            "%s    audio.sound(_choose_sound(%s))" % (indent, local),
        ], block_id)

    if kind == "goto_state":
        # A per-state method's own contract (see StateMachine's class
        # docstring): return the next state's name, or fall off the end
        # (rendered by _render_per_sprite_list's own "pass" for an empty
        # list, or simply nothing further to render otherwise) for "stay".
        return _with_block_comment(["%sreturn %r" % (indent, node["name"])], block_id)

    if kind == "hold":
        line = "%sself.hold(sprite, %s, then=%r)" % (
            indent, render_expr(node["ticks"], hoisted), node["then"])
        return _with_block_comment([line], block_id)

    if kind == "if_else":
        cond_src = render_condition(node["condition"], backend, hoisted)
        lines = _with_block_comment(["%sif %s:" % (indent, cond_src)], block_id)
        lines.extend(_render_per_sprite_list(node["then"], indent + "    ", hit_var,
                                              backend, hoisted))
        else_nodes = node.get("else", [])
        if else_nodes:
            lines.extend(_with_block_comment(["%selse:" % (indent,)], block_id))
            lines.extend(_render_per_sprite_list(else_nodes, indent + "    ", hit_var,
                                                  backend, hoisted))
        return lines

    # kind == "if_action": bind a fresh local for this Action's run_one()
    # result, branch on "found something" (not None -- vs2.DONE included,
    # matching every Action's own "result is None means nothing notable
    # happened" contract), and make that local visible to any nested
    # despawn_hit as this node's own `hit_var`.
    #
    # Fast backend, single-use inlining: when nothing in `then`/`else`
    # actually reaches this node's own hit_var scope through a
    # despawn_hit (see _references_hit_var), the local is read exactly
    # once (the "is not None" check) and is inlined away -- the
    # run_one() call still happens exactly once either way, so this
    # changes nothing observable, see BACKENDS's own docstring.
    bind = node["bind"]
    then_nodes = node["then"]
    else_nodes = node.get("else", [])
    if backend == "fast" and not (_references_hit_var(then_nodes)
                                   or _references_hit_var(else_nodes)):
        cond = "%sif self.%s.run_one(sprite) is not None:" % (indent, bind)
        lines = _with_block_comment([cond], block_id)
        lines.extend(_render_per_sprite_list(then_nodes, indent + "    ", None,
                                              backend, hoisted))
        if else_nodes:
            lines.extend(_with_block_comment(["%selse:" % (indent,)], block_id))
            lines.extend(_render_per_sprite_list(else_nodes, indent + "    ", None,
                                                  backend, hoisted))
        return lines

    local = "_" + bind + "_result"
    lines = _with_block_comment(
        ["%s%s = self.%s.run_one(sprite)" % (indent, local, bind)], block_id)
    lines.extend(_with_block_comment(["%sif %s is not None:" % (indent, local)], block_id))
    lines.extend(_render_per_sprite_list(then_nodes, indent + "    ", local, backend, hoisted))
    if else_nodes:
        lines.extend(_with_block_comment(["%selse:" % (indent,)], block_id))
        lines.extend(_render_per_sprite_list(else_nodes, indent + "    ", local,
                                              backend, hoisted))
    return lines


# ---------------------------------------------------------------------------
# step()/step_one() assembly
# ---------------------------------------------------------------------------

def _collect_hoistable_params(per_sprite_nodes):
    """Every ``"param"`` name read anywhere in ``per_sprite_nodes`` -- the
    fast backend's hoist candidates (see :data:`BACKENDS`'s docstring's
    "hoist" bullet). Only meaningful for a pool subject's own ``while``
    loop, which is the one place the *generated code itself* contains an
    explicit loop for a hoisted local to sit above -- see
    :func:`_render_step_pool`, the only caller.

    Only looks at each node's own top-level expression(s), not inside a
    nested ``"binary_op"``'s own ``left``/``right`` -- a ``param`` read
    buried inside arithmetic stays un-hoisted (rendered ``self.<name>``
    even under the fast backend). A missed optimization, not a
    correctness gap: :func:`render_expr` renders that form correctly
    either way, and every param a game actually needs hoisted so far
    (``Projectile``'s own ``speed_x``/``speed_y``/``range``) is read bare,
    never wrapped in arithmetic."""
    names = set()
    for node in _iter_nodes(per_sprite_nodes):
        for expr in _iter_exprs_in_node(node):
            if expr["kind"] == "param":
                names.add(expr["name"])
    return names


def _hoist_lines(hoisted, indent):
    """``{param_name: local_name}`` -> the ``_h_<name> = self.<name>``
    assignment lines, one per hoisted param, in a deterministic
    (alphabetical) order regardless of dict insertion order. No trailing
    block-id comment: a single hoisted local can aggregate reads from
    several different per-sprite nodes (each with its own, possibly
    different, originating block), so there is no one block this
    synthetic line belongs to."""
    return ["%s%s = self.%s" % (indent, hoisted[name], name) for name in sorted(hoisted)]


def _render_step_pool(model, actions_by_bind, backend="readable"):
    """``def step(self, sprites):`` -- the uniform prologue, then the exact
    downward-indexed despawn-safe loop ``Projectile.step()`` uses (see this
    module's docstring). ``backend="fast"`` additionally hoists every
    ``self.<param>`` read anywhere in the per-sprite tree to a local
    assigned once before the loop -- see :func:`_collect_hoistable_params`."""
    lines = ["    def step(self, sprites):"]
    lines.extend(_render_apply_to_all(model, "sprites", INDENT, actions_by_bind))
    per_sprite = model.get("per_sprite", [])
    if not per_sprite:
        return lines
    hoisted = {}
    if backend == "fast":
        param_names = _collect_hoistable_params(per_sprite)
        hoisted = {name: "_h_%s" % (name,) for name in param_names}
        lines.extend(_hoist_lines(hoisted, INDENT))
    lines.append("%slive = sprites._live" % (INDENT,))
    lines.append("%sindex = len(live) - 1" % (INDENT,))
    lines.append("%swhile index >= 0:" % (INDENT,))
    lines.append("%s    sprite = live[index]" % (INDENT,))
    lines.extend(_render_per_sprite_list(per_sprite, INDENT + "    ", None, backend, hoisted))
    lines.append("%s    index -= 1" % (INDENT,))
    return lines


def _render_step_one(model, actions_by_bind, backend="readable"):
    """``def step_one(self, sprite):`` -- the lone-sprite subject form:
    the uniform prologue calls ``run_one`` directly (no pool to sweep), and
    the per-sprite statements apply to ``sprite`` with no loop at all. No
    hoisting here regardless of ``backend`` -- there is no loop in the
    generated code for a hoisted local to sit above (see
    :data:`BACKENDS`'s docstring)."""
    lines = ["    def step_one(self, sprite):"]
    lines.extend(_render_apply_to_all(model, "sprite", INDENT, actions_by_bind))
    per_sprite = model.get("per_sprite", [])
    lines.extend(_render_per_sprite_list(per_sprite, INDENT, None, backend, None))
    return lines


# ---------------------------------------------------------------------------
# State-machine assembly (Phase 2): one method per declared state, plus
# whichever enter_/exit_ hooks the model actually declares. No step()/
# step_one() at all -- see this module's docstring's "Phase 2" section for
# why: every one of those is inherited from the real StateMachine base.
# ---------------------------------------------------------------------------

def _render_state_machine_attached(model):
    """``def attached(self, subject):`` composing this model's declared
    Actions -- only emitted when there are any. When there are none, this
    function returns ``[]`` and the generated class defines no ``attached``
    override at all, so the base :meth:`StateMachine.attached` (which
    primes ``fsm_state``/``fsm_hold``/``fsm_then``) runs unmodified -- the
    same "override only when there is build-time setup to do" contract
    :class:`~vs2.behaviors.Behavior.attached`'s own docstring states.

    When there *are* Actions, the override must still prime those fsm
    fields itself -- :class:`~vs2.behaviors.StateMachine`'s own docstring:
    "A subclass overriding this ... must call ``StateMachine.attached(self,
    subject)`` too, or nothing above will run." Spelled exactly that way
    (the unbound-call form the real class's docstring itself uses), never
    ``super().attached(subject)`` -- see this module's docstring for why
    that distinction matters on real MicroPython."""
    actions = model.get("actions", [])
    if not actions:
        return []
    lines = ["    def attached(self, subject):"]
    lines.append("%sStateMachine.attached(self, subject)" % (INDENT,))
    for action_decl in actions:
        line = "%sself.%s = self.action(%s)" % (
            INDENT, action_decl["bind"], _render_action_call(action_decl))
        lines.extend(_with_block_comment([line], action_decl.get("block_id")))
    return lines


def _render_state_methods(model, backend="readable"):
    """One ``def <state>(self, sprite):`` per declared state, each preceded
    by ``enter_<state>``/followed by ``exit_<state>`` when the model
    actually declares one -- see model.py's own "## State hats" docstring
    section for why those two are optional and ``step`` is not. No
    hoisting regardless of ``backend`` -- see :func:`_render_step_one`'s
    docstring for why (no explicit loop in a per-state method's own
    generated body to hoist above)."""
    state_machine = model["state_machine"]
    states = state_machine["states"]
    bodies = state_machine["bodies"]
    lines = []
    for index, name in enumerate(states):
        if index > 0:
            lines.append("")
        body = bodies[name]
        if "enter" in body:
            lines.append("    def enter_%s(self, sprite):" % (name,))
            lines.extend(_render_per_sprite_list(body["enter"], INDENT, None, backend, None))
            lines.append("")
        lines.append("    def %s(self, sprite):" % (name,))
        lines.extend(_render_per_sprite_list(body["step"], INDENT, None, backend, None))
        if "exit" in body:
            lines.append("")
            lines.append("    def exit_%s(self, sprite):" % (name,))
            lines.extend(_render_per_sprite_list(body["exit"], INDENT, None, backend, None))
    return lines


# ---------------------------------------------------------------------------
# Import selection: which node kinds does this model actually use anywhere
# (a plain Behavior's flat per_sprite list, or any state's own body)? Only
# "play_sound" currently changes what the generated file needs to import
# (vs2.audio, and vs2.behaviors._choose_sound) -- walking the whole model
# once, up front, keeps that decision in one place rather than re-deriving
# it separately for each shape render_body() can produce.
# ---------------------------------------------------------------------------

def _iter_nodes(nodes):
    for node in nodes:
        yield node
        kind = node["kind"]
        if kind in ("if_else", "if_action"):
            for nested in _iter_nodes(node.get("then", [])):
                yield nested
            for nested in _iter_nodes(node.get("else", [])):
                yield nested


def _used_node_kinds(model):
    kinds = set()
    for node in _iter_nodes(model.get("per_sprite", [])):
        kinds.add(node["kind"])
    state_machine = model.get("state_machine")
    if state_machine:
        for body in state_machine["bodies"].values():
            for hook in ("enter", "step", "exit"):
                for node in _iter_nodes(body.get(hook, [])):
                    kinds.add(node["kind"])
    return kinds


# ---------------------------------------------------------------------------
# Full-file assembly
# ---------------------------------------------------------------------------

def render_body(model, backend="readable"):
    """The generated file's body -- everything except the banner and the
    trailing blob line. Deterministic: the same model and the same
    ``backend`` always render the same body, byte for byte. ``backend`` is
    one of :data:`BACKENDS`; see its docstring for exactly what
    ``"fast"`` changes (constant-fold / hoist / inline, and nothing
    else -- never reordering or restructuring control flow)."""
    if backend not in BACKENDS:
        raise GeneratorError("backend: %r is not one of %s" % (backend, BACKENDS))
    actions_by_bind = {a["bind"]: a for a in model.get("actions", [])}
    params = model.get("params", [])
    param_classes = set()
    param_lines = []
    for param in params:
        param_class, decl_src = _render_param_decl(param)
        param_classes.add(param_class)
        param_lines.append("    %s = %s" % (param["name"], decl_src))

    state = model.get("state", [])
    state_machine = model.get("state_machine")
    needs_audio = "play_sound" in _used_node_kinds(model)

    lines = []
    if model.get("actions"):
        lines.append("from vs2 import actions")
    if needs_audio:
        lines.append("from vs2 import audio")
    base_class = "StateMachine" if state_machine else "Behavior"
    behavior_import_names = [base_class]
    if needs_audio:
        behavior_import_names.append("_choose_sound")
    lines.append("from vs2.behaviors import %s" % (", ".join(sorted(behavior_import_names)),))
    if param_classes:
        lines.append("from vs2.params import %s" % (", ".join(sorted(param_classes)),))
    lines.append("")
    lines.append("")
    lines.append("class %s(%s):" % (model["class_name"], base_class))
    if param_lines:
        lines.extend(param_lines)
        lines.append("")
    if state:
        lines.append("    state = %r" % (tuple(state),))
        lines.append("")

    if state_machine:
        lines.append("    states = %r" % (tuple(state_machine["states"]),))
        lines.append("    initial = %r" % (state_machine["initial"],))
        lines.append("")
        attached_lines = _render_state_machine_attached(model)
        if attached_lines:
            lines.extend(attached_lines)
            lines.append("")
        lines.extend(_render_state_methods(model, backend))
    else:
        lines.extend(_render_attached(model))
        lines.append("")
        if model["subject_kind"] == "pool":
            lines.extend(_render_step_pool(model, actions_by_bind, backend))
        else:
            lines.extend(_render_step_one(model, actions_by_bind, backend))
    return "\n".join(lines)


def generate_source(model, basename, backend="readable"):
    """The full generated file text: banner, body, blank line, blob.
    ``basename`` (e.g. ``"generated_projectile.py"``) is recorded in the
    banner only. ``backend`` (:data:`BACKENDS`) is not recorded anywhere
    in the file either -- the embedded blob always carries the same
    model regardless of which backend rendered it, so switching backends
    and regenerating is not a model change (it changes only the body, and
    therefore the banner's body-sha, correctly)."""
    model_module.validate_model(model)
    body = render_body(model, backend)
    sha = checksum.body_sha(body)
    banner_line = checksum.make_banner(basename, sha)
    blob_line = checksum.make_blob_line(encode_blob(model))
    return checksum.join_generated_file(banner_line, body, blob_line)


class WriteResult:
    """Outcome of :func:`write_behavior_file`. ``status`` is one of
    ``"created"``, ``"updated"``, ``"unchanged"``, ``"hand_edited"`` or
    ``"detached"`` -- the same five outcomes
    ``tools.vs2_scene_gen.generator.WriteResult``/
    ``tools.vs2_event_gen.generator.WriteResult`` document, applied to a
    generated Behavior file instead."""

    def __init__(self, status, path, message):
        self.status = status
        self.path = path
        self.message = message

    def __repr__(self):
        return "WriteResult(%r, %r, %r)" % (self.status, str(self.path), self.message)


def write_behavior_file(model, output_path, backend="readable"):
    """Regenerate ``output_path`` from ``model`` if it is safe to do so.
    Never raises for any of the five normal outcomes above -- only a
    malformed ``model`` (:class:`~model.ModelError`) or an unwritable path
    can raise. ``backend`` -- see :func:`generate_source`."""
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
