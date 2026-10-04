"""The VS2 parameter system: one declaration, four consumers.

A :class:`Parameter` is a **non-data descriptor** — it defines ``__get__``
but never ``__set__`` or ``__delete__``. That is the whole trick: Python's
attribute protocol only gives a class-level descriptor priority over an
instance's own ``__dict__`` when the descriptor is a *data* descriptor. A
non-data descriptor loses that priority, so the moment an instance gets a
plain attribute of the same name, every later read finds it in the
instance's own ``__dict__`` and the descriptor is never consulted again.

:func:`init_params` is what writes that plain attribute. A host class (an
``Action`` or a ``Behavior``, in the modules built on top of this one) calls
it once from its own ``__init__``, passing the keyword arguments the caller
supplied. It walks the class's declared parameters via :func:`declared_params`
(itself a ``dir()`` walk, cached per class), validates the supplied values,
and does one ``setattr`` per parameter — so `self.speed_y` in a game's Step
is an ordinary attribute load, exactly as fast as any other attribute on the
object, with no per-tick descriptor cost.

:class:`Var` is the escape hatch: a parameter value that names a per-sprite
instance variable instead of a literal. ``init_params`` recognises it and
skips range validation (there is no single value to validate yet — it is
resolved per sprite, at build, by the code that owns instance variables).

Nothing here imports from :mod:`vs2` — this module is a standalone leaf so
it can be imported before the rest of the package exists, and the package
imports *it*, never the other way around.
"""


class Var:
    """Marks a parameter value as bound to a per-instance variable.

    ``Moving(speed_y=Var("speed_y"))`` means: don't hoist a literal, read
    the sprite's own ``speed_y`` instance variable instead. Resolving that
    binding — deciding which dispatch tier it puts the owning Action or
    Behavior in — is the build-time job of the modules layered on top of
    this one; this class only carries the name.
    """

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "Var(%r)" % (self.name,)

    def __eq__(self, other):
        return isinstance(other, Var) and other.name == self.name

    def __hash__(self):
        return hash(("vs2.params.Var", self.name))


def _range_text(param):
    if param.min is not None and param.max is not None:
        return "%s..%s" % (param.min, param.max)
    if param.min is not None:
        return ">= %s" % (param.min,)
    if param.max is not None:
        return "<= %s" % (param.max,)
    return "any value"


class Parameter:
    """Base class for every parameter type.

    Holds a default plus the metadata every renderer needs: ``min``, ``max``,
    ``step``, ``label``, ``unit``, ``options``. Subclasses narrow the
    constructor signature to what is actually meaningful for that type (a
    ``Flag`` has no ``min``), but every instance carries the full metadata
    set so introspection never has to special-case a type.
    """

    #: Short lowercase name used in introspection and the wire protocol
    #: (``vs2beh list``). Overridden by every concrete subclass.
    type_name = "parameter"

    def __init__(self, default=None, min=None, max=None, step=None,
                 label=None, unit=None, options=None):
        self.default = default
        self.min = min
        self.max = max
        self.step = step
        self.label = label
        self.unit = unit
        self.options = options
        #: Filled in by ``__set_name__`` when the owning class is built.
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner=None):
        # Accessed on the class itself (owner.__dict__ lookups, dir()-based
        # introspection): hand back the descriptor so callers can read its
        # metadata. Accessed on an instance that never had init_params()
        # run on it (or that never overrode this particular name): fall
        # back to the declared default rather than raising. The normal
        # path — after init_params() has run — never reaches this at all,
        # because the instance's own __dict__ already shadows it.
        if instance is None:
            return self
        return self.default

    def metadata(self):
        """The renderer-facing metadata dict: ``min``, ``max``, ``step``,
        ``label``, ``unit``, ``options``. Present on every parameter type,
        ``None`` where not applicable."""
        return {
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "label": self.label,
            "unit": self.unit,
            "options": self.options,
        }

    def validate(self, owner_name, name, value):
        """Check ``value`` against this parameter's constraints, returning
        it unchanged (or coerced, for :class:`Flag`) on success. Raises
        ``ValueError`` naming the offending path and the valid range.

        Never called for a :class:`Var`-bound value — ``init_params`` skips
        validation for those, since there is no literal to check yet.
        """
        if self.min is not None and value < self.min:
            raise ValueError("%s.%s must be in %s" % (owner_name, name, _range_text(self)))
        if self.max is not None and value > self.max:
            raise ValueError("%s.%s must be in %s" % (owner_name, name, _range_text(self)))
        return value


class Number(Parameter):
    """A plain numeric parameter: slider + entry in the panel, a clamped
    number field in Blockly."""

    type_name = "number"

    def __init__(self, default=0, min=None, max=None, step=None,
                 label=None, unit=None):
        super().__init__(default, min=min, max=max, step=step,
                          label=label, unit=unit)


class Angle(Number):
    """A numeric parameter that is angular rather than linear: a dial
    marked 0 / 64 / 128 / 192 in the panel instead of a plain slider.

    X is angular everywhere in VS2 ("the bottom of the disc" is not
    recoverable from the number 0), which is why this earns its own type
    even though its validation is identical to :class:`Number`.
    """

    type_name = "angle"


class Flag(Parameter):
    """A boolean parameter: a checkbox in the panel and in Blockly."""

    type_name = "flag"

    def __init__(self, default=False, label=None):
        super().__init__(default, label=label)

    def validate(self, owner_name, name, value):
        return bool(value)


class Choice(Parameter):
    """An enumerated parameter: a dropdown over ``options`` in both the
    panel and Blockly."""

    type_name = "choice"

    def __init__(self, default=None, options=(), label=None, unit=None):
        super().__init__(default, options=tuple(options), label=label, unit=unit)

    def validate(self, owner_name, name, value):
        if value not in self.options:
            valid = ", ".join(str(option) for option in self.options)
            raise ValueError("%s.%s must be one of %s; got %r" % (
                owner_name, name, valid, value))
        return value


class Frames(Parameter):
    """A frame or frame sequence from the subject's own image strip: a
    strip of the image's real frames in the panel, an image-strip field in
    Blockly. Resolving it against a real strip happens at build, in the
    module that owns the asset pack — this class only carries the value."""

    type_name = "frames"

    def __init__(self, default=0, label=None, unit=None):
        super().__init__(default, label=label, unit=unit)


class Sound(Parameter):
    """A sound name, or a tuple of names picked from at random: a dropdown
    with a preview button in the panel, populated from ``sounds/``."""

    type_name = "sound"

    def __init__(self, default=None, label=None):
        super().__init__(default, label=label)

    def validate(self, owner_name, name, value):
        if value is not None and not isinstance(value, str) \
                and not isinstance(value, (tuple, list)):
            raise TypeError(
                "%s.%s must be a sound name, a tuple of names, or None; got %r" % (
                    owner_name, name, value))
        return value


class Image(Parameter):
    """An image name from the asset pack: a dropdown in the panel."""

    type_name = "image"

    def __init__(self, default=None, label=None):
        super().__init__(default, label=label)

    def validate(self, owner_name, name, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("%s.%s must be an image name or None; got %r" % (
                owner_name, name, value))
        return value


class PoolRef(Parameter):
    """A reference to a pool, sprite or family, resolved at build against
    the live scene: a dropdown over pools and families in the panel.

    This module has no notion of what a pool or family actually is —
    that lives in ``vs2/__init__.py``, which imports *this* module, never
    the reverse — so a ``PoolRef`` value is carried through unvalidated.
    """

    type_name = "pool"

    def __init__(self, default=None, label=None):
        super().__init__(default, label=label)


class Points(Parameter):
    """A path or region: a table with an overlay editor on the LED preview
    in the panel, opened from the block in Blockly."""

    type_name = "points"

    def __init__(self, default=(), label=None, unit=None):
        super().__init__(default, label=label, unit=unit)


class Callback(Parameter):
    """Names an event hat in the workspace (a generated project has no
    hand-written method to point at). On a detached file this renders as
    the bound method it was generated into — the same parameter, read from
    the other side of ``Detach``. Read-only in the panel; a dropdown over
    the workspace's event hats in Blockly."""

    type_name = "callback"

    def __init__(self, default=None, label=None):
        super().__init__(default, label=label)

    def validate(self, owner_name, name, value):
        if value is not None and not callable(value):
            raise TypeError("%s.%s must be callable or None; got %r" % (
                owner_name, name, value))
        return value


def declared_params(cls):
    """The ``{name: Parameter}`` declared on ``cls`` or any ancestor.

    Walks ``dir(cls)`` once — the only place this module allocates on
    behalf of a caller — and caches the result **on the class itself**, so
    every later call, and every instance of that exact class, reuses the
    same dict at no cost. The cache is stored under a class-private name
    and looked up via ``cls.__dict__`` rather than ``getattr``/``hasattr``,
    so a subclass that adds its own parameters computes and caches its own
    dict rather than silently inheriting its parent's.

    ``dir()`` order is not relied on for anything observable: the result is
    an ordinary dict, and every consumer in this module sorts explicitly
    when order matters (error messages, :func:`introspect`). CPython's
    ``dir()`` happens to sort already; MicroPython's does not — this is
    exactly the gap the sorting closes.
    """
    cached = cls.__dict__.get("_vs2_declared_params")
    if cached is not None:
        return cached
    found = {}
    for name in dir(cls):
        if name.startswith("_"):
            continue
        try:
            value = getattr(cls, name)
        except AttributeError:
            continue
        if isinstance(value, Parameter):
            found[name] = value
    cls._vs2_declared_params = found
    return found


def init_params(instance, kwargs):
    """Bind ``kwargs`` onto ``instance`` against its class's declared
    parameters, and write every declared parameter as a plain instance
    attribute — the step that shadows the descriptor for good.

    Called once, at construction (inside ``build()`` for the game code that
    ends up calling it), from the host class's own ``__init__``:

        class Action:
            def __init__(self, **kwargs):
                params.init_params(self, kwargs)

    An unknown keyword raises ``TypeError`` naming the offender and the
    full valid set. An out-of-range value raises ``ValueError`` naming the
    offending path and the valid range (or, for a :class:`Choice`, the
    valid options). A value that is a :class:`Var` is bound as-is, with no
    range check — there is no single literal to check.
    """
    cls = type(instance)
    declared = declared_params(cls)
    unknown = sorted(name for name in kwargs if name not in declared)
    if unknown:
        valid = ", ".join(sorted(declared.keys()))
        raise TypeError("%s has no parameter %r; valid: %s" % (
            cls.__name__, unknown[0], valid))
    for name, param in declared.items():
        if name in kwargs:
            value = kwargs[name]
            if not isinstance(value, Var):
                value = param.validate(cls.__name__, name, value)
        else:
            value = param.default
        setattr(instance, name, value)


def introspect(cls):
    """Yield ``(name, type_name, default, metadata)`` for every parameter
    declared on ``cls``, sorted by name.

    This is the one function the property panel, the ``vs2beh`` wire
    protocol and the generated reference docs all consume — "one
    declaration, four consumers" (the fourth being this function's own
    caller, the Blockly field generator).
    """
    declared = declared_params(cls)
    for name in sorted(declared):
        param = declared[name]
        yield (name, param.type_name, param.default, param.metadata())


class Parameterized:
    """Optional convenience base: wires :func:`init_params` into
    ``__init__`` for a host class whose constructor is exactly "accept
    keyword parameters, nothing else".

    Not every host class fits that shape — a ``Behavior`` subclass may need
    positional setup before its parameters, for instance — so this is a
    convenience, not a requirement. Any class may call ``init_params``
    directly from a custom ``__init__`` instead of inheriting this.
    """

    def __init__(self, **kwargs):
        init_params(self, kwargs)
