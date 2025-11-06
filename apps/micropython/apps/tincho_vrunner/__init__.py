from apps.tincho_vrunner.pantallas import Título
from apps.tincho_vrunner.nivel_01 import Nivel01
from apps.tincho_vrunner.nivel_02 import Nivel02

Título.siguiente = Nivel01
Nivel01.siguiente = Nivel02
Nivel02.siguiente = Título

def main():
    return Título()
