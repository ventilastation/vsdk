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
        self.hi_score_superado : bool = False

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

        if not self.hi_score_superado and score > self.hi_score_guardado:
            self.al_superar_hi_score.disparar()
            self.hi_score_superado = True
    
    def chequear_hi_score(self, puntaje_final : int):
        if score == -1:
            score = 0

        if puntaje_final < self.hi_scores[-1]["puntaje"]:
            return -1

        for i in range(len(self.hi_scores) - 2, -1, -1):
            if puntaje_final <= self.hi_scores[i]["puntaje"]:
                self.hi_scores[i + 1] = {
                    "nombre": "LUA",
                    "puntaje": puntaje_final
                }
                
                #self.guardar_hi_scores()

                return i + 1
            
        print("Queda #1")
        return 1

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
            },
            {
                "nombre": "TAT",
                "puntaje": 5000
            },
            {
                "nombre": "ION",
                "puntaje": 2500
            }
        ]
        
        self.guardar_hi_scores()