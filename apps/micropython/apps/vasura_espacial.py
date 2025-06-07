from ventilastation.director import director
from ventilastation.scene import Scene

from apps.vasura_scripts.managers.balas_manager import *
from apps.vasura_scripts.managers.enemigos_manager import *
from apps.vasura_scripts.managers.gameplay_manager import *

from apps.vasura_scripts.managers.spawner_enemigos import SpawnerEnemigos

from apps.vasura_scripts.entities.nave import Nave
from apps.vasura_scripts.entities.planeta import Planeta

from apps.vasura_scripts.score.display_puntaje import *
from apps.vasura_scripts.score.hi_score_manager import *

from apps.vasura_scripts.escena_game_over import *

import gc

class VasuraEspacial(Scene):
    stripes_rom = "vasura_espacial"
    def __init__(self):
        super().__init__()

        #HACK? Estos flags son para detectar que ya pasaste por una escena y poder salir del juego directamente desde la de hi-scores
        self.terminada = False

    def on_enter(self):
        super(VasuraEspacial, self).on_enter()
        
        if self.terminada:
            self.quit_game()

        #Inicializacion
        self.planet = Planeta(self)

        self.manager_balas = BalasManager(self)
        self.manager_enemigos = EnemigosManager(self)
        self.spawner_enemigos = SpawnerEnemigos(self.manager_enemigos)
        self.hi_score_manager = HiScoreManager()
        
        self.nave = Nave(self, self.manager_balas)
        
        self.gameplay_manager = GameplayManager(self.nave)

        #Suscripciones a eventos
        self.planet.al_ser_golpeado.suscribir(self.gameplay_manager.on_planet_hit)
        
        self.gameplay_manager.al_perder_vida.suscribir(self.planet.al_perder_vida)
        self.gameplay_manager.game_over.suscribir(self.on_game_over)

        self.manager_enemigos.al_morir_enemigo.suscribir(self.gameplay_manager.al_morir_enemigo)
        self.call_later(1000 * 30, self.juntar_basura)

        self.label_puntajes : DisplayPuntaje = DisplayPuntaje()
        self.gameplay_manager.puntaje_actualizado.suscribir(self.label_puntajes.actualizar)
        
        self.gameplay_manager.puntaje_actualizado.suscribir(self.hi_score_manager.chequear_puntaje_actual)
        self.hi_score_manager.al_superar_hi_score.suscribir(self.label_puntajes.mostrar_medalla)

        #self.reproducir_bgm()

    
    def juntar_basura(self):
        gc.collect()
        self.call_later(1000 * 30, self.juntar_basura)


    def step(self):
        self.nave.step()
        self.manager_enemigos.step()
        self.manager_balas.step()
        self.gameplay_manager.step()
        self.spawner_enemigos.step()
        
        if director.was_pressed(director.BUTTON_D):
            self.quit_game()


    def on_exit(self):
        self.nave.limpiar_eventos()
        self.planet.limpiar_eventos()

        self.manager_enemigos.limpiar()
        self.gameplay_manager.limpiar()
        self.manager_balas.limpiar()
        self.hi_score_manager.limpiar()

        director.music_off()
        
    def reproducir_bgm(self):
        director.music_play("vasura_espacial/cancion_no_robada")
        self.call_later(85000, self.reproducir_bgm)

    def on_game_over(self):
        self.terminada = True
        director.music_play("vasura_espacial/game_over")
        director.push(VasuraGameOver(self.hi_score_manager))
    
    def quit_game(self):
        director.pop()
        raise StopIteration()


def main():
    return VasuraEspacial()

"""
TODO Manteimiento:
- Ubicar bien llamadas a gc.collect() (sugerencia de Ale: entre waves)
- Meter las definiciones de waves en un archivo separado
- Mover constantes de configuracion a un mismo archivo
- Agrupar bien los srtips en pallete groups
- Renombrar archivos de sprites y audio para que se entienda mejor de qué son
"""
