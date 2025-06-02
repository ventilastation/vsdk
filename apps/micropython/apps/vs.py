from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

# Contador de sprites:

# Necesarios:
# 1 para el piso
# 5 para el contador de monedas
# 1 para la burbujita al lado del contador de monedas
# 1 para el item que se está comprando (el que está en el tablero)
# 5 para las opciones del menú
# 9 para los items en el tablero
# 9 para las balas
# 1 para el lolero de prueba
# Total: 32

# Hardodeables:
# 4 para el precio del item del menu
# 1 para la burbujita al lado del precio del item del menu
# 2 para el hp del item del menu (numeros)
# 1 para el hp del item del menu (texto "hp")
# 2 para el atk del item del menu (numeros)
# 1 para el atk del item del menu (texto "atk")
# 11 para las letras de los nombres del menu      
# 12 para las letras de las descripciones del menu
# Total de hardcodeables: 34

# Total: 66

# Dadas dos coordinadas en una matriz de tamaño 3x3 te dice qué indice es en un array tamaño 9
def coords(i, j):
    return i + j*3

class Text:
    def __init__(self, x, y, len, sprite):
        self.chars = []
        self.len = len

        for n in range(len):
            s = Sprite()
            s.set_strip(stripes[sprite])
            s.set_x(x + n * 8)
            s.set_y(y)
            s.set_frame(0)
            s.set_perspective(2)
            self.chars.append(s)

        self.setletters("")

    def setletters(self, text):
        for n, l in enumerate('{message: <{width}}'.format(message=text, width=self.len)):
            if n < len(self.chars):  
                self.chars[n].disable()
                self.chars[n].set_frame(255-ord(l))

class Numbers:
    def __init__(self, x, y, len, label=None, label_width=0, sprite="yellow_numerals.png"):
        self.chars = []
        self.len = len

        if label:
            self.label = Sprite()
            self.label.set_strip(stripes[label])
            self.label.set_x(x)
            self.label.set_y(y)
            self.label.set_frame(0)
            self.label.set_perspective(2)

        for n in range(len):
            s = Sprite()
            s.set_strip(stripes[sprite])
            s.set_x(x + n * 4 + label_width)
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
        self.set_strip(stripes["balas.png"])
        self.is_active = False
        self.is_reloading = False
        self.is_waiting_to_deactivate = False

        self.frame = None

        self.initial_x = 0

    def activate(self, type):
        self.is_active = True
        self.is_reloading = False
        self.is_waiting_to_deactivate = False

        self.type = type

        if type == "Jabon":
            self.close_reach = range(0, self.initial_x+1) # de la izquierda al centro
            self.long_reach  = range(192, 256)            # del centro a la derecha
            self.frame = 0

        elif type == "Desodorante":
            self.close_reach = range(0, self.initial_x+1)      # de la izquierda al centro
            self.long_reach  = range(192+self.initial_x, 256)  # del centro a la derecha
            self.frame = 1

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
            self.set_frame(self.frame)

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

        self.strips = ["jabon.png", "pala.png", "burbujero.png", "desodorante.png", "pasto.png"]
        
        self.frame_amounts = [4, 8, 2, 4, 2]
        self.frame_rates   = [3, 5, 30, 3, 5]
        self.types         = ["Jabon", "Pala", "Burbujero", "Desodorante", "Tocar pasto"]
        self.hps           = [5, 25, 5, 5, 1]
        
    def se_ensucia(self, value, step_counter):
        if step_counter % 20 == 0:
            self.hp -= value
            if self.hp <= 0:
                self.deactivate()

    def deactivate(self):
        self.disable()
        self.is_active = False
        self.bullet.is_waiting_to_deactivate = True
        self.id = None

    def activate_item(self, id):
        self.set_frame(0)
        self.id = id

        self.set_strip(stripes[self.strips[id]])

        self.frame_amount = self.frame_amounts[id]
        self.frame_rate   = self.frame_rates[id]
        self.type         = self.types[id]
        self.hp           = self.hps[id]

        self.is_active = True
        self.bullet.is_waiting_to_deactivate = True

        if self.type == "Jabon":
            self.bullet.activate("Jabon")
        elif self.type == "Desodorante":
            self.bullet.activate("Desodorante")
    
    def next_frame(self):
        self.set_frame((self.frame() + 1) % self.frame_amount)

    def step(self, step_counter):
        
        if step_counter % self.frame_rate == 0:
            if self.bullet.is_active:
                if self.bullet.is_reloading:
                    if self.frame() == self.frame_amount-1:
                        self.bullet.shoot()
                    self.next_frame()
            else:
                self.next_frame()

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
        
        self.y          = 20
        self.selected_y = 16
        
        self.items = [Sprite() for _ in range(5)]
        for i, item in enumerate(self.items):
            item.set_strip(stripes["smeti.png"])
            item.set_x(96+i*18)
            item.set_y(self.y)
            item.set_frame(i)

        self.items[self.selected_id].set_y(self.selected_y)
                
        self.items_name        =  ["Jabon", "Pala", "Burbujero", "Desodorante", "Tocar pasto"]
        self.items_description =  ["limpia nerds", "intocable", "da burbujas", "los espanta", "kabum!"]
        self.items_price       = [100, 200, 300, 400, 500]
        self.hps = [5, 25, 5, 5,  1]
        self.atks = [1,  0, 0, 0, 10]
        
        # self.items_stats       =  ["ATK 01 HP 05", "ATK 00 HP 25", "ATK 00 HP 05", "ATK 00 HP 05", "ATK 10 HP 01"]

        self.text        = Text(x=96,    y=14, len=11, sprite="letras_sirg.png")
        self.description = Text(x=96,    y=26, len=12, sprite="letras_edrev.png")
        self.price       = Numbers(x=72, y=8,  len=4,  label="burbujita.png",        label_width=4)
        self.hp          = Numbers(x=72, y=14, len=2,  label="hp.png" ,              label_width=12)
        self.atk         = Numbers(x=72, y=20, len=2,  label="atk.png",              label_width=12)

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
        self.description.setletters(self.items_description[self.selected_id])
        self.price.setnumbers(self.items_price[self.selected_id])
        self.hp.setnumbers(self.hps[self.selected_id])
        self.atk.setnumbers(self.atks[self.selected_id])
        #     self.stats.setletters(self.items_stats[self.selected_id])

class vs(Scene):

    stripes_rom = "vs"

    def temporarily_place_item(self, i, j):
        self.i = i
        self.j = j
        self.purchased_item.set_frame(self.purchased_item_id + 5)
        self.purchased_item.set_x(48-i*16)
        self.purchased_item.set_y(16+j*16)

    def move_focus_to(self, movement_i, movement_j):
        self.i = (self.i + movement_i) % 3
        self.j = (self.j + movement_j) % 3
        self.purchased_item.set_x(48-self.i*16)
        self.purchased_item.set_y(16+self.j*16)

    def place_item(self):
        self.items[coords(self.i, self.j)].activate_item(self.purchased_item_id)
        self.purchased_item_id = None
        self.purchased_item.disable()

    def add_money(self, value):
        self.money = self.money + value
        self.money_counter.setnumbers(self.money)

    def on_enter(self):
        super(vs, self).on_enter()
        
        self.loleros = [Lolero() for _ in range(1)]
  
        self.purchased_item_id = None
        self.purchased_item = Sprite()
        self.purchased_item.set_strip(stripes["items.png"])
        self.purchased_item.disable()

        self.menu  = Menu()
        self.bullets = [Bullet() for _ in range(9)]
        self.items = [Item(self.bullets[id]) for id in range(9)]

        for i in range(3):
            for j in range(3):
                self.items[coords(i, j)].set_x(48-i*16)
                self.items[coords(i, j)].set_y(16+j*16)
                self.bullets[coords(i, j)].set_initial_x(48-i*16)
                self.bullets[coords(i, j)].set_y(24+j*16)  

        self.i = 0
        self.j = 0

        self.money = 0
        self.money_counter = Numbers(x=66, y=0,  len=5, label="burbujita.png", label_width=5, sprite="white_numerals.png")
        self.add_money(10000)

        self.road = Sprite()
        self.road.set_strip(stripes["road.png"])
        self.road.set_x(192)
        self.road.set_y(16)
        self.road.set_frame(0)
        
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

        if self.purchased_item_id != None:

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
                    self.purchased_item_id = id
                    self.temporarily_place_item(0,0)

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