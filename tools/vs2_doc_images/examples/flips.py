import vs2


class Flips(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        # Bottom of the disc: reads upright with no flips.
        bottom = hud.label("numerals.png", columns=5, x=246, y=1)
        # Top of the disc, no flips: upside down.
        top_plain = hud.label("numerals.png", columns=5, x=118, y=1)
        # Top of the disc, flipped both ways: reads upright.
        top_flipped = hud.label("numerals.png", columns=5,
                                x=118, y=14, flip_x=True, flip_y=True)
        for label in (bottom, top_plain, top_flipped):
            label.set_number(420, width=5, pad="0")


def main():
    return Flips()
