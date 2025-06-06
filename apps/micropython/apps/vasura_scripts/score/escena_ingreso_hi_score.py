from ventilastation.director import director
from ventilastation.scene import Scene

from apps.vasura_scripts.score.hi_score_manager import *
from apps.vasura_scripts.score.hi_score_label import *

from apps.vasura_scripts.common.label import *

class VasuraIngresoHiScore(Scene):
    stripes_rom = "vasura_espacial"

    def __init__(self, hi_score_manager:HiScoreManager):
        super().__init__()

        self.hi_score_manager = hi_score_manager
        


    def on_enter(self):
        HiScoreLabel("¡ENTRASTE", 122, 4)
        HiScoreLabel("AL RANKING!", 122, 16)

        Label("INICIALES:", 246, 24)
        Label("___", 246, 12)

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            self.finished()