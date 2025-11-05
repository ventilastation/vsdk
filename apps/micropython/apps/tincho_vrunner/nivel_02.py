from apps.tincho_vrunner.tincho_level import TinchoLevel, PROP_REBOTE, PROP_DUELE, PROP_POWER

PROPS = {
    0: [(PROP_REBOTE, 0.2)],
    1: [(PROP_REBOTE, 0),(PROP_POWER, 0.5)],
    2: [(PROP_REBOTE, 0.2)],
    3: [(PROP_REBOTE, 0)],
    4: [(PROP_REBOTE, 0.2)],
    5: [(PROP_DUELE, 0.3), (PROP_DUELE, 0.5)],
    6: [(PROP_REBOTE, 0.2)],
    7: [(PROP_REBOTE, 0)],
    8: [(PROP_REBOTE, 0.2)],
    9: [(PROP_DUELE, 0), (PROP_DUELE, 0.5), (PROP_DUELE, 1)],
    10: [(PROP_REBOTE, 0.2)],
    11: [(PROP_REBOTE, 0),(PROP_POWER, 0.5)],
    12: [(PROP_REBOTE, 0.2)],
    13: [(PROP_REBOTE, 0)],
    14: [(PROP_REBOTE, 0.2)],
    15: [(PROP_DUELE, 0.3), (PROP_DUELE, 0.5)],
    16: [(PROP_REBOTE, 0.2)],
    17: [(PROP_REBOTE, 0)],
    18: [(PROP_REBOTE, 0.2)],
    20: [(PROP_REBOTE, 0.5)],
}

TILES = {
    0: "damero",
    1: "pasto",
    10: "damero",
    11: "pasto",
    20: "damero",
}

class Nivel02(TinchoLevel):
    patrás = True
    row_inicial = 18
    win_row = 0
    tiempo_límite = 20
    tiles_info = TILES
    props_info = PROPS

    def on_enter(self):
        super(Nivel02, self).on_enter()
