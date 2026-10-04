"""Renders one model "value" into Python source, and collects the imports
a model needs before any source is emitted.

Four value forms, matching :mod:`model`'s ``_check_value``:

- a literal (``None``/``bool``/``int``/``float``/``str``) -> ``repr()``.
- a list -> a Python tuple literal, recursively rendered (JSON has no
  tuple type; the catalog's own params -- ``PathFollowing.points``,
  ``Animated.frames`` -- are documented and typed as tuples).
- ``{"var": "name"}`` -> ``Var("name")``, the proposal's per-sprite
  binding marker (needs ``from vs2.params import Var``).
- ``{"ref": "attr"}`` -> ``self.attr``, a cross-reference to a pool,
  sprite or family declared earlier in the same model (e.g.
  ``hits=self.enemies``).
- ``{"handler": "name"}`` -> ``self.name``, an event-hook reference the
  generated file deliberately does not itself define -- see this
  package's docstring and ``regenerate.ensure_companion_stub``.
- ``{"expr": "raw source"}`` -> emitted verbatim, unvalidated. An escape
  hatch for a symbolic reference a literal can't spell (``vs2.display.
  width``, say) -- used sparingly; it is the one place this format stops
  being purely declarative, so a generator invariant test never relies on
  it and neither does the vixeous port.
"""


def render_value(value, imports):
    """Return the Python source for ``value``, adding to ``imports`` (a
    set) any name this value needs imported (currently only ``"Var"``)."""
    if isinstance(value, dict):
        (key, inner), = value.items()
        if key == "var":
            imports.add("Var")
            return "Var(%r)" % (inner,)
        if key == "ref":
            return "self.%s" % (inner,)
        if key == "handler":
            return "self.%s" % (inner,)
        if key == "expr":
            return inner
        raise ValueError("unknown value tag %r" % (key,))  # pragma: no cover
    if isinstance(value, (list, tuple)):
        rendered = [render_value(item, imports) for item in value]
        if len(rendered) == 1:
            return "(%s,)" % (rendered[0],)
        return "(%s)" % (", ".join(rendered),)
    return repr(value)


def collect_value_imports(value, imports):
    """Walk ``value`` purely for its import needs, without producing
    source -- used by the generator's import pre-pass so ``from
    vs2.params import Var`` only appears when the model actually uses a
    ``Var`` binding somewhere."""
    render_value(value, imports)
