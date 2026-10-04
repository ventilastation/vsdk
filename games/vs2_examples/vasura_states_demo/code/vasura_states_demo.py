"""Entry point for games/vs2_examples/vasura_states_demo.

The T17 Phase 2 "state hats" proving case: a small, original recreation of
games/vsjam-may25/vasura_espacial's own hand-rolled enemy state machine
(vasura_scripts/estado.py), authored through tools/vs2_behavior_gen's new
state-hat schema instead. See code/build_enemy_states.py's own module
docstring for exactly which of the real game's states this recreates, how
they map onto ``EnemyStates`` (code/enemy_states.py, generated from
code/enemy_states.vs2behavior.json), and the one deliberate departure from
the real transition graph.

Everything *except* the enemy's own per-tick state logic is hand-written
here, matching every other vs2_examples proving game's own split: waves of
enemies spawn periodically, a "shot" button fires a bullet upward, hits
are entirely EnemyStates' own job (its bound Collide action), and the only
things this scene's update() does are input and periodic spawning -- no
enemy ever gets touched directly by hand-written code once spawned.
"""

import vs2
from vs2.behaviors import Transient
from vs2.controls import A, joy1

from games.vs2_examples.vasura_states_demo.code.enemy_states import EnemyStates

WORLD_WIDTH = vs2.display.width
GROUND_Y = 96
BULLET_SPEED = 6
SPAWN_PERIOD = 45


class VasuraStatesDemo(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)

        self.bullets = self.world.sprite_pool("bullet.png", count=4)

        self.explosions = self.world.sprite_pool(
            "explosion.png", count=4, on_empty=vs2.RECYCLE)
        self.explosions.behave(Transient(animate=True, ticks=10))

        self.enemies = self.world.sprite_pool("enemy.png", count=6)
        self.enemies.behave(EnemyStates(
            hits=self.bullets, explosion=self.explosions, sound="boom",
            orbit_ticks=50, chiller_ticks=20, fall_speed=1, ground_y=GROUND_Y,
            on_death=self.on_enemy_death))

        self.ship = self.world.sprite("ship.png", y=4)
        self.ship.x = WORLD_WIDTH // 2

        self.score = 0
        self.next_wave = 1  # spawn the first wave almost immediately

    # -- scoring ----------------------------------------------------------

    def on_enemy_death(self, sprite):
        # EnemyStates' own on_death callback -- called from
        # enter_exploding, once, the tick an enemy is hit or reaches the
        # ground. Every point of "what happens when an enemy dies" this
        # scene cares about funnels through here, exactly the shape
        # games/vs2_examples/vixeous's own add_score() has (see that
        # game's code/vixeous.py) -- a Behavior hands back the fact that
        # something died; the game decides what that is worth.
        self.score += 10

    # -- spawning -----------------------------------------------------------

    def spawn_wave(self):
        for _ in range(2):
            enemy = self.enemies.spawn(
                vs2.display.width // 2 + (self.next_wave % 40) - 20, 8)
            if enemy is not None:
                enemy.visible = True
        self.next_wave = SPAWN_PERIOD

    # -- input --------------------------------------------------------------

    def fire(self):
        self.bullets.spawn(self.ship.x, self.ship.y + 4)

    def update(self):
        if joy1.just_pressed(A):
            self.fire()

        # Every live bullet's own constant upward velocity, hoisted here
        # every tick rather than once at spawn time -- dx/dy is an
        # accumulator the framework applies-and-zeroes once per pool per
        # tick (Scene._commit_pool_motion, right after this update()
        # returns), so a value set only once at spawn would move the
        # bullet exactly one tick's worth and then silently stop.
        for bullet in self.bullets:
            bullet.dy = BULLET_SPEED
            if bullet.y > GROUND_Y:
                self.bullets.despawn(bullet)

        self.next_wave -= 1
        if self.next_wave <= 0:
            self.spawn_wave()


def main():
    return VasuraStatesDemo()
