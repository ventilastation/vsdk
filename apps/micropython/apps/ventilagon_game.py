try:
    import ventilagon
except ImportError:
    from ventilastation import fake_ventilagon as ventilagon
from ventilastation.director import director, comms
from ventilastation.scene import Scene

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


def main():
    return VentilagonGame()