# vixeous_scene.py  -- generated, do not edit. body-sha: 0f75e522
import vs2
from games.vs2_examples.vixeous.code.boss_orbit import BossOrbit
from vs2.behaviors import DespawnBeyond, Moving, Transient


class VixeousScene(vs2.Scene):
    def build(self):
        self.world = self.layer(name='world')
        self.hud = self.layer(name='hud', projection=vs2.HUD)
        self.on_build_0()
        self.terrain = self.world.tilemap('terrain.png', columns=8, rows=9, view_width=256, view_height=128)
        self.on_build_1()
        self.reticle = self.world.sprite('reticle.png')
        self.on_build_2()
        self.player = self.world.sprite('ship.png', y=6)
        self.on_build_3()
        self.shots = self.world.sprite_pool('shots.png', 4)
        self.shots.var('theta', 0)
        self.shots.behave(Moving(speed_y=8))
        self.shots.behave(DespawnBeyond(y_max=179))
        self.on_build_4()
        self.bombs = self.world.sprite_pool('shots.png', 3)
        self.bombs.var('theta', 0)
        self.bombs.behave(Moving(speed_y=4))
        self.on_build_5()
        self.explosions = self.world.sprite_pool('explosion.png', 5, on_empty=vs2.RECYCLE)
        self.explosions.var('theta', 0)
        self.explosions.behave(Transient(animate=True, ticks=18))
        self.on_build_6()
        self.enemies = self.world.sprite_pool('enemy.png', 6)
        self.enemies.var('theta', 0)
        self.enemies.var('kind', 0, min=0, max=2)
        self.enemies.var('phase', 0, min=0, max=127)
        self.enemies.var('hp', 1, min=0)
        self.enemies.behave(Moving(speed_y=-1))
        self.enemies.behave(DespawnBeyond(y_min=0))
        self.on_build_7()
        self.targets = self.world.sprite_pool('targets.png', 5)
        self.targets.var('theta', 0)
        self.targets.var('kind', 0, min=0, max=3)
        self.on_build_8()
        self.boss = self.world.sprite('boss.png', visible=False)
        self.boss.behave(BossOrbit(width=vs2.display.width))
        self.on_build_9()
        self.score_label = self.hud.label('digits.png', columns=9, y=1, flip_x=True, flip_y=True)
        self.on_build_10()
        self.message = self.hud.sprite('messages.png', y=12)
        self.on_build_11()

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

    def on_build_10(self):
        pass

    def on_build_11(self):
        pass

# scene-model: eNq1VdmOmzAU/Rc/UzRktgyPs0h9aFWpm1RVI2TgBtwxtmUbCIr4914zkJgmVFWqeULc9Zy7eUcyTo1JBK2AxOQ724KszZcMBJCAcNqBNiT+uSPUWo0GrdQ8R02uaUtTDjOlBa0pE6jOJK8rgcp1QFhFCzhoQyUKtHhhIndCxqGiCgVatmh/F5CGQZuUwIrSkjharUdJy3Jbknh1fdMH+4waLMu4gzplGSXzLEZpZoF4jmqg5vmZkqmTTgHpSOznNKW0BsUplLRhcqzPUEbUfpQNG6IoqmmFkh0GAsgTjLLuXZjJ8hGMoq24h06KfObQJRXdIvfbu75/dsWsBZbiygeLEE6hTZSUHIUNHWHlsKE1R++LgIw9tiVYSvpnj1Iqq/Q8Slc+wsu3QwhbxaVhUizD/KqpMAwQiI+UCoSEbYytriHAecteUB6tfdzXB9z7PH/DLkUClbJIn3x+evjx8OHpDEICKgbnFf1d9O+DhOsYX/hkbzyyiKH7zyYFc+UwuCv8Dnn3xkP0k7bR6vbIWpXUwNw8OjIq1bygluoChsU87uqoewOqlwtU59tllvt8j8pPOmVuaiuZ19zFKDCUCRuzSmBLK8Xdz+tlDjOZQ+giJnL0OrR7PJE7N8UuMQYIc2bcrQtfdf0wCVNZXJiFm9cww1KHZUO5gRmdsl58AEwmNSScpsD9RwCP+oYzlWynLRz+uulvgpOzgv3ZpCkWGkceBiyPcU4H51Film94tHLclZa/ILO44ah+/+2ROGGDr9wgifrfh+FYow==
