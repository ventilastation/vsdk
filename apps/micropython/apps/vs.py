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
# 3 * 4 = 12 para los loleros
# Total: 43

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

# Total: 77

# Dadas dos coordinadas en una matriz de tamaño 3x3 te dice qué indice es en un array tamaño 9
def coords(i, j):
    return i + j*3

# [(step, tipo de lolero, carril)]

BRIAN = 0
FEDORA = 1
NARUTO = 2
FURRO = 3

test_level = [ (0, BRIAN, 0), (60, FEDORA, 1), (120, NARUTO, 2), (180, FURRO, 0)]

level_0 = [ (120, BRIAN, 0) ] #, (400, BRIAN, 1), (580, BRIAN, 0) ]

level_1 = [ (0, BRIAN, 2), (0, FEDORA, 1), (0, BRIAN, 0), (400, NARUTO, 1), (500, NARUTO, 0), (600, FEDORA, 2)]

level_2 = [ (0, NARUTO, 0), (0, NARUTO, 1), (0, NARUTO, 2), (60, FURRO, 0)]

levels = [level_0, level_1, level_2]

item_names         = ["Jabon", "Pala", "Burbujero", "Desodorante", "Tocar pasto"]
item_descriptions  = ["limpia nerds", "intocable", "da burbujas", "los espanta", "kabum!"]
item_prices        = [100, 200, 200, 400, 500]
item_hps           = [5, 25, 5, 5, 1]
item_atks          = [1, 0, 0, 0, 10]        
item_frame_amount  = [4, 8, 2, 4, 2]
item_frame_rate    = [3, 5, 30, 3, 5]

nerd_names        = ["Lolero", "Fedora guy", "Otaku runner", "furrito", "???"]
nerd_descriptions = ["no se ducha", "m'lady...", "datebayo!", "rawr! XD", "???"]
nerd_hps          = [7, 10, 5, 15,  0]
nerd_atks         = [1, 1, 1,  1,  0]
nerd_speeds       = [ 5,  5,  2,  5, 50]
nerd_speeds_user  = [50/x for x in nerd_speeds]
nerd_frame_amount = [4, 4, 11, 4,  0]

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

    def __init__(self, x, y, len, label=None, label_width=0):
        self.chars = []
        self.len = len
        self.hidden_digits = []

        if label:
            self.label = Sprite()
            self.label.set_strip(stripes[label])
            self.label.set_x(x)
            self.label.set_y(y)
            self.label.set_frame(0)
            self.label.set_perspective(2)

        for n in range(len):
            s = Sprite()
            s.set_strip(stripes["yellow_numerals.png"])
            s.set_x(x + n * 4 + label_width)
            s.set_y(y)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)
        
        self.setnumbers(0)

    def set_sprite(self, sprite):
        for n in range(self.len):
            self.chars[n].set_strip(stripes[sprite])

    def set_label(self, label):
        self.label.set_strip(stripes[label])

    def hide_digits(self, digits):
        self.hidden_digits = digits
        for i in digits:
            self.chars[i].disable()

    def show_digits(self, digits):
        self.hidden_digits = list(set(self.hidden_digits) - set(digits))

    def setnumbers(self, value):
        format_string = f"%0{self.len}d"
        for n, l in enumerate(format_string % value):
            if n < len(self.chars) and n not in self.hidden_digits:
                v = ord(l) - 0x30
                self.chars[n].set_frame(v)




# ______       _           
# | ___ \     | |          
# | |_/ / __ _| | __ _ ___ 
# | ___ \/ _` | |/ _` / __|
# | |_/ / (_| | | (_| \__ \
# \____/ \__,_|_|\__,_|___/

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
            self.long_reach  = range(194, 256)            # del centro a la derecha
            self.frame = 0

        elif type == "Desodorante":
            self.close_reach = range(0, self.initial_x+1)      # de la izquierda al centro
            self.long_reach  = range(194+self.initial_x, 256)  # del centro a la derecha
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



#  _____ _                     
# |_   _| |                    
#   | | | |_ ___ _ __ ___  ___ 
#   | | | __/ _ \ '_ ` _ \/ __|
#  _| |_| ||  __/ | | | | \__ \
#  \___/ \__\___|_| |_| |_|___/
                            
class Item(Sprite): 

    def __init__(self, bullet):
        super().__init__()

        self.bullet = bullet
        self.set_strip(stripes["items.png"])
        self.deactivate()

        self.strips = ["jabon.png", "pala.png", "burbujero.png", "desodorante.png", "pasto.png"]
        
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

        self.frame_amount = item_frame_amount[id]
        self.frame_rate   = item_frame_rate[id]
        self.type         = item_names[id]
        self.hp           = item_hps[id]

        self.is_active = True
        self.bullet.is_waiting_to_deactivate = True
        self.start_animation = False

        if self.type == "Jabon":
            self.bullet.activate("Jabon")
        elif self.type == "Desodorante":
            self.bullet.activate("Desodorante")
    
    def next_frame(self):
        self.set_frame((self.frame() + 1) % self.frame_amount)

    def step(self, step_counter):
        
        if step_counter % self.frame_rate == 0:
            
            if self.bullet.is_active:

                if self.bullet.is_reloading and step_counter % (self.frame_rate*20) == 0:
                    self.start_animation = True
                
                if self.start_animation:
                    if self.frame() == self.frame_amount-1:
                        self.start_animation = False
                        self.bullet.shoot()
                    self.next_frame()

            else:
                self.next_frame()




#  _           _                    
# | |         | |                   
# | |     ___ | | ___ _ __ ___  ___ 
# | |    / _ \| |/ _ \ '__/ _ \/ __|
# | |___| (_) | |  __/ | | (_) \__ \
# \_____/\___/|_|\___|_|  \___/|___/

class Lolero(Sprite):

    def __init__(self, index):
        super().__init__()
        self.frame_amount  = nerd_frame_amount[index]
        self.initial_hp    = nerd_hps[index]
        self.initial_speed = nerd_speeds[index]
        self.morite()
        
    def activate(self, j):
        self.set_x(192)
        self.set_y(16*(j+1))
        self.set_frame(0)
        self.is_active = True
        self.can_move = True
        self.has_debuff = False
        self.modo_fedora = False
        self.debuff_turns = 0
        self.hp    = self.initial_hp
        self.speed = self.initial_speed

    def se_baña(self, value):
        self.hp -= value
        if self.hp <= 0:
            self.morite()

    def se_realentiza(self):
        self.speed = self.initial_speed*4
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
            self.speed = self.initial_speed
            self.has_debuff = False

        if self.is_active and step_counter % self.speed == 0 :

            if self.can_move:
                self.set_x(self.x() + 1)
            self.set_frame((self.frame() + 1) % 4)

            if self.has_debuff:
                self.debuff_turns -= 1

class Brian(Lolero):

    def __init__(self):
        super().__init__(0)
        self.set_strip(stripes["lolero.png"])

class FedoraGuy(Lolero):

    def __init__(self):
        super().__init__(1)
        self.set_strip(stripes["fedora.png"])

    def step(self, step_counter):
        if step_counter % 120 == 0:
            self.modo_fedora = not self.modo_fedora
        
        if self.modo_fedora:
            if self.frame() < 7 and step_counter % 5 == 0:
                self.set_frame(self.frame()+1)
        else:
            super().step(step_counter)

class NarutoRunner(Lolero):

    def __init__(self):
        super().__init__(2)
        self.set_strip(stripes["naruto_runner.png"])
       
class Furro(Lolero):

    def __init__(self):
        super().__init__(3)
        self.set_strip(stripes["furry.png"])
    
    def step(self, step_counter):

        if step_counter % 100 == 0:
            self.set_y((self.y()) % 48 + 16)

        super().step(step_counter)






# ___  ___                 
# |  \/  |                 
# | .  . | ___ _ __  _   _ 
# | |\/| |/ _ \ '_ \| | | |
# | |  | |  __/ | | | |_| |
# \_|  |_/\___|_| |_|\__,_|

class Menu():

    def next_mode(self):

        if self.showing_items:
            # Menu ahora muestra nerds
            self.price.set_label("spd.png")
            self.price.hide_digits([0, 1])
            for item in self.items:
                item.set_strip(stripes["sdren.png"])
        else:
            # Menu ahora muestra items
            self.price.set_label("burbujita.png")
            self.price.show_digits([0, 1])
            for item in self.items:
                item.set_strip(stripes["smeti.png"])
        
        self.showing_items = not self.showing_items
        self.write_description()

    def __init__(self):

        self.selected_id    = 0
        
        self.y          = 20
        self.selected_y = 16

        self.showing_items = True

        self.items = [Sprite() for _ in range(5)]
        for i, item in enumerate(self.items):
            item.set_strip(stripes["smeti.png"])
            item.set_x(96+i*18)
            item.set_y(self.y)
            item.set_frame(i)

        self.items[self.selected_id].set_y(self.selected_y)

        self.name        = Text(x=94,    y=14, len=13, sprite="letras_sirg.png")
        self.description = Text(x=94,    y=26, len=12, sprite="letras_edrev.png")
        self.price       = Numbers(x=70, y=8,  len=4,  label="burbujita.png", label_width=4)
        self.hp          = Numbers(x=70, y=14, len=2,  label="hp.png" ,       label_width=12)
        self.atk         = Numbers(x=70, y=20, len=2,  label="atk.png",       label_width=12)

        self.write_description()
    
    def move_focus_to(self, direction, money):
        self.items[self.selected_id].set_y(self.y)
        self.selected_id = (self.selected_id + direction) % 5
        self.items[self.selected_id].set_y(self.selected_y)
        
        self.price.set_sprite("yellow_numerals.png")
    
        if self.showing_items:
            if money < item_prices[self.selected_id]:
                self.price.set_sprite("red_numerals.png")

        self.write_description()

    def get_focused_item_info(self):
        return self.selected_id, item_names[self.selected_id], item_prices[self.selected_id]

    def change_focused_item_frame(self, i):
        self.items[self.selected_id].set_frame(self.items[self.selected_id].frame() + i)

    def write_description(self):

        mode = int(self.showing_items)
        index = self.selected_id

        self.name.setletters(        [nerd_names,        item_names        ][mode][index])
        self.description.setletters( [nerd_descriptions, item_descriptions ][mode][index])
        self.price.setnumbers(       [nerd_speeds_user,  item_prices       ][mode][index])
        self.hp.setnumbers(          [nerd_hps,          item_hps          ][mode][index])
        self.atk.setnumbers(         [nerd_atks,         item_atks         ][mode][index])

#  _____                         
# |  ___|                        
# | |__ ___  ___ ___ _ __   __ _ 
# |  __/ __|/ __/ _ \ '_ \ / _` |
# | |__\__ \ (_|  __/ | | | (_| |
# \____/___/\___\___|_| |_|\__,_|
                                                            
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
        
        self.brians  = [Brian()        for _ in range(3)]
        self.fedoras = [FedoraGuy()    for _ in range(3)]
        self.otakus  = [NarutoRunner() for _ in range(3)]
        self.furros  = [Furro()        for _ in range(3)]

        self.tribus = [self.brians, self.fedoras, self.otakus, self.furros]

        self.purchased_item_id = None  
        self.purchased_item = Sprite()
        self.purchased_item.set_strip(stripes["items.png"])
        self.purchased_item.disable()

        self.menu  = Menu()
        self.bullets = [Bullet() for _ in range(9)]
        self.items   = [Item(self.bullets[id]) for id in range(9)]

        for i in range(3):
            for j in range(3):
                self.items[coords(i, j)].set_x(48-i*16)
                self.items[coords(i, j)].set_y(16+j*16)
                self.bullets[coords(i, j)].set_initial_x(48-i*16)
                self.bullets[coords(i, j)].set_y(24+j*16)  

        self.i = 0
        self.j = 0

        self.money = 0
        self.money_counter = Numbers(x=66, y=0,  len=5, label="burbujita.png", label_width=5)
        self.money_counter.set_sprite("white_numerals.png")
        self.add_money(1000)

        self.road = Sprite()
        self.road.set_strip(stripes["road.png"])
        self.road.set_x(192)
        self.road.set_y(16)
        self.road.set_frame(0)
        
        self.step_counter = 0
        
        self.level_id = 0
        self.current_lolero_id = 0
        
        self.starting_step_counter = 0

    def next_level(self):
        if self.current_lolero_id == len(levels[self.level_id]) and self.level_id < len(levels):
            self.current_lolero_id = 0
            self.level_id += 1
            self.starting_step_counter = self.step_counter + 150

    def manage_level(self):

        if self.level_id < len(levels):

            if self.current_lolero_id < len(levels[self.level_id]):
                        
                step, lolero_id, j = levels[self.level_id][self.current_lolero_id]
                if self.step_counter >= step + self.starting_step_counter:
                    for lolero in self.tribus[lolero_id]:
                        if not lolero.is_active:
                            lolero.activate(j)
                            print("Activamos un", nerd_names[lolero_id], "en el carril", j)
                            break
                    
                    self.current_lolero_id += 1

    def step(self):

        self.manage_level()

        for bullet in self.bullets:
            bullet.step()

        for item in self.items:
            if item.is_active:
                item.step(self.step_counter)
                if item.type == "Burbujero" and self.step_counter % 30 == 0:
                    self.add_money(100)

        lolero_counter = 0

        for tribu in self.tribus:
            for lolero in tribu:
                if lolero.is_active:
                    lolero_counter += 1
                    if not lolero.modo_fedora:
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
                    
                    # Lolero llega a base
                    if 64-16 < lolero.x() < 192:
                        self.finished()
        
        if lolero_counter == 0:
            self.next_level()

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
                self.menu.move_focus_to(1, self.money)
    
            if director.was_pressed(director.JOY_LEFT):
                self.menu.move_focus_to(-1, self.money)

            if director.was_pressed(director.JOY_UP):
                self.menu.next_mode()

            if director.was_pressed(director.JOY_DOWN):
                self.menu.next_mode()

            if director.was_pressed(director.BUTTON_A):
                if self.menu.showing_items:
                    id, name, price = self.menu.get_focused_item_info()
                    if self.money >= price:
                    
                        self.add_money(-price)
                        self.purchased_item_id = id
                        self.temporarily_place_item(0,0)

                        self.menu.move_focus_to(0, self.money)

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