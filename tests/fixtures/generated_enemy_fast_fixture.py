# generated_enemy_fast_fixture.py  -- generated, do not edit. body-sha: f799b4ca
from vs2 import actions
from vs2 import audio
from vs2.behaviors import StateMachine, _choose_sound
from vs2.params import Callback, Number, PoolRef, Sound


class GeneratedEnemy(StateMachine):
    ground_y = Number(100)
    explosion = PoolRef(None)
    sound = Sound(None)
    on_death = Callback(None)
    hits = PoolRef(None)

    state = ('frames_left',)

    states = ('orbiting', 'falling', 'exploding')
    initial = 'orbiting'

    def attached(self, subject):
        StateMachine.attached(self, subject)
        self.hit = self.action(actions.Collide(targets=self.hits))

    def enter_orbiting(self, sprite):
        self.hold(sprite, 3, then='falling')

    def orbiting(self, sprite):
        if self.hit.run_one(sprite) is not None:
            return 'exploding'

    def falling(self, sprite):
        sprite.frames_left += 1
        if sprite.y >= self.ground_y:
            return 'exploding'

    def enter_exploding(self, sprite):
        _sound_sound = self.sound
        if _sound_sound is not None:
            audio.sound(_choose_sound(_sound_sound))
        _spawn_explosion = self.explosion
        if _spawn_explosion is not None:
            _spawn_explosion.spawn(sprite.x, sprite.y)
        _cb_on_death = self.on_death
        if _cb_on_death is not None:
            _cb_on_death(sprite)

    def exploding(self, sprite):
        sprite.despawn()

    def exit_exploding(self, sprite):
        sprite.frames_left = 0

# behavior-blocks: eNqdlMGOnDAMht8lZw6z6m2l9lKt+hDVKgqJgXRCEiWhHTTi3dcOEGBbOPRGHNvx/9nmyYRM2tnIXn8+l28ujYhoYN+dMVoBq5gILRqeLOEHpPx511ahjxdB9OhhRQ947DTeTlPF6vkaz2x6xwTem5Enx4Ux+BRa8iN8CfsBFoJIoN4s9COmy2nnohQ0YjCJvb7cbuWdNrjBKk6uafRksUNfQ2BTtYuwgzElBB7euIj6thjvnLmIiPTG5j0fz92RnAKRui1CotpayPtFUAb2qSCk4yHw6INOMNOKSeRP1iAXiNxAk9hq572QnbZAbamd0pAblPUqbdt8sAnhEM61b0aMfBV40Eu1Lk7Riz+EK5d1JPjYzcBcXEnzwBRsPL8faUCey0yRuMWNaPGC7G+sxAUeOFA7GRESX9MvjA6IKvZbmAF2xRhkGoTZbm7TlEGC3ydWMIuf3lFMg0UtIIuf6JFWukr8MhVpQsqhH8x5nQREOqs0LeAuqXQ9rgJFZbcrphVzWBn79hWtQbddOt/Ssj20qWAiHPqgG55tOJUd2D2U1uEGf3p5GzNERbBcqFHFydh1zqiSuHBFg5b3eAXzy7FLu9/LvxXMv7L/04AitEUNgoa+yFkaRzO7N24atiyEIQ71L5CJrx2gFUI1EPIC4XB8ACS81jY=
