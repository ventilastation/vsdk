import vs2


class Legibility(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        near_rim = hud.label("numerals.png", columns=5, glyphs="0123456789",
                             x=246, y=1)
        near_centre = hud.label("numerals.png", columns=5, glyphs="0123456789",
                                x=246, y=44)
        near_rim.set_number(420, width=5, pad="0")
        near_centre.set_number(420, width=5, pad="0")


def main():
    return Legibility()
