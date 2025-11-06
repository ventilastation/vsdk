import sys
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite, reset_sprites

class MenuSprite(Sprite):
    pass

class Menu(Scene):

    def __init__(self, options, selected_index=0):
        """Where options is a list of: (option id, strip id, frame, width)"""

        super(Menu, self).__init__()
        self.options = options[:]
        self.selected_index = selected_index

    def on_enter(self):
        super(Menu, self).on_enter()
        self.sprites = []
        self.y_step = 20 #250 // len(self.options)
        for n, (option_id, strip_name, frame) in enumerate(self.options):
            sprite = MenuSprite()
            sprite.selected_frame = frame
            sprite.set_x(-32)
            sprite.set_y(int(n * self.y_step))
            sprite.set_perspective(1)
            sprite.set_strip(stripes[strip_name])
            sprite.set_frame(frame)

            self.sprites.append(sprite)

    def both_console_buttons(self):
        """Check if both buttons are pressed."""
        return (
            (director.was_pressed(director.JOY_LEFT) and director.is_pressed(director.JOY_RIGHT)) or
            (director.was_pressed(director.JOY_RIGHT) and director.is_pressed(director.JOY_LEFT))
        ) and not director.is_pressed(director.JOY_UP) and not director.is_pressed(director.JOY_DOWN)

    def step(self):
        if director.was_pressed(director.JOY_DOWN):
            director.sound_play(b'vyruss/shoot3')
            self.selected_index -= 1
            if self.selected_index == -1:
                self.selected_index = 0
            print("Selected menu option", self.options[self.selected_index][0])
        if director.was_pressed(director.JOY_UP):
            director.sound_play(b'vyruss/shoot3')
            self.selected_index += 1
            if self.selected_index > len(self.options) - 1:
                self.selected_index = len(self.options) - 1
            print("Selected menu option", self.options[self.selected_index][0])
        if (director.was_pressed(director.BUTTON_A) or self.both_console_buttons()):
            director.sound_play(b'vyruss/shoot1')
            try:
                self.on_option_pressed(self.selected_index)
            except StopIteration:
                raise
            except Exception as e:
                sys.print_exception(e)

        for n, sprite in enumerate(self.sprites):
            if n == self.selected_index:
                sprite.set_y(0)
                sprite.set_perspective(2)
                sprite.set_frame(sprite.selected_frame)
            elif n < self.selected_index:
                sprite.set_y(255)
                sprite.set_perspective(1)
                sprite.disable()
            else:
                curr_y = sprite.y()
                dest_y = int((n - self.selected_index) * self.y_step + 45)
                if dest_y < 0:
                    y = 255
                else:
                    if dest_y > 255:
                        y = 255
                    else:
                        y = curr_y - (curr_y - dest_y) // 4

                if 1 < y < 120:
                    sprite.set_frame(sprite.selected_frame)
                else:
                    sprite.disable()
                sprite.set_y(y)
                sprite.set_perspective(1)

    def on_option_pressed(self, option_index):
        # print('pressed:', option_index)
        pass
