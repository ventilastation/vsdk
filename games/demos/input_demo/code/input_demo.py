"""Live visualiser for every Input Protocol v2 controller control.

The four HUD rows deliberately use 84 compact-font sprites: enough to show
both joysticks at once, while leaving room below the rotor's 100-sprite limit.
An uppercase letter means the labelled input is held; a dot means it is up.
"""

from ventilastation.director import director
from vs2 import HUD, Scene, Sprite


FONT = "tinyfont_menu.png"
FONT_WIDTH = 4
LINE_LENGTH = 21
LINE_HEIGHT = 7
LINE_Y = (12, 19, 26, 33)


def _marker(pressed, label):
    return label if pressed else "."


def _state_line(prefix, directions, faces, start, back):
    """Format one compact controller state row.

    The heading above the rows gives the fixed order: LRUD, ABXY, Start,
    Back. Keeping each state at 15 characters lets the screen remain legible
    at the rotor's native resolution.
    """
    direction_text = "".join(
        _marker(pressed, label) for pressed, label in zip(directions, "LRUD")
    )
    face_text = "".join(
        _marker(pressed, label) for pressed, label in zip(faces, "ABXY")
    )
    return "%s:%s %s %s%s" % (
        prefix, direction_text, face_text,
        _marker(start, "S"), _marker(back, "B"),
    )


class TextLine:
    """One fixed-width HUD line made from the shared compact font."""

    def __init__(self, layer, y):
        self.value = None
        self.sprites = []
        for index in range(LINE_LENGTH):
            x = (LINE_LENGTH * FONT_WIDTH // 2 - index * FONT_WIDTH) % 256
            self.sprites.append(layer.add(Sprite(FONT, x=x, y=y, frame=0)))

    def set_value(self, value):
        value = str(value)[:LINE_LENGTH]
        if value == self.value:
            return
        self.value = value
        for index, sprite in enumerate(self.sprites):
            sprite.frame = ord(value[index]) if index < len(value) else 0


class InputDemo(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(InputDemo, self).on_enter()
        hud = self.layer("input-demo", mode=HUD)
        self.lines = [TextLine(hud, y) for y in LINE_Y]
        self.last_state = None
        self.lines[0].set_value("     LRUD ABXY S B")
        self.lines[3].set_value(".=UP LETTER=HELD")
        self.refresh()

    def input_state(self):
        joy1_directions = (
            director.is_pressed(director.JOY_LEFT),
            director.is_pressed(director.JOY_RIGHT),
            director.is_pressed(director.JOY_UP),
            director.is_pressed(director.JOY_DOWN),
        )
        joy1_faces = (
            director.is_pressed(director.BUTTON_A),
            director.is_pressed(director.BUTTON_B),
            director.is_pressed(director.BUTTON_X),
            director.is_pressed(director.BUTTON_Y),
        )
        joy2_directions = (
            director.is_pressed2(director.JOY2_LEFT),
            director.is_pressed2(director.JOY2_RIGHT),
            director.is_pressed2(director.JOY2_UP),
            director.is_pressed2(director.JOY2_DOWN),
        )
        joy2_faces = (
            director.is_pressed2(director.BUTTON2_A),
            director.is_pressed2(director.BUTTON2_B),
            director.is_pressed2(director.BUTTON2_X),
            director.is_pressed2(director.BUTTON2_Y),
        )
        return (
            joy1_directions,
            joy1_faces,
            director.is_extra(director.EXTRA_JOY1_START),
            director.is_extra(director.EXTRA_JOY1_BACK),
            joy2_directions,
            joy2_faces,
            director.is_extra(director.EXTRA_JOY2_START),
            director.is_extra(director.EXTRA_JOY2_BACK),
        )

    def refresh(self):
        state = self.input_state()
        if state == self.last_state:
            return
        self.last_state = state
        self.lines[1].set_value(_state_line("J1", *state[0:4]))
        self.lines[2].set_value(_state_line("J2", *state[4:8]))

    def step(self):
        self.refresh()


def main():
    return InputDemo()
