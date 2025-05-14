import sys
from ventilastation.director import director
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite, reset_sprites


class Menu(Scene):

    def __init__(self, options, selected_index=0):
        """Where options is a list of: (option id, strip id, frame, width)"""

        super(Menu, self).__init__()
        self.options = options[:]
        self.selected_index = selected_index

    def on_enter(self):
        self.sprites = []
        self.y_step = 180 // len(self.options)
        for n, (option_id, strip_id, frame, width) in enumerate(self.options):
            sprite = Sprite()
            sprite.set_x(-32)
            sprite.set_y(int(n * self.y_step))
            sprite.set_perspective(1)
            sprite.set_strip(strip_id)
            sprite.set_frame(frame)

            self.sprites.append(sprite)

    def step(self):
        if director.was_pressed(director.JOY_DOWN):
            director.sound_play(b'vyruss/shoot3')
            self.selected_index -= 1
            if self.selected_index == -1:
                self.selected_index = 0
        if director.was_pressed(director.JOY_UP):
            director.sound_play(b'vyruss/shoot3')
            self.selected_index += 1
            if self.selected_index > len(self.options) - 1:
                self.selected_index = len(self.options) - 1
        if director.was_pressed(director.BUTTON_A):
            director.sound_play(b'vyruss/shoot1')
            try:
                self.on_option_pressed(self.selected_index)
            except StopIteration:
                raise
            except Exception as e:
                sys.print_exception(e)

        for n, sprite in enumerate(self.sprites):
            #sprite.set_x(start_x + accumulated_width - offset)
            if n == self.selected_index:
                sprite.set_y(0)
                sprite.set_perspective(2)
            else:
                curr_y = sprite.y()
                dest_y = int((n - self.selected_index) * self.y_step + 16) % 256
                y = curr_y - (curr_y - dest_y) // 4
                sprite.set_y(y)
                sprite.set_perspective(1)
            
            #accumulated_width += self.options[option_index][3]  # option width

    def on_option_pressed(self, option_index):
        # print('pressed:', option_index)
        pass
