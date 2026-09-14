"""VS2 Actions: the reusable, parameterised units of per-tick work.

An :class:`Action` is a small parameterised object -- ``Move(speed_x=2)``,
``Collide(targets=self.baddies)`` -- that a game or a :class:`~vs2.Behavior`
(a later task) runs against sprites every tick. Two call forms exist because
they cost differently, and a :class:`~vs2.Behavior` needs both:

``action.run(sprites)``
    Column-wise: apply to every live sprite in a :class:`~vs2.SpritePool`,
    with any uniform parameter reads hoisted once per call rather than once
    per sprite. This is the fast tier, and the reason this module exists --
    see ``### What the dispatch shape costs`` in the proposal for the
    measurements.

``action.run_one(sprite)``
    Per-sprite: apply to exactly one sprite. This is what a Behavior's own
    per-sprite decision loop calls when it branches -- skipping some
    sprites, applying different Actions to different sprites -- and it
    costs the price of that flexibility (measured at roughly 42% over the
    column-wise form on MicroPython).

**Results.** ``run_one()`` returns ``None`` when nothing notable happened,
:data:`vs2.DONE` when a durative Action finished this tick (``MoveTo``
arrived, ``Animate`` completed a ``once`` cycle), or an object it found
(``Collide`` returns the sprite hit). ``run()`` returns nothing -- only the
per-sprite form reports a result, which is also why a durative Action or one
that reports a hit is normally driven through ``run_one()`` inside a
Behavior's per-sprite loop, not through ``run()``.

**Traversal is indexed, always.** Every loop in this module walks
``pool._live`` (or a target's own cached tuple) with an indexed ``while``,
never ``for sprite in pool`` -- see the module docstring convention shared
across ``vs2`` -- so no Action here allocates an iterator.

**Movement accumulates; the framework commits.** ``Move`` and ``MoveTo``
write into ``sprite.dx``/``sprite.dy``, never ``sprite.x``/``sprite.y``
directly. :meth:`vs2.Scene._commit_pool_motion` applies the accumulator to
position once per pool per tick and zeros it, so two movement Actions
composed on one subject add rather than fight.

**``field=``.** An Action that writes a scalar other than position takes
``field=``, naming the attribute it writes -- a built-in one (``frame``) or
an instance variable declared with :meth:`~vs2.SpritePool.var`. ``Move`` and
``MoveTo`` are the exception: position is special-cased as the ``dx``/``dy``
accumulator, so neither exposes a ``field=`` at all.

**``Var``-bound parameters force the per-sprite path.** A literal parameter
value can be hoisted once per ``run()`` call; a :class:`~vs2.params.Var`
value names a per-sprite instance variable and has to be read fresh for
every sprite, so any Action holding one falls back to the same per-sprite
loop ``run_one()`` uses, forwarding its own base-class ``run()`` rather than
hoisting a value that was never a single literal to begin with.
"""

from . import DONE, Family, Layer, Sprite, SpritePool, display
from . import _intersects_circular
from . import params as _params
from .params import Angle, Choice, Frames, Number, Var


def _any_var(*values):
    """True if any of ``values`` is a :class:`~vs2.params.Var` binding."""
    index = 0
    count = len(values)
    while index < count:
        if isinstance(values[index], Var):
            return True
        index += 1
    return False


def _resolve(value, sprite):
    """A parameter's effective value for ``sprite`` this tick: the literal
    unchanged, or the named instance variable read off ``sprite`` if it is
    :class:`~vs2.params.Var`-bound."""
    if isinstance(value, Var):
        return getattr(sprite, value.name)
    return value


def _wrapped_delta(a, b):
    """The shortest signed distance from ``a`` to ``b`` around the display's
    circular X axis: negative if the shorter arc runs backward, positive
    forward, in ``(-width/2, width/2]``."""
    width = display.width
    delta = (b - a) % width
    if delta > width / 2:
        delta -= width
    return delta


def _clamp_step(delta, speed):
    """``delta`` clamped to at most ``abs(speed)`` in either direction --
    the per-tick step :class:`MoveTo` takes toward its target, sized so it
    never overshoots."""
    max_step = speed if speed >= 0 else -speed
    if delta > max_step:
        return max_step
    if delta < -max_step:
        return -max_step
    return delta


def _past_or_at(step, value, boundary):
    """Whether ``value`` has reached or passed ``boundary`` walking in the
    direction of ``step`` (positive or negative)."""
    if step > 0:
        return value >= boundary
    return value <= boundary


def _layer_label(layer):
    name = getattr(layer, "name", None)
    return name if name else "unnamed"


def _layer_of(subject):
    """The single :class:`~vs2.Layer` a Collide subject or target belongs
    to -- a :class:`~vs2.Sprite`, :class:`~vs2.SpritePool` or
    :class:`~vs2.Family` all expose ``.layer``."""
    if isinstance(subject, (Sprite, SpritePool, Family)):
        return subject.layer
    raise TypeError(
        "must be a Sprite, SpritePool or Family; got %r" % (subject,))


class Action:
    """Base class for every Action.

    Subclasses declare their parameters as class-level
    :class:`~vs2.params.Parameter` attributes (the same descriptor system
    :class:`~vs2.Behavior` uses), and this base class's ``__init__`` binds
    keyword arguments against them via :func:`vs2.params.init_params`.

    Override :meth:`run` when hoisting a uniform parameter read saves
    something (see :class:`Move`); the default here is always correct, just
    not the fast tier.
    """

    def __init__(self, **kwargs):
        _params.init_params(self, kwargs)

    def run(self, sprites):
        """Apply this Action to every live sprite in ``sprites`` (a
        :class:`~vs2.SpritePool`). Any per-sprite result :meth:`run_one`
        would have returned is discarded -- callers that need results call
        :meth:`run_one` themselves in their own per-sprite loop.

        The default here is a plain indexed walk over ``sprites._live``,
        downward so a ``run_one`` that despawns its sprite stays safe. It
        allocates nothing and never assumes ``run_one`` is side-effect-free,
        which is why it does not try to be clever about order.
        """
        live = sprites._live
        index = len(live) - 1
        while index >= 0:
            self.run_one(live[index])
            index -= 1

    def run_one(self, sprite):
        """Apply this Action to one sprite. Returns ``None`` when nothing
        notable happened, :data:`vs2.DONE` when a durative Action finished,
        or an object it found. Override in every concrete Action."""
        return None


class Move(Action):
    """Constant velocity, with optional acceleration. Writes into
    ``sprite.dx``/``sprite.dy`` -- never ``sprite.x``/``sprite.y`` directly
    -- so it composes with any other movement Action on the same subject.

    Acceleration is Action-level, shared state (``self.speed_x``/
    ``self.speed_y`` themselves creep every tick), not per-sprite, and is
    only ever advanced from :meth:`run`, once per call -- never from
    :meth:`run_one`, which may be called anywhere from zero to once per live
    sprite in a single tick by a Behavior's own per-sprite loop, and would
    otherwise apply acceleration that many times over. A literal
    non-zero ``accel_x``/``accel_y`` therefore requires literal (non-
    ``Var``) ``speed_x``/``speed_y`` -- there is no single value on ``self``
    to accelerate when speed is read per sprite instead -- and ``accel_x``/
    ``accel_y`` themselves may never be ``Var``-bound.

    ``run`` itself is chosen once, at construction, between three bodies
    (plain, accelerating, or the ``Var``-bound per-sprite fallback) and
    stored as a plain instance attribute -- the same non-data-descriptor
    shadowing trick :mod:`vs2.params` uses for parameters, applied to a
    method instead of an attribute. This is not just tidiness: measured on
    the MicroPython unix port, merely having the accel bookkeeping's two
    extra attribute reads reachable in ``run``'s own bytecode cost ~12% on
    every call *even for a pool that never uses acceleration* (verified by
    isolating it down to those two reads alone; see this task's report for
    the numbers). Splitting the bodies so the common, uniform, no-frills
    case never has that code in its own call at all makes the column-wise
    path exactly the worked example's cost again -- confirmed at parity
    (within noise) on the same interpreter.
    """

    speed_x = Angle(0, min=-32, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(0, min=-32, max=32, step=0.25,
                      label="Radial speed", unit="led/tick")
    accel_x = Angle(0, min=-8, max=8, step=0.05,
                    label="Angular acceleration", unit="col/tick^2")
    accel_y = Number(0, min=-8, max=8, step=0.05,
                      label="Radial acceleration", unit="led/tick^2")

    def __init__(self, **kwargs):
        Action.__init__(self, **kwargs)
        if isinstance(self.accel_x, Var) or isinstance(self.accel_y, Var):
            raise ValueError("Move: accel_x/accel_y cannot be Var-bound")
        self._uses_var = (isinstance(self.speed_x, Var)
                           or isinstance(self.speed_y, Var))
        if self._uses_var and (self.accel_x or self.accel_y):
            raise ValueError(
                "Move: accel_x/accel_y requires literal (non-Var) "
                "speed_x/speed_y")
        if self._uses_var:
            self.run = self._run_var
        elif self.accel_x or self.accel_y:
            self.run = self._run_accel
        else:
            self.run = self._run_plain

    def _run_plain(self, sprites):
        """The column-wise path for the common case: literal, unchanging
        speed. Byte-for-byte the worked example's loop -- no acceleration
        bookkeeping is reachable from here at all."""
        dx = self.speed_x
        dy = self.speed_y
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            sprite = live[index]
            sprite.dx += dx
            sprite.dy += dy
            index += 1

    def _run_accel(self, sprites):
        """Same loop, plus the once-per-call acceleration update -- chosen
        instead of :meth:`_run_plain` only when accel is actually
        configured, so that cost is never paid by a pool that does not use
        it."""
        dx = self.speed_x
        dy = self.speed_y
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            sprite = live[index]
            sprite.dx += dx
            sprite.dy += dy
            index += 1
        self.speed_x += self.accel_x
        self.speed_y += self.accel_y

    def _run_var(self, sprites):
        """The per-sprite fallback :meth:`Action.run` would give us
        anyway, spelled out here so ``self.run`` can be assigned uniformly
        in ``__init__`` rather than left unset for this one case."""
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self.run_one(live[index])
            index += 1

    def run_one(self, sprite):
        """Apply to one sprite, for a Behavior that branches per sprite."""
        sprite.dx += _resolve(self.speed_x, sprite)
        sprite.dy += _resolve(self.speed_y, sprite)
        return None


class MoveTo(Action):
    """Move toward an absolute position at up to ``speed_x``/``speed_y``
    per tick, writing into ``sprite.dx``/``sprite.dy`` like :class:`Move`.
    Returns :data:`vs2.DONE` (from :meth:`run_one`) the tick a sprite's
    step exactly closes the remaining distance -- it never overshoots.

    ``x`` wraps the shorter way around the display's circular axis; ``y``
    does not, matching :attr:`vs2.Sprite.y`'s own non-wrapping depth/LED
    axis.

    Stateless per call, deliberately: it holds no per-sprite "already
    reported arrival" latch, since one ``MoveTo`` instance is routinely
    applied to many different sprites converging on the same target (a
    shared latch on the Action itself would be wrong for exactly the
    reason :class:`Move`'s acceleration must *not* be shared per sprite).
    So it keeps returning :data:`vs2.DONE` for as long as a sprite sits
    exactly on the target -- a Behavior that must act once reacts the tick
    it first sees ``DONE`` and then typically stops calling this Action
    for that sprite (despawning it, switching its state, or picking a new
    target).
    """

    x = Angle(0, label="Target angle", unit="col")
    y = Number(0, label="Target depth", unit="led")
    speed_x = Angle(0, min=0, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(0, min=0, max=32, step=0.25,
                      label="Radial speed", unit="led/tick")

    def __init__(self, **kwargs):
        Action.__init__(self, **kwargs)
        self._uses_var = _any_var(self.x, self.y, self.speed_x, self.speed_y)
        # Same instance-attribute dispatch as Move, for the same reason:
        # keep the common (literal) case's bytecode free of anything the
        # Var-bound fallback needs.
        self.run = self._run_var if self._uses_var else self._run_plain

    def _run_plain(self, sprites):
        target_x = self.x
        target_y = self.y
        speed_x = self.speed_x
        speed_y = self.speed_y
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            sprite = live[index]
            step_x = _clamp_step(_wrapped_delta(sprite.x, target_x), speed_x)
            step_y = _clamp_step(target_y - sprite.y, speed_y)
            sprite.dx += step_x
            sprite.dy += step_y
            index += 1

    def _run_var(self, sprites):
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            self.run_one(live[index])
            index += 1

    def run_one(self, sprite):
        target_x = _resolve(self.x, sprite)
        target_y = _resolve(self.y, sprite)
        speed_x = _resolve(self.speed_x, sprite)
        speed_y = _resolve(self.speed_y, sprite)
        delta_x = _wrapped_delta(sprite.x, target_x)
        delta_y = target_y - sprite.y
        step_x = _clamp_step(delta_x, speed_x)
        step_y = _clamp_step(delta_y, speed_y)
        sprite.dx += step_x
        sprite.dy += step_y
        if step_x == delta_x and step_y == delta_y:
            return DONE
        return None


class Animate(Action):
    """Step a frame index from ``first`` to ``last`` over ``ticks`` ticks
    per frame, writing it to ``field`` (defaulting to ``"frame"``, so a
    plain ``Animate(first=0, last=3, ticks=8)`` drives ``sprite.frame`` the
    way a hand-written animation counter would).

    ``mode`` is ``"loop"`` (wrap back to ``first`` forever, the default),
    ``"once"`` (hold on ``last`` and return :data:`vs2.DONE` from
    :meth:`run_one` the tick it gets there), or ``"pingpong"`` (bounce
    between ``first`` and ``last`` forever). ``first`` may be greater than
    ``last`` to play backward.

    The clock -- elapsed ticks toward the next frame, the current frame,
    and ``pingpong``'s direction -- is Action-level state, advanced exactly
    once per :meth:`run` call, the same reasoning as :class:`Move`'s
    acceleration: it must change once per tick, not once per sprite, so
    every live sprite driven by one ``Animate`` instance shares one clock
    and shows the same frame in the same tick (a squad animating in
    lockstep). :meth:`run_one` never advances the clock -- it writes
    whatever frame the most recent :meth:`run` computed, and returns that
    same tick's result, so a Behavior branching per sprite can still see
    ``DONE`` without the clock racing ahead. Because of this, ``first``/
    ``last``/``ticks``/``mode`` may not be ``Var``-bound: a truly
    independent per-sprite clock needs per-sprite state this Action does
    not keep (that is a richer catalog Behavior's job, layered on top).
    """

    first = Frames(0, label="First frame")
    last = Frames(0, label="Last frame")
    ticks = Number(1, min=1, step=1, label="Ticks per frame", unit="tick")
    mode = Choice("loop", options=("loop", "once", "pingpong"), label="Mode")

    def __init__(self, field="frame", **kwargs):
        if not isinstance(field, str):
            raise TypeError(
                "Animate: field must be a string naming an attribute; "
                "got %r" % (field,))
        self.field = field
        Action.__init__(self, **kwargs)
        if _any_var(self.first, self.last, self.ticks, self.mode):
            raise ValueError(
                "Animate: first/last/ticks/mode must be literal, not "
                "Var-bound -- this Action's clock is shared per instance, "
                "not per sprite")
        self._frame = self.first
        self._elapsed = 0
        self._direction = 1
        self._done_latched = False
        self._last_result = None

    def _advance(self):
        first = self.first
        last = self.last
        self._last_result = None
        if first == last:
            self._frame = first
            return
        self._elapsed += 1
        if self._elapsed < self.ticks:
            return
        self._elapsed = 0
        step = 1 if last > first else -1
        mode = self.mode
        if mode == "once":
            if self._done_latched:
                return
            self._frame += step
            if _past_or_at(step, self._frame, last):
                self._frame = last
                self._done_latched = True
                self._last_result = DONE
        elif mode == "pingpong":
            self._frame += step * self._direction
            if self._direction > 0 and _past_or_at(step, self._frame, last):
                self._frame = last
                self._direction = -1
            elif self._direction < 0 and _past_or_at(-step, self._frame, first):
                self._frame = first
                self._direction = 1
        else:  # "loop"
            self._frame += step
            if step > 0 and self._frame > last:
                self._frame = first
            elif step < 0 and self._frame < last:
                self._frame = first

    def run(self, sprites):
        # Write the frame this tick displays *before* advancing the clock --
        # so the very first call shows ``first`` rather than skipping ahead
        # to whatever comes after it, and each later call shows the frame
        # scheduled by the *previous* tick's advance, held for exactly
        # ``ticks`` calls.
        frame_value = self._frame
        field = self.field
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            setattr(live[index], field, frame_value)
            index += 1
        self._advance()

    def run_one(self, sprite):
        setattr(sprite, self.field, self._frame)
        return self._last_result


class Collide(Action):
    """Whether the subject sprite overlaps anything in ``targets`` (a
    :class:`~vs2.Sprite`, :class:`~vs2.SpritePool` or :class:`~vs2.Family`),
    tested in world space -- the coordinate system ``sprite.x``/``sprite.y``
    are already stored in, box-versus-box by default, or a circular test
    when ``radius=`` is given. Same-layer only: ``targets`` and the subject
    Collide is actually run against must share one :class:`~vs2.Layer`, and
    a mismatch is an error naming both, since a box test comparing two
    different projection curves is not meaningful (see the proposal's
    *Collision* section). ``space="screen"`` is an explicit escape hatch
    that instead compares each sprite's rendered LED row (through the
    layer's curve, so precision is lost near a tunnel's centre) -- ``world``
    is correct on every layer, including HUD, where the two are identical.

    ``run_one()`` returns the first sprite ``targets`` hit, or ``None``.

    The same-layer check runs once, the first time :meth:`run` or
    :meth:`run_one` is actually invoked for a subject (or immediately, at
    construction, if ``subject=`` is passed) -- after that it is cached and
    every later call skips it entirely, so a scene that never misuses this
    pays nothing for the check once it is past its first tick.
    """

    def __init__(self, targets, radius=None, space="world", subject=None):
        self.radius = radius
        if space not in ("world", "screen"):
            raise ValueError(
                "Collide: space must be 'world' or 'screen'; got %r" % (space,))
        self.space = space
        self._resolve_targets(targets)
        self._subject_layer = None
        if subject is not None:
            self._bind_subject(_layer_of(subject))

    def _resolve_targets(self, targets):
        if isinstance(targets, Family):
            self._target_layer = targets.layer
            pools = []
            sprites = []
            for kind, member in targets._members:
                if kind == "pool":
                    pools.append(member)
                else:
                    sprites.append(member)
            self._target_pools = tuple(pools)
            self._target_sprites = tuple(sprites)
        elif isinstance(targets, SpritePool):
            self._target_layer = targets.layer
            self._target_pools = (targets,)
            self._target_sprites = ()
        elif isinstance(targets, Sprite):
            self._target_layer = targets.layer
            self._target_pools = ()
            self._target_sprites = (targets,)
        else:
            raise TypeError(
                "Collide: targets must be a Sprite, SpritePool or Family; "
                "got %r" % (targets,))

    def _bind_subject(self, layer):
        if layer is not self._target_layer:
            raise ValueError(
                "Collide targets are on layer %s but its subject is on "
                "layer %s; Collide only compares sprites on one layer"
                % (_layer_label(self._target_layer), _layer_label(layer)))
        self._subject_layer = layer

    def _y_for(self, sprite):
        if self.space == "screen":
            return self._target_layer.to_row(sprite.y)
        return sprite.y

    def _hits(self, x1, y1, w1, h1, sprite, candidate):
        if candidate is sprite:
            return False
        x2 = candidate.x
        y2 = self._y_for(candidate)
        radius = self.radius
        if radius is not None:
            delta_x = _wrapped_delta(x1, x2)
            delta_y = y1 - y2
            return (delta_x * delta_x + delta_y * delta_y) <= radius * radius
        w2 = candidate.width
        h2 = candidate.height
        return (_intersects_circular(x1, w1, x2, w2)
                and y1 < y2 + h2 and y1 + h1 > y2)

    def run_one(self, sprite):
        if self._subject_layer is None:
            self._bind_subject(sprite.layer)
        x1 = sprite.x
        y1 = self._y_for(sprite)
        w1 = sprite.width
        h1 = sprite.height
        pools = self._target_pools
        pool_index = 0
        pool_count = len(pools)
        while pool_index < pool_count:
            live = pools[pool_index]._live
            candidate_index = 0
            candidate_count = len(live)
            while candidate_index < candidate_count:
                candidate = live[candidate_index]
                if self._hits(x1, y1, w1, h1, sprite, candidate):
                    return candidate
                candidate_index += 1
            pool_index += 1
        sprites = self._target_sprites
        sprite_index = 0
        sprite_count = len(sprites)
        while sprite_index < sprite_count:
            candidate = sprites[sprite_index]
            if self._hits(x1, y1, w1, h1, sprite, candidate):
                return candidate
            sprite_index += 1
        return None

    def run(self, sprites):
        if self._subject_layer is None:
            self._bind_subject(sprites.layer)
        live = sprites._live
        index = len(live) - 1
        while index >= 0:
            self.run_one(live[index])
            index -= 1
