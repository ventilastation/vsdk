import vs2


class Layers(vs2.Scene):
    def build(self):
        self.sky = self.layer("sky", projection=vs2.FULLSCREEN)
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.sky.sprite("tierra.png", x=0, y=0)
        self.world.sprite("ship.png", x=128, y=0)
        self.hud.label("numerals.png", columns=5, glyphs="0123456789",
                       x=246, y=1, text="00420")


def main():
    return Layers()
