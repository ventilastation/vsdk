from apps.vasura_scripts.entities.enemigos.enemigo import *

tabla_test = [
    (Driller, 60),
    (Chiller, 10),
    (Bully, 30),
]

comportamiento_test = dict(
    piso_inicial=2.5,
    piso_minimo=0.5, 
    techo_inicial=6, 
    techo_minimo=0.75, 
    step_piso=0.05, 
    step_techo=0.1, 
    tabla_porcentajes=tabla_test
)
