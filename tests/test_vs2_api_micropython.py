"""Smoke the public VS2 surface on the MicroPython unix runtime itself."""

import sys

sys.path.insert(0, "apps/micropython")

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


def main():
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()
    stripes["ship.png"] = 0
    runtime.platform.sprites.stripes[0] = {
        "width": 1, "height": 1, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.micro_vs2", "vs2")

    import vs2
    # Exercise MicroPython's actual IMPORT_STAR opcode.  A function-scope
    # source-level star import is invalid syntax, so execute it in globals.
    exec("from vs2.controls import *")

    assert globals()["LEFT"] == 1
    assert globals()["joy1"] is not globals()["joy2"]
    assert vs2.display.width == 256 and vs2.display.height == 54
    assert int(vs2.controls.idle_ms) >= 0
    assert vs2.controls.idle_ms // 1000 >= 0
    assert isinstance(hash(vs2.controls.idle_ms), int)

    class Game(vs2.Scene):
        def build(self):
            # Allocation order intentionally disagrees with layer order.
            world = self.layer("world", projection=vs2.TUNNEL)
            hud = self.layer("hud", projection=vs2.HUD)
            self.badge = hud.sprite("ship.png")
            self.ship = world.sprite("ship.png")

    game = Game()
    director.push(game)
    payload = vs2.export_scene_payload(game)
    # Sprite records are layer-major: world is record zero even though the
    # HUD badge was allocated first. The native backend receives this same
    # sealing order through set_draw_order().
    sprite_offset = 16 + 2 * 8
    assert payload[sprite_offset] == 0
    assert payload[sprite_offset + 24] == 1
    assert payload[-4:] == bytes((0, 0, 0, 1))
    print("vs2 micropython API: package controls and layer order passed")


if __name__ == "__main__":
    main()
