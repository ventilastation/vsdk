# enemy_states.py  -- generated, do not edit. body-sha: 9c125311
from vs2 import actions
from vs2 import audio
from vs2.behaviors import StateMachine, _choose_sound
from vs2.params import Callback, Number, PoolRef, Sound


class EnemyStates(StateMachine):
    hits = PoolRef(None, label='Player shots')
    orbit_ticks = Number(80, min=1, max=255, step=1, label='Orbit duration', unit='tick')
    chiller_ticks = Number(30, min=1, max=255, step=1, label='Chiller-fall duration', unit='tick')
    fall_speed = Number(2, min=0, max=8, step=0.25, label='Fall speed', unit='led/tick')
    ground_y = Number(100, min=0, max=255, step=1, label='Ground', unit='led')
    explosion = PoolRef(None, label='Explosion pool')
    sound = Sound(None, label='Explosion sound')
    on_death = Callback(None, label='On death')

    states = ('orbiting', 'chiller_falling', 'falling', 'exploding')
    initial = 'orbiting'

    def attached(self, subject):
        StateMachine.attached(self, subject)
        self.hit = self.action(actions.Collide(targets=self.hits))

    def enter_orbiting(self, sprite):
        self.hold(sprite, self.orbit_ticks, then='chiller_falling')

    def orbiting(self, sprite):
        _hit_result = self.hit.run_one(sprite)
        if _hit_result is not None:
            return 'exploding'

    def enter_chiller_falling(self, sprite):
        self.hold(sprite, self.chiller_ticks, then='falling')

    def chiller_falling(self, sprite):
        _hit_result = self.hit.run_one(sprite)
        if _hit_result is not None:
            return 'exploding'

    def falling(self, sprite):
        sprite.y += self.fall_speed
        if sprite.y >= self.ground_y:
            return 'exploding'
        else:
            _hit_result = self.hit.run_one(sprite)
            if _hit_result is not None:
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

# behavior-blocks: eNq9VU1v2zAM/SuBzt6WZghQGNguRbdjB+xYBIJsM7FWWRIseYsR+L+P+rAtN01abNjgi0RR75EiH30irLRcSUPyx1Nc01IwgwZyp4TgFZCMsPaAhhOxuADrl09cVuijWcsa9JCsAdzWHE+HISNFOMY9GXYIoLXoqVWUCYFUaPEkNF67l9D03y2zYBDLY4aIKtizTliSy06IjAhWAN4n3wTroV2ZWlnzjDwjttdup5USZMgSjNv1jPDQFtyuqq5lLmW81bAjyTfbLa64JPnNhKqcJ7W8fHLgxoL2p5FFdk0BLR50ElPNifNbsn5MWO9qLgS07/b4DG8iL8OFv6DfzOxfHKvRANVIeRsJ1xOhi4yOPoFt/X6zvUgooPpwTnqzTpL+2qpOVudZzqQH70H7NySIfEuqZWPcH7VQBh915cs/McBov9Yfl6BMjD9ijduIE7ZXgB7kqgJm6xkBNTZaIkiJz14w94woDY0FN7rlFoJUjBNGsqQNw76Q4GRYqIqDF+TYKq6CXB6cCaTFt3M6imqtlfCR1yBjrZ1nRkJ7XVT1sguHYTfWCZEToWcEhImBRiC+p2GoTKxzMAeF8yDktqxT5YIadvhlieGlfDTOAfpieVw9opPR7Jfj9wVftsIxyflZJEeEIP3l896NuVOcjEnGrpJ0Kud5yRePF+9UEGL0GSf1m/xYg0nZywVKVDtMkbCy7JpOhKhjD7mwMepSyYr7ssyQpWoQ1fkK2NuriWdEYVzk8ye0tvxQX4lskrb7KcT2+LdNk8J46D/sPD/33yak59J7VVDpP+U/ygmz4jhGORNjDCFaE/68+WNqPE9qXs247qVMV/yA0tIx1zB5f0LrVZbfDL8BHP/G9A==
