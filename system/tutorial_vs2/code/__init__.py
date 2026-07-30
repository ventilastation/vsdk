import vs2
from vs2.controls import A, B, LEFT, RIGHT, UP, DOWN, joy1


CHAR_WIDTH = 9
DISPLAY_LEN = 18
STEP_QUARTERS = 1
ACCEL_FRAMES = 8
MAX_STEP_QUARTERS = 16


class TextDisplay:
    def __init__(self, layer, y):
        # Logical text writes left-to-right; Label owns the rotor's reversed
        # cell storage direction.
        self.label = layer.label("rainbow437.png", columns=DISPLAY_LEN,
                                 x=-(DISPLAY_LEN * CHAR_WIDTH // 2), y=y)

    def set_value(self, value):
        self.label.text = value


def format_quarters(value):
    sign = ""
    if value < 0:
        sign = "-"
        value = -value
    return "%s%d.%02d" % (sign, value // 4, (value % 4) * 25)


class TutorialVs2(vs2.Scene):
    asset_pack = "other"

    def build(self):
        self.fullscreen = self.layer("fullscreen", projection=vs2.FULLSCREEN)
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)
        self.title = TextDisplay(self.hud, 0)
        self.coordinates = TextDisplay(self.hud, 14)
        self.flags = TextDisplay(self.hud, 28)

        self.entries = [
            {"name": "BICHOS", "sprite": self.world.sprite("galaga.png", x=-8, y=0, frame=6), "xq": -32, "yq": 0},
            {"name": "SIGN", "sprite": self.hud.sprite("gameover.png", x=224, y=16), "xq": 896, "yq": 64},
            {"name": "PLANET", "sprite": self.fullscreen.sprite("bembi.png", x=0, y=0), "xq": 0, "yq": 0},
            {"name": "VOOM", "sprite": self.fullscreen.sprite("doom.png", x=0, y=0), "xq": 0, "yq": 0},
        ]
        self.current = 0
        self.flip_state = 0
        self.x_direction = 0
        self.y_direction = 0
        self.x_hold_frames = 0
        self.y_hold_frames = 0
        self.activate(0)

    def active(self):
        return self.entries[self.current]

    def activate_next(self):
        self.activate((self.current + 1) % len(self.entries))

    def activate(self, index):
        self.current = index
        self.reset_movement()
        for number, entry in enumerate(self.entries):
            entry["sprite"].visible = number == index
        self.apply_entry_state()
        self.refresh_display()

    def apply_entry_state(self):
        entry = self.active()
        sprite = entry["sprite"]
        sprite.x = entry["xq"] / 4
        sprite.y = entry["yq"] / 4
        sprite.flip_x = bool(self.flip_state & 1)
        sprite.flip_y = bool(self.flip_state & 2)

    def cycle_flip(self):
        self.flip_state = (self.flip_state + 1) % 4
        self.apply_entry_state()
        self.refresh_display()

    def cycle_frame(self):
        sprite = self.active()["sprite"]
        if sprite.image.frames > 1:
            sprite.frame = (sprite.frame + 1) % sprite.image.frames
        self.refresh_display()

    def move_active(self, dx, dy):
        if not dx and not dy:
            return
        entry = self.active()
        entry["xq"] += dx
        entry["yq"] += dy
        self.apply_entry_state()
        self.refresh_display()

    def reset_movement(self):
        self.x_direction = self.y_direction = 0
        self.x_hold_frames = self.y_hold_frames = 0

    def axis_delta(self, axis, direction):
        if direction == 0:
            if axis == "x":
                self.x_direction = self.x_hold_frames = 0
            else:
                self.y_direction = self.y_hold_frames = 0
            return 0
        if axis == "x":
            if direction != self.x_direction:
                self.x_hold_frames = 0
            self.x_direction = direction
            self.x_hold_frames += 1
            held = self.x_hold_frames
        else:
            if direction != self.y_direction:
                self.y_hold_frames = 0
            self.y_direction = direction
            self.y_hold_frames += 1
            held = self.y_hold_frames
        step = STEP_QUARTERS + min((held - 1) // ACCEL_FRAMES,
                                   MAX_STEP_QUARTERS - STEP_QUARTERS)
        return direction * step

    def refresh_display(self):
        entry = self.active()
        sprite = entry["sprite"]
        self.title.set_value("VS2 %s" % entry["name"])
        self.coordinates.set_value("X=%s Y=%s" % (format_quarters(entry["xq"]),
                                                    format_quarters(entry["yq"])))
        self.flags.set_value("FX=%d FY=%d FR=%02d" %
                             (sprite.flip_x, sprite.flip_y, sprite.frame))

    def update(self):
        if joy1.just_pressed(A):
            self.activate_next()
        if joy1.just_pressed(B):
            self.cycle_flip()
        if joy1.just_pressed(vs2.controls.X):
            self.cycle_frame()
        x_direction = (1 if joy1.held(LEFT) else 0) - (1 if joy1.held(RIGHT) else 0)
        y_direction = (1 if joy1.held(UP) else 0) - (1 if joy1.held(DOWN) else 0)
        self.move_active(self.axis_delta("x", x_direction),
                         self.axis_delta("y", y_direction))


def main():
    return TutorialVs2()
