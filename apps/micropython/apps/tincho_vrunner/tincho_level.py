from ventilastation.director import director, PIXELS, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from urandom import choice, randrange, seed

class MySprite(Sprite):
    pass


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

VELOCIDADES = [0, 1/8, 1/4, 1/2, 1, 2, 3]
VELOCIDAD_POWERUP = 5

DURACIONES = {
    0: 20,
    1/8: 50,
    1/4: 50,
    1/2: 300,
    1: 400,
    2: 600,
    3: 600,
    VELOCIDAD_POWERUP: 1200,
}

PLAYER_HORIZONTAL_DELAY = {
    0: 8,
    1/8: 8,
    1/4: 6,
    1/2: 4,
    1: 2,
    2: 1,
    3: 1,
    VELOCIDAD_POWERUP: 1,
}

PLAYER_HORIZONTAL_VEL = {
    0: 2,
    1/8: 2,
    1/4: 2,
    1/2: 2,
    1: 2,
    2: 2,
    3: 2,
    VELOCIDAD_POWERUP: 1,
}

PLAYER_WIDTH = 14
MAX_PLAYER_X = - (ROWS_WIDTH // 2)
MIN_PLAYER_X = (ROWS_WIDTH - PLAYER_WIDTH) - (ROWS_WIDTH // 2)


PROP_SPRITES_LEN = 3 * 8

PROP_REBOTE = 0
PROP_DUELE = 1
PROP_POWER = 2

DEBUG_SIN_DESFAZAJE = False #or True
DEBUG_VELOCIDAD = False #or True
DEBUG_CUR_TILE_Y = False #or True
DEBUG_TIEMPO = False #or True

def make_me_a_planet(strip):
    planet = MySprite()
    planet.set_strip(stripes[strip])
    planet.set_perspective(FULLSCREEN_MODE)
    planet.set_x(0)
    planet.set_y(255)
    planet.set_frame(0)
    return planet


def get_damero_strip(tile, _tile_x, tile_y):
    # if tile == "pasto":
    #     return stripes["suelo2.png"]
    # return stripes["damero2.png"]
    return stripes["suelos.png"]


def get_damero_frame(tile, tile_x, tile_y):
    if tile == "pasto":
        return tile_x
    elif tile == "damero":
        return 3 + ((tile_x + tile_y) % 2)
    elif tile == "fin":
        return 5
    return 5

def get_prop_frame(prop, x_prop):
    if prop == PROP_REBOTE:
        if x_prop < 0.2:
            return 0
        elif x_prop <= 0.4:
            return 1
        elif x_prop <= 0.6:
            return 2
        elif x_prop <= 0.8:
            return 3
        return 4
    elif prop == PROP_DUELE:
        return 5
    elif prop == PROP_POWER:
        return 6

def get_tunel_x(sprite, tile_x, width=None):
    return COLS_CENTERS[tile_x] - (width or sprite.width()) // 2

def get_tunel_x_proporcional(sprite, x_prop, width=None):
    w = width or sprite.width()
    return int((ROWS_WIDTH - w) * x_prop) - (ROWS_WIDTH // 2)

def get_tunel_y(_sprite, tile_y):
    return (tile_y + 1) * TILE_HEIGHT

class TinchoLevel(Scene):
    stripes_rom = "tincho_vrunner"

    siguiente = None
    patrás = False
    row_inicial = 0
    win_row = -1
    tiempo_límite = 30
    tiles_info = {}
    props_info = {}

    def on_enter(self):
        super(TinchoLevel, self).on_enter()

        self.cur_frame = 0
        self.cur_tile_y = self.row_inicial
        self.y_acc = 0

        self.hud_tiempo = []
        for i in range(2):
            s = MySprite()
            s.set_strip(stripes["numeritos.png"])
            s.set_x(128 - i * (s.width() + 2))
            s.set_y(0)
            s.set_frame(0)
            s.set_perspective(HUD_MODE)
            self.hud_tiempo.append(s)

        self.player = MySprite()
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
        #     tile = MySprite()
        #     self.tiles_centro.append(tile)
        #     tile.set_strip(stripes["centro.png"])
        #     tile.set_x(i * CENTRO_WIDTH)
        #     tile.set_y(54-tile.height())
        #     tile.set_frame(0)
        #     tile.set_perspective(HUD_MODE)

        self.props = []
        for i in range(PROP_SPRITES_LEN):
            prop = MySprite()
            prop.set_strip(stripes["props.png"])
            prop.set_perspective(TUNNEL_MODE)
            prop.disable()
            prop.tile_y = 0
            self.props.append(prop)

        self.poner_props_en_current_cacho_de_tunel()

        self.tiles_suelo = []
        for tile_x in range(DAMERO_COLS):
            for tile_y in range(DAMERO_ROWS):
                tile = MySprite()
                tile.set_perspective(TUNNEL_MODE)
                self.tiles_suelo.append(tile)
                tile.set_x(get_tunel_x(tile, tile_x, width=32) + (0 if DEBUG_SIN_DESFAZAJE else DESFAZAJES[tile_y % len(DESFAZAJES)-1]*2))
                tile.set_y(get_tunel_y(tile, tile_y))
                t = self.get_tile(self.row_inicial + tile_y)
                tile.set_strip(get_damero_strip(t, tile_x, self.row_inicial + tile_y))
                tile.set_frame(get_damero_frame(t, tile_x, self.row_inicial + tile_y))
                tile.tile_x = tile_x
                tile.tile_y = self.row_inicial + tile_y

        self.fondo_rojo = make_me_a_planet("rojo.png")
        self.fondo_rojo.disable()
        self.fondo_amarillo = make_me_a_planet("amarillo.png")
        self.fondo_amarillo.disable()
        make_me_a_planet("negro.png")

        self.run_vel = 0 if DEBUG_VELOCIDAD else (VELOCIDADES[-1] if self.patrás else 1/4)
        self.run_dir = -1 if self.patrás else 1
        self.actualizar_strip_player()

        self.run_acc = 0
        self.con_power = False

        self.duration = 1000
        if not DEBUG_VELOCIDAD:
            if self.patrás:
                self.call_later(self.duration, self.ir_patrás)
            else:
                self.call_later(self.duration, self.acelerar)

        self.terminaste = False
        self.tiempo_que_falta = self.tiempo_límite
        self.tirame_las_agujas()
        if not DEBUG_VELOCIDAD:
            self.call_later(1000, self.reducir_un_segundo)

    def step(self):
        self.cur_frame = (self.cur_frame + 1) % 256

        dy = 0

        if self.run_vel >= 1:
            dy = self.run_vel * self.run_dir
            self.y_acc += dy
        else:
            self.run_acc += self.run_vel * self.run_dir
            entero = int(self.run_acc)
            if entero:
                dy = entero
                self.y_acc += dy
                self.run_acc = 0

        cambió_tile = False
        if abs(self.y_acc) >= TILE_HEIGHT:
            self.y_acc = 0
            self.cur_tile_y += self.run_dir
            if DEBUG_CUR_TILE_Y:
                print("tile: %d" % self.cur_tile_y)
            cambió_tile = True

        self.actualizar_frame_player()

        self.animar_paisaje(dy)

        if cambió_tile:
            self.poner_props_en_current_cacho_de_tunel(dy)
            if not self.terminaste and (not self.patrás and self.cur_tile_y >= self.win_row) or (self.patrás and self.cur_tile_y <= self.win_row) and not DEBUG_VELOCIDAD:
                self.pasó_la_meta()

        if director.was_pressed(director.BUTTON_D): # or director.timedout:
            self.finished()

        if self.terminaste:
            return

        x_axis = director.is_pressed(director.JOY_LEFT) - director.is_pressed(director.JOY_RIGHT)
        if x_axis and not self.cur_frame % PLAYER_HORIZONTAL_DELAY[self.run_vel]:
            new_x = self.player_x + x_axis * PLAYER_HORIZONTAL_VEL[self.run_vel]
            self.player_x = max(min(new_x, MIN_PLAYER_X), MAX_PLAYER_X)
            self.player.set_x(self.player_x)

        if DEBUG_VELOCIDAD:
            if director.was_pressed(director.BUTTON_A):
                # self.powerup()
                self.run_vel = 0
            if director.was_pressed(director.JOY_LEFT):
                self.run_dir = -1
                self.run_vel = 1/4
            if director.was_pressed(director.JOY_RIGHT):
                self.run_dir = 1
                self.run_vel = 1/4
            if director.was_pressed(director.JOY_DOWN):
                self.run_dir = -1
                self.run_vel = 2
            if director.was_pressed(director.JOY_UP):
                self.run_dir = 1
                self.run_vel = 2
            return

        if self.run_dir > 0:
            self.probar_colisiones()

    def finished(self):
        director.pop()
        raise StopIteration()

    def get_tile(self, tile_y):
        prev_y = 0
        for y in sorted(self.tiles_info):
            if y <= tile_y:
                prev_y = y
            else:
                break
        return self.tiles_info[prev_y]

    def actualizar_strip_player(self):
        s = "tincho_palante.png" if self.run_dir > 0 else "tincho_patras.png"
        self.player.set_strip(stripes[s])

    def actualizar_frame_player(self):
        if self.player_no_me_duele:
            if self.cur_frame % 2:
                self.player.disable()
                return
        if self.run_vel == VELOCIDAD_POWERUP:
            self.player.set_frame(((self.cur_frame // 4) % 2) + 4)
        elif self.run_vel >= 1/2:
            self.player.set_frame((self.cur_frame // 4) % 4)
        elif self.run_vel >= 1/4:
            self.player.set_frame((self.cur_frame // 8) % 4)
        else:
            self.player.set_frame((self.cur_frame // 16) % 4)

    def animar_paisaje(self, dy):
        for tile in self.tiles_suelo:
            y = tile.y() - dy
            pega_la_vuelta = False
            if y > ROWS_HEIGHT:
                tile.set_y(y - ROWS_HEIGHT)
                tile.tile_y = self.cur_tile_y - 1
                pega_la_vuelta = True
            elif y < 0:
                tile.set_y(ROWS_HEIGHT + y)
                tile.tile_y = self.cur_tile_y + DAMERO_ROWS - 1
                pega_la_vuelta = True
            else:
                tile.set_y(y)
            if pega_la_vuelta:
                t = self.get_tile(tile.tile_y)
                tile.set_strip(get_damero_strip(t, tile.tile_x, tile.tile_y))
                tile.set_frame(get_damero_frame(t, tile.tile_x, tile.tile_y))

        for prop in self.props:
            prop.set_y(prop.y() - dy)

    def poner_props_en_current_cacho_de_tunel(self, dy=0):
        props_pa_poner = {}
        for k, v in self.props_info.items():
            if k >= self.cur_tile_y-1 and k < self.cur_tile_y + DAMERO_ROWS:
                props_pa_poner[k] = v

        prop_idx = 0
        for tile_y, prop_info in props_pa_poner.items():
            for tipo_prop, x_prop in prop_info:
                prop = self.props[prop_idx]
                prop.tile_y = tile_y
                prop.set_x(get_tunel_x_proporcional(prop, x_prop))
                prop.set_y(get_tunel_y(prop, tile_y - self.cur_tile_y) - dy)
                prop.set_frame(get_prop_frame(tipo_prop, x_prop))
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
            if prop.frame() <= 4:# PROP_REBOTE:
                rebote.append(prop)
            elif prop.frame() == 5: #PROP_DUELE:
                duele.append(prop)
            elif prop.frame() == 6: #PROP_POWER:
                power.append(prop)

        if self.player.collision(rebote):
            self.ir_patrás_un_rato()
        elif not self.player_no_me_duele and self.player.collision(duele):
            self.bajar_un_cambio()
        elif self.player.collision(power):
            self.powerup()

    def powerup(self):
        self.con_power = True
        self.run_vel = VELOCIDAD_POWERUP
        self.fondo_amarillo.set_frame(0)
        director.sound_play("tincho_vrunner/powerup%d" % randrange(3))
        self.call_later(DURACIONES[self.run_vel], self.fin_powerup)

    def fin_powerup(self):
        self.con_power = False
        self.run_vel = VELOCIDADES[len(VELOCIDADES)-1]
        self.fondo_amarillo.disable()

    def acelerar(self):
        if self.run_dir < 1:
            self.call_later(self.duration, self.acelerar)
            return
        if self.terminaste:
            return
        if self.con_power:
            self.call_later(self.duration, self.acelerar)
            return

        cur_index = VELOCIDADES.index(self.run_vel)
        if cur_index == len(VELOCIDADES)-1:
            self.call_later(self.duration, self.acelerar)
            return

        new_index = cur_index + 1
        self.run_vel = VELOCIDADES[max(min(new_index, len(VELOCIDADES)-1), 0)]
        self.call_later(self.duration, self.acelerar)

    def ir_patrás_un_rato(self):
        director.sound_play("tincho_vrunner/rebota%d" % randrange(3))
        self.run_dir = -1
        self.run_vel = VELOCIDAD_POWERUP if self.con_power else VELOCIDADES[-1]
        self.actualizar_strip_player()
        self.call_later(self.duration // (2 if self.con_power else 4), self.ir_patrás)

    def set_vulnerable(self):
        self.player_no_me_duele = False
        self.fondo_rojo.disable()

    def bajar_un_cambio(self):
        self.run_vel = min(1/2, self.run_vel)
        self.player_no_me_duele = True
        self.fondo_rojo.set_frame(0)
        director.sound_play("tincho_vrunner/duele%d" % randrange(3))
        self.call_later(self.duration // 2, self.set_vulnerable)


    def fin_patrás(self):
        self.run_dir = 1
        self.run_vel = 1/4
        self.player.set_strip(stripes["tincho_palante.png"])
        self.call_later(self.duration // 4, self.acelerar)

    def ir_patrás(self):
        if self.terminaste:
            return
        if self.con_power:
            self.call_later(self.duration // 4, self.ir_patrás)
            return

        cur_index = VELOCIDADES.index(self.run_vel)
        if cur_index == 0:
            self.fin_patrás()
            return

        new_index = cur_index - 1
        self.run_vel = VELOCIDADES[max(min(new_index, len(VELOCIDADES)-1), 0)]
        self.actualizar_strip_player()
        self.call_later(DURACIONES[self.run_vel], self.ir_patrás)

    def pasó_la_meta(self):
        self.terminaste = True
        self.run_dir = 1
        self.run_vel = 1/16
        self.fondo_amarillo.set_frame(0)
        self.call_later(self.duration * 5, self.vamos_al_siguiente)

    def vamos_al_siguiente(self):
        director.pop()
        director.push(self.siguiente())
        raise StopIteration()

    def vamos_otra_vez(self):
        director.pop()
        director.push(self.__class__())
        raise StopIteration()

    def reducir_un_segundo(self):
        if self.terminaste:
            return
        self.tiempo_que_falta -= 1
        if self.tiempo_que_falta <= 0:
            # alpiste, perdiste
            self.terminaste = True
            self.fondo_rojo.set_frame(0)
            self.run_vel = 1/16
            self.call_later(self.duration * 3, self.vamos_otra_vez)

        if DEBUG_TIEMPO:
            print("falta: %d" % self.tiempo_que_falta)
        self.tirame_las_agujas()

        self.call_later(1000, self.reducir_un_segundo)

    def tirame_las_agujas(self):
        i = 0
        t = self.tiempo_que_falta
        if t == 0:
            self.hud_tiempo[0].set_frame(0)
            return
        while t > 0:
            self.hud_tiempo[i].set_frame(t % 10)
            t = t // 10
            i += 1
        if i == 1:
            self.hud_tiempo[1].set_frame(0)
