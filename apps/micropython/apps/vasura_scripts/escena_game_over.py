import utime

from ventilastation.director import director
from ventilastation.scene import Scene

from apps.vasura_scripts.score.hi_score_manager import *
from apps.vasura_scripts.score.hi_score_label import *

from apps.vasura_scripts.common.label import *
from apps.vasura_scripts.score.escena_hi_scores import VasuraHiScoresScene

class VasuraGameOver(Scene):
    stripes_rom = "vasura_espacial"

    def __init__(self, hi_score_manager:HiScoreManager):
        super().__init__()
        self.hi_score_manager = hi_score_manager

        self.call_later(5000, self.advance)

    def on_enter(self):
        HiScoreLabel("GAME OVER :(", 120, 12)

        Label("TU PUNTAJE:", 246, 24)
        Label(str(self.hi_score_manager.puntaje_jugadore), 246, 12)

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            self.finished()
    
    def advance(self):
        if self.hi_score_manager.hi_score_superado:
            #Ir a pantalla para ingresar tu nombre
            pass
        else:
            director.push(VasuraHiScoresScene(self.hi_score_manager))
            pass