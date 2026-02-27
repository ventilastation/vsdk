try:
    import ventilagon
except ImportError:
    from ventilastation import fake_ventilagon as ventilagon
from ventilastation.director import director, comms, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

class VentilagonGame(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(VentilagonGame, self).on_enter()
        ventilagon.enter()
        self.last_buttons = None

    def sending_loop(self):
        sending = ventilagon.sending()
        while sending:
            comms.send(sending)
            sending = ventilagon.sending()

    def on_exit(self):
        super().on_exit()
        ventilagon.exit()
        self.sending_loop()

    def step(self):
        buttons = director.buttons
        if buttons != self.last_buttons:
            self.last_buttons = buttons
            ventilagon.received(buttons)

        if director.was_pressed(director.BUTTON_D) or (director.timedout and ventilagon.is_idle()):
            director.pop()
            raise StopIteration()

        self.sending_loop()


def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

class VentilagonIdle(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(VentilagonIdle, self).on_enter()

        self.logo = Sprite()
        self.logo.set_x(-32)
        self.logo.set_y(0)
        self.logo.set_perspective(2)
        self.logo.set_strip(stripes["empeza.png"])
        self.logo.set_frame(0)

        self.empeza = Sprite()
        self.empeza.set_x(128-32)
        self.empeza.set_y(0)
        self.empeza.set_perspective(2)
        self.empeza.set_strip(stripes["super-ventilagon.png"])
        self.empeza.set_frame(0)

        self.idle_screens = [make_me_a_planet(stripes[s]) for s in ["ventilagon-empezar1.png", "ventilagon-empezar2.png"]]
        self.idle_shown = 0
        self.change_idle_screen()
        director.reset_timeout()
        director.sound_play("ventilagon/audio/es/superventilagon")
        comms.send(b"arduino attract")

    def change_idle_screen(self):
        for s in self.idle_screens:
            s.disable()
        self.idle_screens[self.idle_shown].set_frame(0)
        self.idle_shown = (self.idle_shown + 1) % len(self.idle_screens)
        self.call_later(500, self.change_idle_screen)


    def both_console_buttons(self):
        """Check if both buttons are pressed."""
        return (
            (director.was_pressed(director.JOY_LEFT) and director.is_pressed(director.JOY_RIGHT)) or
            (director.was_pressed(director.JOY_RIGHT) and director.is_pressed(director.JOY_LEFT))
        ) and not director.is_pressed(director.JOY_UP) and not director.is_pressed(director.JOY_DOWN)

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            comms.send(b"arduino stop")
            raise StopIteration()

        if (director.was_pressed(director.BUTTON_A) or self.both_console_buttons()):
            comms.send(b"arduino stop")
            director.push(VentilagonGame())

        if (director.timedout):
            from apps.gallery import Gallery
            director.push(Gallery())


def main():
    return VentilagonIdle()