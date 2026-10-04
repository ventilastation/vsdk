"""Control-plane support for the ``vs2beh`` live-tune protocol.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The live-tune loop`` and
``## State machines``. Work-breakdown card:
``docs/vs2-behaviors-implementation.md`` T11.

Exposes scene/project variables and every attached Behavior's (and its
Actions') parameters over the same in-band text command channel
``povcal``/``povperf``/``hallfilter`` already use (see ``director.py``'s
``_dispatch_control``), so the property panel (T12) can list, read and
write them against a live game -- desktop emulator, browser, or the
physical console over USB serial -- with the change visible on the next
tick and no restart::

    > vs2beh list
    {"subjects": [...]}

    > vs2beh set enemies.damageable.hp 2
    vs2beh_ok enemies.damageable.hp=2

    > vs2beh reset enemies.damageable.hp
    vs2beh_ok enemies.damageable.hp=1

**The subject-naming gap.** ``SpritePool``/``Sprite``/``Family`` have no
``name=`` parameter anywhere in ``vs2/__init__.py`` -- only ``Layer``
does. But the protocol addresses a subject by name (``enemies.damageable
.hp``), and every example in the spec assigns a pool/sprite/family to a
``self.<name>`` attribute inside ``build()`` (``self.enemies = ...``).
So :func:`_discover_names` derives a subject's protocol name by walking
the *scene instance's own public attributes* and matching by identity,
rather than adding a ``name=`` parameter to ``vs2/__init__.py`` (which
four other Wave-5 agents are editing this same wave). This is
deliberately "option 1" from this task's card: no new ``vs2/__init__.py``
surface, at the cost of two documented edge cases -- see
:func:`_discover_names`.

**Zero cost for a game that never uses ``vs2beh``.** This module is only
imported lazily from ``director.py``'s ``elif cmd == "vs2beh":`` branch,
the first time that command actually arrives. It never imports
``vs2.params`` at module scope either -- see :func:`_build_registry` --
so loading this module costs nothing until a ``vs2beh`` command is
actually dispatched against a scene that looks like a real ``vs2.Scene``.

**The kinds-table read path.** T12 (the inspector panel, same wave) built a
``kinds`` table editor against a documented ``{"fields": [...], "rows":
[{"name", "values"}, ...]}`` wire shape that this module did not originally
emit -- found and fixed at Wave-5 merge time. Row order can't reflect
declaration order: ``SpritePool.kinds()`` takes ``**rows``, and MicroPython's
``**kwargs`` capture does not preserve call-site order (confirmed directly
against the real interpreter), unlike ``var()``'s own ``_var_order`` fix
(T5), which works because each variable is declared in its own call. Rows
are sorted by name instead -- deterministic and stable across repeated
``list`` calls, which is what the panel's "editing a cell never reorders
other rows" contract actually needs.

**The kinds-table write path.** Added later: one ``_Target`` per cell,
addressed as ``<subject>.kinds.<kind_name>.<field_name>`` and going
through the exact same ``set``/``reset`` verbs every scalar parameter
already uses -- no new top-level command, see :func:`_register_kind_cells`.
Writing replaces the whole row tuple (``SpritePool._kind_rows`` moved from
build-time-immutable to live-tune-writable the moment this landed);
``vs2.SpritePool.kinds()`` now also keeps ``_kind_rows_default``, a frozen
snapshot of the rows exactly as declared, since a kinds cell has no
scalar-``Parameter``-style fixed default of its own to restore from once
its live copy can change. **Still open:** the panel's
``mountKindsEditor`` is not yet mounted into the live panel tree -- real,
scoped follow-up work, not silently swept under this fix.

**Never crashes the control loop.** ``director.py.step_once()`` calls
``_dispatch_control()`` with no surrounding ``try``/``except`` (only the
scene's own ``scene_step()`` is guarded, and that guard re-raises after
reporting). A malformed ``vs2beh`` command -- a typo'd path, a
missing argument, an out-of-range value -- must never propagate past
:func:`handle_command` and take the whole board down with it, so this
module catches broadly (``except Exception``) rather than the narrower
tuples ``color_calibration``/``pov_profiling``/``hall_filter_control``
use for their own, much smaller command sets.
"""

import json


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def handle_command(parts, send, scene=None):
    """Handle ``vs2beh``. Commands are ``list``, ``set <path> <value>`` and
    ``reset <path>``, where ``<path>`` is a dotted address such as
    ``enemies.damageable.hp``, ``enemies.damageable.blink.on_ticks``,
    ``scene.score``, ``project.high_score`` or ``enemies.enemy.state``.

    ``list`` builds its payload fresh on every call -- nothing is cached
    across ticks or across calls -- and sends it as one JSON line. ``set``
    parses one wire token into the target's declared type and writes it
    directly onto the live Behavior/Action/pool/scene/project instance, so
    it is visible on the very next Step. ``reset`` writes the target's
    declared default the same way.
    """
    command = parts[0] if parts else "list"
    if not _is_vs2_scene(scene):
        send(b"vs2beh_error scene does not support vs2beh (not a vs2.Scene)")
        return
    try:
        payload, registry = _build_registry(scene)
        if command == "list":
            send(json.dumps(payload).encode())
            return
        if command not in ("set", "reset"):
            raise ValueError(
                "unknown vs2beh command %r; valid: list, set, reset" % (command,))
        if len(parts) < 2:
            raise ValueError("%s needs a path" % (command,))
        path = parts[1]
        target = registry.get(path)
        if target is None:
            raise ValueError(_unknown_path_message(path, registry.keys()))
        if command == "set":
            if len(parts) < 3:
                raise ValueError("set needs a value: vs2beh set %s <value>" % (path,))
            value = target.coerce(parts[2])
        else:
            value = target.default
        applied = target.apply(value)
        send(("vs2beh_ok %s=%s" % (path, applied)).encode())
    except Exception as error:
        send(("vs2beh_error %s" % (error,)).encode())


def _is_vs2_scene(scene):
    """Duck-typed: every ``vs2.Scene`` has these three, set up in
    ``Scene.__init__``/``on_enter`` (see ``vs2/__init__.py``); nothing
    else reaching this handler (``None``, or a legacy V1
    ``ventilastation.sprites`` scene) does."""
    return (scene is not None
            and hasattr(scene, "_behaviors")
            and hasattr(scene, "_vars")
            and hasattr(scene, "_pools"))


# ---------------------------------------------------------------------------
# Subject discovery -- the design-gap fix (see module docstring).
# ---------------------------------------------------------------------------

def _discover_names(scene):
    """``({id(subject): name}, {name: subject})`` for every pool, sprite
    or family reachable through one of ``scene``'s own public (non-``_``)
    attributes, matched by object identity, not by any name the object
    itself carries (it carries none).

    **Tie-break rule** (first documented edge case): if more than one
    attribute references the same object, the first match in
    ``sorted(dir(scene))`` order wins -- deterministic and independent of
    MicroPython's unordered ``dir()``, unlike "declaration order" (which
    this module has no way to observe for plain attribute assignments).

    **Unreachable objects** (second documented edge case): a pool/sprite/
    family built in ``build()`` but never assigned to ``self.<name>`` --
    used only as a local variable, or reachable solely as a member of a
    ``Family`` that is itself assigned -- has no entry here and is
    silently excluded from ``vs2beh list`` and from every path this
    module resolves. There is no name to address it by, and inventing one
    (``"pool_0"``) would be unstable across rebuilds and would collide
    with a real name a rename introduced later. A game wanting a pool
    tunable over ``vs2beh`` must assign it to a scene attribute, which
    every example in the spec already does.

    Duck-typed via ``_behaviors``/``_behavior_order`` (the pair every
    ``SpritePool``, ``Sprite`` and ``Family`` carries, set up in their own
    ``__init__``) rather than ``isinstance`` against ``vs2.SpritePool``/
    ``vs2.Sprite``/``vs2.Family`` -- this module otherwise never imports
    ``vs2`` itself (see the module docstring's "zero cost" note), and this
    is the one place it would otherwise have to.
    """
    id_to_name = {}
    name_to_object = {}
    for attr in sorted(dir(scene)):
        if attr.startswith("_"):
            continue
        try:
            value = getattr(scene, attr)
        except Exception:
            continue
        if value is scene:
            continue
        if not (hasattr(value, "_behaviors") and hasattr(value, "_behavior_order")):
            continue
        key = id(value)
        if key not in id_to_name:
            id_to_name[key] = attr
            name_to_object[attr] = value
    return id_to_name, name_to_object


def _kind_of(obj):
    """``"pool"``/``"sprite"``/``"family"`` for an object
    :func:`_discover_names` found, by the same duck-typed-attribute trick:
    only ``SpritePool`` carries ``_var_defaults``, only ``Family`` carries
    ``_members``; anything left over that already passed
    :func:`_discover_names`'s ``_behaviors`` check is a lone ``Sprite``."""
    if hasattr(obj, "_var_defaults"):
        return "pool"
    if hasattr(obj, "_members"):
        return "family"
    return "sprite"


# ---------------------------------------------------------------------------
# Registry: one JSON payload plus one flat {path: _Target} map, built
# together in a single pass so `list` and `set`/`reset` never disagree
# about what is addressable.
# ---------------------------------------------------------------------------

class _Target:
    """One addressable ``vs2beh`` path.

    ``get()`` reads the live value. ``apply(value)`` writes an
    already-typed value and returns what was actually written (a
    ``Parameter``'s ``validate()`` may coerce, e.g. ``Flag`` to ``bool``).
    ``coerce(raw)`` parses one wire token (always a plain string -- see
    ``director.py``'s ``cmd_line.split()``) into that type. ``default`` is
    what ``reset`` writes back.
    """

    def __init__(self, get, apply, coerce, default):
        self.get = get
        self.apply = apply
        self.coerce = coerce
        self.default = default


def _reject(message):
    """A ``_Target``'s ``apply``/``coerce`` for a path that is
    structurally present (so it shows up in ``list``) but not writable
    over this protocol -- a ``Var``-bound parameter, or a parameter type
    this module does not parse from one wire token (``Sound``, ``Image``,
    ``Callback``, ``Points``)."""
    def raiser(*_args):
        raise ValueError(message)
    return raiser


def _identity_coerce(raw):
    return raw


def _var_get(container, name):
    def get():
        return getattr(container, name)
    return get


def _var_apply(container, name, parameter, owner_label):
    def apply(value):
        if parameter is not None and hasattr(parameter, "validate"):
            value = parameter.validate(owner_label, name, value)
        setattr(container, name, value)
        return value
    return apply


def _coerce_scalar(raw, type_name, options):
    if type_name == "flag":
        low = raw.strip().lower()
        if low in ("1", "true", "on", "yes"):
            return True
        if low in ("0", "false", "off", "no"):
            return False
        raise ValueError("flag value must be true/false (or 1/0); got %r" % (raw,))
    if type_name in ("number", "angle", "frames"):
        try:
            if "." in raw or "e" in raw.lower():
                return float(raw)
            return int(raw)
        except ValueError:
            raise ValueError("%r is not a number" % (raw,))
    if type_name == "choice":
        for option in options or ():
            if str(option) == raw:
                return option
        return raw  # let Choice.validate() report the real error, naming options
    return raw


def _var_coerce(parameter):
    type_name = parameter.type_name
    options = parameter.options

    def coerce(raw):
        return _coerce_scalar(raw, type_name, options)
    return coerce


def _kind_cell_get(pool, kind_name, field_index):
    def get():
        return pool._kind_rows[kind_name][field_index]
    return get


def _kind_cell_apply(pool, kind_name, field_index, parameter, owner_label):
    def apply(value):
        if parameter is not None and hasattr(parameter, "validate"):
            value = parameter.validate(owner_label, "kinds." + kind_name, value)
        row = list(pool._kind_rows[kind_name])
        row[field_index] = value
        pool._kind_rows[kind_name] = tuple(row)
        return value
    return apply


def _register_kind_cells(registry, subject_name, pool):
    """Register one writable ``_Target`` per kinds-table cell
    (``<subject>.kinds.<kind_name>.<field_name>``), the write half of the
    read path already built into the ``list`` payload above. Reads and
    writes both go through ``pool._kind_rows`` directly (never cached),
    so a ``list`` right after a ``set`` always reflects it -- the same
    "no restart needed" contract every other ``vs2beh`` path already
    gives.

    ``reset`` restores from ``pool._kind_rows_default``, a frozen
    snapshot ``kinds()`` takes at declaration time -- unlike a scalar
    ``var()``'s single, never-changing default, a kinds row has no
    fixed default of its own once ``_kind_rows`` itself becomes
    writable, so that snapshot is the only thing a live-tune ``reset``
    can mean here.
    """
    if not pool._kind_rows:
        return
    fields = pool._kind_fields
    for kind_name in sorted(pool._kind_rows.keys()):
        for field_index, field_name in enumerate(fields):
            path = "%s.kinds.%s.%s" % (subject_name, kind_name, field_name)
            parameter = pool._var_defaults.get(field_name)
            owner_label = "%s.kinds.%s" % (subject_name, kind_name)
            default_row = pool._kind_rows_default.get(kind_name)
            default_value = default_row[field_index] if default_row is not None else None
            coerce = _var_coerce(parameter) if parameter is not None else _identity_coerce
            registry[path] = _Target(
                _kind_cell_get(pool, kind_name, field_index),
                _kind_cell_apply(pool, kind_name, field_index, parameter, owner_label),
                coerce, default_value)


def _poolref_coerce(name_to_object):
    def coerce(raw):
        if raw in ("none", "None", ""):
            return None
        target = name_to_object.get(raw)
        if target is None:
            raise ValueError("unknown subject %r for a pool parameter" % (raw,))
        return target
    return coerce


def _unsupported_coerce(path, type_name):
    return _reject("%s is a %s parameter; not settable over vs2beh" % (path, type_name))


def _render_ref(value, id_to_name):
    if value is None:
        return None
    return id_to_name.get(id(value))


def _render_scalar(type_name, value):
    if type_name == "callback":
        return getattr(value, "__name__", None) if value is not None else None
    if isinstance(value, tuple):
        return list(value)
    return value


def _metadata_entry(name, type_name, value, metadata):
    entry = {"name": name, "type": type_name, "value": value}
    if metadata:
        for key in ("min", "max", "step", "label", "unit", "options"):
            val = metadata.get(key)
            if val is not None:
                if key == "options" and not isinstance(val, list):
                    val = list(val)
                entry[key] = val
    return entry


def _register_scalar_vars(registry, path_prefix, container, var_defaults, names):
    """Build the ``vars`` list (and registry entries) for a scene,
    project or pool's own :meth:`var`-declared variables. ``names`` is the
    order to render them in -- the pool's own ``_var_order`` (MicroPython
    dicts do not preserve insertion order, so that list, not
    ``var_defaults.keys()``, is what gives a stable order) or, for scene
    and project variables (which track no such order themselves, since
    nothing depends on their positional order the way ``kinds()`` does),
    ``sorted(var_defaults.keys())``.
    """
    entries = []
    for name in names:
        parameter = var_defaults[name]
        path = path_prefix + "." + name
        value = getattr(container, name, parameter.default)
        entries.append(_metadata_entry(name, parameter.type_name, value, parameter.metadata()))
        registry[path] = _Target(
            _var_get(container, name),
            _var_apply(container, name, parameter, path_prefix),
            _var_coerce(parameter),
            parameter.default)
    return entries


def _named_actions(behavior):
    """``[(name, action), ...]`` in registration order for every Action
    ``behavior`` registered via ``self.action(...)`` (T8's
    ``Behavior.actions`` property) -- named the same way subjects are
    (:func:`_discover_names`): by matching object identity against the
    behavior's own ``self.<name>`` attributes, since an Action is not
    individually named by ``Behavior.action()`` itself (see
    ``vs2/behaviors.py``'s own docstring on this). An Action registered
    but reachable through no such attribute (composed and used only
    locally inside ``attached()``) is omitted -- the same "unaddressable"
    rule :func:`_discover_names` documents for a subject.
    """
    registered = getattr(behavior, "actions", ())
    if not registered:
        return []
    ids = {}
    for action in registered:
        ids.setdefault(id(action), action)
    found = {}
    for attr in sorted(dir(behavior)):
        if attr.startswith("_"):
            continue
        try:
            value = getattr(behavior, attr)
        except Exception:
            continue
        key = id(value)
        if key in ids and key not in found:
            found[key] = attr
    result = []
    for action in registered:
        name = found.get(id(action))
        if name is not None:
            result.append((name, action))
    return result


def _register_params(registry, path_prefix, instance, declared, introspect_fn, var_cls,
                      id_to_name, name_to_object):
    """Build the ``params`` list (and registry entries) for one Behavior
    or Action instance -- shared body, since both use the same
    ``vs2.params`` declaration system (T1/T4/T8)."""
    entries = []
    for name, type_name, default, metadata in introspect_fn(type(instance)):
        raw_value = getattr(instance, name, default)
        path = path_prefix + "." + name
        parameter = declared.get(name)
        if isinstance(raw_value, var_cls):
            # Var-bound: the spec's own "one toggle... marks a var-bound
            # parameter as per-sprite" -- shown, but not settable here;
            # the per-sprite instance variable it names is the thing to
            # edit (typically that pool's own .var()-declared entry).
            entries.append(_metadata_entry(name, type_name, {"var": raw_value.name}, metadata))
            message = ("%s is bound to instance variable %r; edit that variable "
                       "instead of setting it here" % (path, raw_value.name))
            registry[path] = _Target(_var_get(instance, name), _reject(message),
                                      _reject(message), default)
            continue
        display_value = (_render_ref(raw_value, id_to_name) if type_name == "pool"
                          else _render_scalar(type_name, raw_value))
        entries.append(_metadata_entry(name, type_name, display_value, metadata))
        if type_name == "pool":
            coerce = _poolref_coerce(name_to_object)
        elif type_name in ("sound", "image", "callback", "points"):
            coerce = _unsupported_coerce(path, type_name)
        elif parameter is not None:
            coerce = _var_coerce(parameter)
        else:
            coerce = _identity_coerce
        registry[path] = _Target(
            _var_get(instance, name),
            _var_apply(instance, name, parameter, type(instance).__name__),
            coerce, default)
    return entries


# ---------------------------------------------------------------------------
# State machines. T10 (StateMachine) is a sibling Wave-5 task building in
# ``vs2/behaviors.py`` in parallel and had not landed in this worktree as
# this was written -- see this task's report. Rather than depend on its
# actual class, this targets exactly the *contract* the spec's "##
# State machines" section describes and nothing more:
#   - a ``states`` class attribute: a tuple of state-name strings
#     (``states = ("descending", "orbiting", ...)``);
#   - one primed byte, ``sprite.fsm_state``, indexing into it;
#   - optional ``enter_<name>``/``exit_<name>`` hooks, matched by name.
# Any object -- T10's real StateMachine or a hand-rolled stand-in -- that
# carries a non-empty ``states`` tuple is treated as a state machine.
# ---------------------------------------------------------------------------

def _resolve_state_sprite(kind, subject):
    """Which sprite's ``fsm_state`` a subject-level state path reads or
    forces. State is inherently per-sprite, but the protocol addresses a
    whole subject, so: a lone ``sprite`` subject is unambiguous; a
    ``pool`` or ``family`` subject reports its first live sprite as a
    representative sample (documented judgment call -- see this task's
    report); a ``scene`` subject has no sprite behind it at all (a
    scene-level Behavior may not even be state-machine-shaped in practice,
    but this returns ``None`` either way rather than guessing). ``None``
    when there is no live sprite to report on.
    """
    if kind == "sprite":
        return subject
    if kind == "pool":
        live = getattr(subject, "_live", None)
        return live[0] if live else None
    if kind == "family":
        for member_kind, member in getattr(subject, "_members", ()):
            if member_kind == "sprite":
                return member
            live = getattr(member, "_live", None)
            if live:
                return live[0]
        return None
    return None


def _state_get(behavior, states, kind, subject):
    def get():
        sprite = _resolve_state_sprite(kind, subject)
        if sprite is None:
            return None
        index = getattr(sprite, "fsm_state", 0)
        if 0 <= index < len(states):
            return states[index]
        return index
    return get


def _state_apply(behavior, states, kind, subject):
    def apply(value):
        if value not in states:
            raise ValueError("state must be one of %s; got %r"
                              % (", ".join(states), value))
        sprite = _resolve_state_sprite(kind, subject)
        if sprite is None:
            raise ValueError("no live sprite to force state on")
        current_index = getattr(sprite, "fsm_state", 0)
        # Mimic a natural transition as closely as this stand-in contract
        # allows: run the outgoing state's exit hook (if any), write the
        # byte, clear any pending timed-hold (a stale hold firing right
        # after a forced transition would silently undo it), then run the
        # incoming state's enter hook (if any) -- see this task's report
        # for why, and that this needs reconfirming once T10 lands for
        # real.
        if 0 <= current_index < len(states):
            exit_hook = getattr(behavior, "exit_" + states[current_index], None)
            if exit_hook is not None:
                exit_hook(sprite)
        sprite.fsm_state = states.index(value)
        if hasattr(sprite, "fsm_hold"):
            sprite.fsm_hold = 0
        enter_hook = getattr(behavior, "enter_" + value, None)
        if enter_hook is not None:
            enter_hook(sprite)
        return value
    return apply


def _maybe_add_state_param(entries, registry, path_prefix, behavior, declared,
                            subject_kind, subject_obj):
    """Append a synthetic ``state`` param -- read-only metadata plus a
    registry entry -- when ``behavior`` looks like a state machine and
    does not already declare a real parameter named ``state`` (a real
    declared parameter always wins; this is a fallback, not a shadow)."""
    if "state" in declared:
        return
    states = getattr(behavior, "states", None)
    if not states:
        return
    path = path_prefix + ".state"
    get = _state_get(behavior, states, subject_kind, subject_obj)
    default = getattr(behavior, "initial", states[0])
    registry[path] = _Target(get, _state_apply(behavior, states, subject_kind, subject_obj),
                              _identity_coerce, default)
    try:
        value = get()
    except Exception:
        value = None
    entries.append(_metadata_entry("state", "choice", value, {"options": list(states)}))


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _register_behaviors(registry, subject_path, subject_obj, subject_kind,
                         introspect_fn, declared_params_fn, var_cls,
                         id_to_name, name_to_object):
    entries = []
    behaviors_by_name = getattr(subject_obj, "_behaviors", None) or {}
    for behavior_name in sorted(behaviors_by_name.keys()):
        behavior = behaviors_by_name[behavior_name]
        behavior_path = subject_path + "." + behavior_name
        declared = declared_params_fn(type(behavior))
        params_out = _register_params(registry, behavior_path, behavior, declared,
                                       introspect_fn, var_cls, id_to_name, name_to_object)
        _maybe_add_state_param(params_out, registry, behavior_path, behavior, declared,
                                subject_kind, subject_obj)
        actions_out = []
        for action_name, action in _named_actions(behavior):
            action_path = behavior_path + "." + action_name
            action_declared = declared_params_fn(type(action))
            action_params = _register_params(registry, action_path, action, action_declared,
                                              introspect_fn, var_cls, id_to_name, name_to_object)
            actions_out.append({"name": action_name, "class": type(action).__name__,
                                 "params": action_params})
        entries.append({"name": behavior_name, "class": type(behavior).__name__,
                         "params": params_out, "actions": actions_out})
    return entries


def _build_registry(scene):
    """Walk ``scene`` once, building the ``vs2beh list`` JSON payload and a
    flat ``{path: _Target}`` map together, so the two can never disagree
    about what is addressable. Allocates freely -- this only ever runs
    once per ``vs2beh`` command, never per tick (the acceptance bullet
    this satisfies: "list allocates only when called").
    """
    from vs2.params import declared_params, introspect, Var
    from vs2 import project as vs2_project

    id_to_name, name_to_object = _discover_names(scene)
    registry = {}
    subjects = []

    # -- the scene itself: its own declared variables plus any Behavior
    # attached directly to it (wave spawning and the like). --
    scene_var_names = sorted(scene._vars.keys())
    scene_behaviors = getattr(scene, "_behaviors", None) or {}
    if scene_var_names or scene_behaviors:
        var_entries = _register_scalar_vars(registry, "scene", scene, scene._vars, scene_var_names)
        behavior_entries = _register_behaviors(
            registry, "scene", scene, "scene", introspect, declared_params, Var,
            id_to_name, name_to_object)
        subjects.append({"name": "scene", "kind": "scene",
                          "vars": var_entries, "behaviors": behavior_entries})

    # -- the project: variables only (a Family/Behavior cannot attach to
    # vs2.project -- it lives above the scene stack, not inside one). --
    project_var_names = sorted(vs2_project._vars.keys())
    if project_var_names:
        var_entries = _register_scalar_vars(
            registry, "project", vs2_project, vs2_project._vars, project_var_names)
        subjects.append({"name": "project", "kind": "project", "vars": var_entries})

    # -- every named pool/sprite/family with something to tune. --
    for name in sorted(name_to_object.keys()):
        obj = name_to_object[name]
        kind = _kind_of(obj)
        obj_behaviors = getattr(obj, "_behaviors", None) or {}
        has_vars = kind == "pool" and obj._var_defaults
        if not has_vars and not obj_behaviors:
            continue
        entry = {"name": name, "kind": kind}
        if kind == "pool":
            entry["count"] = obj.capacity
            entry["vars"] = _register_scalar_vars(
                registry, name, obj, obj._var_defaults, obj._var_order)
            if obj._kind_rows:
                # SpritePool.kinds() takes **rows, and MicroPython's **kwargs
                # capture does not preserve call-site order (confirmed
                # directly: def f(**kw): ...; f(zebra=1, apple=2) sees
                # ['apple', 'zebra'], hash order, not call order) -- there is
                # no declaration order to recover here, unlike _var_order
                # (T5's fix for var(), which IS called once per name and can
                # append to a list at each call). So row order is sorted by
                # kind name instead: not "as authored", but deterministic and
                # stable across repeated `list` calls, which is what T12's
                # kinds editor actually needs ("editing a cell never reorders
                # other rows").
                entry["kinds"] = {
                    "fields": list(obj._kind_fields),
                    "rows": [
                        {"name": kind_name, "values": list(obj._kind_rows[kind_name])}
                        for kind_name in sorted(obj._kind_rows.keys())
                    ],
                }
                _register_kind_cells(registry, name, obj)
        elif kind == "family":
            entry["count"] = len(obj)
        entry["behaviors"] = _register_behaviors(
            registry, name, obj, kind, introspect, declared_params, Var,
            id_to_name, name_to_object)
        subjects.append(entry)

    return {"subjects": subjects}, registry


# ---------------------------------------------------------------------------
# "An unknown path returns an error naming the closest valid one."
# ---------------------------------------------------------------------------

def _edit_distance(a, b):
    """Levenshtein distance, iterative two-row DP. Only ever called on an
    already-failed ``set``/``reset`` (never per tick, never on a
    successful command), against a handful to a few dozen candidate
    paths, so plain O(len(a) * len(b)) with no native acceleration is
    fine -- there is no allocation or timing budget to protect here."""
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)
    if len_a == 0:
        return len_b
    if len_b == 0:
        return len_a
    previous = list(range(len_b + 1))
    for i in range(1, len_a + 1):
        current = [i] + [0] * len_b
        char_a = a[i - 1]
        for j in range(1, len_b + 1):
            cost = 0 if char_a == b[j - 1] else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
        previous = current
    return previous[len_b]


def _closest(path, candidates):
    best = None
    best_distance = None
    for candidate in candidates:
        distance = _edit_distance(path, candidate)
        if best_distance is None or distance < best_distance:
            best = candidate
            best_distance = distance
    return best


def _unknown_path_message(path, candidates):
    names = sorted(candidates)
    if not names:
        return "unknown path %r; this scene has nothing tunable" % (path,)
    match = _closest(path, names)
    return "unknown path %r; did you mean %r?" % (path, match)
