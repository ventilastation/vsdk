"""Deterministic, maximum-budget VS2 scene for physical acceptance tests.

This is intentionally a system-only fixture rather than a launcher entry.  It
uses the shared ``other`` asset pack so the hardware oracle can render the same
scene on the host without maintaining a second set of golden bitmap assets.
"""

import vs2


LAYER_COUNT = 8
TUNNEL_LAYER_COUNT = LAYER_COUNT - 1
SPRITE_COUNT = 100
TILEMAP_COUNT = 16
ENVIRONMENT_TILEMAP_COUNT = 3
LABEL_COUNT = TILEMAP_COUNT - ENVIRONMENT_TILEMAP_COUNT

TUNNEL_DEPTH_MIN = 16
TUNNEL_DEPTH_MAX = 240
TUNNEL_DEPTH_SPAN = TUNNEL_DEPTH_MAX - TUNNEL_DEPTH_MIN
ENVIRONMENT_COLUMNS = 8
ENVIRONMENT_ROWS = 17
ENVIRONMENT_TILE_HEIGHT = 16
# Match Vixeous's eight-row terrain window: enough depth to fill the useful
# tunnel LEDs without scanning the far half of a 256-row source plane for
# every ground/object/cloud column.
ENVIRONMENT_VIEW_HEIGHT = 8 * ENVIRONMENT_TILE_HEIGHT

GROUND_FRAMES = 8
OBJECT_FRAME_BASE = 8
OBJECT_FRAMES = 4
CLOUD_FRAME_BASE = 12
CLOUD_FRAMES = 4

HUD_LABEL_COLUMNS = 2
HUD_LABEL_X_STEP = 128
HUD_LABEL_Y_STEP = 8
_LABEL_IDENTITIES = (
    (1, 0), (1, 1),
    (2, 0), (2, 1),
    (3, 0), (3, 1),
    (4, 0), (4, 1),
    (5, 0), (5, 1),
    (6, 0), (6, 1),
    (7, 0),
)
_SPRITES_PER_LAYER = (15, 15, 14, 14, 14, 14, 14)
_LAYER_X_SPEEDS = (1, 2, 3, 4, -3, -2, -1)
_LAYER_Y_SPEEDS = (1, 2, 3, 4, -2, -3, -4)
_ENVIRONMENT_SCROLL_EVERY = 2
_LAYER_SCROLL_EVERY = 4


class Vs2Hardware(vs2.Scene):
    asset_pack = "other"
    idle_timeout = None
    back_button = False

    def _label_position(self, display_index):
        return (
            (display_index % HUD_LABEL_COLUMNS) * HUD_LABEL_X_STEP,
            (display_index // HUD_LABEL_COLUMNS) * HUD_LABEL_Y_STEP,
        )

    def _label(self, layer, display_index, layer_index, label_index):
        x, y = self._label_position(display_index)
        label = layer.label(
            "tinyfont_menu.png",
            columns=21,
            x=x,
            y=y,
        )
        label.text = "L%d.%d VS2 USB %03d" % (
            layer_index,
            label_index,
            layer_index * 17 + label_index,
        )
        return label

    def _sprite_position(self, layer_index, global_index):
        y = TUNNEL_DEPTH_MIN + (
            global_index * TUNNEL_DEPTH_SPAN // SPRITE_COUNT
        )
        x = (global_index * 37 + layer_index * 19) % vs2.display.width
        if global_index == 0:
            x = -0.75
        elif global_index % 9 == 0:
            x += 0.5
        return x, y

    def _sprite(self, layer, layer_index, index, global_index):
        x, y = self._sprite_position(layer_index, global_index)
        sprite = layer.sprite(
            "galaga.png",
            x=x,
            y=y,
            frame=(global_index * 5 + index) % 12,
            visible=global_index != SPRITE_COUNT - 1,
            flip_x=bool(global_index & 1),
            flip_y=bool(global_index & 2),
        )
        return sprite

    def _environment_cells(self, kind):
        cells = bytearray(
            [vs2.EMPTY_TILE] * (ENVIRONMENT_COLUMNS * ENVIRONMENT_ROWS)
        )
        for row in range(ENVIRONMENT_ROWS):
            for column in range(ENVIRONMENT_COLUMNS):
                index = row * ENVIRONMENT_COLUMNS + column
                if kind == "ground":
                    cells[index] = (row * 3 + column * 5) % GROUND_FRAMES
                elif kind == "objects":
                    if (row * 5 + column * 3) % 11 in (0, 1):
                        cells[index] = OBJECT_FRAME_BASE + (
                            row + column * 3
                        ) % OBJECT_FRAMES
                elif (row * 7 + column * 5) % 13 in (0, 1, 2):
                    cells[index] = CLOUD_FRAME_BASE + (
                        row * 2 + column
                    ) % CLOUD_FRAMES
        return cells

    def _environment_tilemap(self, layer, kind):
        return layer.tilemap(
            "vs2_environment.png",
            columns=ENVIRONMENT_COLUMNS,
            rows=ENVIRONMENT_ROWS,
            cells=self._environment_cells(kind),
            x=0,
            y=0,
            view_width=vs2.display.width,
            view_height=ENVIRONMENT_VIEW_HEIGHT,
        )

    def build(self):
        self.tunnel_layers = [
            self.layer("acceptance%d" % index, projection=vs2.TUNNEL)
            for index in range(TUNNEL_LAYER_COUNT)
        ]
        self.label_layer = self.layer("labels", projection=vs2.HUD)
        self.test_layers = self.tunnel_layers + [self.label_layer]
        self.labels = []
        self.sprites = []
        self.layer_labels = [[] for _ in range(LAYER_COUNT)]
        self.layer_sprites = [[] for _ in range(LAYER_COUNT)]
        self.tick = 0
        self.animate = True

        # These two maps are deliberately below every sprite in the flattened
        # draw order. The sparse object map exercises transparent tile cells
        # without hiding the Vixeous-style ground beneath it.
        self.ground = self._environment_tilemap(self.tunnel_layers[0], "ground")
        self.objects = self._environment_tilemap(self.tunnel_layers[0], "objects")

        global_index = 0
        for layer_index, layer in enumerate(self.tunnel_layers):
            sprite_count = _SPRITES_PER_LAYER[layer_index]
            for index in range(sprite_count):
                sprite = self._sprite(layer, layer_index, index, global_index)
                self.sprites.append(sprite)
                self.layer_sprites[layer_index].append(sprite)
                global_index += 1

        # Clouds are the topmost tunnel drawable. The final HUD layer is
        # reserved exclusively for labels, keeping their glyphs above every
        # tunnel layer and preserving their full six-pixel radial height.
        self.clouds = self._environment_tilemap(self.tunnel_layers[-1], "clouds")
        for display_index, identity in enumerate(_LABEL_IDENTITIES):
            layer_index, label_index = identity
            label = self._label(
                self.label_layer,
                display_index,
                layer_index,
                label_index,
            )
            self.labels.append(label)
            self.layer_labels[-1].append(label)

        self.environment_scroll = (
            (self.ground, 1, 1),
            (self.objects, 2, 3),
            (self.clouds, -3, 2),
        )

    def update(self):
        if not self.animate:
            return
        self.tick += 1
        if self.tick % _LAYER_SCROLL_EVERY == 0:
            layer_index = (
                self.tick // _LAYER_SCROLL_EVERY - 1
            ) % TUNNEL_LAYER_COUNT
            dx = _LAYER_X_SPEEDS[layer_index]
            dy = _LAYER_Y_SPEEDS[layer_index]
            for sprite in self.layer_sprites[layer_index]:
                sprite.x = (sprite.x + dx) % vs2.display.width
                sprite.y = TUNNEL_DEPTH_MIN + (
                    sprite.y - TUNNEL_DEPTH_MIN + dy
                ) % TUNNEL_DEPTH_SPAN

        if self.tick % _ENVIRONMENT_SCROLL_EVERY == 0:
            for tilemap, dx, dy in self.environment_scroll:
                tilemap.x = (tilemap.x + dx) % vs2.display.width
                tilemap.view_y = (
                    tilemap.view_y + dy
                ) % ENVIRONMENT_TILE_HEIGHT

    def prepare_capture(self):
        """Restore the build-time frame and stop motion for C-oracle parity."""
        self.animate = False
        self.tick = 0
        global_index = 0
        for layer_index in range(TUNNEL_LAYER_COUNT):
            for sprite in self.layer_sprites[layer_index]:
                sprite.x, sprite.y = self._sprite_position(
                    layer_index, global_index
                )
                global_index += 1
        for display_index, label in enumerate(self.labels):
            label.x, label.y = self._label_position(display_index)
        for tilemap, _dx, _dy in self.environment_scroll:
            tilemap.x = 0
            tilemap.view_y = 0


def main():
    return Vs2Hardware()
