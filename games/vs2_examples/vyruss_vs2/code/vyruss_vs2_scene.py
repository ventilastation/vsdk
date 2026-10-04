# vyruss_vs2_scene.py  -- generated, do not edit. body-sha: ac42a947
import vs2
from games.vs2_examples.vyruss_vs2.code.baddie_formation import BaddieFormation
from vs2.behaviors import DespawnBeyond, Moving, Transient


class VyrussScene(vs2.Scene):
    def build(self):
        self.fullscreen = self.layer(name='planet', projection=vs2.FULLSCREEN)
        self.world = self.layer(name='world')
        self.hud = self.layer(name='hud', projection=vs2.HUD)
        self.on_build_0()
        self.planet = self.fullscreen.sprite('saturno.png', y=255, visible=False)
        self.on_build_1()
        self.player = self.world.sprite('ll9.png', y=-1)
        self.on_build_2()
        self.laser = self.world.sprite_pool('disparo.png', 1)
        self.laser.behave(Moving(speed_y=6))
        self.laser.behave(DespawnBeyond(y_max=164))
        self.on_build_3()
        self.bombs = self.world.sprite_pool('disparo.png', 8)
        self.bombs.behave(Moving(speed_y=-3))
        self.bombs.behave(DespawnBeyond(y_min=-1))
        self.on_build_4()
        self.baddies = self.world.sprite_pool('galaga.png', 50)
        self.baddies.behave(BaddieFormation(width=vs2.display.width))
        self.on_build_5()
        self.explosions = self.world.sprite_pool('explosion.png', 8, on_empty=vs2.RECYCLE)
        self.explosions.behave(Transient(animate=True, ticks=5))
        self.on_build_6()
        self.player_explosion = self.world.sprite('explosion_nave.png', visible=False)
        self.on_build_7()
        self.scoreboard = self.hud.label('numerals.png', columns=9, x=110, flip_x=True, flip_y=True)
        self.on_build_8()
        self.game_over = self.hud.sprite('gameover.png', x=vs2.display.width - 32, visible=False)
        self.on_build_9()

    def on_build_0(self):
        pass

    def on_build_1(self):
        pass

    def on_build_2(self):
        pass

    def on_build_3(self):
        pass

    def on_build_4(self):
        pass

    def on_build_5(self):
        pass

    def on_build_6(self):
        pass

    def on_build_7(self):
        pass

    def on_build_8(self):
        pass

    def on_build_9(self):
        pass

# scene-model: eNqdlN9v2jAQx/+Vys8BAR3VmsdSqj2wPbTrpGlC1iU5wKt/yXYCUZX/fedQIFTNhPoW39nf+9w3Z7+yXIL3XINClrJftSu9f8pRI0uYhBqdZ+mfVwYhOMqvSil97hA1pQsHW8gknu2wEjQGygoF6yjpIZROm6HVa4q+CF3EoHUixBKV8IIkWLoC6TFhO5aOElazdDKdNsuEvXEdVa0zfzEPwmiKPjwvFk+zx/n8B2uSI8HWOFn8B4966uBJeduDRhCDcUeXfGpPZriBSpg3Y1r7KPvdVKKVseBAUeSVlBALTjI3TZQ57LxHb2Gr77A2ujg7UHMFZMD45ksTe89NqQMtT7CFoKPuQy+5NUZ2bciMyvyncAfXl/MK3brUwf36SVwoCoH9wHdt/sE4Be3fT5gyRRknh61pRvyw8hOOO1BWxkU7x5xiw9wUONyr81Xn+KmNrSjCJn7gzkaUeCqi06gM97mm2+B0dOpwDRLWcFGDJC6Np9r9Pf50oL1AHc7wQFM1msg0uJJuSBD5C8WnPZ4fy/RDJcxojsoG+tfscT77PVvMu6T7O8KPSuwDdXowKrzoTjfLjvSm7L2ZPjcOMwMu7siNLBU5ld4mbCWF5btD++2qPqwOXLpU6KjaOZGEDGO78U6N98/KqAMT54ab6uw5iLEYuvy56h+bq8HV9YSM3dddvnu8vj3fsxikYq3J6bj5B7Iq3oE=
