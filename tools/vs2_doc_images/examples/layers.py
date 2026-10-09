import vs2


class Layers(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.clouds = self.layer("clouds", projection=vs2.FULLSCREEN)
        self.hud = self.layer("hud", projection=vs2.HUD)

        ship = self.world.sprite("ship.png", y=0)
        ship.x = -(ship.width // 2)                  # centred on the bottom
        self.world.sprite("enemy.png", x=-40, y=50)
        self.world.sprite("enemy.png", x=40, y=50)
        self.world.sprite("enemy.png", x=0, y=90)
        self.clouds.sprite("clouds.png", x=0, y=0)
        # The score is at the top of the disc, flipped to read upright.
        self.hud.label("numerals.png", columns=5, x=118, y=1,
                       flip_x=True, flip_y=True, text="04730")


def main():
    return Layers()
