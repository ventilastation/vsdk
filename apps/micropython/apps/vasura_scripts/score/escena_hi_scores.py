from ventilastation.director import director
from ventilastation.scene import Scene

from apps.vasura_scripts.score.hi_score_manager import *
from apps.vasura_scripts.score.lebal import *

from apps.vasura_scripts.common.label import *

class VasuraHiScoresScene(Scene):
    stripes_rom = "vasura_espacial"

    def __init__(self, hi_score_manager:HiScoreManager):
        super().__init__()

        self.hi_score_manager = hi_score_manager
        self.labels = []


    def on_enter(self):
        super(VasuraHiScoresScene, self).on_enter()

        for i in range(len(self.hi_score_manager.hi_scores)):
            entry = self.hi_score_manager.hi_scores[i]
            y = 5 + 12 * i
            text = str(i + 1) + "." + entry["nombre"] + " " + str(entry["puntaje"])
            
            self.labels.append(Lebal(text, 120, y, "noziroh8x8"))
        
        Label("GRACIAS POR", 247, 16, "rainbow8x8")
        Label("JUGAR \x03", 247, 4, "rainbow8x8")

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            
            raise StopIteration()