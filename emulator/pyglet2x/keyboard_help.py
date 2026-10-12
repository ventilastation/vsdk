"""Draw the shared keyboard diagram with native pyglet shapes and labels."""

import pyglet
from pyglet import shapes
from keyboard_layout import LAYOUT


class KeyboardDiagram:
    def __init__(self):
        self.key_state = None
        self.batch = pyglet.graphics.Batch()
        background = pyglet.graphics.Group(order=0)
        foreground = pyglet.graphics.Group(order=1)
        text = pyglet.graphics.Group(order=2)
        self.caps = []
        for entry in LAYOUT["context"] + LAYOUT["keys"]:
            border = shapes.RoundedRectangle(0, 0, 40, 40, radius=4, batch=self.batch, group=background)
            face = shapes.RoundedRectangle(0, 0, 40, 40, radius=3, batch=self.batch, group=foreground)
            label = pyglet.text.Label(entry["key"], font_name="Arial", weight="bold",
                                      anchor_x="center", anchor_y="center", batch=self.batch, group=text)
            control = pyglet.text.Label(entry.get("control", ""), font_name="Arial",
                                        anchor_x="center", anchor_y="center", batch=self.batch, group=text)
            self.caps.append((entry, border, face, label, control))
        self.titles = [pyglet.text.Label("Player %d  ·  %s" % (player, description),
                                       font_name="Arial", weight="bold", anchor_y="top",
                                       batch=self.batch, group=text)
                       for player, description in [(1, "letter keys"), (2, "arrows + numpad")]]
        self.footer = pyglet.text.Label(
            "Try keys here: they light up without controlling the game.\n"
            "F1 help · F4 settings · F2 CPU/GPU · F3 compare · F5 hall filter\n"
            "Ctrl/⌘-U upgrade · Q quit · Esc closes help, or returns to the launcher\n"
            "One gamepad: left stick P1, right stick/shoulders P2. Two pads: one per player.\n"
            "Select is Back; C/D are X/Y in the game API.",
            font_name="Arial", anchor_y="top", multiline=True, width=900,
            color=(174, 191, 197, 255), batch=self.batch, group=text,
        )

    def draw(self, left, bottom, width, height):
        unit = min((width - 44) / (LAYOUT["width"] * 2 + 0.6),
                   max(1, height - 175) / LAYOUT["height"])
        top = bottom + height - 70
        origins = [left + 22, left + 22 + (LAYOUT["width"] + 0.6) * unit]
        colors = [(135, 221, 196), (245, 175, 195)]
        for index, title in enumerate(self.titles):
            title.position = (origins[index], top, 0)
            title.font_size = min(14, max(10, unit * 0.38))
            title.color = (*colors[index], 255)
        diagram_top = top - 27
        for entry, border, face, label, control in self.caps:
            color = colors[entry["player"] - 1]
            x = origins[entry["player"] - 1] + entry["x"] * unit
            h = entry.get("h", 1) * unit - 3
            w = entry.get("w", 1) * unit - 3
            y = diagram_top - entry["y"] * unit - h
            border.position = (x, y)
            border.width, border.height = w, h
            face.position = (x + 1, y + 3)
            face.width, face.height = max(1, w - 2), max(1, h - 4)
            bound = "symbol" in entry
            held = bound and self.key_state is not None and any(
                self.key_state[getattr(pyglet.window.key, name)]
                for name in [entry["symbol"]] + entry.get("aliases", []))
            border.color = color if bound else (64, 80, 90)
            face.color = color if held else (33, 48, 57) if bound else (23, 35, 43)
            label.position = (x + w / 2, y + h / 2 + (unit * 0.13 if bound else 0), 0)
            label.font_size = unit * (0.17 if len(entry["key"]) > 3 else 0.32)
            label.color = (12, 28, 35, 255) if held else (236, 244, 246, 255) if bound else (111, 130, 139, 255)
            control.position = (x + w / 2, y + h / 2 - unit * 0.22, 0)
            control.font_size = unit * 0.145
            control.color = (12, 28, 35, 255) if held else (*color, 255)
        self.footer.position = (left + 22, diagram_top - LAYOUT["height"] * unit - 10, 0)
        self.footer.width = max(1, width - 44)
        self.footer.font_size = min(10, max(7, unit * 0.27))
        self.batch.draw()
