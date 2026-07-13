from ventilastation.director import director
from vs2 import FULLSCREEN, HUD, TUNNEL, Scene, Sprite


CHAR_WIDTH = 9
DISPLAY_LEN = 18
STEP_QUARTERS = 1
ACCEL_FRAMES = 8
MAX_STEP_QUARTERS = 16


class TextDisplay:
    def __init__(self, y):
        self.chars = []
        for n in range(DISPLAY_LEN):
            x = (256 - n * CHAR_WIDTH + (DISPLAY_LEN * CHAR_WIDTH) // 2) % 256
            self.chars.append(Sprite("rainbow437.png", x=x, y=y, frame=0, mode=HUD))
        self.set_value("")

    def set_value(self, value):
        value = str(value)[:DISPLAY_LEN]
        for n in range(DISPLAY_LEN):
            frame = ord(value[n]) if n < len(value) else 0
            self.chars[n].frame = frame


def format_quarters(value):
    sign = ""
    if value < 0:
        sign = "-"
        value = -value
    return "%s%d.%02d" % (sign, value // 4, (value % 4) * 25)


class TutorialVs2(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(TutorialVs2, self).on_enter()
        self.title = TextDisplay(0)
        self.coordinates = TextDisplay(14)
        self.flags = TextDisplay(28)

        self.entries = [
            {
                "name": "BICHOS",
                "sprite": Sprite("galaga.png", x=-8, y=16, frame=6, mode=TUNNEL),
                "xq": -32,
                "yq": 64,
                "frames": 12,
            },
            {
                "name": "SIGN",
                "sprite": Sprite("gameover.png", x=224, y=16, frame=0, mode=HUD),
                "xq": 896,
                "yq": 64,
                "frames": 1,
            },
            {
                "name": "PLANET",
                "sprite": Sprite("bembi.png", x=0, y=255, frame=0, mode=FULLSCREEN),
                "xq": 0,
                "yq": 1020,
                "frames": 1,
            },
            {
                "name": "VOOM",
                "sprite": Sprite("doom.png", x=0, y=255, frame=0, mode=FULLSCREEN),
                "xq": 0,
                "yq": 1020,
                "frames": 1,
            },
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
        for n, entry in enumerate(self.entries):
            entry["sprite"].visible = n == index
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
        entry = self.active()
        frames = entry["frames"]
        if frames > 1:
            entry["sprite"].frame = (entry["sprite"].frame + 1) % frames
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
        self.x_direction = 0
        self.y_direction = 0
        self.x_hold_frames = 0
        self.y_hold_frames = 0

    def axis_delta(self, axis, direction):
        if direction == 0:
            if axis == "x":
                self.x_direction = 0
                self.x_hold_frames = 0
            else:
                self.y_direction = 0
                self.y_hold_frames = 0
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

        step = STEP_QUARTERS + min((held - 1) // ACCEL_FRAMES, MAX_STEP_QUARTERS - STEP_QUARTERS)
        return direction * step

    def refresh_display(self):
        entry = self.active()
        sprite = entry["sprite"]
        self.title.set_value("VS2 %s" % entry["name"])
        self.coordinates.set_value(
            "X=%s Y=%s" % (format_quarters(entry["xq"]), format_quarters(entry["yq"]))
        )
        self.flags.set_value(
            "FX=%d FY=%d FR=%02d" % (sprite.flip_x, sprite.flip_y, sprite.frame)
        )

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            self.finished()

        if director.was_pressed(director.BUTTON_A):
            self.activate_next()

        if director.was_pressed(director.BUTTON_B):
            self.cycle_flip()

        if director.was_pressed(director.BUTTON_C):
            self.cycle_frame()

        x_direction = 0
        y_direction = 0
        if director.is_pressed(director.JOY_LEFT):
            x_direction += 1
        if director.is_pressed(director.JOY_RIGHT):
            x_direction -= 1
        if director.is_pressed(director.JOY_UP):
            y_direction += 1
        if director.is_pressed(director.JOY_DOWN):
            y_direction -= 1
        dx = self.axis_delta("x", x_direction)
        dy = self.axis_delta("y", y_direction)
        self.move_active(dx, dy)

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return TutorialVs2()
