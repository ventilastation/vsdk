from apps.tincho_vrunner.tincho_level import TinchoLevel, PROP_REBOTE, PROP_DUELE, PROP_POWER

WIN_ROW = 55

PROPS = {
    0: [(PROP_REBOTE, 0.2)],
    1: [(PROP_REBOTE, 0),],
    2: [(PROP_REBOTE, 0.2)],
    3: [(PROP_REBOTE, 0)],
    4: [(PROP_REBOTE, 0.2)],

    6: [(PROP_REBOTE, 0.8)],
    7: [(PROP_REBOTE, 1)],
    8: [(PROP_REBOTE, 0.8)],
    9: [(PROP_REBOTE, 1)],
    10: [(PROP_REBOTE, 0.8), (PROP_DUELE, 0)],

    13: [(PROP_REBOTE, 0.2), (PROP_DUELE, 1)],
    14: [(PROP_REBOTE, 0), (PROP_REBOTE, 0.4)],
    15: [(PROP_REBOTE, 0.2)],
    16: [(PROP_REBOTE, 0), (PROP_REBOTE, 0.4)],
    17: [(PROP_REBOTE, 1)],
    18: [(PROP_REBOTE, 0.8)],

    23: [(PROP_DUELE, 0.4)],
    24: [(PROP_DUELE, 0.2), (PROP_DUELE, 0.6)],

    26: [(PROP_POWER, 0.2), (PROP_POWER, 0.6)],
    27: [(PROP_POWER, 0.4)],

    29: [(PROP_DUELE, 0.2), (PROP_DUELE, 0.8)],
    30: [(PROP_DUELE, 0.0), (PROP_DUELE, 1)],

    38: [(PROP_REBOTE, 1)],
    39: [(PROP_REBOTE, 0.8)],
    40: [(PROP_REBOTE, 0.6)],
    41: [(PROP_REBOTE, 0.4)],
    42: [(PROP_REBOTE, 0.2)],

    45: [(PROP_REBOTE, 0), (PROP_POWER, 1)],
    46: [(PROP_REBOTE, 0.2)],
    47: [(PROP_REBOTE, 0.4)],
    48: [(PROP_REBOTE, 0.6)],
    49: [(PROP_REBOTE, 1)],

    50: [(PROP_DUELE, 0), (PROP_DUELE, 1)],
    51: [(PROP_DUELE, 0.2), (PROP_DUELE, 0.8)],
    53: [(PROP_DUELE, 0.4), (PROP_DUELE, 1)],
}

TILES = {
    0: "fin",
    3: "pasto",
    25: "damero",
    29: "pasto",
    50: "damero",
    WIN_ROW: "fin",
}

class Nivel01(TinchoLevel):
    win_row = WIN_ROW
    tiempo_límite = 25
    tiles_info = TILES
    props_info = PROPS

    def on_enter(self):
        super(Nivel01, self).on_enter()
