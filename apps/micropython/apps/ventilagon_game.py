import ventilagon
from ventilastation.director import director
from ventilastation.scene import Scene
try:
    import ventilastation.serialcomms as comms
except Exception:
    import ventilastation.comms


class VentilagonGame(Scene):
    def on_enter(self):
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
