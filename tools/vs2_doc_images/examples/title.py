import vs2
from vs2.controls import *


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        self.banner = hud.sprite("messages.png", x=96, y=12)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Play())


class Play(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        world.sprite("ship.png", x=128, y=12)
        world.sprite("enemy.png", x=128, y=110)

    def update(self):
        if joy1.just_pressed(B):
            self.pop()


def main():
    return Title()
