"""Vyruss VS2: hand-written game logic.

This is T18's port of games/alecu/vyruss_vs2/code/vyruss_vs2.py, following
the exact T15 "scene editor / build() generator" precedent
games/vs2_examples/vixeous/code/vixeous.py already proved: the declarative
object graph (layers, sprite pools, sprites, Behaviors) that the original
build() constructed by hand now lives in vyruss_vs2_scene.vs2model.json
and is generated into vyruss_vs2_scene.py by tools/vs2_scene_gen.
Everything with control flow -- input, collision, scoring, level
progression, the player's explode/respawn/game-over sequence -- stays
hand-written here, exactly as the original update() and its helpers
always were. **Updated 2026-09-14**: the baddie entrance choreography's
fixed five-phase part (formerly TravelCloser/TravelX/TravelAway, popped
off a per-baddie queue by hand) is now BaddieFormation, a real generated
Behavior (build_baddie_formation.py) -- see the "baddies" bullet below
and that module's own docstring for exactly what moved and what (the
final TravelTo approach, and the runtime attack-run reassignment) is
still, deliberately, hand-written.

**Behavior-catalog mappings used, and what stayed hand-written -- see this
task's report for the full writeup:**

- ``laser`` (a 1-slot pool) and ``bombs``: plain constant-velocity motion
  plus a despawn-past-a-bound, the exact shape vixeous's own ``shots``/
  ``bombs`` pools already proved maps to ``Moving(speed_y=...)`` +
  ``DespawnBeyond(...)``. The hit-check itself (a laser overlapping a
  baddie, scoring and spawning an explosion with side effects beyond
  "despawn both") stays hand-written in :meth:`update_projectiles`, same
  reasoning vixeous's port gives for not forcing ``Projectile``/``Collide``
  -as-a-Behavior onto custom hit resolution.
- ``explosions`` (an ``on_empty=RECYCLE`` pool): the original's
  ``boom.age += 1; if age >= image.frames: despawn() else: frame = age``
  is the exact shape vixeous's port already proved maps to
  ``Transient(animate=True, ticks=<frame count>)`` (``explosion.png`` has
  5 frames, so ``ticks=5``). Same caveat vixeous's port documented:
  ``Transient``'s own ``transient_elapsed`` state is primed only at attach
  time, never reset by a ``RECYCLE`` pool's ``spawn()`` (a framework gap,
  not something this port works around) -- and note a second, smaller
  divergence this port found: ``Transient``'s per-tick frame math
  (``frame = elapsed * frames // ticks``, checked *after* incrementing
  elapsed) shows frame 1 on an explosion's very first tick, never frame 0,
  where the original's ``age``-indexed loop always showed frame 0 first.
  Cosmetically negligible at 5 frames, but real -- not hidden here.
- ``baddies``: the original's queue of heterogeneous movement-strategy
  objects (``TravelTo``/``TravelX``/``TravelCloser``/``TravelAway``,
  popped off ``baddie.movements`` as each finishes) is a fundamentally
  different shape than the pre-existing catalog offers -- ``PathFollowing``
  is a *fixed* waypoint path attached once at build time, not a queue.
  **As of 2026-09-14, the fixed five-phase entrance part (everything
  except the final ``TravelTo`` approach) is instead ``BaddieFormation``**,
  a real generated ``StateMachine`` Behavior built from
  ``tools/vs2_behavior_gen``'s block-representable schema (see
  ``build_baddie_formation.py``'s own module docstring for the full
  design, including a real tick-by-tick parity proof against the
  original) -- attached in :meth:`on_build_5`. ``TravelTo`` itself (a
  "move *toward* a destination" primitive, not a fixed-distance walk)
  stays hand-written, as does the attack run's own runtime reassignment
  (``update_attacking``'s ``baddie.movements = [TravelCloser(...),
  TravelAway(...)]``) -- neither fits the shape ``BaddieFormation``
  covers, and forcing either in would not honestly represent the
  choreography, the same judgment call this bullet always made, now
  narrower than before.
- ``player_explosion`` (a single hidden sprite, not a pool): this looked
  at first like another ``Transient(animate=True, ticks=4)`` candidate
  (``explosion_nave.png`` has 4 frames, same "age-indexed frame, despawn
  at image.frames" shape as ``explosions``) -- but a Behavior attached to
  a lone :class:`~vs2.Sprite` subject has its ``step_one`` called every
  tick unconditionally, regardless of ``sprite.visible``
  (``vs2.Scene._run_behaviors``'s ``"sprite"`` branch), whereas this
  sprite is shown and hidden repeatedly by game logic (every time the
  player dies) rather than living in a pool that is only ever `spawn()`-ed
  when wanted. A ``Transient`` attached here would start counting down
  from the moment ``build()`` runs, expire once (calling ``hide()`` on an
  already-hidden sprite) long before the player's first death, and never
  fire again -- the catalog has no "dormant until shown" gate for a
  standalone sprite. So this stays hand-written, unlike ``explosions``:
  a second, and different, catalog mismatch from the one the module
  docstring above already covers.
- Collision resolution generally (``kill_baddie``, ``explode_player``,
  the player-vs-baddie/bomb checks in :meth:`update_player_collision`)
  stays hand-written for the same reason vixeous's port gives: it carries
  score, lives, explosion-spawning and state-transition side effects well
  beyond "despawn both", which is all ``Projectile``/``Collide``-as-a-
  -Behavior offer.
"""

from urandom import choice, randrange, seed
import utime

import vs2
from vs2.controls import A, DOWN, LEFT, RIGHT, UP, joy1

from games.vs2_examples.vyruss_vs2.code import vyruss_vs2_scene
from games.vs2_examples.vyruss_vs2.code.baddie_formation import BaddieFormation

LEVELS = (
    (2, "saturno.png", 3),
    (3, "jupiter.png", 4),
    (4, "marte.png", 6),
    (5, "tierra.png", 8),
)
MAX_BOMBS = max(level[2] for level in LEVELS)
MAX_GROUPS = max(level[0] for level in LEVELS)
BADDIES_PER_GROUP = 10
MAX_BADDIES = MAX_GROUPS * BADDIES_PER_GROUP
MAX_EXPLOSIONS = 8
X_SPEED = 3
Y_SPEED = 2
RIM_Y = -1
BADDIE_START_Y = 154
BADDIE_FINAL_Y = (119, 100, 81, 62)
LASER_FAR_Y = 164
PLANET_CENTER_Y = 255

ENTERING = 0
ATTACKING = 1
DEFEATED = 2


def heading(up, down, left, right):
    """Return the angular heading selected by the eight-way controls."""
    if up:
        return 128 if not left and not right else (96 if left else 160)
    if down:
        return 0 if not left and not right else (32 if left else 224)
    if left:
        return 64
    if right:
        return 192
    return None


def angle_delta(destination, current):
    """Shortest signed distance from ``current`` to ``destination``."""
    half = vs2.display.width // 2
    return ((destination - current + half) % vs2.display.width) - half


def turn_toward(current, destination):
    delta = angle_delta(destination, current)
    return -1 if delta < 0 else (1 if delta > 0 else 0)


def move_toward_angle(current, destination, speed):
    delta = angle_delta(destination, current)
    if abs(delta) <= speed:
        return destination % vs2.display.width
    return (current + (-speed if delta < 0 else speed)) % vs2.display.width


def move_toward_depth(current, destination, speed):
    delta = destination - current
    if abs(delta) <= speed:
        return destination
    return current + (-speed if delta < 0 else speed)


class TravelTo:
    """The one phase of the original baddie-formation choreography that
    stays hand-written -- see build_baddie_formation.py's own module
    docstring for why (a "move *toward* a destination" primitive, not a
    fixed-distance walk like the five phases BaddieFormation now owns)."""

    def __init__(self, x, y):
        self.dest_x = x
        self.dest_y = y

    def step(self, sprite):
        sprite.x = move_toward_angle(sprite.x, self.dest_x, X_SPEED)
        sprite.y = move_toward_depth(sprite.y, self.dest_y, Y_SPEED)

    def finished(self, sprite):
        return sprite.x == self.dest_x and sprite.y == self.dest_y


class TravelBy:
    """Still used by update_attacking()'s own runtime reassignment for an
    attack run -- a per-call *dynamic* distance, the reason that phase
    stays hand-written rather than reusing BaddieFormation's own
    closer1/away states (which always reset their travel distance from a
    fixed Behavior-level param on enter, not a value computed per call;
    see build_baddie_formation.py's own module docstring). TravelX itself
    (the entrance choreography's own sideways phases) has no remaining
    caller -- that part is BaddieFormation's xmove1/xmove2 now -- so only
    this base class plus TravelCloser/TravelAway are kept."""

    def __init__(self, count):
        self.remaining = abs(count)
        self.direction = -1 if count < 0 else 1

    def finished(self, _sprite):
        return self.remaining <= 0


class TravelCloser(TravelBy):
    def step(self, sprite):
        distance = min(Y_SPEED, self.remaining)
        sprite.y -= distance
        self.remaining -= distance


class TravelAway(TravelBy):
    def step(self, sprite):
        distance = min(Y_SPEED, self.remaining)
        sprite.y += distance
        self.remaining -= distance


class VyrussVs2(vyruss_vs2_scene.VyrussScene):
    BLINK_RATE = 45
    BLINK_FRAMES = {0: 0, 14: 1, 22: 2, 37: 3}

    def __init__(self):
        vyruss_vs2_scene.VyrussScene.__init__(self)
        seed(utime.ticks_ms())

    # -- build()-time hooks -------------------------------------------------
    # build() itself (layers, pools, sprites, Behaviors) is entirely
    # generated from vyruss_vs2_scene.vs2model.json; these numbered hooks
    # are where this hand-written subclass does the post-construction work
    # that format can't express.

    def on_build_0(self):
        # Right after the layers exist, before the planet sprite -- the
        # same bookkeeping the original build() set as its first three
        # lines, before it went on to create any layer.
        self.level = 0
        self.score = 0
        self.lives = 3

    def on_build_5(self):
        # Right after self.baddies exists, before explosions -- attaches
        # BaddieFormation, a real generated Behavior (games/vs2_examples/
        # vyruss_vs2/code/baddie_formation.py) that T15's scene-model
        # schema has no way to declare itself: tools/vs2_scene_gen's own
        # generator hardcodes "from vs2.behaviors import <classes>" for
        # every model-declared Behavior, and this one is not a catalog
        # class. Attaching by hand here is the same sanctioned escape
        # hatch games/vs2_examples/vasura_states_demo/code/
        # vasura_states_demo.py already uses for its own non-catalog
        # EnemyStates. See build_baddie_formation.py's own module
        # docstring for the full design and what still stays hand-written.
        self.baddies.behave(BaddieFormation(width=vs2.display.width))

    def on_build_9(self):
        # The last hook: right after game_over, before build() returns.
        # game_over.x depends on the display width, which the model's flat
        # value grammar cannot express -- the same reason vixeous's port
        # centers its own message/score_label here instead of in the
        # model. start_level() -- unchanged from the original -- takes it
        # from here exactly as the original build()'s own last line did.
        self.game_over.x = vs2.display.width - 32
        self.start_level()

    # -- game logic (unchanged from the original except where noted in
    # this module's own docstring) -----------------------------------------

    def start_level(self):
        self.waves, planet, self.simultaneous_bombs = LEVELS[self.level]
        self.planet.image = planet
        self.planet.hide()
        self.game_over.hide()
        self.player_explosion.hide()
        self.player.show()
        self.player.x = vs2.display.width - self.player.width // 2
        self.player.y = RIM_Y
        self.player.frame = 0
        self.player_frame_clock = -1
        self.player_exploded = False
        self.baddies.despawn_all()
        self.bombs.despawn_all()
        self.laser.despawn_all()
        self.explosions.despawn_all()
        self.everyone = []
        self.groups = [[]]
        self.attacking = []
        self.max_attacking = 1
        self.group_steps = 0
        self.num_baddies = 0
        self.next_bomb = 37
        self.state = ENTERING
        self.planet_animating = False
        self.ship_warping = False
        self.update_scoreboard()
        vs2.audio.music("vy-main")

    def update_scoreboard(self):
        self.scoreboard.set_number(self.score, width=5, pad="0")
        self.scoreboard.write(
            6, 0, "***"[:self.lives], pad=True)

    def add_baddie(self):
        final_x_positions = (
            0, 128, 55, 183, 18, 73, 146,
            201, 37, 91, 238, 110, 165, 219,
        )
        final_y_positions = BADDIE_FINAL_Y
        bases = (120, 216, 24, 248, 120)
        number = self.num_baddies
        final_x = final_x_positions[number % len(final_x_positions)]
        final_y = final_y_positions[number // len(final_x_positions)]
        self.num_baddies += 1
        frame = (self.num_baddies % 5) * 2 + 2
        base_x = bases[len(self.groups) - 1]
        odd = len(self.groups[-1]) % 2
        start_x = base_x + (16 if odd else -16)
        baddie = self.baddies.spawn(
            start_x, BADDIE_START_Y, frame=frame)
        if baddie is None:
            return
        baddie.base_frame = frame
        baddie.frame_clock = 0
        baddie.dead = False
        baddie.finished = False
        # The fixed five-phase entrance choreography (equivalent to the
        # original's own TravelCloser(85), TravelX(±112), TravelCloser(34),
        # TravelX(∓96), TravelAway(45)) now runs inside the BaddieFormation
        # Behavior attached in on_build_5 -- x_dir is the one input it
        # needs from spawn time (see build_baddie_formation.py's own
        # docstring for why xmove1/xmove2 derive opposite signs from this
        # single flag). final_x/final_y are kept on the sprite (the
        # original only ever needed them as TravelTo's own constructor
        # args) so update_one_baddie() can queue the hand-written final
        # approach once the Behavior reports formation_done.
        baddie.x_dir = 1 if odd else -1
        baddie.final_x = final_x
        baddie.final_y = final_y
        baddie.movements = None
        self.groups[-1].append(baddie)
        self.everyone.append(baddie)

    def update_one_baddie(self, baddie):
        if baddie.dead:
            return
        baddie.frame_clock += 1
        baddie.frame = (
            baddie.base_frame + (0 if baddie.frame_clock & 8 else 1)
        )
        if baddie.movements:
            # A hand-written queue is running -- either the final TravelTo
            # approach queued just below, or an attack run's own
            # TravelCloser/TravelAway pair (update_attacking()).
            baddie.finished = False
            movement = baddie.movements[0]
            movement.step(baddie)
            if movement.finished(baddie):
                baddie.movements.pop(0)
        elif baddie.movements is not None and not baddie.finished:
            # A hand-written queue (attack run or the final approach) just
            # drained -- matches the original's own "movements is an empty
            # list, not None" signal exactly (movements starts None here,
            # never an empty list, until something actually queues onto
            # it -- see add_baddie()'s own comment).
            baddie.finished = True
        elif baddie.movements is None and baddie.formation_done:
            # BaddieFormation's own entrance choreography just reported
            # done (one tick behind this method seeing it: Scene.scene_step
            # runs update() before _run_behaviors(), the same "checks the
            # position as of the start of this tick" lag vixeous.py's own
            # docstring already documents for Moving/DespawnBeyond -- real,
            # minor, not a bug). Queue the one phase that stays
            # hand-written, exactly the original's own TravelTo(final_x,
            # final_y) queue tail.
            baddie.movements = [TravelTo(baddie.final_x, baddie.final_y)]

    def group_finished(self):
        group = self.groups[-1]
        return bool(group) and all(
            baddie.dead or baddie.finished for baddie in group)

    def update_entering(self):
        for baddie in self.everyone:
            self.update_one_baddie(baddie)
        self.group_steps += 1
        if (self.group_steps % 8 == 0
                and len(self.groups[-1]) < BADDIES_PER_GROUP):
            self.add_baddie()
        if self.group_finished():
            self.group_steps = 0
            if len(self.groups) < self.waves:
                self.groups.append([])
            else:
                self.state = ATTACKING
        self.next_bomb -= 1
        if self.next_bomb <= 0:
            self.drop_bomb()
            self.next_bomb = 20 + randrange(30)

    def update_attacking(self):
        for baddie in self.everyone:
            self.update_one_baddie(baddie)
            if baddie.finished and baddie in self.attacking:
                self.attacking.remove(baddie)
                self.max_attacking += 1
        if not self.everyone:
            self.start_defeated()
            return
        if len(self.attacking) < self.max_attacking:
            baddie = choice(self.everyone)
            if baddie not in self.attacking:
                distance = max(0, baddie.y - RIM_Y)
                baddie.movements = [
                    TravelCloser(distance), TravelAway(distance)]
                baddie.finished = False
                self.attacking.append(baddie)
                self.drop_bomb()

    def start_defeated(self):
        self.state = DEFEATED
        self.planet.y = PLANET_CENTER_Y
        self.planet.frame = 0
        self.planet.show()
        self.planet_animating = True
        self.ship_warping = False
        vs2.audio.music("vy-3warps")
        self.call_later(4000, self.warp_player)

    def warp_player(self):
        self.ship_warping = True

    def finish_level(self):
        self.level += 1
        if self.level >= len(LEVELS):
            self.pop()
        else:
            self.start_level()

    def update_defeated(self):
        if self.planet_animating:
            self.planet.y -= 1
            if self.planet.y <= RIM_Y:
                self.planet.y = RIM_Y
                self.planet_animating = False
                self.call_later(1500, self.finish_level)
        if self.ship_warping:
            self.player.y += 2
            if self.player.y > 250:
                self.ship_warping = False

    def fire(self):
        if len(self.laser) or self.player_exploded:
            return
        laser = self.laser.spawn(
            self.player.x + 6, self.player.y + 11, frame=0)
        if laser is not None:
            vs2.audio.sound("shoot1")

    def drop_bomb(self):
        if not self.everyone or len(self.bombs) >= self.simultaneous_bombs:
            return
        source = choice(self.everyone)
        bomb = self.bombs.spawn(
            source.x + 6, source.y + 11, frame=1)
        if bomb is not None:
            vs2.audio.sound("shoot3")

    def update_input(self):
        if joy1.just_pressed(A):
            self.fire()
        target = heading(
            joy1.held(UP), joy1.held(DOWN),
            joy1.held(LEFT), joy1.held(RIGHT))
        if target is not None and not self.player_exploded:
            target = (
                target - self.player.width // 2
            ) % vs2.display.width
            self.player.x = move_toward_angle(
                self.player.x, target, 2)
        if not self.player_exploded and self.state != DEFEATED:
            # The original game keeps the fighter on the rim. The rework port
            # accidentally also treated DOWN as radial movement, so steering
            # down changed two axes at once. Once a wave is defeated, the warp
            # sequence owns Y and flies the fighter inward toward the planet.
            self.player.y = RIM_Y

    def animate_player(self):
        if self.player_exploded:
            return
        self.player_frame_clock = (
            self.player_frame_clock + 1
        ) % self.BLINK_RATE
        frame = self.BLINK_FRAMES.get(self.player_frame_clock)
        if frame is not None:
            self.player.frame = frame

    def kill_baddie(self, baddie):
        if baddie.dead:
            return
        x = baddie.x + baddie.width // 2 - 16
        y = baddie.y + baddie.height // 2 - 16
        baddie.dead = True
        baddie.hide()
        if baddie in self.everyone:
            self.everyone.remove(baddie)
        if baddie in self.attacking:
            self.attacking.remove(baddie)
            self.max_attacking += 1
        # explosions is Transient(animate=True, ticks=5) now (see this
        # module's own docstring) -- it drives boom.frame for the whole
        # lifetime itself, so this no longer sets a frame or an "age"
        # counter the way the original did.
        self.explosions.spawn(x, y)
        self.score += randrange(10, 19)
        self.update_scoreboard()
        vs2.audio.sound("explosion2")

    def explode_player(self):
        if self.player_exploded:
            return
        self.player_exploded = True
        self.player.hide()
        self.player_explosion.x = (
            self.player.x + self.player.width // 2
            - self.player_explosion.width // 2
        )
        self.player_explosion.y = (
            self.player.y + self.player.height // 2
            - self.player_explosion.height // 2
        )
        self.player_explosion.frame = 0
        self.player_explosion.age = 0
        self.player_explosion.show()
        self.lives -= 1
        self.update_scoreboard()
        vs2.audio.sound("explosion3")
        if self.lives:
            self.call_later(1500, self.respawn_player)
        else:
            self.game_over.show()
            vs2.audio.music("vy-gameover")
            self.call_later(8333, self.pop)

    def respawn_player(self):
        self.player_explosion.hide()
        self.player_exploded = False
        self.player.x = vs2.display.width - self.player.width // 2
        self.player.y = RIM_Y
        self.player.frame = 0
        self.player_frame_clock = -1
        self.player.show()

    def update_projectiles(self):
        # laser's y-motion and its despawn past LASER_FAR_Y are now the
        # model's Moving(speed_y=6) + DespawnBeyond(y_max=164) (see this
        # module's own docstring); this loop only does what those two
        # Behaviors cannot: the hit-check against a live baddie, and the
        # score/explosion/sound side effects of a hit. bombs' y-motion and
        # despawn past RIM_Y are likewise now Moving(speed_y=-3) +
        # DespawnBeyond(y_min=-1) -- the original had no bomb-vs-anything
        # hit check of its own (bombs only ever hurt the player, checked
        # separately in update_player_collision), so nothing hand-written
        # is left for bombs here at all. Same for explosions' per-tick
        # frame/age bookkeeping, now Transient(animate=True, ticks=5).
        for laser in self.laser:
            hit = None
            for baddie in self.everyone:
                if laser.overlaps(baddie):
                    hit = baddie
                    break
            if hit is not None:
                self.laser.despawn(laser)
                self.kill_baddie(hit)

    def update_player_collision(self):
        if self.player_exploded:
            return
        hit = self.player.first_overlap(self.bombs)
        if hit is not None:
            self.bombs.despawn(hit)
            self.explode_player()
            return
        for baddie in self.everyone:
            if self.player.overlaps(baddie):
                self.kill_baddie(baddie)
                self.explode_player()
                return

    def update_player_explosion(self):
        # player_explosion stays a hand-written age counter, not a
        # Transient: see this module's own docstring for why a Behavior
        # attached to a lone sprite is the wrong shape for a sprite that
        # is repeatedly shown and hidden by game logic rather than
        # spawned from a pool.
        if not self.player_explosion.visible:
            return
        self.player_explosion.age += 1
        if self.player_explosion.age >= self.player_explosion.image.frames:
            self.player_explosion.hide()
        else:
            self.player_explosion.frame = self.player_explosion.age

    def update(self):
        self.update_input()
        if self.state == ENTERING:
            self.update_entering()
        elif self.state == ATTACKING:
            self.update_attacking()
        else:
            self.update_defeated()
        self.animate_player()
        self.update_projectiles()
        self.update_player_collision()
        self.update_player_explosion()


def main():
    return VyrussVs2()
