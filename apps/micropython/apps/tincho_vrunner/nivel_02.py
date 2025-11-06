from apps.tincho_vrunner.tincho_level import TinchoLevel, PROP_REBOTE, PROP_DUELE, PROP_POWER

PROPS = {
    10: [(PROP_REBOTE, 0.6)],
    14: [(PROP_REBOTE, 0.0),(PROP_REBOTE, 0.2),(PROP_REBOTE, 0.8),(PROP_REBOTE, 1)],
    20: [(PROP_POWER, 0.5)],
    22: [(PROP_REBOTE, 0.6),(PROP_REBOTE, 0.8),(PROP_REBOTE, 1)],
    26: [(PROP_REBOTE, 0.0),(PROP_REBOTE, 0.2),(PROP_REBOTE, 0.4)],
    30: [(PROP_REBOTE, 0.0),(PROP_REBOTE, 0.2),(PROP_REBOTE, 0.4),(PROP_REBOTE, 0.6),(PROP_REBOTE, 0.8),(PROP_REBOTE, 1)],
}

TILES = {
    5: "fin",
    8: "pasto",
    16: "damero",
    19: "pasto",
    35: "fin",
}

class Nivel02(TinchoLevel):
    patrás = True
    row_inicial = 35
    win_row = 5
    tiempo_límite = 30
    tiles_info = TILES
    props_info = PROPS

    def on_enter(self):
        super(Nivel02, self).on_enter()
