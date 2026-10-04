# generated_projectile_fixture.py  -- generated, do not edit. body-sha: 3a3f142b
from vs2 import actions
from vs2.behaviors import Behavior
from vs2.params import Angle, Number, PoolRef


class GeneratedProjectile(Behavior):
    speed_x = Angle(0, min=-32, max=32, step=0.25, label='Angular speed', unit='col/tick')
    speed_y = Number(8, min=-32, max=32, step=0.25, label='Radial speed', unit='led/tick')
    range = Number(180, min=1, max=255, step=1, label='Range', unit='led')
    hits = PoolRef(None, label='Hits what')

    state = ('shot_flown',)

    def attached(self, subject):
        self.move = self.action(actions.Move(speed_x=self.speed_x, speed_y=self.speed_y))
        self.hit = self.action(actions.Collide(targets=self.hits))

    def step(self, sprites):
        self.move.run(sprites)
        live = sprites._live
        index = len(live) - 1
        while index >= 0:
            sprite = live[index]
            sprite.shot_flown += self.speed_y
            if sprite.shot_flown > self.range:
                sprite.despawn()
            else:
                _hit_result = self.hit.run_one(sprite)
                if _hit_result is not None:
                    _hit_result.despawn()
                    sprite.despawn()
            index -= 1

# behavior-blocks: eNqNk8FO4zAQhl8F+RwW2lUl1APSag9wQUJcEbKm8TTxMrEtx6EbVXn3HdtpGroUOGU8Hv/fzG9nL6AM2ppWrJ/3YyxLgpYT4sG+oSgE+IpXe9E6RCX/xvBVG8UFDjw0XGGgQV4eCoZiDPuvansxcPEmVzQRNxT/tfHbEmk17yRwgKE9r15r3p1J81oMLyzgHPUyWAlEPHFGcj6h5Hj4Dg16CKgevf2D3AtFdiJkmxRuoaMg1teFINggS4lfpuoI/EWai8sbYKN+LjnQRqwvY3TiEpsU0LHIj+WqEKF3cRNMlWid4Y7XorR0FXT5mmyZsDdH7BMoDfRtav8x1XTNBv0RS6g+wC5urudgU+GBuFytRuRiAvqxIOMWn7HeY0xHdOTc801e7GoIJ5c76TlrKd2tQy9b53XA/JYb25nwjQdYHAqgLLuGLzHktuOXy2ob5JbszqQuS2uUjq9zJlzahrXjIcLtnJg1jsS5lLDsirjlXa+r+pM+s4/xLSO1ebTZo56yL9MYeivzDxQ9qtGkI+OewtbBzsj0PxSnabZxeKeTtM+qjOWjU8/z+WK628SfRx6mitdUiDf0bXJvMfwDqIV2fQ==
