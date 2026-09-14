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
# --- Attributes ---
#
# Wave 5, T9a (docs/vs2-behaviors-implementation.md). Spec:
# docs/vs2-behaviors-proposal.md, "## The catalog", "### Attributes -- built
# in, tiny, attached from the panel, never forked".
#
# Eight of the spec's eleven attributes ship here: Transient, Animated,
# DespawnBeyond, Recycling, Lifetime, Blinking, Pinned, Shaking.
#
# **Carried, Flashing and Cycling are deliberately not built.** The proposal
# says outright that all eleven ship "except Carried, Flashing and Cycling,
# which wait on named palette colours" -- a ``vs2.display.color(name, ...)``/
# ``__images__.yaml``-declared-palette mechanism described in the proposal's
# own "## Named palette colours" section. Nothing in
# ``docs/vs2-behaviors-implementation.md`` builds that mechanism -- not this
# task, not any other -- so it is a genuine gap in the plan, not a corner
# this task cut. Building it here would mean inventing renderer/panel-facing
# infrastructure no task owns, which is exactly what this task's brief warns
# against. Flagged for the plan's authors; see this task's report.
#
# **None of the eight below accepts a Var-bound parameter.** Unlike the
# Movements tier (where a per-sprite offset is an obvious, named use case),
# the proposal's own Attributes listing gives no example of per-sprite
# variation on any of these eight -- every parameter here is a plain
# literal, hoisted once per Behavior instance. A future task can add Var
# support if a real game needs it; this keeps the first release the
# "tiny, attached from the panel" shape the spec asks for. Where per-sprite
# variation is wanted today, attach the same class twice (with different
# literal parameters and an explicit ``name=``) to two different pools.
#
# Imported here rather than folded into the top-of-file import block so two
# independent additions to this file (T9a here, T9b building "### Movements"
# concurrently in the same module) touch different, non-adjacent lines and
# merge without a manual conflict.
# =============================================================================

import random

from . import Family, Sprite, SpritePool, audio
from .params import Callback, Choice, Flag, Frames, Points, Sound


def _retire(sprite):
    """Take ``sprite`` out of a Behavior's reach the way the proposal's
    "Despawn is the off switch" means it: :meth:`~vs2.Sprite.despawn` back
    to its pool when it has one, or :meth:`~vs2.Sprite.hide` when it is a
    standalone sprite (:meth:`~vs2.Layer.sprite`, not
    :meth:`~vs2.Layer.sprite_pool`) with no pool to return to --
    ``despawn()`` itself raises ``ValueError`` there, since a standalone
    sprite was never live in a :class:`~vs2.SpritePool` to begin with.
    """
    if getattr(sprite, "_pool", None) is not None:
        sprite.despawn()
    else:
        sprite.hide()


def _sample_sprite(subject):
    """One representative sprite of ``subject`` (a :class:`~vs2.Sprite`,
    :class:`~vs2.SpritePool` or :class:`~vs2.Family`), or ``None`` for an
    empty pool/family -- used only at :meth:`Behavior.attached` time to
    read shared, build-time-only facts like an image's frame count, never
    in a Step."""
    if isinstance(subject, SpritePool):
        if subject._live:
            return subject._live[0]
        if subject._free:
            return subject._free[0]
        return None
    if isinstance(subject, Family):
        for _kind, member in subject._members:
            sample = _sample_sprite(member)
            if sample is not None:
                return sample
        return None
    return subject  # a lone Sprite


def _choose_sound(value):
    """A concrete sound name for :attr:`vs2.audio`'s ``sound()`` -- picked
    at random when ``value`` is a tuple/list (the proposal's "``sound=``
    accepts a tuple ... picked from at random"), otherwise ``value``
    itself unchanged."""
    if isinstance(value, (tuple, list)):
        return value[random.randrange(len(value))]
    return value


def _validated_range(value, label):
    """``value`` coerced to a ``(low, high)`` pair with ``low <= high``,
    for a ``Points``-typed range parameter (:class:`Recycling`'s
    ``x_range``/``y_range``) -- checked once, at construction, not in a
    Step."""
    if len(value) != 2:
        raise ValueError(
            "%s must be a (min, max) pair; got %r" % (label, value))
    low, high = value
    if low > high:
        raise ValueError(
            "%s: min (%r) must not exceed max (%r)" % (label, low, high))
    return (low, high)


class Transient(Behavior):
    """A sprite that lives for exactly :attr:`ticks` ticks, then retires
    itself -- the proposal's worked example is an explosion:
    ``Transient(animate=True, ticks=3, sound="boom")`` on a pool of
    ``on_empty=vs2.RECYCLE`` explosion sprites.

    :attr:`sound` and :attr:`on_end` fire together, once, on the tick
    :attr:`ticks` elapses -- right before the sprite retires -- not on
    spawn: nothing in the Behavior/Action surface gives a Behavior a
    "this sprite was just spawned" signal to hang a spawn-time sound off
    of (see this task's report), but "elapsed has now reached the
    configured lifetime" is a fact :meth:`step`/:meth:`step_one` can
    always detect for themselves, regardless of when the sprite's life
    began. For the shipped worked example this plays "boom" as the
    explosion's last visible frame disappears rather than as it first
    appears; a game wanting an on-spawn cue plays it itself, once, right
    after calling ``spawn()``.

    :attr:`animate`, when set, drives :attr:`~vs2.Sprite.frame` linearly
    across the subject's own image strip over the sprite's lifetime --
    frame ``0`` at ``elapsed == 0``, the last frame on the tick it
    retires -- computed from the frame count :meth:`attached` reads once
    off a representative sprite (see :func:`_sample_sprite`), not a
    separate ``first``/``last`` pair: a Transient's whole point is "play
    through what you've got, then go", not general-purpose animation
    control (that is :class:`Animated`'s job, and the two compose --
    attach both to the same pool for a Transient whose *in-lifetime*
    frame sequence needs more control than a linear sweep).
    """

    animate = Flag(False, label="Animate across its lifetime")
    ticks = Number(30, min=1, step=1, label="Lifetime", unit="tick")
    sound = Sound(None, label="Sound on expiry")
    on_end = Callback(None, label="On expiry")

    #: Ticks elapsed since this sprite's *last attach-time priming* --
    #: not since its last respawn. ``vs2.SpritePool.spawn()`` resets every
    #: ``var()``-declared instance variable but not a Behavior's own
    #: ``state`` (see ``vs2/__init__.py``'s ``spawn()``), so a sprite
    #: recycled through a ``RECYCLE`` pool after a full prior life may
    #: retire one tick after its new spawn instead of after a fresh
    #: :attr:`ticks`-tick life. This is a framework gap this task found
    #: but does not own the fix for (``vs2/__init__.py`` is off limits for
    #: this task) -- flagged plainly in the report, matching
    #: ``Projectile``'s own ``shot_flown`` state field, which has the
    #: identical characteristic and the same T8 precedent of not working
    #: around it locally.
    state = ("transient_elapsed",)

    def attached(self, subject):
        self._frames = None
        if self.animate:
            sample = _sample_sprite(subject)
            if sample is not None and sample.image.frames > 1:
                self._frames = sample.image.frames

    def _expire(self, sprite):
        sound = self.sound
        if sound is not None:
            audio.sound(_choose_sound(sound))
        on_end = self.on_end
        if on_end is not None:
            on_end(sprite)
        _retire(sprite)

    def _tick(self, sprite):
        ticks = self.ticks
        frames = self._frames
        elapsed = sprite.transient_elapsed + 1
        if frames is not None:
            frame = (elapsed * frames) // ticks
            if frame >= frames:
                frame = frames - 1
            sprite.frame = frame
        if elapsed >= ticks:
            self._expire(sprite)
        else:
            sprite.transient_elapsed = elapsed

    def step(self, sprites):
        live = sprites._live
        index = len(live) - 1                  # downward: despawn-safe
        while index >= 0:
            self._tick(live[index])
            index -= 1

    def step_one(self, sprite):
        self._tick(sprite)


class Lifetime(Behavior):
    """The plain form of :class:`Transient`: despawns a sprite exactly
    :attr:`ticks` ticks after its last attach-time priming, calling
    :attr:`on_expire` once, right before retiring it. No animation, no
    sound -- a bullet's range-independent fallback timeout, a pickup that
    should vanish if nobody grabs it, anything that just needs to go away
    after a while.

    Shares :class:`Transient`'s framework-level caveat: state resets at
    attach time, not at each respawn (see :attr:`Transient.state`'s
    docstring) -- flagged in this task's report, not worked around here.
    """

    ticks = Number(30, min=1, step=1, label="Lifetime", unit="tick")
    on_expire = Callback(None, label="On expiry")

    state = ("lifetime_elapsed",)

    def _tick(self, sprite):
        ticks = self.ticks
        elapsed = sprite.lifetime_elapsed + 1
        if elapsed >= ticks:
            on_expire = self.on_expire
            if on_expire is not None:
                on_expire(sprite)
            _retire(sprite)
        else:
            sprite.lifetime_elapsed = elapsed

    def step(self, sprites):
        live = sprites._live
        index = len(live) - 1                  # downward: despawn-safe
        while index >= 0:
            self._tick(live[index])
            index -= 1

    def step_one(self, sprite):
        self._tick(sprite)


class DespawnBeyond(Behavior):
    """Retires a sprite the tick it leaves a world-space box: any of
    :attr:`y_min`/:attr:`y_max`/:attr:`x_min`/:attr:`x_max` left ``None``
    (the default for all four) is simply not checked, so
    ``DespawnBeyond(y_min=0)`` -- the proposal's own example -- checks
    only the one bound it was given.

    The proposal's own "Despawn is the off switch": this is the catalog
    entry that reaches for that off switch on plain exit from view, the
    same job a hand-written ``if shot.y > SHOT_RANGE: pool.despawn(shot)``
    does today.
    """

    y_min = Number(None, label="Min depth", unit="led")
    y_max = Number(None, label="Max depth", unit="led")
    x_min = Number(None, label="Min angle", unit="col")
    x_max = Number(None, label="Max angle", unit="col")
    on_leave = Callback(None, label="On leaving bounds")

    def __init__(self, **kwargs):
        Behavior.__init__(self, **kwargs)
        if (self.y_min is None and self.y_max is None
                and self.x_min is None and self.x_max is None):
            raise ValueError(
                "DespawnBeyond needs at least one of "
                "y_min/y_max/x_min/x_max")

    def _out_of_bounds(self, sprite):
        y_min = self.y_min
        if y_min is not None and sprite.y < y_min:
            return True
        y_max = self.y_max
        if y_max is not None and sprite.y > y_max:
            return True
        x_min = self.x_min
        if x_min is not None and sprite.x < x_min:
            return True
        x_max = self.x_max
        if x_max is not None and sprite.x > x_max:
            return True
        return False

    def _tick(self, sprite):
        if self._out_of_bounds(sprite):
            on_leave = self.on_leave
            if on_leave is not None:
                on_leave(sprite)
            _retire(sprite)

    def step(self, sprites):
        live = sprites._live
        index = len(live) - 1                  # downward: despawn-safe
        while index >= 0:
            self._tick(live[index])
            index -= 1

    def step_one(self, sprite):
        self._tick(sprite)


class Recycling(Behavior):
    """Keeps a sprite alive forever, teleporting it to a fresh random
    position within :attr:`x_range`/:attr:`y_range` the tick it steps
    outside that same box -- the "never despawn" counterpart to
    :class:`DespawnBeyond`, for perpetual background elements (starfield
    drift, rain, ambient clutter) that should keep going indefinitely
    rather than round-trip through a pool's free list.

    Writes :attr:`~vs2.Sprite.x`/:attr:`~vs2.Sprite.y` directly rather
    than accumulating into ``dx``/``dy``: a teleport to a fresh random
    spot is a discontinuity, not a velocity to compose with whatever
    other movement touched this sprite earlier in the same Step -- the
    same reasoning :class:`Pinned` documents at more length. A sprite
    that is both ``Recycling`` and independently ``Moving`` on the same
    axis is exactly the "two things own this field" situation the
    proposal's Movements section calls out for the accumulator-based
    Actions; this Behavior does not attempt to detect that combination
    itself (out of this task's scope -- see the acceptance notes on the
    combined-T9 build-time check).
    """

    x_range = Points((0, 255), label="X range", unit="col")
    y_range = Points((0, 255), label="Y range", unit="led")

    def __init__(self, **kwargs):
        Behavior.__init__(self, **kwargs)
        self.x_range = _validated_range(self.x_range, "x_range")
        self.y_range = _validated_range(self.y_range, "y_range")

    def _out_of_bounds(self, sprite):
        x_min, x_max = self.x_range
        y_min, y_max = self.y_range
        return (sprite.x < x_min or sprite.x > x_max
                or sprite.y < y_min or sprite.y > y_max)

    def _tick(self, sprite):
        if self._out_of_bounds(sprite):
            x_min, x_max = self.x_range
            y_min, y_max = self.y_range
            sprite.x = random.uniform(x_min, x_max)
            sprite.y = random.uniform(y_min, y_max)

    def step(self, sprites):
        live = sprites._live
        index = 0
        count = len(live)                       # never despawns: forward
        while index < count:
            self._tick(live[index])
            index += 1

    def step_one(self, sprite):
        self._tick(sprite)


class Blinking(Behavior):
    """Toggles :attr:`~vs2.Sprite.visible` on for :attr:`on_ticks`, off
    for :attr:`off_ticks`, repeating -- for :attr:`duration` ticks total
    (``0``, the default, means forever), calling :attr:`on_end` and
    forcing the sprite back to visible the tick :attr:`duration` elapses,
    so a finite blink never gets stuck invisible.
    """

    on_ticks = Number(4, min=1, step=1, label="On ticks", unit="tick")
    off_ticks = Number(4, min=1, step=1, label="Off ticks", unit="tick")
    duration = Number(0, min=0, step=1,
                       label="Duration (0 = forever)", unit="tick")
    on_end = Callback(None, label="On finished blinking")

    #: See :attr:`Transient.state`'s docstring -- the same attach-time-
    #: only priming caveat applies here.
    state = ("blink_elapsed",)

    def _tick(self, sprite):
        duration = self.duration
        elapsed = sprite.blink_elapsed
        if duration and elapsed >= duration:
            return                              # already finished: no-op
        cycle = self.on_ticks + self.off_ticks
        sprite.visible = (elapsed % cycle) < self.on_ticks
        elapsed += 1
        sprite.blink_elapsed = elapsed
        if duration and elapsed >= duration:
            sprite.visible = True
            on_end = self.on_end
            if on_end is not None:
                on_end(sprite)

    def step(self, sprites):
        live = sprites._live
        index = 0
        count = len(live)                       # never despawns: forward
        while index < count:
            self._tick(live[index])
            index += 1

    def step_one(self, sprite):
        self._tick(sprite)


class Pinned(Behavior):
    """Copies :attr:`to`'s position, plus a fixed offset, onto this
    Behavior's own subject every tick -- a turret riding a boss, a shield
    orbiting... no, an eye following a body, anything that must track
    another sprite exactly.

    **Build-time, unlike Carried.** The proposal contrasts the two
    directly: "``Carried`` is a runtime relationship where ``Pinned`` is
    a build-time one". :attr:`to` is resolved exactly once, in
    :meth:`attached`, to a direct object reference held in ``self._to`` --
    never a lookup, never re-resolved, in a Step. (``Carried`` itself is
    not built by this task -- it is one of the three attributes waiting
    on named palette colours; see this file's "Attributes" section
    docstring.)

    **Writes ``sprite.x``/``sprite.y`` directly, not ``dx``/``dy``.** The
    proposal's own "### Movements" section documents the same choice for
    three Movements Actions: "The exceptions set an absolute position
    rather than a velocity: ``PathFollowing``, ``Laned`` and ``Pilotable``
    with ``bounds`` each own the field they write." A pinned sprite's
    position is not a delta to accumulate alongside some other movement's
    contribution -- it *is* ``to``'s position plus a fixed offset,
    recomputed from scratch every tick, with nothing sensible to compose
    it against. Two more reasons beyond "there is nothing to add":

    1. **Correctness of the observed target position.** By the time any
       Behavior's ``step``/``step_one`` runs, ``to.x``/``to.y`` already
       reflect *this* tick's fully-committed position only if ``to``'s
       own movement was a plain field write (like another ``Pinned``);
       if ``to`` moves via ``dx``/``dy`` (``Moving``, ``Patrolling``,
       ...), that pool's contribution commits once, in
       ``Scene._commit_pool_motion()``, *after every Behavior in attach
       order has run* -- so reading ``to.x``/``to.y`` mid-pass always
       sees last tick's committed position for a ``dx``/``dy``-moved
       anchor, one Step stale, regardless of attach order. That staleness
       is real either way this Behavior writes its own output; it is not
       an argument for using the accumulator, only context for why a
       pinned sprite trails its ``dx``/``dy``-moved anchor by exactly one
       Step (usually invisible at 33 Hz, and the same one-Step lag a
       hand-written pin would have).
    2. **No spurious extra lag from this Behavior's own output.** Writing
       through ``dx``/``dy`` would mean this Step's freshly-computed
       target position only lands on ``sprite.x``/``sprite.y`` at the
       *end* of the Behavior pass (the one shared commit), same as a
       direct write here would -- so there is no latency difference
       between the two for this Behavior's own contribution. The
       difference is simplicity and correctness under composition: a
       direct write is exactly "be here now", with no accumulator state
       to reset, no risk of ``Pinned`` and some other Behavior on the
       same subject fighting over ``dx``/``dy`` in ways that would only
       be coincidentally correct.

    ``offset_x``/``offset_y`` are literal (see this file's top-of-section
    note on Var support) -- a pool of differently-offset followers is two
    attachments with two explicit ``name=``s, not one ``Var``-bound one.
    """

    to = PoolRef(None, label="Follow")
    offset_x = Number(0, label="X offset", unit="col")
    offset_y = Number(0, label="Y offset", unit="led")

    def __init__(self, **kwargs):
        Behavior.__init__(self, **kwargs)
        if not isinstance(self.to, Sprite):
            raise TypeError(
                "Pinned: to= must be a single Sprite (an anchor to "
                "follow); got %r" % (self.to,))

    def attached(self, subject):
        self._to = self.to

    def step(self, sprites):
        to = self._to
        x = to.x + self.offset_x
        y = to.y + self.offset_y
        live = sprites._live
        index = 0
        count = len(live)                       # never despawns: forward
        while index < count:
            sprite = live[index]
            sprite.x = x
            sprite.y = y
            index += 1

    def step_one(self, sprite):
        to = self._to
        sprite.x = to.x + self.offset_x
        sprite.y = to.y + self.offset_y


class Shaking(Behavior):
    """A temporary, zero-centred jitter added to a sprite's position for
    :attr:`ticks` ticks, then removed exactly, landing back on the
    un-shaken position -- a hit reaction, a screen-shake-alike scoped to
    one sprite instead of the whole layer.

    **Writes into ``dx``/``dy``, unlike this section's other two movers**
    (:class:`Pinned`, :class:`Recycling`): a shake must *compose* with
    whatever else is moving the sprite (a hit ship still under
    ``Pilotable`` control, say), so each tick it accumulates the *change*
    from last tick's random offset to a new one -- ``new - previous`` --
    rather than the new offset outright, so the net effect of every prior
    tick's jitter still cancels through the ordinary commit pass. The
    final tick forces the new offset to ``(0, 0)``, undoing the last
    jitter exactly rather than leaving one tick's random displacement
    permanently baked into the sprite's position.
    """

    amplitude_x = Number(2, min=0, step=0.25, label="X amplitude", unit="col")
    amplitude_y = Number(2, min=0, step=0.25, label="Y amplitude", unit="led")
    ticks = Number(10, min=1, step=1, label="Duration", unit="tick")

    #: See :attr:`Transient.state`'s docstring -- the same attach-time-
    #: only priming caveat applies here: a respawned sprite that shook
    #: once already will not automatically shake again.
    state = ("shake_elapsed", "shake_off_x", "shake_off_y")

    def _tick(self, sprite):
        ticks = self.ticks
        elapsed = sprite.shake_elapsed
        if elapsed >= ticks:
            return                              # already finished: no-op
        elapsed += 1
        if elapsed >= ticks:
            # Final tick: cancel the last offset outright instead of
            # rolling a new one, so the sprite lands exactly back on its
            # un-shaken position rather than keeping one tick's random
            # displacement forever.
            new_x = 0
            new_y = 0
        else:
            amplitude_x = self.amplitude_x
            amplitude_y = self.amplitude_y
            new_x = random.uniform(-amplitude_x, amplitude_x) if amplitude_x else 0
            new_y = random.uniform(-amplitude_y, amplitude_y) if amplitude_y else 0
        sprite.dx += new_x - sprite.shake_off_x
        sprite.dy += new_y - sprite.shake_off_y
        sprite.shake_off_x = new_x
        sprite.shake_off_y = new_y
        sprite.shake_elapsed = elapsed

    def step(self, sprites):
        live = sprites._live
        index = 0
        count = len(live)                       # never despawns: forward
        while index < count:
            self._tick(live[index])
            index += 1

    def step_one(self, sprite):
        self._tick(sprite)


def _next_sequence_index(index, direction, length, mode):
    """Advance ``index`` (into a 0-based sequence of ``length`` items) by
    one step in ``direction`` (``+1``/``-1``), applying ``mode``'s
    boundary rule -- shared by :class:`Animated`'s pool and single-sprite
    dispatch so the three-way loop/once/pingpong branch exists exactly
    once. Returns ``(index, direction, done)``; ``done`` is only ever
    ``True`` for ``"once"`` mode's final arrival (kept for symmetry with
    :class:`~vs2.actions.Animate`'s own :data:`vs2.DONE`-on-arrival
    convention, even though nothing in this file's callers currently
    consume it -- :class:`Animated` has no ``on_end``/result parameter in
    the proposal's own listing).
    """
    if length <= 1:
        return 0, direction, mode == "once"
    index += direction
    if mode == "pingpong":
        if index >= length:
            index = length - 2
            direction = -1
        elif index < 0:
            index = 1
            direction = 1
        return index, direction, False
    if mode == "once":
        if index >= length:
            return length - 1, direction, True
        if index < 0:
            return 0, direction, True
        return index, direction, False
    # "loop"
    if index >= length:
        index = 0
    elif index < 0:
        index = length - 1
    return index, direction, False


class Animated(Behavior):
    """Steps a sprite's displayed frame (or, with :attr:`images`, its
    whole :class:`~vs2.Image`) through a sequence, independently per
    sprite -- unlike :class:`~vs2.actions.Animate` (see below).

    **Why this does not wrap ``vs2.actions.Animate``.** That Action's
    clock is deliberately Action-level, shared by every sprite one
    instance drives -- its own docstring: "every live sprite driven by
    one ``Animate`` instance shares one clock ... a squad animating in
    lockstep." That is wrong for a pool of independently (re)spawned
    sprites: two enemies spawned five ticks apart would show the exact
    same frame in the same tick instead of each playing from its own
    start. ``Animate`` also has no ``bank``/``bank_size``, ``frames=``,
    ``duration=`` or ``images=`` at all -- the full parameter set this
    class needs. So ``Animated`` keeps its own per-sprite clock
    (:attr:`state`) and its own advance logic (:func:`_next_sequence_index`)
    rather than composing ``Animate`` and bolting the extra parameters on
    from outside; there would be nothing left of ``Animate`` to reuse.

    **``frames=`` is the general mechanism; ``first``/``last`` is the
    convenience case** (the proposal's own framing): a non-empty
    :attr:`frames` tuple plays back exactly, in order -- any flicker
    pattern, including repeats and non-monotonic jumps, no
    ``first``/``last``/``mode`` combination could produce.
    :attr:`first`/:attr:`last` only builds an implied ascending (or,
    when ``last < first``, descending) run, and only when :attr:`frames`
    is empty.

    **``duration=`` vs. ``ticks=``.** Both express speed. :attr:`duration`
    -- ticks to play the *whole* sequence once, allowing a continuous,
    fractional per-tick advance -- wins whenever it is non-zero;
    otherwise :attr:`ticks` -- ticks held per frame, an integer divisor,
    matching :class:`~vs2.actions.Animate`'s own parameter of the same
    name -- applies. Both are declared; the editor is expected to offer
    both and store one, per the proposal's own wording.

    **``bank``/``bank_size`` offset the frame index** written to
    :attr:`~vs2.Sprite.frame` by ``bank * bank_size`` -- a second strip of
    frames per direction, for art ``flip_x`` cannot mirror correctly.
    They are meaningless, and rejected at construction, together with
    :attr:`images`: that mode swaps whole ``Image`` handles rather than a
    frame number within one strip, so there is no frame index for a bank
    offset to apply to.

    **``images=`` resolves once, at :meth:`attached`.** Each entry is
    resolved through the subject's own ``scene.image()`` there, into a
    tuple of real :class:`~vs2.Image` handles -- so the per-tick write is
    ``sprite.image = self._images[index]`` with an already-``Image``
    argument. ``Sprite.image``'s own setter always re-resolves its
    argument through ``scene.image()``, but that function's first check
    is ``isinstance(value, Image): return value`` -- an already-resolved
    handle short-circuits before the name-keyed cache dict is ever
    touched, so no name (a string) is looked up, let alone built, in a
    Step.
    """

    first = Frames(0, label="First frame")
    last = Frames(0, label="Last frame")
    ticks = Number(1, min=1, step=1, label="Ticks per frame", unit="tick")
    mode = Choice("loop", options=("loop", "once", "pingpong"), label="Mode")
    bank = Number(0, min=0, step=1, label="Bank")
    bank_size = Number(0, min=0, step=1, label="Bank size", unit="frame")
    frames = Points((), label="Explicit frame sequence")
    duration = Number(0, min=0, step=1,
                       label="Duration (0 = use ticks)", unit="tick")
    images = Points((), label="Image sequence")

    #: ``anim_elapsed`` is a fractional leaky-bucket accumulator (0..1) so
    #: ``ticks=`` and ``duration=`` share one advance path; ``anim_index``
    #: is the current position in the sequence; ``anim_dir`` is
    #: ``pingpong``'s current direction (``0`` reads as ``+1`` -- see
    #: :meth:`_advance`). Same attach-time-only priming caveat as this
    #: section's other stateful attributes (:attr:`Transient.state`).
    state = ("anim_elapsed", "anim_index", "anim_dir")

    def __init__(self, **kwargs):
        Behavior.__init__(self, **kwargs)
        if self.frames and self.images:
            raise ValueError(
                "Animated: frames= and images= are mutually exclusive; "
                "got both")
        if self.bank_size and self.images:
            raise ValueError(
                "Animated: bank/bank_size apply to the frame-index path "
                "only; got both bank_size and images=")
        if self.duration and self.duration < 1:
            raise ValueError(
                "Animated: duration must be at least 1 tick when given; "
                "got %r" % (self.duration,))

    def attached(self, subject):
        if self.images:
            self._images = tuple(
                subject.layer.scene.image(name) for name in self.images)
            self._sequence = None
        else:
            self._images = None
            if self.frames:
                self._sequence = tuple(int(f) for f in self.frames)
            elif self.last >= self.first:
                self._sequence = tuple(range(self.first, self.last + 1))
            else:
                self._sequence = tuple(range(self.first, self.last - 1, -1))
        self._length = (len(self._images) if self._images is not None
                         else len(self._sequence))
        self._step_per_tick = (1.0 / self.duration) if self.duration \
            else (1.0 / self.ticks)
        self._bank_offset = int(self.bank) * int(self.bank_size)

    def _display(self, sprite, index):
        if self._images is not None:
            sprite.image = self._images[index]
        else:
            sprite.frame = self._sequence[index] + self._bank_offset

    def _advance(self, sprite, mode, step_per_tick, length):
        # Display *before* advancing -- the first call shows sequence[0]
        # (or images[0]), matching vs2.actions.Animate.run()'s own
        # documented convention, not whatever comes after it.
        self._display(sprite, sprite.anim_index)
        elapsed = sprite.anim_elapsed + step_per_tick
        direction = sprite.anim_dir or 1
        seq_index = sprite.anim_index
        while elapsed >= 1.0:
            elapsed -= 1.0
            seq_index, direction, _done = _next_sequence_index(
                seq_index, direction, length, mode)
        sprite.anim_elapsed = elapsed
        sprite.anim_dir = direction
        sprite.anim_index = seq_index

    def step(self, sprites):
        mode = self.mode
        step_per_tick = self._step_per_tick
        length = self._length
        live = sprites._live
        index = 0
        count = len(live)                       # never despawns: forward
        while index < count:
            self._advance(live[index], mode, step_per_tick, length)
            index += 1

    def step_one(self, sprite):
        self._advance(sprite, self.mode, self._step_per_tick, self._length)
# T9b -- The catalog's Movements tier, plus ShuffleBag
# =============================================================================
#
# Spec: docs/vs2-behaviors-proposal.md, "## The catalog" -> "### Movements"
# (accumulate-vs-absolute), plus "## Layers" -> "### Cameras"/"### Geometry
# helpers" for Aiming's to_depth/polar. Work-breakdown card:
# docs/vs2-behaviors-implementation.md T9 (split T9a attributes / T9b
# movements -- this block is T9b's whole share). Everything below this
# banner is new; nothing above it (Behavior, Projectile) is touched.
#
# These imports are additional to the ones at the top of this file, kept
# separate on purpose: T9a (the sibling agent building the catalog's
# Attributes tier in this same module, concurrently) is likely editing the
# top-of-file import block too, and two independent diffs touching the same
# import lines is exactly the merge collision the plan's own instructions
# ask each of us to avoid. A second `from .params import ...` further down
# the file is unusual style but costs nothing at runtime and keeps this
# whole section a clean append.
import random
from math import atan2, cos, pi, sin, sqrt

from . import controls
from . import Family, Sprite, SpritePool, display
from . import audio as _audio
from .params import Callback, Choice, Flag, Points, Sound, Var


# -----------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------

def _play_sound(sound):
    """Play ``sound`` (a name, a tuple/list of names picked from at random,
    or ``None`` to no-op) -- the ``sound=`` convention the proposal
    describes as common to every event-firing Behavior in the catalog
    ("## The catalog": "sound= accepts a tuple as well as a name, picked
    from at random"). Indexing rather than ``random.choice`` so this stays
    a plain call with no new container built.
    """
    if sound is None:
        return
    if isinstance(sound, (tuple, list)):
        if not sound:
            return
        sound = sound[random.randint(0, len(sound) - 1)]
    _audio.sound(sound)


def _maybe_fire(joy, fires, fire_button, fire_sound, sprite):
    """Shared trigger-pull body for :class:`Pilotable` and :class:`Aiming`:
    on the tick ``fire_button`` is freshly pressed (an edge, not a level --
    see ``vs2.controls``), spawn one sprite from the ``fires`` pool at
    ``sprite``'s own position and play ``fire_sound``. A no-op wherever
    ``fires`` was never given, so a Pilotable/Aiming used purely for
    movement pays nothing extra."""
    if fires is None:
        return
    if joy.just_pressed(fire_button):
        shot = fires.spawn(sprite.x, sprite.y)
        if shot is not None:
            _play_sound(fire_sound)


def _is_absolute_position_movement(behavior):
    """Whether ``behavior`` sets an absolute sprite position rather than
    accumulating into ``dx``/``dy`` -- the proposal's ### Movements split:
    "The exceptions set an absolute position rather than a velocity:
    PathFollowing, Laned and Pilotable with bounds each own the field they
    write". :class:`PathFollowing` and :class:`Laned` always qualify;
    :class:`Pilotable` only when its own ``bounds=`` is set (unbounded
    Pilotable composes through dx/dy like any other accumulating
    movement). Referencing the three classes by name here is safe even
    though they are defined later in this section -- this function's body
    is only evaluated the first time it is *called*, at build time inside
    some ``attached()``, long after the whole module has finished
    importing and every name below is bound.
    """
    if isinstance(behavior, (PathFollowing, Laned)):
        return True
    if isinstance(behavior, Pilotable):
        return behavior.bounds is not None
    return False


def _guard_absolute_position(subject, behavior):
    """Raise ``ValueError`` naming both sides if ``subject`` already
    carries another absolute-position movement besides ``behavior`` itself.

    Called from ``attached()``, where ``vs2._attach_behavior`` has already
    appended ``behavior`` to ``subject.behaviors`` (see that function's own
    docstring: name/limit checks and registration happen *before*
    ``attached()`` runs) -- so this only has to walk ``subject.behaviors``
    once and skip ``behavior`` itself to find every *other* Behavior
    already attached, pairwise conflict and same-class-twice alike.
    """
    for existing in subject.behaviors:
        if existing is behavior:
            continue
        if _is_absolute_position_movement(existing):
            raise ValueError(
                "%s and %s both set an absolute position on this subject; "
                "dx/dy is an accumulator, not a target, so only one of "
                "PathFollowing, Laned, or Pilotable(bounds=...) may be "
                "attached per subject (got %r and %r)"
                % (type(existing).__name__, type(behavior).__name__,
                   existing, behavior))


class ShuffleBag:
    """A Fisher-Yates shuffle bag: draws every item exactly once per cycle,
    in a freshly re-permuted order each time the bag empties, so the
    long-run distribution is exactly uniform across items rather than
    merely independent per draw the way ``random.choice()`` is (which can
    hand back the same item many times running, or skip another for a long
    stretch, purely by chance).

    Not a :class:`Behavior` -- a small standalone utility, per the
    proposal's own placement: "``Spawner``'s ``schedule``... Types come
    from a ``ShuffleBag``... ``ShuffleBag`` ships in ``vs2`` beside the
    behaviors" ("## The catalog" -> "### Composed"). ``Spawner`` itself is
    Composed-tier and not built by this wave, but this class is explicitly
    T9's to ship regardless::

        bag = ShuffleBag(("driller", "chiller", "chiller"))
        kind = bag.draw()   # every one of the three drawn once before any
                             # repeats, in a random order that reshuffles
                             # (and re-permutes) once exhausted

    The shuffle itself is the same in-place Fisher-Yates walk as
    ``ventilastation/shuffler.py``'s own ``shuffled()`` (same algorithm,
    same ``random.randint`` calls), applied directly to this bag's own
    list rather than a copy, so refilling the bag allocates nothing beyond
    the one-time list built at construction.
    """

    def __init__(self, items):
        items = list(items)
        if not items:
            raise ValueError("ShuffleBag needs at least one item")
        self._items = items
        #: Draws taken since the last shuffle. Starts equal to the item
        #: count so the very first draw() triggers a shuffle before
        #: anything is handed out, rather than handing out construction
        #: order on the first cycle.
        self._index = len(items)

    def __len__(self):
        return len(self._items)

    def draw(self):
        """The next item. Allocates nothing once warm, apart from the
        in-place reshuffle that runs exactly once per full cycle through
        every item (a fixed, one-time-per-cycle cost, not a per-draw one)."""
        items = self._items
        if self._index >= len(items):
            self._shuffle()
            self._index = 0
        item = items[self._index]
        self._index += 1
        return item

    def _shuffle(self):
        items = self._items
        index = len(items) - 1
        while index > 0:
            swap = random.randint(0, index)
            items[index], items[swap] = items[swap], items[index]
            index -= 1


# -----------------------------------------------------------------------
# Moving -- constant velocity plus optional acceleration.
# -----------------------------------------------------------------------

class Moving(Behavior):
    """Constant velocity, with optional acceleration -- a thin Behavior
    wrapper over :class:`~vs2.actions.Move`, so a designer attaches
    movement from the catalog instead of a game writing ``Move(...)``
    itself. Writes only into ``dx``/``dy`` (via the hoisted ``Move``
    action), so ``Moving`` plus ``Patrolling`` on one subject is
    unremarkable, per the proposal's own worked example ("### Movements").
    """

    speed_x = Angle(0, min=-32, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(0, min=-32, max=32, step=0.25,
                      label="Radial speed", unit="led/tick")
    accel_x = Angle(0, min=-8, max=8, step=0.05,
                    label="Angular acceleration", unit="col/tick^2")
    accel_y = Number(0, min=-8, max=8, step=0.05,
                      label="Radial acceleration", unit="led/tick^2")

    def attached(self, subject):
        self.move = self.action(actions.Move(
            speed_x=self.speed_x, speed_y=self.speed_y,
            accel_x=self.accel_x, accel_y=self.accel_y))

    def step(self, sprites):
        self.move.run(sprites)

    def step_one(self, sprite):
        self.move.run_one(sprite)


# -----------------------------------------------------------------------
# Patrolling -- an oscillation on one axis plus a constant drift.
# -----------------------------------------------------------------------

class Patrolling(Behavior):
    """Oscillates back and forth on one axis (``field``) around wherever
    the sprite already is, while drifting at a constant rate on both axes
    (``drift_x``/``drift_y``) -- a sentry pacing a beat while the whole
    formation creeps forward, in one Behavior. Composes: every tick it
    contributes is a finite difference (this tick's point on the wave
    minus last tick's), written into ``dx``/``dy`` like any other
    accumulating movement, never an absolute position.

    ``wave`` picks the oscillation's shape: ``"sine"`` (smooth, the
    default), ``"triangle"`` (constant-speed back and forth) or
    ``"square"`` (an instant snap between the two extremes at the
    half-period mark -- a sentry that *teleports* between two posts, which
    a finite-difference accumulator renders correctly as one large delta
    on the tick the snap happens and none the rest of the period).

    Each sprite gets its own phase (``state``: primed to 0, like
    :class:`Projectile`'s ``shot_flown``), so a pool of patrolling sprites
    does not oscillate in lockstep merely because they share one
    ``Patrolling`` instance and one set of parameters.
    """

    field = Choice("y", options=("x", "y"), label="Oscillation axis")
    amplitude = Number(8, min=0, max=255, step=0.25, label="Amplitude")
    period = Number(60, min=1, max=6000, step=1, label="Period", unit="tick")
    wave = Choice("sine", options=("sine", "triangle", "square"),
                  label="Waveform")
    drift_x = Angle(0, min=-32, max=32, step=0.25,
                    label="Angular drift", unit="col/tick")
    drift_y = Number(0, min=-32, max=32, step=0.25,
                      label="Radial drift", unit="led/tick")

    #: Ticks elapsed since this sprite started patrolling -- the wave's
    #: own clock, per sprite (free ones included), per Behavior.state's
    #: usual priming.
    state = ("patrol_phase",)

    def _wave_offset(self, phase):
        period = self.period
        amplitude = self.amplitude
        t = (phase % period) / period  # 0..1 fraction of one period
        wave = self.wave
        if wave == "square":
            return amplitude if t < 0.5 else -amplitude
        if wave == "triangle":
            if t < 0.25:
                return amplitude * (4.0 * t)
            if t < 0.75:
                return amplitude * (2.0 - 4.0 * t)
            return amplitude * (4.0 * t - 4.0)
        return amplitude * sin(2.0 * pi * t)  # "sine"

    def _advance(self, sprite, field, drift_x, drift_y):
        prev_phase = sprite.patrol_phase
        phase = prev_phase + 1
        sprite.patrol_phase = phase
        delta = self._wave_offset(phase) - self._wave_offset(prev_phase)
        if field == "x":
            sprite.dx += drift_x + delta
            sprite.dy += drift_y
        else:
            sprite.dx += drift_x
            sprite.dy += drift_y + delta

    def step(self, sprites):
        field = self.field
        drift_x = self.drift_x
        drift_y = self.drift_y
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self._advance(live[index], field, drift_x, drift_y)
            index += 1

    def step_one(self, sprite):
        self._advance(sprite, self.field, self.drift_x, self.drift_y)


# -----------------------------------------------------------------------
# PathFollowing -- absolute position: walks a fixed sequence of waypoints.
# -----------------------------------------------------------------------

class PathFollowing(Behavior):
    """Moves toward each of ``points`` in turn at up to
    ``speed_x``/``speed_y`` per tick, arriving via the same clamped-step
    maths :class:`~vs2.actions.MoveTo` uses (never overshoots; still
    written through ``dx``/``dy``, matching that Action's own precedent of
    an "absolute position" movement that nonetheless goes through the
    accumulator -- see :func:`_guard_absolute_position`'s docstring for
    why that still counts as "owning the field").

    One of the three absolute-position movements: attaching a second one
    (``PathFollowing``, :class:`Laned`, or bounded :class:`Pilotable`) to
    the same subject is a build-time ``ValueError`` naming both.

    ``points`` is the active route: a tuple of ``(x, y)`` world-space
    waypoints. ``paths``, if given, is a ``{name: points}`` table of
    additional named routes a game can switch to at runtime via
    :meth:`select` -- letting one ``PathFollowing`` serve several patrol
    routes (or be reused across differently-shaped enemies in one pool)
    without re-attaching.

    ``relative=True`` treats every waypoint as an offset from wherever the
    sprite happened to be the first tick this Behavior ever moved it,
    captured lazily per sprite (not at attach time, when a pool's sprites
    are not necessarily spawned yet) -- so one authored loop shape can be
    reused at any spawn point.

    ``loop=True`` (the default) restarts at the first waypoint after the
    last is reached, cycling forever. With ``loop=False`` the path holds at
    the final waypoint once, and ``then`` (``"hold"`` or ``"despawn"``)
    decides what happens next; ``on_finish`` (a callback) fires exactly
    once, the tick it arrives, regardless of ``then``.
    """

    points = Points((), label="Waypoints")
    relative = Flag(False, label="Relative to start")
    speed_x = Angle(4, min=0, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(4, min=0, max=32, step=0.25,
                      label="Radial speed", unit="led/tick")
    loop = Flag(True, label="Loop")
    then = Choice("hold", options=("hold", "despawn"),
                  label="When the path finishes")
    on_finish = Callback(None, label="On finish")

    #: path_index: which waypoint is the current target.
    #: path_done: 1 once a non-looping path has arrived and stopped.
    #: path_started/path_origin_x/path_origin_y: the lazily-captured
    #: starting point ``relative=True`` measures every waypoint from.
    state = ("path_index", "path_done", "path_started",
              "path_origin_x", "path_origin_y")

    def __init__(self, paths=None, **kwargs):
        Behavior.__init__(self, **kwargs)
        #: ``{name: tuple_of_points}`` extra named routes -- see
        #: :meth:`select`. Empty when the caller never passed ``paths=``.
        self.paths = dict(paths) if paths else {}

    def attached(self, subject):
        _guard_absolute_position(subject, self)
        points = tuple(self.points)
        if not points:
            raise ValueError(
                "PathFollowing needs at least one waypoint in points=")
        self._points = points

    def select(self, name):
        """Switch the active route to ``self.paths[name]`` -- allocates
        (a dict lookup plus a fresh tuple), so this is a game-logic call,
        not a per-tick one, matching every other structural mutator in
        this module."""
        self._points = tuple(self.paths[name])

    def _advance(self, sprite, speed_x, speed_y, relative, loop, then,
                 on_finish):
        if sprite.path_done:
            return
        if relative and not sprite.path_started:
            sprite.path_origin_x = sprite.x
            sprite.path_origin_y = sprite.y
            sprite.path_started = 1
        points = self._points
        target_x, target_y = points[sprite.path_index]
        if relative:
            target_x += sprite.path_origin_x
            target_y += sprite.path_origin_y
        delta_x = actions._wrapped_delta(sprite.x, target_x)
        delta_y = target_y - sprite.y
        step_x = actions._clamp_step(delta_x, speed_x)
        step_y = actions._clamp_step(delta_y, speed_y)
        sprite.dx += step_x
        sprite.dy += step_y
        if step_x != delta_x or step_y != delta_y:
            return
        index = sprite.path_index + 1
        if index < len(points):
            sprite.path_index = index
            return
        if loop:
            sprite.path_index = 0
            return
        sprite.path_done = 1
        if on_finish is not None:
            on_finish(sprite)
        if then == "despawn":
            sprite.despawn()

    def step(self, sprites):
        speed_x = self.speed_x
        speed_y = self.speed_y
        relative = self.relative
        loop = self.loop
        then = self.then
        on_finish = self.on_finish
        live = sprites._live
        index = len(live) - 1  # downward: `then="despawn"` can despawn
        while index >= 0:
            self._advance(live[index], speed_x, speed_y, relative, loop,
                          then, on_finish)
            index -= 1

    def step_one(self, sprite):
        self._advance(sprite, self.speed_x, self.speed_y, self.relative,
                      self.loop, self.then, self.on_finish)


# -----------------------------------------------------------------------
# Pilotable -- player-controlled movement, one dial for four feels.
# -----------------------------------------------------------------------

class Pilotable(Behavior):
    """Player-controlled movement. One parameter set collapses rim
    control, turn-with-camera-follow-lag, momentum-with-damping and free
    eight-way into a single continuous dial rather than four separate
    Behaviors (see this task's report for the full worked-math writeup):

    - ``scheme`` picks which joystick axes drive movement at all:
      ``"eight_way"`` (LEFT/RIGHT and UP/DOWN both contribute) or
      ``"rim"`` (LEFT/RIGHT only -- the vertical axis never contributes,
      so a rim-runner cannot be nudged off its rim no matter what inertia
      or damping say).
    - ``inertia=0`` is direct control: this tick's velocity is exactly the
      held direction times ``speed_x``/``speed_y``, computed fresh with no
      memory of the previous tick. ``inertia>0`` switches on a persisted
      per-sprite velocity that eases toward that same target at a rate of
      ``1/(1+inertia)`` per tick -- bigger inertia, slower to change
      direction, the classic "heavier ship" feel.
    - ``damping`` only has anything to decay once ``inertia>0`` has given
      the sprite a persisted velocity in the first place; it then scales
      that velocity by ``(1-damping)`` every tick, independently of how
      fast ``inertia`` lets it turn -- so a ship can steer sluggishly
      (high inertia) yet coast to a stop quickly (high damping), or the
      reverse, a combination four separate Behaviors could not offer as
      one continuous dial.
    - ``follow_lag=0`` is a fixed camera: this Behavior never touches
      ``layer.camera_x``/``camera_y`` at all. ``follow_lag>0`` eases the
      subject's own layer's camera toward the sprite's position at
      ``wrapped_delta(camera, sprite) / follow_lag`` per tick -- bigger
      follow_lag, laggier catch-up. This is what reads as "turning" even
      though the sprite itself only ever moves left/right: the *view* pans
      behind it with a lag.
    - ``bounds``, when set (``(x_min, x_max, y_min, y_max)``, any entry
      ``None`` to leave that side open), is the one case that turns this
      from an accumulating velocity into an absolute-position movement
      (see :func:`_guard_absolute_position`): the intended new position is
      computed exactly as above and then clamped to ``bounds``, and the
      tick's ``dx``/``dy`` is the exact delta needed to land there --
      still written through the accumulator, but no longer meaningfully
      additive with a second absolute-position movement on the same
      subject, hence the build-time conflict check.

    ``fires``/``fire_button``/``fire_sound`` are the optional weapon: on
    the tick ``fire_button`` is freshly pressed, one sprite spawns from
    ``fires`` at this sprite's position and ``fire_sound`` plays (a tuple
    picked at random, per the catalog's ``sound=`` convention).
    """

    player = Choice(1, options=(1, 2), label="Player")
    scheme = Choice("eight_way", options=("eight_way", "rim"),
                    label="Control scheme")
    speed_x = Angle(2, min=0, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(2, min=0, max=32, step=0.25,
                      label="Radial speed", unit="led/tick")
    inertia = Number(0, min=0, max=32, step=0.25, label="Inertia")
    damping = Number(0, min=0, max=1, step=0.01, label="Damping")
    follow_lag = Number(0, min=0, max=255, step=1,
                          label="Camera follow lag", unit="tick")
    bounds = Points(None, label="Bounds (x_min, x_max, y_min, y_max)")
    fires = PoolRef(None, label="Fires from")
    fire_button = Choice(controls.A, options=(controls.A, controls.B, controls.X),
                          label="Fire button")
    fire_sound = Sound(None, label="Fire sound")

    #: Persisted velocity -- only ever meaningfully non-zero when
    #: inertia>0 (direct control, inertia=0, never reads or writes it).
    state = ("pilot_vx", "pilot_vy")

    def attached(self, subject):
        if self.bounds is not None:
            x_min, x_max, y_min, y_max = self.bounds
            self.bounds = (x_min, x_max, y_min, y_max)
            _guard_absolute_position(subject, self)
        self._joy = controls.joy1 if self.player == 1 else controls.joy2
        self._layer = subject.layer

    def _target_velocity(self, joy, speed_x, speed_y, rim):
        if joy.held(controls.RIGHT):
            vx = speed_x
        elif joy.held(controls.LEFT):
            vx = -speed_x
        else:
            vx = 0
        if rim:
            return vx, 0
        if joy.held(controls.DOWN):
            vy = speed_y
        elif joy.held(controls.UP):
            vy = -speed_y
        else:
            vy = 0
        return vx, vy

    def _velocity_for(self, sprite, target_vx, target_vy, inertia, damping):
        if not inertia:
            return target_vx, target_vy
        rate = 1.0 / (1.0 + inertia)
        vx = sprite.pilot_vx + (target_vx - sprite.pilot_vx) * rate
        vy = sprite.pilot_vy + (target_vy - sprite.pilot_vy) * rate
        if damping:
            vx *= (1.0 - damping)
            vy *= (1.0 - damping)
        sprite.pilot_vx = vx
        sprite.pilot_vy = vy
        return vx, vy

    def _advance(self, sprite, joy, speed_x, speed_y, rim, inertia, damping,
                 follow_lag, bounds, fires, fire_button, fire_sound):
        target_vx, target_vy = self._target_velocity(joy, speed_x, speed_y, rim)
        vx, vy = self._velocity_for(sprite, target_vx, target_vy, inertia,
                                     damping)
        if bounds is not None:
            x_min, x_max, y_min, y_max = bounds
            new_x = sprite.x + vx
            new_y = sprite.y + vy
            if x_min is not None and new_x < x_min:
                new_x = x_min
            elif x_max is not None and new_x > x_max:
                new_x = x_max
            if y_min is not None and new_y < y_min:
                new_y = y_min
            elif y_max is not None and new_y > y_max:
                new_y = y_max
            sprite.dx += actions._wrapped_delta(sprite.x, new_x)
            sprite.dy += new_y - sprite.y
        else:
            sprite.dx += vx
            sprite.dy += vy
        if follow_lag:
            layer = self._layer
            layer.camera_x += (actions._wrapped_delta(layer.camera_x, sprite.x)
                                / follow_lag)
            layer.camera_y += (sprite.y - layer.camera_y) / follow_lag
        _maybe_fire(joy, fires, fire_button, fire_sound, sprite)

    def step(self, sprites):
        joy = self._joy
        speed_x = self.speed_x
        speed_y = self.speed_y
        rim = self.scheme == "rim"
        inertia = self.inertia
        damping = self.damping
        follow_lag = self.follow_lag
        bounds = self.bounds
        fires = self.fires
        fire_button = self.fire_button
        fire_sound = self.fire_sound
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self._advance(live[index], joy, speed_x, speed_y, rim, inertia,
                          damping, follow_lag, bounds, fires, fire_button,
                          fire_sound)
            index += 1

    def step_one(self, sprite):
        self._advance(sprite, self._joy, self.speed_x, self.speed_y,
                      self.scheme == "rim", self.inertia, self.damping,
                      self.follow_lag, self.bounds, self.fires,
                      self.fire_button, self.fire_sound)


# -----------------------------------------------------------------------
# Aiming -- a crosshair, not steering.
# -----------------------------------------------------------------------

class Aiming(Behavior):
    """A crosshair: an internal cartesian stick position, nudged by
    ``speed`` per tick per held direction and clamped to the unit disc,
    converted into this subject's own layer's terms through ``atan2``
    (:meth:`~vs2.Layer.polar`'s own angle), ``sqrt``
    (:meth:`~vs2.Layer.polar`'s own radius) and the layer's inverse
    projection (:meth:`~vs2.Layer.to_depth`) -- three operations, and the
    reason this sits beside :class:`Pilotable` rather than folding into
    it: a crosshair points *at a place on the disc*, it does not steer a
    thing around it.

    Does **not** collapse into :func:`_guard_absolute_position`'s
    conflict check: unlike ``PathFollowing``/``Laned``/bounded
    ``Pilotable``, its own ``dx``/``dy`` contribution is already "the
    entire delta to this tick's aim point" (the same shape
    :class:`~vs2.actions.MoveTo` already establishes as safe to write
    through the accumulator), so a second movement composing with it is
    unusual but not a conflict the framework needs to forbid.

    ``bounds``, when given, is ``(radius_min, radius_max)`` on the aim
    disc itself (either may be ``None``) -- a minimum and/or maximum reach
    for the crosshair, distinct from :class:`Pilotable`'s own ``bounds``
    (a world-space box), since here there is no absolute position to
    fence in, only how far out the stick may point.
    """

    player = Choice(1, options=(1, 2), label="Player")
    speed = Number(0.05, min=0, max=1, step=0.01, label="Aim speed")
    bounds = Points(None, label="Bounds (radius_min, radius_max)")
    fires = PoolRef(None, label="Fires from")
    fire_button = Choice(controls.A, options=(controls.A, controls.B, controls.X),
                          label="Fire button")
    fire_sound = Sound(None, label="Fire sound")

    #: The virtual stick position, cartesian, clamped to the unit disc.
    state = ("aim_x", "aim_y")

    def attached(self, subject):
        self._joy = controls.joy1 if self.player == 1 else controls.joy2
        self._layer = subject.layer

    def _advance(self, sprite, joy, step, bounds, layer, fires, fire_button,
                 fire_sound):
        ax = sprite.aim_x
        ay = sprite.aim_y
        if joy.held(controls.RIGHT):
            ax += step
        if joy.held(controls.LEFT):
            ax -= step
        if joy.held(controls.DOWN):
            ay += step
        if joy.held(controls.UP):
            ay -= step
        magnitude = sqrt(ax * ax + ay * ay)
        if magnitude > 1.0:
            ax /= magnitude
            ay /= magnitude
            magnitude = 1.0
        if bounds is not None and magnitude > 0.0:
            radius_min, radius_max = bounds
            clamped = magnitude
            if radius_min is not None and clamped < radius_min:
                clamped = radius_min
            if radius_max is not None and clamped > radius_max:
                clamped = radius_max
            if clamped != magnitude:
                scale = clamped / magnitude
                ax *= scale
                ay *= scale
        sprite.aim_x = ax
        sprite.aim_y = ay
        angle, radius = layer.polar(ax, ay)
        if radius > 1.0:
            radius = 1.0
        row = radius * (display.height - 1)
        depth = layer.to_depth(row)
        sprite.dx += actions._wrapped_delta(sprite.x, angle)
        sprite.dy += depth - sprite.y
        _maybe_fire(joy, fires, fire_button, fire_sound, sprite)

    def step(self, sprites):
        joy = self._joy
        step = self.speed
        bounds = self.bounds
        layer = self._layer
        fires = self.fires
        fire_button = self.fire_button
        fire_sound = self.fire_sound
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self._advance(live[index], joy, step, bounds, layer, fires,
                          fire_button, fire_sound)
            index += 1

    def step_one(self, sprite):
        self._advance(sprite, self._joy, self.speed, self.bounds,
                      self._layer, self.fires, self.fire_button,
                      self.fire_sound)


# -----------------------------------------------------------------------
# Chasing -- turn-limited pursuit of the nearest live target.
# -----------------------------------------------------------------------

class Chasing(Behavior):
    """Homes toward the nearest live member of ``target`` (a
    :class:`~vs2.Sprite`, :class:`~vs2.SpritePool` or :class:`~vs2.Family`)
    at up to ``speed_x``/``speed_y`` per tick, turning its own heading
    toward the target by at most ``turn_rate`` radians per tick rather
    than snapping straight at it the way :class:`~vs2.actions.MoveTo`
    would -- a turning circle, not a magnet. Composes through ``dx``/``dy``
    like :class:`Moving`; it is not an absolute-position movement.

    Gives up (contributes nothing this tick) once the nearest candidate is
    farther than ``give_up_range``, and calls ``on_reach`` the tick it
    physically overlaps whatever it caught (:meth:`~vs2.Sprite.overlaps`),
    latched so it fires once per approach rather than every tick the two
    stay touching.
    """

    speed_x = Angle(2, min=0, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(2, min=0, max=32, step=0.25,
                      label="Radial speed", unit="led/tick")
    turn_rate = Number(0.15, min=0, max=pi, step=0.01,
                         label="Turn rate", unit="rad/tick")
    give_up_range = Number(255, min=0, max=1000, step=1,
                             label="Give-up range")
    on_reach = Callback(None, label="On reach")

    #: chase_heading: this sprite's own current direction of travel, in
    #: radians -- the state turn_rate limits the per-tick change of.
    #: chase_reached: latch so on_reach fires once per approach.
    state = ("chase_heading", "chase_reached")

    def __init__(self, target, **kwargs):
        Behavior.__init__(self, **kwargs)
        self.target = target

    def attached(self, subject):
        target = self.target
        if isinstance(target, Family):
            pools = []
            sprites_ = []
            for kind, member in target._members:
                if kind == "pool":
                    pools.append(member)
                else:
                    sprites_.append(member)
            self._target_pools = tuple(pools)
            self._target_sprites = tuple(sprites_)
            self._target_sprite = None
        elif isinstance(target, SpritePool):
            self._target_pools = (target,)
            self._target_sprites = ()
            self._target_sprite = None
        elif isinstance(target, Sprite):
            self._target_pools = ()
            self._target_sprites = ()
            self._target_sprite = target
        else:
            raise TypeError(
                "Chasing: target must be a Sprite, SpritePool or Family; "
                "got %r" % (target,))

    def _nearest(self, sprite):
        if self._target_sprite is not None:
            return self._target_sprite
        best = None
        best_dist = None
        pools = self._target_pools
        pool_index = 0
        pool_count = len(pools)
        while pool_index < pool_count:
            live = pools[pool_index]._live
            candidate_index = 0
            candidate_count = len(live)
            while candidate_index < candidate_count:
                candidate = live[candidate_index]
                dx = actions._wrapped_delta(sprite.x, candidate.x)
                dy = candidate.y - sprite.y
                dist = dx * dx + dy * dy
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best = candidate
                candidate_index += 1
            pool_index += 1
        sprites_ = self._target_sprites
        sprite_index = 0
        sprite_count = len(sprites_)
        while sprite_index < sprite_count:
            candidate = sprites_[sprite_index]
            dx = actions._wrapped_delta(sprite.x, candidate.x)
            dy = candidate.y - sprite.y
            dist = dx * dx + dy * dy
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = candidate
            sprite_index += 1
        return best

    def _advance(self, sprite, speed_x, speed_y, turn_rate, give_up_range,
                 on_reach):
        candidate = self._nearest(sprite)
        if candidate is None:
            return
        delta_x = actions._wrapped_delta(sprite.x, candidate.x)
        delta_y = candidate.y - sprite.y
        distance = sqrt(delta_x * delta_x + delta_y * delta_y)
        if distance > give_up_range:
            sprite.chase_reached = 0
            return
        desired = atan2(delta_y, delta_x)
        heading = sprite.chase_heading
        diff = (desired - heading + pi) % (2 * pi) - pi
        if diff > turn_rate:
            diff = turn_rate
        elif diff < -turn_rate:
            diff = -turn_rate
        heading += diff
        sprite.chase_heading = heading
        sprite.dx += cos(heading) * speed_x
        sprite.dy += sin(heading) * speed_y
        if sprite.overlaps(candidate):
            if not sprite.chase_reached:
                sprite.chase_reached = 1
                if on_reach is not None:
                    on_reach(sprite, candidate)
        else:
            sprite.chase_reached = 0

    def step(self, sprites):
        speed_x = self.speed_x
        speed_y = self.speed_y
        turn_rate = self.turn_rate
        give_up_range = self.give_up_range
        on_reach = self.on_reach
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self._advance(live[index], speed_x, speed_y, turn_rate,
                          give_up_range, on_reach)
            index += 1

    def step_one(self, sprite):
        self._advance(sprite, self.speed_x, self.speed_y, self.turn_rate,
                      self.give_up_range, self.on_reach)


# -----------------------------------------------------------------------
# Orbiting -- circular motion, native to this display's own coordinates.
# -----------------------------------------------------------------------

class Orbiting(Behavior):
    """Circular motion, expressed in this display's own polar terms
    rather than reinvented in cartesian ones: ``x`` is already the angle
    around the disc and ``y`` is already the radius (see the proposal's
    "## Layers" -> "### Cameras"), so an orbit needs no trigonometry at
    all. A constant angular velocity (``speed``, added into ``dx`` every
    tick like :class:`Moving`'s own ``speed_x``) carries the sprite around
    the disc, while ``y`` is pulled to exactly ``centre_y`` -- the orbit's
    radius -- every tick, so a sprite that spawns off-radius snaps onto
    the orbit on its very first Step rather than drifting toward it.
    Composes through ``dx``/``dy`` like any other accumulating movement.
    """

    centre_y = Number(0, min=0, max=255, step=0.25,
                        label="Orbit radius", unit="led")
    speed = Angle(2, min=-32, max=32, step=0.25,
                  label="Angular speed", unit="col/tick")

    def attached(self, subject):
        self.move = self.action(actions.Move(speed_x=self.speed, speed_y=0))

    def _pull(self, sprite, centre_y):
        sprite.dy += centre_y - sprite.y

    def step(self, sprites):
        self.move.run(sprites)
        centre_y = self.centre_y
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self._pull(live[index], centre_y)
            index += 1

    def step_one(self, sprite):
        self.move.run_one(sprite)
        self._pull(sprite, self.centre_y)


# -----------------------------------------------------------------------
# Laned -- absolute position: snaps between a fixed set of depth lanes.
# -----------------------------------------------------------------------

class Laned(Behavior):
    """Confines the radial (``y``) position to one of a fixed set of lane
    centres, easing toward the current lane at up to ``speed`` per tick --
    a highway/elevator mechanic (concentric rings at fixed depths, rather
    than the angular "rim" a :class:`Pilotable` scheme locks onto). One of
    the three absolute-position movements (see
    :func:`_guard_absolute_position`): it owns ``y`` outright, so a second
    absolute-position movement on the same subject is a build-time error
    naming both -- but it leaves ``x`` alone entirely, so composing it
    with an accumulating movement that drives ``x`` (:class:`Moving`'s
    ``speed_x``, say, for constant forward drift around the disc while
    hopping between depth lanes) is exactly the intended use.

    Switching lanes is the game's own call, not an input this Behavior
    reads: set ``sprite.lane_index`` (an int index into ``centres``) and
    the next tick eases toward the new centre, firing ``on_change`` (a
    callback, given ``sprite`` and the new index) the tick it arrives.
    """

    centres = Points((0,), label="Lane centres (depth)")
    speed = Number(4, min=0, max=32, step=0.25,
                    label="Lane-change speed", unit="led/tick")
    on_change = Callback(None, label="On lane arrival")

    #: lane_arrived_at: which lane index (encoded as index+1, so the
    #: priming-to-0 default reads as "never arrived anywhere yet" without
    #: colliding with the real index 0) on_change was last fired for --
    #: a plain boolean latch is not enough here, because the game may
    #: reassign lane_index directly (see the class docstring) to a lane
    #: close enough to reach in the very next tick, and a same-tick
    #: "already arrived" boolean left over from the *previous* lane would
    #: wrongly suppress that new arrival's own on_change.
    state = ("lane_index", "lane_arrived_at")

    def attached(self, subject):
        _guard_absolute_position(subject, self)
        centres = tuple(self.centres)
        if not centres:
            raise ValueError("Laned needs at least one lane in centres=")
        self._centres = centres

    def _advance(self, sprite, speed, on_change):
        centres = self._centres
        index = sprite.lane_index
        if index < 0 or index >= len(centres):
            index = 0
            sprite.lane_index = 0
        target_y = centres[index]
        delta_y = target_y - sprite.y
        step_y = actions._clamp_step(delta_y, speed)
        sprite.dy += step_y
        if step_y == delta_y:
            marker = index + 1
            if sprite.lane_arrived_at != marker:
                sprite.lane_arrived_at = marker
                if on_change is not None:
                    on_change(sprite, index)

    def step(self, sprites):
        speed = self.speed
        on_change = self.on_change
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self._advance(live[index], speed, on_change)
            index += 1

    def step_one(self, sprite):
        self._advance(sprite, self.speed, self.on_change)
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
