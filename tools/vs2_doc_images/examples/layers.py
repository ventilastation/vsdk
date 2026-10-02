import vs2


class Layers(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.clouds = self.layer("clouds", projection=vs2.FULLSCREEN)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.world.sprite("ship.png", x=128, y=0)
        self.world.sprite("enemy.png", x=88, y=50)
        self.world.sprite("enemy.png", x=168, y=50)
        self.world.sprite("enemy.png", x=128, y=90)
        self.clouds.sprite("clouds.png", x=0, y=0)
        self.hud.label("numerals.png", columns=5, glyphs="0123456789",
                       x=246, y=1, text="00420")


def main():
    return Layers()
