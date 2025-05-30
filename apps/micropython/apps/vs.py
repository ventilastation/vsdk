from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

# Contador de sprites:
# 5 para cada item del menu
# 5 para el contador de monedas
# 11 para las letras de las descripciones del menu -> hardcodeable
# 3 para el precio de los items del menu           -> hardcodeable
# 9 para los items en el tablero
# 1 para el piso
# 9 balas
# n loleros
# = 43 + n

class Text:
    def __init__(self, x, y, len):
        self.chars = []
        self.len = len

        for n in range(len):
            s = Sprite()
            s.set_strip(stripes["vga_pc734.png"])
            s.set_x(x + n * 8)
            s.set_y(y)
            s.set_frame(0)
            s.set_perspective(2)
            self.chars.append(s)

        self.setletters("")

    def setletters(self, text):
        for n, l in enumerate('{message: <{width}}'.format(message=text, width=self.len)):
            if n < len(self.chars):  
                self.chars[n].set_frame(255-ord(l))

class Numbers:
    def __init__(self, x, y, len):
        self.chars = []
        self.len = len
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

class Item(Sprite): 

    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["items.png"])
        self.disable()
        self.active_frame = None
        self.hp = 0

        self.i = 0        
        self.j = 0        
        
        self.hps    = [5, 25, 5, 5, 1]
        self.speeds = [ 30,   0,  30,  30, 0]

        self.bullet = Sprite()

    def se_ensucia(self, value, step_counter):
        if step_counter % 20 == 0:
            self.hp -= value
            if self.hp <= 0:
                self.deactivate()

    def deactivate(self):
        self.active_frame = None
        self.disable()

    def is_actived(self):
        return self.active_frame != None

    def temporarily_set_frame(self, frame):
        self.set_frame(frame)

    def definitely_set_frame(self, frame):
        self.set_frame(frame)
        self.active_frame = frame
        
        self.scene.bullets[self.i][self.j].is_waiting_to_deactivate = True

        self.hp = self.hps[self.active_frame]

        if self.active_frame == 0:
            self.scene.bullets[self.i][self.j].activate("Jabon")
        elif self.active_frame == 3:
            self.scene.bullets[self.i][self.j].activate("Desodorante")

    def restore_active_frame(self):
        if self.is_actived():
            self.set_frame(self.active_frame)
        else:
            self.disable()
    
    def step(self, step_counter):
        
        if self.is_actived():
            
            if step_counter % 30 == 0:

                if self.active_frame == 2:
                    self.scene.add_money(100)

class Items():

    def __init__(self, scene):
        
        self.scene = scene
        self.items = [[Item(self.scene) for _ in range(3)] for _ in range(3)]

        for i in range(3):
            for j in range(3):
                self.items[i][j].set_x(48-i*16)
                self.items[i][j].set_y(16+j*16)
                self.items[i][j].i = i
                self.items[i][j].j = j

        self.i = 0
        self.j = 0

        self.frame = None
        self.temp_frame = None

    def activate_item_at(self, frame, temp_frame, i, j):
        self.i = i
        self.j = j
        self.frame = frame
        self.temp_frame = temp_frame
        self.items[self.i][self.j].temporarily_set_frame(self.temp_frame)

    def move_focus_to(self, movement_i, movement_j):
        self.items[self.i][self.j].restore_active_frame()
        self.i = (self.i + movement_i) % 3
        self.j = (self.j + movement_j) % 3
        self.items[self.i][self.j].temporarily_set_frame(self.temp_frame)

    def place_item(self):
        self.items[self.i][self.j].definitely_set_frame(self.frame)
        self.frame = None
        self.temp_frame = None

    def step(self, step_counter):
        for i in range(3):
            for j in range(3):
                self.items[i][j].step(step_counter)

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
        
        self.items_name =  ["Jabon", "Pala", "Burbujero", "Desodorante", "Tocar pasto"]
        self.items_price = [100, 200, 300, 400, 500]

        self.text  = Text(x=93, y=18, len=11)
        self.price = Numbers(x=72, y=21, len=4)
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

class Bullet(Sprite):
    
    def __init__(self):

        super().__init__()
        self.set_strip(stripes["vga_pc734.png"])
        self.initial_x = 0
        self.initial_y = 0
        self.is_active = False
        self.is_reloading = False
        self.is_waiting_to_deactivate = False
        self.close_reach = None
        self.long_reach = None
        self.type = ""

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

    def set_initial_y(self, y):
        self.initial_y = y
        self.set_y(y)

    def deactivate(self):
        self.is_active = False
        self.disable()
        self.set_x(self.initial_x)

    def reset(self):
        if self.is_waiting_to_deactivate:
            self.deactivate()
        else:
            self.is_reloading = True
            self.disable()
            self.set_x(self.initial_x)

    def step(self, step_counter):

        if self.is_active:
            if not self.is_reloading:
                if self.x() in self.close_reach or self.x() in self.long_reach:
                    self.set_frame(6)
                    self.set_x(self.x()-1)
                else:
                    self.reset()
            else:
                if step_counter % 30 == 0:
                    self.is_reloading = False

class Lolero(Sprite):

    def __init__(self):
        super().__init__()
        self.set_strip(stripes["numerals.png"])
        self.revive()
        self.debuff_turns = 0

    def revive(self):
        self.set_x(192)
        self.set_y(20)
        self.set_frame(5)
        self.is_active = True
        self.hp = 5
        self.speed = 5
        self.is_moving = True


    def se_baña(self, value):
        print("Lolero se baña")
        self.hp -= value
        if self.hp <= 0:
            print("lolero se muere")
            self.morite()

    def se_realentiza(self):
        print("Lolero se realentiza")
        self.speed = 20
        self.debuff_turns = 3

    def morite(self):
        self.set_x(192) 
        self.disable()
        self.is_active = False 
    
    def step(self, step_counter):
        
        if self.debuff_turns <= 0:
            self.speed = 5

        if self.is_active and step_counter % self.speed == 0 :

            if self.is_moving:            
                self.set_x(self.x() + 1)

            if self.speed != 5:
                self.debuff_turns -= 1

class vs(Scene):
    stripes_rom = "vs"

    def add_money(self, value):
        self.money = self.money + value
        self.money_counter.setnumbers(self.money)

    def on_enter(self):
        super(vs, self).on_enter()

        self.step_counter = 0

        self.menu  = Menu()
        self.items = Items(self)
        
        self.bullets = [[Bullet() for _ in range(3)] for _ in range(3)]

        for i in range(3):
            for j in range(3):
                self.bullets[i][j].set_initial_x(48-i*16)
                self.bullets[i][j].set_initial_y(16+j*16)       

        self.money = 10000
        self.money_counter = Numbers(x=165, y=8, len=5)
        self.money_counter.setnumbers(self.money)

        self.road = Sprite()
        self.road.set_strip(stripes["road.png"])
        self.road.set_x(192)
        self.road.set_y(16)
        self.road.set_frame(0)

        self.placing_item = False

        self.loleros = [Lolero() for _ in range(1)]

    def step(self):
        
        self.items.step(self.step_counter)
               
        for i in range(3):
            for j in range(3):
                self.bullets[i][j].step(self.step_counter)

        for lolero in self.loleros:
            if lolero.is_active:
                lolero.step(self.step_counter)
                lolero.is_moving = True
                for row in self.bullets:
                    bullet = lolero.collision(row)
                    if bullet:
                        if bullet.is_active and not bullet.is_reloading:
                            if bullet.type == "Jabon":
                                lolero.se_baña(1)
                            if bullet.type == "Desodorante":
                                lolero.se_realentiza()
                            bullet.reset()

                for row in self.items.items:
                    item = lolero.collision(row)
                    if item:
                        if item.is_actived():
                            lolero.is_moving = False
                            if item.active_frame == 4:
                                lolero.se_baña(10)
                            item.se_ensucia(1, self.step_counter)


        if director.was_pressed(director.BUTTON_D):
            self.finished()

        if self.placing_item:

            if director.was_pressed(director.JOY_RIGHT):
                self.items.move_focus_to(1,0)
    
            if director.was_pressed(director.JOY_LEFT):
                self.items.move_focus_to(-1,0)
    
            if director.was_pressed(director.JOY_UP):
                self.items.move_focus_to(0,1)
    
            if director.was_pressed(director.JOY_DOWN):
                self.items.move_focus_to(0,-1)

            if director.was_pressed(director.BUTTON_A):
                self.items.place_item()
                self.menu.change_focused_item_frame(-5)
                self.placing_item = False

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
                    self.money = self.money - price
                    self.money_counter.setnumbers(self.money)
                    self.items.activate_item_at(frame=id, temp_frame=id+5, i=0, j=0)
                    self.menu.change_focused_item_frame(5)
                    self.placing_item = True
                    print("Compramos "  + name)

                else:
                    print("No alcanza la plata")
        
        self.step_counter += 1

    def finished(self):
        director.pop()
        raise StopIteration()

def main():
    return vs()