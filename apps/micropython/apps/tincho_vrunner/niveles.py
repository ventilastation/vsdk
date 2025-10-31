from ventilastation.director import director, PIXELS, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from urandom import choice, randrange, seed


FULLSCREEN_MODE = 0
TUNNEL_MODE = 1
HUD_MODE = 2

CENTRO_WIDTH = 32

DAMERO_COLS = 3
DAMERO_ROWS = 8
TILE_WIDTH = 32
TILE_HEIGHT = 16

ROWS_WIDTH = TILE_WIDTH * DAMERO_COLS
ROWS_HEIGHT = TILE_HEIGHT * DAMERO_ROWS
ROWS_HI_HEIGHT = TILE_HEIGHT * (DAMERO_ROWS - 5)
ROWS_LO_HEIGHT = TILE_HEIGHT * (DAMERO_ROWS - 3)

COLS_CENTERS = [int(TILE_WIDTH * (DAMERO_COLS/2 - 0.5 -c) ) for c in range(DAMERO_COLS)]

# FIXME
DESFAZAJES = [0, 1, 2, 1, 1, 0, -1, -1]

VELOCIDADES = [1/8, 1/4, 1/2, 1, 2, 3]
VELOCIDAD_POWERUP = 5

PLAYER_HORIZONTAL_DELAY = {
    1/8: 8,
    1/4: 6,
    1/2: 4,
    1: 2,
    2: 1,
    3: 1,
    VELOCIDAD_POWERUP: 1,
}

PLAYER_HORIZONTAL_VEL = {
    1/8: 1,
    1/4: 1,
    1/2: 1,
    1: 1,
    2: 1,
    3: 2,
    VELOCIDAD_POWERUP: 2,
}

PLAYER_WIDTH = 14
MAX_PLAYER_X = - (ROWS_WIDTH // 2)
MIN_PLAYER_X = (ROWS_WIDTH - PLAYER_WIDTH) - (ROWS_WIDTH // 2)


PROP_SPRITES_LEN = 3 * 8

PROP_REBOTE = 0
PROP_DUELE = 1
PROP_POWER = 2

DEBUG_SIN_DESFAZAJE = False #or True

WIN_ROW = 40



# TODO: datos del nivel:
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


def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(stripes[strip])
    planet.set_perspective(FULLSCREEN_MODE)
    planet.set_x(0)
    planet.set_y(255)
    planet.set_frame(0)
    return planet


def get_tile(tile_y):
    prev_y = 0
    for y in sorted(TILES):
        if y <= tile_y:
            prev_y = y
        else:
            break
    return TILES[prev_y]


def get_damero_strip(tile, _tile_x, tile_y):
    if tile == "pasto":
        return stripes["suelo.png"]
    return stripes["damero.png"]


def get_damero_frame(tile, tile_x, tile_y):
    if tile == "damero":
        return (tile_x + tile_y) % 2
    return 0

def get_tunel_x(sprite, tile_x, width=None):
    return COLS_CENTERS[tile_x] - (width or sprite.width()) // 2

def get_tunel_x_proporcional(sprite, x_prop, width=None):
    w = width or sprite.width()
    return int((ROWS_WIDTH - w) * x_prop) - (ROWS_WIDTH // 2)

def get_tunel_y(_sprite, tile_y):
    return (tile_y + 1) * TILE_HEIGHT

class Nivel01(Scene):
    stripes_rom = "tincho_vrunner"

    def on_enter(self):
        super(Nivel01, self).on_enter()

        self.cur_frame = 0
        self.cur_tile_y = 0
        self.y_acc = 0

        self.player = Sprite()
        self.player.set_strip(stripes["tincho_palante.png"])
        self.player_x = -(self.player.width() // 2)
        self.player.set_x(self.player_x)
        self.player.set_y(0)
        self.player.set_frame(0)
        self.player.set_perspective(HUD_MODE)
        self.player_no_me_duele = False # or True

        # self.has_centro = True
        # self.tiles_centro = []
        # for i in range(256 // CENTRO_WIDTH):
        #     tile = Sprite()
        #     self.tiles_centro.append(tile)
        #     tile.set_strip(stripes["centro.png"])
        #     tile.set_x(i * CENTRO_WIDTH)
        #     tile.set_y(54-tile.height())
        #     tile.set_frame(0)
        #     tile.set_perspective(HUD_MODE)

        # TODO una lista de props
        self.props = []
        for i in range(PROP_SPRITES_LEN):
            prop = Sprite()
            prop.set_strip(stripes["props.png"])
            prop.set_perspective(TUNNEL_MODE)
            prop.disable()
            prop.tile_y = 0
            self.props.append(prop)

        self.poner_props_en_current_cacho_de_tunel()

        self.tiles_suelo = {}
        for tile_x in range(DAMERO_COLS):
            for tile_y in range(DAMERO_ROWS):
                tile = Sprite()
                tile.set_perspective(TUNNEL_MODE)
                self.tiles_suelo[(tile_x, tile_y)] = tile
                tile.set_x(get_tunel_x(tile, tile_x, width=32) + (0 if DEBUG_SIN_DESFAZAJE else DESFAZAJES[tile_y % len(DESFAZAJES)-1]*2))
                tile.set_y(get_tunel_y(tile, tile_y))
                t = get_tile(tile_y)
                tile.set_strip(get_damero_strip(t, tile_x, tile_y))
                tile.set_frame(get_damero_frame(t, tile_x, tile_y))
                tile.tile_x = tile_x
                tile.tile_y = tile_y

        make_me_a_planet("negro.png")

        self.run_vel = 1/4
        self.run_dir = 1
        self.run_acc = 0
        self.con_power = False

        self.duration = 1000
        self.call_later(self.duration, self.acelerar)
        self.ganaste = False

    def step(self):
        self.cur_frame = (self.cur_frame + 1) % 256

        self.update_player_frame()

        if abs(self.run_vel) >= 1:
            self.y_acc += self.run_vel
            self.animar_paisaje(self.run_vel)
        else:
            self.run_acc += self.run_vel
            entero = int(self.run_acc)
            if entero:
                self.y_acc += entero
                self.animar_paisaje(entero)
                self.run_acc = 0

        if abs(self.y_acc) > TILE_HEIGHT:
            dir = 1 if self.run_vel > 0 else -1
            self.y_acc = 0
            self.cur_tile_y += 1 * dir
            self.poner_props_en_current_cacho_de_tunel()
            if not self.ganaste and self.cur_tile_y >= WIN_ROW:
                print("GANASTE")
                self.ganaste = True
                self.camara_lenta()

        if director.was_pressed(director.BUTTON_D): # or director.timedout:
            self.finished()

        if self.ganaste:
            return

        x_axis = director.is_pressed(director.JOY_LEFT) - director.is_pressed(director.JOY_RIGHT)
        if x_axis and not self.cur_frame % PLAYER_HORIZONTAL_DELAY[abs(self.run_vel)]:
            new_x = self.player_x + x_axis * PLAYER_HORIZONTAL_VEL[abs(self.run_vel)]
            self.player_x = max(min(new_x, MIN_PLAYER_X), MAX_PLAYER_X)
            self.player.set_x(self.player_x)

        if self.run_dir > 0:
            self.probar_colisiones()

        # if director.was_pressed(director.BUTTON_A):
        #     self.powerup()


    def finished(self):
        director.pop()
        raise StopIteration()

    def update_player_frame(self):
        if self.player_no_me_duele:
            if self.cur_frame % 2:
                self.player.disable()
                return
        if abs(self.run_vel) == VELOCIDAD_POWERUP:
            self.player.set_frame(((self.cur_frame // 4) % 2) + 4)
        elif abs(self.run_vel) == VELOCIDADES[-1]:
            self.player.set_frame((self.cur_frame // 4) % 4)
        elif abs(self.run_vel) >= 1:
            self.player.set_frame((self.cur_frame // 8) % 4)
        else:
            self.player.set_frame((self.cur_frame // 16) % 4)

    def animar_paisaje(self, dy):
        for tile in self.tiles_suelo.values():
            y = tile.y() - dy
            pega_la_vuelta = False
            if y > ROWS_HEIGHT:
                tile.set_y(y - ROWS_HEIGHT)
                tile.tile_y = self.cur_tile_y
                pega_la_vuelta = True
            elif y < 0:
                tile.set_y(ROWS_HEIGHT + y)
                tile.tile_y = self.cur_tile_y + DAMERO_ROWS
                pega_la_vuelta = True
            else:
                tile.set_y(y)
            if pega_la_vuelta:
                t = get_tile(tile.tile_y)
                tile.set_strip(get_damero_strip(t, tile.tile_x, tile.tile_y))
                tile.set_frame(get_damero_frame(t, tile.tile_x, tile.tile_y))

        for prop in self.props:
            prop.set_y(prop.y() - dy)

    def poner_props_en_current_cacho_de_tunel(self):
        props_pa_poner = {}
        for k, v in PROPS.items():
            if k >= self.cur_tile_y and k < self.cur_tile_y + DAMERO_ROWS:
                props_pa_poner[k] = v

        prop_idx = 0
        for tile_y, prop_info in props_pa_poner.items():
            for tipo_prop, x_prop in prop_info:
                prop = self.props[prop_idx]
                prop.tile_y = tile_y
                prop.set_x(get_tunel_x_proporcional(prop, x_prop))
                prop.set_y(get_tunel_y(prop, tile_y - self.cur_tile_y))
                prop.set_frame(tipo_prop)
                prop_idx += 1

        while prop_idx < len(self.props):
            prop = self.props[prop_idx]
            prop.disable()
            prop_idx += 1

    def probar_colisiones(self):
        rebote = []
        duele = []
        power = []
        for prop in self.props:
            if prop.tile_y != self.cur_tile_y + 1:
                continue
            if prop.frame() == PROP_REBOTE:
                rebote.append(prop)
            elif prop.frame() == PROP_DUELE:
                duele.append(prop)
            elif prop.frame() == PROP_POWER:
                power.append(prop)

        if self.player.collision(rebote):
            self.ir_patrás_un_rato()
        elif not self.player_no_me_duele and self.player.collision(duele):
            self.bajar_un_cambio()
        elif self.player.collision(power):
            self.powerup()

    def powerup(self):
        self.con_power = True
        self.run_vel = VELOCIDAD_POWERUP * self.run_dir
        self.call_later(self.duration, self.fin_powerup)

    def fin_powerup(self):
        self.con_power = False
        self.run_vel = VELOCIDADES[len(VELOCIDADES)-1] * self.run_dir

    def acelerar(self):
        if self.ganaste:
            return
        if self.con_power:
            self.call_later(self.duration, self.acelerar)
            return

        cur_index = VELOCIDADES.index(abs(self.run_vel))
        if cur_index == len(VELOCIDADES)-1:
            return

        new_index = cur_index + 1
        self.run_vel = VELOCIDADES[max(min(new_index, len(VELOCIDADES)-1), 0)] * self.run_dir
        s = "tincho_palante.png" if self.run_vel > 0 else "tincho_patras.png"
        self.player.set_strip(stripes[s])
        self.call_later(self.duration, self.acelerar)

    def camara_lenta(self):
        self.run_dir = 1
        self.run_vel = 1/16

    def ir_patrás_un_rato(self):
        self.run_dir *= -1
        self.run_vel = self.run_vel * self.run_dir
        s = "tincho_palante.png" if self.run_vel > 0 else "tincho_patras.png"
        self.player.set_strip(stripes[s])
        self.call_later(self.duration // 4, self.desacelerar)

    def set_vulnerable(self):
        self.player_no_me_duele = False

    def bajar_un_cambio(self):
        self.run_vel = min(1/2, self.run_vel)
        self.player_no_me_duele = True
        self.call_later(self.duration // 2, self.set_vulnerable)


    def fin_patrás(self):
        self.run_dir = 1
        self.run_vel = 1/4
        s = "tincho_palante.png" if self.run_vel > 0 else "tincho_patras.png"
        self.player.set_strip(stripes[s])
        self.call_later(self.duration // 4, self.acelerar)

    def desacelerar(self):
        if self.ganaste:
            return
        if self.con_power:
            self.call_later(self.duration // 4, self.desacelerar)
            return

        cur_index = VELOCIDADES.index(abs(self.run_vel))
        if cur_index == 0:
            self.fin_patrás()
            return

        new_index = cur_index - 1
        self.run_vel = VELOCIDADES[max(min(new_index, len(VELOCIDADES)-1), 0)] * self.run_dir
        s = "tincho_palante.png" if self.run_vel > 0 else "tincho_patras.png"
        self.player.set_strip(stripes[s])

        self.call_later(self.duration // 4, self.desacelerar)
