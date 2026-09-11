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
