# vyruss_vs2_scene.py  -- generated, do not edit. body-sha: 1d9f39db
import vs2
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
        self.on_build_5()
        self.explosions = self.world.sprite_pool('explosion.png', 8, on_empty=vs2.RECYCLE)
        self.explosions.behave(Transient(animate=True, ticks=5))
        self.on_build_6()
        self.player_explosion = self.world.sprite('explosion_nave.png', visible=False)
        self.on_build_7()
        self.scoreboard = self.hud.label('numerals.png', columns=9, x=110, flip_x=True, flip_y=True)
        self.on_build_8()
        self.game_over = self.hud.sprite('gameover.png', visible=False)
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

# scene-model: eNqdlMFu2zAMht+FZ3dItqVYfVyaYYdsh3YdMAyBQVuMq1WWBEl2YgR+91FuktpDPQQ9ipR+fvxN+gCFQu8zjRVBCj9bV3t/X5AmSEBhS85D+vsAGILj/LZWyheOSHNaONxhrmh0wyrUFDgrKyyjpMdQO23eWV1y9ElqEYPWyRBLNNJLloB0i8pTAntIZwm0kL5fLLpNAkeus6p15g8VQRrN0S8P6/X98m61+g5dcibYGafEf/C4pwGeUjcTaAxxNR/osk/9y5wesZHmaExvH2e/mUb2MhYdVhw5sBKRyFjmuosyp5u35C3u9GdqjRajB21WIRswv/7Yxd4LU+vAxxdYIfmpe9XLzBqjhjbkpsr9m3CvPlzOK3Xv0gD30xtxUQhJEfios5i9CJWosMSLdGhvlfE8H9O9/3CovSQdRs2g5mr84dPgah7EIIsnji8mWjuXmYZKwOiMKhvYUrhbLX8t16sh6fMoZmcleEWd97Khi1an2wykH+vJBfCFcZQbdKK3WtUVO5XeJLBV0mb7U/v9qT2dTly6rshxtTGRwpxiu3F058/bOxvAlLzCmWlGWxdjMXThX6FX3Pyz/V8fbiEGWaa3L513fwEa/Jt2
