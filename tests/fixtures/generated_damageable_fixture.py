# generated_damageable_fixture.py  -- generated, do not edit. body-sha: c4202f40
from vs2 import actions
from vs2 import audio
from vs2.behaviors import Behavior, _choose_sound
from vs2.params import Callback, Flag, Number, PoolRef, Sound


class GeneratedDamageable(Behavior):
    hp = Number(1, min=1, max=99, step=1, label='Hit points')
    invulnerable_ticks = Number(0, min=0, max=255, step=1, label='Invulnerability', unit='tick')
    blink = Flag(False, label='Hide while invulnerable')
    explosion = PoolRef(None, label='Explosion pool')
    sound = Sound(None, label='Sound on death')
    score = Number(0, min=0, max=9999, label='Points on death')
    on_death = Callback(None, label='On death')
    hits = PoolRef(None, label='Damaged by')

    state = ('damage_taken', 'invuln_left')

    def attached(self, subject):
        self.hit = self.action(actions.Collide(targets=self.hits))

    def step(self, sprites):
        live = sprites._live
        index = len(live) - 1
        while index >= 0:
            sprite = live[index]
            if sprite.invuln_left > 0:
                sprite.invuln_left += -1
                if sprite.invuln_left <= 0:
                    if self.blink == True:
                        sprite.visible = True
            else:
                _hit_result = self.hit.run_one(sprite)
                if _hit_result is not None:
                    sprite.damage_taken += 1
                    sprite.invuln_left = self.invulnerable_ticks
                    if self.blink == True:
                        sprite.visible = False
                    if sprite.damage_taken >= self.hp:
                        _cb_on_death = self.on_death
                        if _cb_on_death is not None:
                            _cb_on_death(sprite, self.score)
                        _sound_sound = self.sound
                        if _sound_sound is not None:
                            audio.sound(_choose_sound(_sound_sound))
                        _spawn_explosion = self.explosion
                        if _spawn_explosion is not None:
                            _spawn_explosion.spawn(sprite.x, sprite.y)
                        sprite.despawn()
            index -= 1

# behavior-blocks: eNrdVU2PmzAQ/SuRz1TKVtrDRk0v7artqZV6jCLLwCRxMxgLTDYo4r93bPNhyIbdSD31BuPhjefNe8OFicTIXJVstbm0zzxBUVKAfckRZQosYqLYU+DCDD2AcY9HqVLK0aIQGWUokQG9HiSdNk3EYn9M76zZEoDWWHOTc4FIpSjiivD2s2+goBAG0q8iE3sQMdqqDtvfLIWdqNCw1UPEUMRAIOy7NAudS0UVI5aJM1s9PdGDVC6ru5Cmw9KAdkFTaxtUVRZDwZooAF4OwD/UqUJ7oViiNHWH/vHxsYVf9vCyT0XgRibH8na5iFWK6FgxmzcuvhNYQthZCouXg0RYhAUGmmOU6sj6AjsU+zGgqhAHvOezxryk0RJfOQ4w0MUHKJcwA/U7r1S6IKQUhDkMUKWNDzD+9RbBv9zUQpR2fP0AB4bLJC+AzY5ufMOfV3cjSXeRFiUhGcZiOoUxjpdiuojribwnXJGWNRS81IU04MSa5CqV1kmBT5I8IznbRhB2JjgoDemeTQTFXRLZKCchsc90XMj9IfyMhEmisLM8Cazoy6V1HZCM3BUC+/VRumj7sdxxb3XbywGUN39GM5st8dD0CCJJqqxCf3XfwoqljjFuxJEgLbNdi2B412aXG/bZF7i1VV5xWWPx7yJ6gukt1FG8Xr+HY1NUENA8ItTFAjpnej/JUno7T/u+qugWQ9Ns7+52IqvJaFpdvdb0dKFr9t6O/U9icwvJG7kZIKwJee/Ea7cGCtIoat6tmNHGCWWmxYtVtLPleLmdbzNztnTUt89rL7X2MAVfhSaybebZeNNOH97y03gX/Pu98ml972KZ7fj/d6OvuO2G3yJsxu6KRlzbtCr+A4nhXef+F3yCwomTtupf+yQkgQ==
