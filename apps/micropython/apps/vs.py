from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

# Contador de sprites:
# 5 para cada item del menu
# 5 para el contador de monedas
# 11 para las letras de los nombres del menu       -> hardcodeable
# 11 para las letras de las descripciones del menu -> hardcodeable
# 3 para el precio de los items del menu           -> hardcodeable
# 9 para los items en el tablero
# 1 para el piso
# 9 para las balas
# 1 para el lolero de prueba
# = 44


# Dadas dos coordinadas en una matriz de tamaño 3x3 te dice qué indice es en un array tamaño 9
def coords(i, j):
    return i + j*3

class Text:
    def __init__(self, x, y, len, sprite, invert):
        self.chars = []
        self.len = len
        self.invert = invert

        for n in range(len):
            s = Sprite()
            s.set_strip(stripes[sprite])
            if self.invert:
                s.set_x(x + n * 8)
            else:
                s.set_x(x - n * 8)
            s.set_y(y)
            s.set_frame(0)
            s.set_perspective(2)
            self.chars.append(s)

        self.setletters("")

    def setletters(self, text):
        for n, l in enumerate('{message: <{width}}'.format(message=text, width=self.len)):
            if n < len(self.chars):  
                self.chars[n].disable()
                if self.invert:
                    self.chars[n].set_frame(255-ord(l))
                else:
                    self.chars[n].set_frame(ord(l))

class Numbers:
    def __init__(self, x, y, len):
        self.chars = []
        self.len = len

        self.burbujita = Sprite()
        self.burbujita.set_strip(stripes["burbujita.png"])
        self.burbujita.set_frame(0)
        self.burbujita.set_x(x - 4)
        self.burbujita.set_y(y)
        self.burbujita.set_perspective(2)

        for n in range(len):
            s = Sprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(x + n * 4)
            s.set_y(y)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)
        
        self.setnumbers(0)

    def setnumbers(self, value):
        format_string = f"%0{self.len}d"
        for n, l in enumerate(format_string % value):
            if n < len(self.chars):
                v = ord(l) - 0x30
                self.chars[n].set_frame(v)

class Bullet(Sprite):
    
    def __init__(self):

        super().__init__()
        self.set_strip(stripes["vga_pc734.png"])
        self.is_active = False
        self.is_reloading = False
        self.is_waiting_to_deactivate = False

        self.initial_x = 0
        # self.close_reach = None
        # self.long_reach = None
        # self.type = ""

    def activate(self, type):
        self.is_active = True
        self.is_reloading = False
        self.is_waiting_to_deactivate = False

        self.type = type

        if type == "Jabon":
            self.close_reach = range(0, self.initial_x+1) # de la izquierda al centro
            self.long_reach  = range(192, 256)            # del centro a la derecha
        elif type == "Desodorante":
            self.close_reach = range(0, self.initial_x+1)      # de la izquierda al centro
            self.long_reach  = range(192+self.initial_x, 256)  # del centro a la derecha

    def set_initial_x(self, x):
        self.initial_x = x
        self.set_x(x)

    def deactivate(self):
        self.disable()
        self.set_x(self.initial_x)
        self.is_active = False
        self.type = ""

    def reset(self):
        if self.is_waiting_to_deactivate:
            self.deactivate()
        else:
            self.disable()
            self.set_x(self.initial_x)
            self.is_reloading = True

    def shoot(self):
        if self.is_active:
            self.is_reloading = False
            self.set_frame(6)

    def step(self):
        if self.is_active and not self.is_reloading:
            if self.x() in self.close_reach or self.x() in self.long_reach:
                self.set_x(self.x()-1)
            else:
                self.reset()

class Item(Sprite): 

    def __init__(self, bullet):
        super().__init__()

        self.bullet = bullet
        self.set_strip(stripes["items.png"])
        self.deactivate()

    
        self.hps    = [5, 25, 5, 5, 1]
        self.types  = ["Jabon", "Pala", "Burbujero", "Desodorante", "Tocar pasto"]
        
        self.strips = ["jabon.png", "pala.png", "burbujero.png", "desodorante.png", "pasto.png"]
        self.frame_amounts = [4, 8, 2, 4, 2]
        self.frame_rates   = [5, 5, 5, 5, 5]

    def se_ensucia(self, value, step_counter):
        if step_counter % 20 == 0:
            self.hp -= value
            if self.hp <= 0:
                self.deactivate()

    def deactivate(self):
        self.disable()
        self.is_active = False
        self.bullet.is_waiting_to_deactivate = True
        self.active_frame = None

    def temporarily_activate_item(self, frame):
        self.set_frame(frame)
        self.set_strip(stripes["items.png"])


    def definitely_activate_item(self, frame):
        self.set_frame(frame)
        self.active_frame = frame

        self.set_strip(stripes[self.strips[frame]])
        self.frame_amount = self.frame_amounts[frame]
        self.frame_rate   = self.frame_rates[frame]

        self.is_active = True
        self.bullet.is_waiting_to_deactivate = True

        self.hp = self.hps[self.active_frame]
        self.type = self.types[self.active_frame]

        if self.type == "Jabon":
            self.bullet.activate("Jabon")
        elif self.type == "Desodorante":
            self.bullet.activate("Desodorante")

    def restore_active_frame(self):

        if self.is_active:
            self.set_frame(self.active_frame)
            self.set_strip(stripes[self.strips[self.active_frame]])
        else:
            self.disable()
    
    def step(self, step_counter):
        
        if self.bullet.is_active:
            if self.bullet.is_reloading:
                    
                if self.frame() == self.frame_amount-1:
                    self.bullet.shoot()
                self.set_frame((self.frame() + 1) % self.frame_amount)
                
        else:
            if step_counter % self.frame_rate == 0:
                self.set_frame((self.frame() + 1) % self.frame_amount)


class Lolero(Sprite):

    def __init__(self):
        super().__init__()
        self.set_strip(stripes["lolero.png"])
        self.revive()

    def revive(self):
        self.set_x(192)
        self.set_y(18)
        self.set_frame(0)
        self.is_active = True
        self.can_move = True
        self.has_debuff = False
        self.debuff_turns = 0
        self.hp = 5
        self.speed = 5

    def se_baña(self, value):
        self.hp -= value
        if self.hp <= 0:
            self.morite()

    def se_realentiza(self):
        self.speed = 20
        self.debuff_turns = 3
        self.has_debuff = True

    def morite(self):
        self.disable()
        self.set_x(192) 
        self.is_active = False
        self.can_move = False
        self.has_debuff = False
    
    def step(self, step_counter):
        
        if self.debuff_turns <= 0:
            self.speed = 5
            self.has_debuff = False

        if self.is_active and step_counter % self.speed == 0 :

            if self.can_move:
                self.set_x(self.x() + 1)
                self.set_frame((self.frame() + 1) % 4)

            if self.has_debuff:
                self.debuff_turns -= 1

class Menu():
    def __init__(self):

        self.selected_id    = 0
        
        self.y          = 24
        self.selected_y = 20
        
        self.items = [Sprite() for _ in range(5)]
        for i, item in enumerate(self.items):
            item.set_strip(stripes["smeti.png"])
            item.set_x(72+i*18)
            item.set_y(self.y)
            item.set_frame(i)

        self.items[self.selected_id].set_y(self.selected_y)
        
        #self.hps    = [5, 25, 5, 5, 1]
        
        self.items_name        =  ["Jabon", "Pala", "Burbujero", "Desodorante", "Tocar pasto"]
        self.items_stats       =  ["atk  1 HP 30", "atk  0 HP 25", "atk  0 HP  5", "atk  0 HP  5", "atk 10 HP  1"]
        self.items_description =  ["limpia nerds", "intocable", "da burbujas", "los espanta", "kabum!"]
        self.items_price       = [100, 200, 300, 400, 500]

        self.text        = Text(x=93,   y=18, len=11, sprite="vga_pc734.png",         invert=True)
        self.stats       = Text(x=93,   y=30, len=13, sprite="vga_pc734_verde.png",   invert=True)
        self.description = Text(x=64-9, y=27, len=13, sprite="vga_pc734_celeste.png", invert=False)
        self.price       = Numbers(x=72, y=21,  len=4)
        self.write_description()

    def move_focus_to(self, direction):
        self.items[self.selected_id].set_y(self.y)
        self.selected_id = (self.selected_id + direction) % 5
        self.items[self.selected_id].set_y(self.selected_y)
        self.write_description()

    def get_focused_item_info(self):
        return self.selected_id, self.items_name[self.selected_id], self.items_price[self.selected_id]

    def change_focused_item_frame(self, i):
        self.items[self.selected_id].set_frame(self.items[self.selected_id].frame() + i)

    def write_description(self):
        self.text.setletters(self.items_name[self.selected_id])
        self.price.setnumbers(self.items_price[self.selected_id])
        self.stats.setletters(self.items_description[self.selected_id])
        self.description.setletters(self.items_stats[self.selected_id])

class vs(Scene):

    stripes_rom = "vs"

    def activate_item_at(self, i, j):
        self.i = i
        self.j = j
        self.selection_item.set_frame(self.item_to_place + 5)
        self.selection_item.set_x(48-i*16)
        self.selection_item.set_y(16+j*16)

    def move_focus_to(self, movement_i, movement_j):
        self.i = (self.i + movement_i) % 3
        self.j = (self.j + movement_j) % 3
        self.selection_item.set_x(48-self.i*16)
        self.selection_item.set_y(16+self.j*16)

    def place_item(self):
        self.items[coords(self.i, self.j)].definitely_activate_item(self.item_to_place)
        self.item_to_place = None
        self.selection_item.disable()

    def add_money(self, value):
        self.money = self.money + value
        self.money_counter.setnumbers(self.money)

    def on_enter(self):
        super(vs, self).on_enter()
  
        self.selection_item = Sprite()
        self.selection_item.set_strip(stripes["items.png"])
        self.selection_item.disable()

        self.menu  = Menu()
        self.bullets = [Bullet() for _ in range(9)]
        self.items = [Item(self.bullets[id]) for id in range(9)]

        for i in range(3):
            for j in range(3):
                self.items[coords(i, j)].set_x(48-i*16)
                self.items[coords(i, j)].set_y(16+j*16)
                self.bullets[coords(i, j)].set_initial_x(48-i*16)
                self.bullets[coords(i, j)].set_y(16+j*16)  

        self.i = 0
        self.j = 0

        self.loleros = [Lolero() for _ in range(1)]

        self.money = 0
        self.money_counter = Numbers(x=165, y=8, len=5)
        self.add_money(10000)

        self.road = Sprite()
        self.road.set_strip(stripes["road.png"])
        self.road.set_x(192)
        self.road.set_y(16)
        self.road.set_frame(0)

        self.item_to_place = None
        
        self.step_counter = 0

    def step(self):
        
        for bullet in self.bullets:
            bullet.step()

        for item in self.items:
            if item.is_active:
                item.step(self.step_counter)
                if item.type == "Burbujero" and self.step_counter % 30 == 0:
                    self.add_money(100)

        for lolero in self.loleros:
            if lolero.is_active:

                lolero.can_move = True
                bullet = lolero.collision(self.bullets)
                if bullet:
                    if bullet.is_active and not bullet.is_reloading:
                        if bullet.type == "Jabon":
                            lolero.se_baña(1)
                        if bullet.type == "Desodorante":
                            lolero.se_realentiza()
                        bullet.reset()

                item = lolero.collision(self.items)
                if item:
                    if item.is_active:
                        lolero.can_move = False
                        item.se_ensucia(1, self.step_counter)
                        if item.type == "Tocar pasto":
                            lolero.se_baña(10)
                            item.deactivate()

                lolero.step(self.step_counter)

        if self.item_to_place != None:

            if director.was_pressed(director.JOY_RIGHT):
                self.move_focus_to(1,0)
    
            if director.was_pressed(director.JOY_LEFT):
                self.move_focus_to(-1,0)
    
            if director.was_pressed(director.JOY_UP):
                self.move_focus_to(0,1)
    
            if director.was_pressed(director.JOY_DOWN):
                self.move_focus_to(0,-1)

            if director.was_pressed(director.BUTTON_A):
                self.place_item()
                self.menu.change_focused_item_frame(-5)

        else:

            if director.was_pressed(director.JOY_RIGHT):
                self.menu.move_focus_to(1)
    
            if director.was_pressed(director.JOY_LEFT):
                self.menu.move_focus_to(-1)

            # if director.was_pressed(director.JOY_UP):
                # Quizás up y down puedan cambiar la descripcion del item

            # if director.was_pressed(director.JOY_DOWN):
                # Quizás up y down puedan cambiar la descripcion del item

            if director.was_pressed(director.BUTTON_A):
                id, name, price = self.menu.get_focused_item_info()
                if self.money >= price:
                    
                    self.add_money(-price)
                    self.item_to_place = id
                    self.activate_item_at(0,0)

                    self.menu.change_focused_item_frame(5)
                    print("Compramos "  + name)

                else:
                    print("No alcanza la plata")
        
        if director.was_pressed(director.BUTTON_D):
            self.finished()

        self.step_counter += 1

    def finished(self):
        director.pop()
        raise StopIteration()

def main():
    return vs()