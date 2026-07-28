"""Live visualiser for every Input Protocol v2 controller control."""

import vs2
from vs2.controls import A, B, BACK, DOWN, LEFT, RIGHT, START, UP, X, Y, joy1, joy2


FONT = "tinyfont_menu.png"
LINE_LENGTH = 21
LINE_COUNT = 3
TEXT_X = -(LINE_LENGTH * 4 // 2)


def _marker(pressed, label):
    return label if pressed else "."


def _state_line(prefix, directions, faces, start, back):
    direction_text = "".join(_marker(pressed, label) for pressed, label in zip(directions, "LRUD"))
    face_text = "".join(_marker(pressed, label) for pressed, label in zip(faces, "ABXY"))
    line = "%s:%s %s %s%s" % (prefix, direction_text, face_text,
                                _marker(start, "S"), _marker(back, "B"))
    red = []
    for index, pressed in enumerate(directions):
        if pressed:
            red.append(3 + index)
    for index, pressed in enumerate(faces):
        if pressed:
            red.append(8 + index)
    if start:
        red.append(13)
    if back:
        red.append(14)
    return line, red


class InputDemo(vs2.Scene):
    asset_pack = "other"
    back_button = False

    def build(self):
        self.hud = self.layer("input-demo", projection=vs2.HUD)
        self.text = self.hud.label(FONT, columns=LINE_LENGTH, rows=LINE_COUNT,
                                   x=TEXT_X, y=0)
        self.line_values = [None] * LINE_COUNT
        self.last_state = None
        self.set_line(0, "     LRUD ABXY S B")
        self.refresh()

    def set_line(self, row, value, red_positions=()):
        value = str(value)[:LINE_LENGTH]
        if value == self.line_values[row]:
            return
        self.line_values[row] = value
        self.text.write(0, row, value)
        for index in red_positions:
            self.text.write(index, row, value[index], frame_offset=0x80, pad=False)

    @staticmethod
    def input_state():
        return (
            (joy1.held(LEFT), joy1.held(RIGHT), joy1.held(UP), joy1.held(DOWN)),
            (joy1.held(A), joy1.held(B), joy1.held(X), joy1.held(Y)),
            joy1.held(START), joy1.held(BACK),
            (joy2.held(LEFT), joy2.held(RIGHT), joy2.held(UP), joy2.held(DOWN)),
            (joy2.held(A), joy2.held(B), joy2.held(X), joy2.held(Y)),
            joy2.held(START), joy2.held(BACK),
        )

    def refresh(self):
        state = self.input_state()
        if state == self.last_state:
            return
        self.last_state = state
        first, first_red = _state_line("J1", *state[0:4])
        second, second_red = _state_line("J2", *state[4:8])
        self.set_line(1, first, first_red)
        self.set_line(2, second, second_red)

    def update(self):
        self.refresh()


def main():
    return InputDemo()
