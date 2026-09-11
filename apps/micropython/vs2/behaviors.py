"""VS2 Behaviors: the ``Behavior`` base class, and ``Projectile`` as its
worked example.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## Behaviors`` and ``## The
Step``. Work-breakdown card: ``docs/vs2-behaviors-implementation.md`` T8.

A :class:`Behavior` is what :meth:`vs2.Sprite.behave`,
:meth:`vs2.SpritePool.behave`, :meth:`vs2.Family.behave` and
:meth:`vs2.Scene.behave` attach. The dispatch mechanism that actually calls
one every Step already lives in ``vs2/__init__.py`` -- :func:`_attach_behavior`
and :meth:`vs2.Scene._run_behaviors`, built by an earlier task duck-typed
against ``getattr(behavior, "step"/"step_one"/"step_scene", None)`` with no
``Behavior`` base class in sight. This module is what actually implements
that shape (:class:`Behavior` is not consulted by dispatch as a type check
-- it just happens to be the base every real Behavior inherits, and
``vs2/__init__.py``'s own validation reads it the same duck-typed way).

**Zero cost for a game that never imports this.** ``vs2/__init__.py`` never
imports this module -- a game that only uses sprites, pools and Actions
never pays to load ``Behavior``, let alone a full catalog. Import
explicitly: ``from vs2.behaviors import Behavior, Projectile``.

**Subject kinds and their step method** (see the proposal's ``###
Subjects``): a :class:`~vs2.SpritePool` subject calls :meth:`Behavior.step`,
a lone :class:`~vs2.Sprite` calls :meth:`Behavior.step_one`, a
:class:`~vs2.Family` dispatches each member to whichever of the two fits its
own kind, and the :class:`~vs2.Scene` itself calls
:meth:`Behavior.step_scene`. A subclass defines only the form(s) its
intended subject needs -- attaching it to a subject whose kind needs a form
it does not define is a build-time ``TypeError`` (see
``vs2._behavior_kind_mismatch``).
"""

from . import actions
from . import params
from .params import Angle, Number, PoolRef


class Behavior:
    """Base class for every Behavior.

    Subclasses declare their tunable parameters as class-level
    :class:`~vs2.params.Parameter` attributes -- the same non-data-
    descriptor system :class:`~vs2.actions.Action` uses -- and override
    :meth:`attached` to compose the Actions that carry out the uniform
    part of their work, and one of :meth:`step`/:meth:`step_one`/
    :meth:`step_scene` to carry the per-sprite (or per-scene) decisions.

    This does **not** inherit :class:`vs2.params.Parameterized`, even
    though that mixin's whole body is ``def __init__(self, **kwargs):
    init_params(self, kwargs)``: a ``Behavior`` needs its own bookkeeping
    (:attr:`_actions`) set up around that call, which a subclass overriding
    an inherited ``__init__`` would have to reach past
    ``super().__init__()`` for anyway. Calling
    :func:`~vs2.params.init_params` directly is the same amount of code
    with one less base class to explain.
    """

    #: Per-sprite field names this Behavior needs on every sprite of its
    #: subject, primed to ``0`` at attach time -- free sprites included --
    #: by ``vs2._attach_behavior`` (see the proposal's ``### Per-instance
    #: state``). A plain tuple, not a :class:`~vs2.params.Parameter`, so it
    #: is invisible to :func:`~vs2.params.declared_params`. Empty by
    #: default: a Behavior that declares none costs nothing extra at
    #: attach time and reads no framework state at all.
    state = ()

    def __init__(self, **kwargs):
        #: Every Action this Behavior has registered via :meth:`action`,
        #: in registration order -- what :attr:`actions` reads back for
        #: introspection (the property panel, a future block editor).
        #: Actions are not individually named: the proposal's ``###
        #: Attaching`` only names *Behaviors* (the path a control protocol
        #: or panel addresses a parameter by, e.g.
        #: ``enemies.patrolling.amplitude``) -- a registered Action is
        #: addressed through the plain instance attribute the subclass
        #: assigns it to (``self.move``, ``self.hit``, ...), exactly like
        #: any other Behavior-owned parameter.
        self._actions = []
        params.init_params(self, kwargs)

    def action(self, instance):
        """Register ``instance`` (an :class:`~vs2.actions.Action`) so the
        panel and a future block editor can find every Action this
        Behavior composed, and so the caller gets the same object back for
        reuse across ticks::

            self.move = self.action(Move(speed_x=self.speed_x))

        Call this only from :meth:`attached` -- it is bookkeeping, not a
        per-tick operation, and calling it from :meth:`step` would grow
        :attr:`_actions` forever.

        Returns:
            The same ``instance``, unchanged, so assignment and
            registration is one line.

        Raises:
            TypeError: If ``instance`` is not an
                :class:`~vs2.actions.Action`.
        """
        if not isinstance(instance, actions.Action):
            raise TypeError(
                "Behavior.action() expects an Action instance; got %r"
                % (instance,))
        self._actions.append(instance)
        return instance

    @property
    def actions(self):
        """Every Action this Behavior has registered via :meth:`action`,
        in registration order, as a plain tuple."""
        return tuple(self._actions)

    def attached(self, subject):
        """Called once, at build time, right after this Behavior is fully
        attached to ``subject`` (see ``vs2._attach_behavior``) -- with
        every Behavior attached earlier on the same subject already fully
        registered, so this may look one up via
        ``subject.behavior(OtherClass)`` and cache a direct reference (the
        proposal's ``Cross-behavior wiring``).

        This is where composition happens, and it may allocate -- it runs
        once per attachment, never again. Override it to build the
        Actions this Behavior needs via :meth:`action`, and to resolve any
        other subject this Behavior's own parameters reference. The base
        implementation does nothing, so a Behavior with no build-time
        setup (state-only, or one implemented entirely as a per-sprite
        decision with literal parameters) does not need to override this
        at all.
        """


class Projectile(Behavior):
    """Travels at a constant angular/radial velocity, expires past
    :attr:`range`, and retires the first sprite in :attr:`hits` it
    overlaps -- the proposal's worked example (``## Behaviors``), in the
    exact hybrid shape ``### What the dispatch shape costs`` measures:
    everything uniform (:class:`~vs2.actions.Move`) hoisted into one
    column-wise ``action.run(sprites)`` call, with the per-sprite loop
    carrying only the two decisions (expired? hit?) that must run one
    sprite at a time.

    **Trimmed from the spec's full listing.** The proposal's version also
    takes a ``damage`` parameter and, on a hit, runs a ``Spawn`` (an
    explosion pool) and a ``PlaySound`` (an impact sound) Action before
    despawning both sprites, then calls a ``hurt(other, self.damage)``
    the spec never defines as a vs2 primitive anywhere in the
    implementation plan -- it reads as the *game's* own damage function,
    not framework surface, the same way a real game would write its own
    ``Damageable`` Behavior rather than get one from this module. ``Spawn``
    and ``PlaySound`` are catalog Actions: T4 (this framework's Wave 3
    Action task) shipped only ``Move``/``MoveTo``/``Animate``/``Collide``,
    and the catalog itself is T9's job (Wave 5), not this module's. So
    this class uses only what exists today -- ``Move`` and ``Collide`` --
    and despawns whatever it hits outright instead of routing through a
    damage system that is not built yet. Restoring the fuller behaviour
    once T9 lands ``Spawn``/``PlaySound`` (and a game defines its own hit
    handling) is a few more lines in :meth:`attached` and :meth:`step`,
    not a redesign: the hybrid shape -- one hoisted ``Move``, one
    per-sprite loop carrying only decisions -- is unchanged either way.
    """

    speed_x = Angle(0, min=-32, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(8, min=-32, max=32, step=0.25,
                      label="Radial speed", unit="led/tick")
    range = Number(180, min=1, max=255, step=1,
                    label="Range", unit="led")
    hits = PoolRef(None, label="Hits what")

    #: Per-sprite distance flown so far, compared against :attr:`range`
    #: every tick. Primed to 0 on every sprite of this Behavior's subject
    #: (free ones included) when it is attached -- see
    #: ``vs2._attach_behavior``'s state-priming step.
    state = ("shot_flown",)

    def attached(self, subject):
        self.move = self.action(
            actions.Move(speed_x=self.speed_x, speed_y=self.speed_y))
        self.hit = self.action(actions.Collide(self.hits))

    def step(self, sprites):
        self.move.run(sprites)                  # uniform: hoisted, column-wise
        limit = self.range
        live = sprites._live                    # per-sprite: decisions only
        index = len(live) - 1
        while index >= 0:                       # downward: despawn-safe
            sprite = live[index]
            sprite.shot_flown += self.speed_y
            if sprite.shot_flown > limit:
                sprite.despawn()
            else:
                other = self.hit.run_one(sprite)
                if other is not None:
                    other.despawn()
                    sprite.despawn()
            index -= 1
