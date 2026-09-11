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


# =============================================================================
# StateMachine (T10) -- a self-contained block, deliberately kept separate
# from Behavior/Projectile above (T8's own section): T9a and T9b add catalog
# entries to this same file in the same wave, so this section owns nothing
# above this banner and nothing below it should need to change to add more
# catalog entries elsewhere in the file.
#
# Spec: docs/vs2-behaviors-proposal.md, "## State machines". Work-breakdown
# card: docs/vs2-behaviors-implementation.md T10.
# =============================================================================

from . import StateConflictError  # noqa: E402


class StateMachine(Behavior):
    """A :class:`Behavior` whose per-sprite logic is a named state machine::

        class Enemy(StateMachine):
            speed_x = Number(1.25, min=0, max=8, step=0.25)
            speed_y = Number(0.6, min=0, max=8, step=0.25)

            states  = ("descending", "orbiting", "chasing", "exploding")
            initial = "descending"

            def descending(self, sprite):
                sprite.dy -= self.speed_y
                if sprite.y <= GROUND:
                    return "exploding"

            def enter_orbiting(self, sprite):
                self.hold(sprite, 128, then="descending")

            def orbiting(self, sprite):
                sprite.dx += self.speed_x * sprite.facing

    **States are named** (:attr:`states`), and the name is what the panel,
    the live-tune protocol and a traceback report -- :meth:`state_name`
    is the byte-to-name direction of that mapping, for exactly those
    consumers, never called by the tick itself. **A per-state method takes
    the sprite and returns the next state's name, or ``None`` to stay** --
    ``descending``/``orbiting``/``chasing``/``exploding`` above, one per
    entry in :attr:`states`. **``enter_<state>``/``exit_<state>`` are
    optional hooks**, matched by name (``enter_orbiting`` above; there is
    no ``exit_descending``, and that is fine -- exit hooks are optional and
    skipped when absent). **:meth:`hold` is the timed-transition
    primitive**: "a temporary status -- invulnerable, powered up, reversed,
    slowed -- is a state with a hold on it."

    **Dispatch is one primed byte plus a tuple of bound methods indexed by
    it.** :meth:`attached` resolves :attr:`states` (a tuple of name
    strings) into ``self._state_methods`` (a parallel tuple of *bound
    methods*, via ``getattr(self, name)``) exactly once, at build time,
    where allocating is allowed. Every tick after that, dispatch is
    ``self._state_methods[sprite.fsm_state](sprite)`` -- one integer
    index, one call, no string comparison, no lookup of any kind. The
    initial state's index (:attr:`initial`, resolved at the same time) is
    what primes ``sprite.fsm_state`` -- not necessarily ``0``.

    **``fsm_state``/``fsm_hold``/``fsm_then`` are the three reserved names
    the proposal sets aside for exactly this** (see
    ``vs2._RESERVED_VAR_NAMES``) -- one byte for the current state index,
    a countdown, and the state to enter when it reaches zero. They are
    *not* declared via :attr:`Behavior.state` the way a subclass's own
    per-sprite fields are: ``vs2._prime_pool_state``/``_prime_sprite_state``/
    ``_prime_scene_state`` reject **every** name in ``_RESERVED_VAR_NAMES``
    unconditionally, including from the one Behavior the framework reserved
    them for -- there is no carve-out for "the declaring class is the
    canonical owner" (confirmed by tracing ``vs2/__init__.py`` directly, and
    by ``test_vs2_behaviors.py``'s own
    ``test_state_conflict_reserved_name``, which asserts exactly this
    rejection). Putting them in ``state = (...)`` here would make every
    single attach of a :class:`StateMachine` raise ``StateConflictError``
    immediately. So :meth:`attached` primes them itself, by hand, using the
    same zero-allocation ``setattr``-on-every-sprite walk
    ``_prime_pool_state``/``_prime_sprite_state`` already use internally
    (free sprites included, for a pool) -- and separately guards against
    *two* StateMachines sharing one subject (which would silently corrupt
    each other's fsm_state) via its own ``_fsm_owner`` marker, the same
    protection the framework's own owner-tracking gives every other
    Behavior-declared state name.

    **Subject kinds.** :class:`StateMachine` defines both :meth:`step`
    (for a pool subject) and :meth:`step_one` (for a lone-sprite subject),
    which is also what lets it attach to a :class:`~vs2.Family` (whose
    dispatch needs either, per member). It does not define ``step_scene``:
    a scene has no single sprite's worth of ``fsm_state`` to carry, so a
    scene-subject state machine is out of scope for this class (the same
    "a subclass defines only the form(s) its declared subject needs" rule
    the proposal states for the catalog generally) -- attaching one to a
    ``Scene`` is therefore correctly rejected as a build-time
    ``TypeError``, exactly like any other kind mismatch.

    ``Scene._run_behaviors()``'s ``"pool"`` branch calls **only**
    ``behavior.step(pool)`` for a pool-kind attachment -- it never calls
    ``step_one`` per member of a pool (traced directly in
    ``vs2/__init__.py``; there is no framework-level per-sprite fan-out for
    a pool subject). A state machine is normally attached to a *pool* of
    interchangeable sprites (one ``Enemy`` instance's parameters shared by
    many enemies, each carrying its own ``fsm_state``), so
    :meth:`StateMachine.step` itself does the indexed, downward,
    despawn-safe per-sprite loop (the same shape ``Projectile.step`` uses)
    and dispatches each sprite through the private ``_dispatch_one``
    helper -- rather than assuming the framework will call ``step_one`` per
    pool member, which it does not.
    """

    #: Every state name, in declaration order -- also the byte-to-name
    #: direction of the mapping :meth:`attached` resolves (``self.states[i]``
    #: is exactly what :meth:`state_name` returns for a sprite whose
    #: ``fsm_state`` is ``i``). A subclass overrides this; the base class
    #: declares no states, so instantiating one directly (rather than
    #: subclassing) fails loudly at :meth:`attached` time.
    states = ()

    #: Name of the state a newly-primed sprite starts in. Defaults to
    #: ``states[0]`` when left unset, resolved once at :meth:`attached`
    #: time -- not necessarily index ``0`` in general, since a subclass may
    #: set this to any of its own :attr:`states`.
    initial = None

    def attached(self, subject):
        """Resolve :attr:`states` into indexed dispatch tables (allocating
        here is fine -- this runs once, at build time) and prime
        ``fsm_state``/``fsm_hold``/``fsm_then`` on every sprite of
        ``subject``. See the class docstring for why priming is done by
        hand here rather than via :attr:`Behavior.state`.

        A subclass overriding this (to build its own Actions, the same way
        :meth:`Projectile.attached` does) must call
        ``StateMachine.attached(self, subject)`` too, or nothing above will
        run.
        """
        states = self.states
        if not states:
            raise ValueError(
                "%s declares no states; set states = (...)"
                % (type(self).__name__,))
        # "One primed byte plus a tuple of bound methods indexed by it"
        # (the proposal's own phrase): resolved once, here, so the tick
        # does exactly one tuple index and one call -- no string
        # comparison, no name lookup of any kind. Every declared state
        # needs its own method (even a no-op ``pass``) -- a state handled
        # entirely by an enter_<state> hook (a terminal state that
        # despawns on entry, say) still needs one purely so this
        # resolves; missing one is a build-time error naming the offender
        # and the class, not a bare AttributeError at first dispatch.
        methods = []
        for name in states:
            method = getattr(self, name, None)
            if method is None:
                raise TypeError(
                    "%s declares state %r but defines no %s() method"
                    % (type(self).__name__, name, name))
            methods.append(method)
        self._state_methods = tuple(methods)
        self._enter_hooks = tuple(
            getattr(self, "enter_" + name, None) for name in states)
        self._exit_hooks = tuple(
            getattr(self, "exit_" + name, None) for name in states)
        # The other direction (name -> index) is what a per-state method's
        # returned name, and hold()'s then=, both need -- resolved once
        # into a dict here rather than a linear .index() scan repeated at
        # every transition.
        self._name_to_index = dict(zip(states, range(len(states))))
        initial = self.initial
        if initial is None:
            initial = states[0]
        if initial not in self._name_to_index:
            raise ValueError(
                "%s.initial %r is not one of its declared states: %s"
                % (type(self).__name__, initial, ", ".join(states)))
        self._initial_index = self._name_to_index[initial]

        if hasattr(subject, "_members"):       # Family
            members = subject._members
            member_index = 0
            member_count = len(members)
            while member_index < member_count:
                member_kind, member = members[member_index]
                if member_kind == "pool":
                    self._prime_pool(member)
                else:
                    self._prime_sprite(member)
                member_index += 1
        elif hasattr(subject, "_live"):         # SpritePool
            self._prime_pool(subject)
        else:                                    # lone Sprite
            self._prime_sprite(subject)

    def _prime_pool(self, pool):
        """Prime every sprite of ``pool`` -- free ones included, the same
        idiom ``vs2._prime_pool_state`` uses -- and record ownership on
        the pool itself so a second ``StateMachine`` on the same pool is
        caught instead of silently sharing (and corrupting) one set of
        fsm_* fields."""
        owner = getattr(pool, "_fsm_owner", None)
        if owner is not None:
            raise StateConflictError(
                "state machine fields (fsm_state/fsm_hold/fsm_then) on "
                "this pool are already owned by %r; %r cannot attach a "
                "second StateMachine to the same subject" % (owner, self))
        pool._fsm_owner = self
        initial = self._initial_index
        enter_hook = self._enter_hooks[initial]
        for sprite in pool._free:
            sprite.fsm_state = initial
            sprite.fsm_hold = 0
            sprite.fsm_then = initial
            if enter_hook is not None:
                enter_hook(sprite)
        for sprite in pool._live:
            sprite.fsm_state = initial
            sprite.fsm_hold = 0
            sprite.fsm_then = initial
            if enter_hook is not None:
                enter_hook(sprite)

    def _prime_sprite(self, sprite):
        """Prime one standalone sprite. See :meth:`_prime_pool`."""
        owner = getattr(sprite, "_fsm_owner", None)
        if owner is not None:
            raise StateConflictError(
                "state machine fields (fsm_state/fsm_hold/fsm_then) on "
                "this sprite are already owned by %r; %r cannot attach a "
                "second StateMachine to the same subject" % (owner, self))
        sprite._fsm_owner = self
        initial = self._initial_index
        sprite.fsm_state = initial
        sprite.fsm_hold = 0
        sprite.fsm_then = initial
        enter_hook = self._enter_hooks[initial]
        if enter_hook is not None:
            enter_hook(sprite)

    def hold(self, sprite, ticks, then):
        """Schedule a timed transition: ``ticks`` Steps from now, force
        ``sprite`` into state ``then`` -- regardless of what its current
        state's per-tick method returns meanwhile, which keeps running
        normally every tick until the hold expires.

        Call this from an ``enter_<state>`` hook to make that state
        self-expiring, exactly as the class docstring's ``orbiting``
        example does. Resolving ``then`` is one dict lookup, not called
        every tick (only when something enters a self-expiring state).

        Raises:
            ValueError: If ``then`` does not name one of :attr:`states`.
        """
        try:
            then_index = self._name_to_index[then]
        except KeyError:
            raise ValueError(
                "%s.hold(): %r is not one of its declared states: %s"
                % (type(self).__name__, then, ", ".join(self.states)))
        sprite.fsm_hold = ticks
        sprite.fsm_then = then_index

    def state_name(self, sprite):
        """``sprite``'s current state, by name -- the byte-to-name
        direction of the mapping :meth:`attached` resolved, for the panel,
        the live-tune protocol (T11) and a traceback. An O(1) tuple index,
        not a comparison, and never called by the tick itself."""
        return self.states[sprite.fsm_state]

    def force_state(self, sprite, name):
        """Force ``sprite`` straight into state ``name``, firing the
        outgoing state's ``exit_<...>`` and the incoming one's
        ``enter_<...>`` exactly as a normal transition would. For a
        debugger, a live-tune "set" command (T11), or a test -- never
        called by the tick itself.

        Raises:
            ValueError: If ``name`` does not name one of :attr:`states`.
        """
        try:
            index = self._name_to_index[name]
        except KeyError:
            raise ValueError(
                "%s.force_state(): %r is not one of its declared states: %s"
                % (type(self).__name__, name, ", ".join(self.states)))
        self._enter(sprite, index)

    def _dispatch_one(self, sprite):
        """The whole per-sprite tick: one index, one call, then the hold
        countdown -- no string comparison anywhere in this method.

        Deliberately calls out to :meth:`_unknown_state_error` rather than
        building that error's message inline. Measured directly on the
        MicroPython unix port: a multi-argument ``%``-formatted string
        expression (``type(self).__name__``, an indexed lookup, a
        ``", ".join(...)`` call) sitting in an *unreached* branch of this
        method -- reached only when a step method returns a typo'd state
        name, never in steady state -- still cost this whole method ~7-8x
        on every call, not just the calls that take that branch (60
        sprites x 1000 ticks: ~90ms with the message-building code
        elsewhere vs. ~900ms with the identical expression inlined here,
        see this task's report). Isolating the same construction into its
        own rarely-called method removes that cost from every steady-state
        tick entirely, whatever the exact compiler mechanism is -- this
        method's own body stays trivial to compile either way, which
        the try/except -> ``dict.get()`` change alone (see below) did not
        fully achieve on its own.

        Also **no try/except anywhere in this method**: a ``try/except``
        nested inside an ``if`` that is never taken measured at a similar
        (~9x) cost, for the same reason -- see :meth:`hold`/
        :meth:`force_state` (called rarely, never every tick) for where
        plain try/except is still fine to use.
        """
        index = sprite.fsm_state
        next_name = self._state_methods[index](sprite)
        if next_name is not None:
            next_index = self._name_to_index.get(next_name, -1)
            if next_index < 0:
                self._unknown_state_error(index, next_name)
            self._enter(sprite, next_index)
            return
        hold = sprite.fsm_hold
        if hold > 0:
            hold -= 1
            sprite.fsm_hold = hold
            if hold == 0:
                self._enter(sprite, sprite.fsm_then)

    def _unknown_state_error(self, index, next_name):
        """Raise the "unknown state name" error for :meth:`_dispatch_one`
        -- split out into its own method (called only on this rare,
        game-bug path, never in steady state) so the expensive-to-compile
        message expression cannot tax :meth:`_dispatch_one`'s own
        per-tick cost. See :meth:`_dispatch_one`'s docstring for why."""
        raise ValueError(
            "%s's %r step returned unknown state %r; valid: %s"
            % (type(self).__name__, self.states[index], next_name,
               ", ".join(self.states)))

    def _enter(self, sprite, new_index):
        """Move ``sprite`` from its current state to ``new_index``,
        firing the outgoing ``exit_<...>`` (if declared) then the
        incoming ``enter_<...>`` (if declared), and clearing any pending
        hold -- a fresh state starts without one unless its own
        ``enter_<...>`` schedules a new one."""
        old_index = sprite.fsm_state
        if new_index == old_index:
            sprite.fsm_hold = 0
            return
        exit_hook = self._exit_hooks[old_index]
        if exit_hook is not None:
            exit_hook(sprite)
        sprite.fsm_state = new_index
        sprite.fsm_hold = 0
        sprite.fsm_then = new_index
        enter_hook = self._enter_hooks[new_index]
        if enter_hook is not None:
            enter_hook(sprite)

    def step(self, pool):
        """Pool-subject dispatch (see the class docstring's "Subject
        kinds" paragraph for why this loop lives here rather than relying
        on a per-member ``step_one`` the framework does not call). Indexed
        and downward over ``pool._live`` -- despawn-safe, zero-allocation,
        the same shape :meth:`Projectile.step` uses -- because a state's
        own step method (or an ``enter_<...>``/``exit_<...>`` hook it
        triggers) may legitimately despawn the sprite it was just called
        with (a terminal "gone" state's ``enter_gone`` doing exactly
        that)."""
        live = pool._live
        index = len(live) - 1
        while index >= 0:
            self._dispatch_one(live[index])
            index -= 1

    def step_one(self, sprite):
        """Lone-sprite-subject dispatch: a :class:`StateMachine` attached
        directly to a single :class:`~vs2.Sprite` (a boss, a single
        scripted actor) rather than a pool."""
        self._dispatch_one(sprite)
