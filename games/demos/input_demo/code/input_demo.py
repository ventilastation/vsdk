"""Live visualiser for every Input Protocol v2 controller control.

One 21x3 compact-font tilemap shows both joysticks without consuming the
rotor sprite table.  Pressed controls use the red glyphs from the ROM menu's
combined font strip; released controls are white dots.
"""

from ventilastation.director import director
from vs2 import EMPTY_TILE, HUD, Scene, Tilemap


FONT = "tinyfont_menu.png"
FONT_WIDTH = 4
FONT_HEIGHT = 6
LINE_LENGTH = 21
LINE_COUNT = 3
TEXT_X = -(LINE_LENGTH * FONT_WIDTH // 2)
# HUD Y=0 is the outermost LED.  Keep the compact readout at the visible edge.
TEXT_Y = 0


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
    line = "%s:%s %s %s%s" % (
        prefix, direction_text, face_text,
        _marker(start, "S"), _marker(back, "B"),
    )
    red_positions = []
    for index, pressed in enumerate(directions):
        if pressed:
            red_positions.append(3 + index)
    for index, pressed in enumerate(faces):
        if pressed:
            red_positions.append(8 + index)
    if start:
        red_positions.append(13)
    if back:
        red_positions.append(14)
    return line, red_positions


class InputDemo(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(InputDemo, self).on_enter()
        self.hud = self.layer("input-demo", mode=HUD)
        self.text_frames = bytearray(LINE_LENGTH * LINE_COUNT)
        for index in range(len(self.text_frames)):
            self.text_frames[index] = EMPTY_TILE
        self.text = self.hud.add(Tilemap(
            FONT, self.text_frames,
            columns=LINE_LENGTH, rows=LINE_COUNT,
            tile_width=FONT_WIDTH, tile_height=FONT_HEIGHT,
            x=TEXT_X, y=TEXT_Y,
        ))
        self.line_values = [None] * LINE_COUNT
        self.last_state = None
        self.set_line(0, "     LRUD ABXY S B")
        self.refresh()

    def set_line(self, row, value, red_positions=()):
        value = str(value)[:LINE_LENGTH]
        if value == self.line_values[row]:
            return
        self.line_values[row] = value
        offset = row * LINE_LENGTH
        for index in range(LINE_LENGTH):
            # The legacy font sprite placement runs clockwise by decrementing
            # x. Reverse the map columns to preserve that readable order.
            frame = ord(value[index]) if index < len(value) else EMPTY_TILE
            if index in red_positions:
                # ``tinyfont_menu.png`` packs matching red glyphs at 0x80.
                frame |= 0x80
            self.text_frames[offset + LINE_LENGTH - 1 - index] = frame

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
        joy1_line, joy1_red = _state_line("J1", *state[0:4])
        joy2_line, joy2_red = _state_line("J2", *state[4:8])
        self.set_line(1, joy1_line, joy1_red)
        self.set_line(2, joy2_line, joy2_red)

    def step(self):
        self.refresh()


def main():
    return InputDemo()
