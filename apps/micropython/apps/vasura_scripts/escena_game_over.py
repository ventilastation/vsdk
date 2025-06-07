from ventilastation.director import director
from ventilastation.scene import Scene

from apps.vasura_scripts.score.hi_score_manager import *
from apps.vasura_scripts.score.hi_score_label import *
from apps.vasura_scripts.score.escena_hi_scores import *
from apps.vasura_scripts.score.escena_ingreso_hi_score import *

class VasuraGameOver(Scene):
    stripes_rom = "vasura_espacial"

    def __init__(self, hi_score_manager:HiScoreManager):
        super().__init__()
        self.hi_score_manager = hi_score_manager
        self.terminada = False

    def on_enter(self):
        super(VasuraGameOver, self).on_enter()

        if self.terminada:
            director.pop()

        HiScoreLabel("GAME OVER :(", 120, 12)

        Label("TU PUNTAJE:", 246, 24)
        Label(str(self.hi_score_manager.puntaje_jugadore), 246, 12)

        self.call_later(5000, self.advance)   
    
    def advance(self):
        self.terminada = True

        if self.hi_score_manager.hi_score_superado:
            director.push(VasuraIngresoHiScore(self.hi_score_manager))
            pass
        else:
            director.push(VasuraHiScoresScene(self.hi_score_manager))
            pass