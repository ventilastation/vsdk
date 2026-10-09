"""A pool of enemies spawned in a V, heading for the ship on the rim. The pool is
not updated here: the screenshot shows the moment after spawning."""

import vs2


class Pools(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", y=0)
        self.ship.x = -(self.ship.width // 2)     # centred on the bottom of the disc
        self.enemies = self.world.sprite_pool("enemy.png", count=16)
        for i in range(7):
            self.enemies.spawn(x=(i - 3) * 20, y=20 + abs(i - 3) * 16)


def main():
    return Pools()
