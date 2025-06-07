import ujson

from apps.vasura_scripts.common.evento import Evento

class HiScoreManager:
    def __init__(self):
        #Eventos
        self.al_superar_hi_score : Evento = Evento()

        #Config
        path_base = "./apps/vasura_files/"
        self.archivo_principal = path_base + "tabla_puntajes.json"
        self.archivo_backup = path_base + "tabla_puntajes.bak"

        #Estado
        self.jugadore_esta_en_ranking : bool = False
        self.hi_score_superado : bool = False
        self.posicion_jugadore : int = -1
        self.puntaje_jugadore : int = 0

        try:
            with open(self.archivo_principal, 'r') as file:
                self.hi_scores = ujson.load(file)
        except:
            try:
                self.restaurar_backup()

                with open(self.archivo_principal, 'r') as file:
                    self.hi_scores = ujson.load(file)
            except:
                self.inicializar_hi_scores()
                pass
        

        self.hi_score_guardado = self.hi_scores[0]["puntaje"]
    
    
    def chequear_puntaje_actual(self, score : int):
        #HACK. Ver GameplayManager.restar_puntos().
        if score == -1:
            score = 0

        self.puntaje_jugadore = score
        self.jugadore_esta_en_ranking = score > self.hi_scores[-1]["puntaje"]
        
        if self.jugadore_esta_en_ranking and not self.hi_score_superado and score > self.hi_score_guardado:
            self.al_superar_hi_score.disparar()
            self.hi_score_superado = True
    
    def guardar_puntaje_actual(self, iniciales:str):
        if self.puntaje_jugadore < self.hi_scores[-1]["puntaje"]:
            return -1

        for i in range(len(self.hi_scores) - 2, -1, -1):
            if self.puntaje_jugadore <= self.hi_scores[i]["puntaje"]:
                self.hi_scores[i + 1] = {
                    "nombre": iniciales,
                    "puntaje": self.puntaje_jugadore
                }

                self.guardar_hi_scores()
                
                return

    def guardar_hi_scores(self):
        try:
            with open(self.archivo_principal, 'w') as file:
                file.write(ujson.dumps(self.hi_scores))
        except:
            self.restaurar_backup()
        else:
            with open(self.archivo_backup, 'w') as file:
                file.write(ujson.dumps(self.hi_scores))
    
    def restaurar_backup(self):
        with open(self.archivo_backup, 'r') as backup:
            scores_backup = ujson.load(backup)

            with open(self.archivo_principal, 'w') as main:
                main.write(ujson.dumps(scores_backup))

    def inicializar_hi_scores(self):
        self.hi_scores = [
            {
                "nombre": "VEN",
                "puntaje": 10000
            },
            {
                "nombre": "TIL",
                "puntaje": 9500
            },
            {
                "nombre": "ASS",
                "puntaje": 7500
            }#,
            #{
            #    "nombre": "TAT",
            #    "puntaje": 5000
            #},
            #{
            #    "nombre": "ION",
            #    "puntaje": 2500
            #}
        ]
        
        self.guardar_hi_scores()
    
    def limpiar(self):
        self.al_superar_hi_score.limpiar()