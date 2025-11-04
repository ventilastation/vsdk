from apps.tincho_vrunner.tincho_level import TinchoLevel, PROP_REBOTE, PROP_DUELE, PROP_POWER

WIN_ROW = 40

PROPS = {
    0: [(PROP_REBOTE, 0.2)],
    1: [(PROP_REBOTE, 0),],
    2: [(PROP_REBOTE, 0.2)],
    3: [(PROP_REBOTE, 0)],
    4: [(PROP_REBOTE, 0.2)],
    5: [(PROP_DUELE, 0.3), (PROP_DUELE, 0.5)],
    6: [(PROP_REBOTE, 0.2)],
    7: [(PROP_REBOTE, 0)],
    8: [(PROP_REBOTE, 0.2)],
    9: [(PROP_POWER, 0.5)],
    #
    10: [(PROP_REBOTE, 0.8)],
    11: [(PROP_REBOTE, 1)],
    12: [(PROP_REBOTE, 0.8)],
    13: [(PROP_REBOTE, 1)],
    14: [(PROP_REBOTE, 0.8)],
    15: [(PROP_REBOTE, 0.5)],
    16: [(PROP_REBOTE, 0.8)],
    17: [(PROP_REBOTE, 1)],
    18: [(PROP_REBOTE, 0.8)],
    19: [(PROP_REBOTE, 1)],
    20: [(PROP_REBOTE, 0.2)],
    21: [(PROP_REBOTE, 0)],
    22: [(PROP_REBOTE, 0.2)],
    23: [(PROP_REBOTE, 0)],
    24: [(PROP_REBOTE, 0.2)],
    25: [(PROP_REBOTE, 0.5)],
    26: [(PROP_REBOTE, 0.2)],
    27: [(PROP_REBOTE, 0)],
    28: [(PROP_REBOTE, 0.2)],
    29: [(PROP_REBOTE, 0), (PROP_POWER, 0.5)],
    30: [(PROP_REBOTE, 0.2)],

    32: [(PROP_REBOTE, 0)],
    33: [(PROP_REBOTE, 0.2)],
    34: [(PROP_REBOTE, 0.4)],
    35: [(PROP_REBOTE, 0.6)],
    36: [(PROP_DUELE, 0.8)],
    37: [(PROP_REBOTE, 1)],
}

TILES = {
    0: "damero",
    5: "pasto",
    10: "damero",
    15: "pasto",
    20: "damero",
    25: "pasto",
    30: "damero",
    35: "pasto",
    WIN_ROW: "damero",
}

class Nivel01(TinchoLevel):
    win_row = WIN_ROW
    tiempo_límite = 20
    tiles_info = TILES
    props_info = PROPS

    def on_enter(self):
        super(Nivel01, self).on_enter()
