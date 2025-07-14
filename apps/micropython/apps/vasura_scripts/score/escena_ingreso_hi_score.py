from ventilastation.director import director
from ventilastation.scene import Scene

from apps.vasura_scripts.score.hi_score_manager import *
from apps.vasura_scripts.score.lebal import *
from apps.vasura_scripts.score.hi_score_tag_character import *
from apps.vasura_scripts.score.escena_hi_scores import *

from apps.vasura_scripts.common.label import *

class VasuraIngresoHiScore(Scene):
    stripes_rom = "vasura_espacial"

    def __init__(self, hi_score_manager:HiScoreManager):
        super().__init__()

        self.hi_score_manager = hi_score_manager
        self.current_char_index : int = 0
        self.terminada = False


    def on_enter(self):
        super(VasuraIngresoHiScore, self).on_enter()

        if self.terminada:
            director.pop()

        Lebal("\xADENTRASTE", 122, 4, "wobniar8x8")
        Lebal("AL RANKING!", 122, 16, "wobniar8x8")

        Label("INICIALES", 246, 20, "rainbow8x8")

        self.chars = [
            HiScoreTagCharacter(5,   4),
            HiScoreTagCharacter(251, 4),
            HiScoreTagCharacter(241, 4)
        ]

        self.chars[0].select()
        

    def step(self):
        if self.current_char_index > 2:
            return

        self.chars[self.current_char_index].step()
        
        if director.was_pressed(director.JOY_UP) or director.was_pressed(director.JOY_RIGHT):
            self.chars[self.current_char_index].increase_index()
            return
        
        if director.was_pressed(director.JOY_DOWN) or director.was_pressed(director.JOY_LEFT):
            self.chars[self.current_char_index].decrease_index()
            return
        
        if director.was_pressed(director.BUTTON_A):
            self.chars[self.current_char_index].deselect()

            if self.current_char_index < 2:
                director.sound_play('vasura_espacial/hi_score_char_select')
                self.chars[self.current_char_index].deselect()
                self.current_char_index += 1
                self.chars[self.current_char_index].select()
            else:
                director.sound_play('vasura_espacial/hi_score_enter')
                self.chars[self.current_char_index].deselect()
                self.current_char_index += 1

                self.hi_score_manager.guardar_puntaje_actual(
                    self.chars[0].get_char() + 
                    self.chars[1].get_char() + 
                    self.chars[2].get_char()
                )
                
                #Reproducir sonido
                
                self.terminada = True
                self.call_later(2000, lambda: director.push(VasuraHiScoresScene(self.hi_score_manager)))
                
            return

        if director.was_pressed(director.BUTTON_D):
            director.pop()

            raise StopIteration()
    