# vixeous_scene.py  -- generated, do not edit. body-sha: e9b4b506
import vs2
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

# scene-model: eNq1VcmO2zAM/Red3WKc2TI+zgL00F66AUUxMBibidmRJUGS7RgD/3tpw07kJimKFHMy9PhIPlIU/SoyCc6lCkoUifhOW9SV+5KhQhEJCS1aJ5KfrwK8t0xotJU5W3ILDawkzowerQVSbM60rErFxmUkqIQN7q3vjdow44VU3oMksQTDgNUN8+8iURM2aYG0KbxI4sVyRBrKfSGSxfVNF+0yWvSUyV7qlGVE5lmcseRRBI5mKC3wcwWZo06RaEUS5nSF9o7hFRZQkx77M7SRrZ90TUMUAxZKRl45EGKecpRl14eZmI/oDDTqHlut8plDm5aw5dpv77ruuW9mpbgVV6FYlnBMbWq0lgzWMMrKcQ2VZO+LSIx37Av0ILrnoKSVLlfnlXQVKrx8O4W4NVI70uq0zK8WlCNkIaFSUCyJrzHxtsKI5y17YTxehrqv97p3ef6mXasUS+O5fPH56eHHw8enMwpSWBKe1/R38b8PEj/H5CIs9iYoljW0/3lJ0dw4DO6Cv0PeHXmIfpQbL24P2KYAh3N6fEAqzLyhHuwGh4d5eKuj7Q1KvTxR6vx1ORdsmv54YtPU5IiXqkjWIB3OghTVybXrMm0xlbBCGa5eXqVrSSbdTrM/nNrpNMnJaUN/tmaKxeQ40FCic73T3nlE3OnNGS/62TNW/8LM87ti84dvj6IHa/63DEjc/QbyaydX
