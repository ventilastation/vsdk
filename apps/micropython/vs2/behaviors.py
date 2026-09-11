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
