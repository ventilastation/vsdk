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
# = 33

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

    def __init__(self):
        super().__init__()
        self.set_strip(stripes["items.png"])
        self.disable()
        self.active_frame = None

    def is_actived(self):
        return self.active_frame != None

    def temporarily_set_frame(self, frame):
        self.set_frame(frame)

    def definitely_set_frame(self, frame):
        self.set_frame(frame)
        self.active_frame = frame

    def restore_active_frame(self):
        if self.is_actived():
            self.set_frame(self.active_frame)
        else:
            self.disable()

class Items():

    def __init__(self):
        
        self.items = [[Item() for _ in range(3)] for _ in range(3)]

        for i in range(3):
            for j in range(3):
                self.items[i][j].set_x(48-i*16)
                self.items[i][j].set_y(16+j*16)

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
        
        self.items_name =  ["Jabon", "Cepillo", "Dispenser", "Desodorante", "Pasto"]
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

class vs(Scene):
    stripes_rom = "vs"

    def on_enter(self):
        super(vs, self).on_enter()

        self.menu  = Menu()
        self.items = Items()
        
        self.money = 500
        self.money_counter = Numbers(x=165, y=8, len=5)
        self.money_counter.setnumbers(self.money)

        self.placing_item = False

    def step(self):
        
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
            

    def finished(self):
        director.pop()
        raise StopIteration()

def main():
    return vs()