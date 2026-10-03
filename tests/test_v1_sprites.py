"""The V1 Sprite API (ventilastation.sprites) behaves the same in the
emulators as on the console, whose implementation is
hardware/rotor/modules/povdisplay/sprites.c: the desktop and browser
emulators use ventilastation/emu_sprites.py, tests and scripted runs the
headless backend."""

import os
import pathlib
import random
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "micropython"))
sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", random)

# emu_spritelib maps sprites onto the display's memory with uctypes, which
# CPython lacks; each sprite gets a plain object instead.
fake_uctypes = types.ModuleType("uctypes")
fake_uctypes.UINT8 = 0
fake_uctypes.INT8 = 0
fake_uctypes.struct = lambda _address, _layout: types.SimpleNamespace(
    x=0, y=0, image_strip=0, frame=255, perspective=1)
sys.modules.setdefault("uctypes", fake_uctypes)

from ventilastation import emu_sprites, emu_spritelib  # noqa: E402
from ventilastation.platforms.headless import HeadlessSprites  # noqa: E402

DISABLED_FRAME = 255


def strip(width, height, frames):
    """A strip buffer as the director hands it to the backends."""
    return bytes([width, height, frames, 0]) + bytes(width * height * frames)


class EmulatorBackend:
    name = "emu_sprites"

    def __init__(self):
        emu_spritelib.stripes.clear()
        emu_sprites.get_sprite = lambda _num: fake_uctypes.struct(0, None)

    def install(self, number, data):
        emu_spritelib.stripes[number] = data

    def sprite(self):
        return emu_sprites.Sprite()


class HeadlessBackend:
    name = "headless"

    def __init__(self):
        self.backend = HeadlessSprites()

    def install(self, number, data):
        self.backend.set_imagestrip(number, data)

    def sprite(self):
        return self.backend.Sprite()


BACKENDS = (EmulatorBackend, HeadlessBackend)


def placed(backend, strip_number, x, y, frame=0):
    sprite = backend.sprite()
    sprite.set_strip(strip_number)
    sprite.set_x(x)
    sprite.set_y(y)
    sprite.set_frame(frame)
    return sprite


class DisabledTargetTests(unittest.TestCase):
    """sprites.c's collision() skips disabled targets. The emulators used to
    return them, so a disabled sprite listed before an enabled one at the
    same place hid the real hit (games/vsjam-may25/vs keeps unbought
    bullets disabled in the list it checks)."""

    def test_a_disabled_target_never_collides(self):
        for backend_type in BACKENDS:
            with self.subTest(backend_type.name):
                backend = backend_type()
                backend.install(0, strip(8, 8, 1))
                shooter = placed(backend, 0, 10, 10)
                hidden = placed(backend, 0, 10, 10, frame=DISABLED_FRAME)
                self.assertIsNone(shooter.collision([hidden]))

    def test_a_disabled_target_does_not_hide_an_enabled_one(self):
        for backend_type in BACKENDS:
            with self.subTest(backend_type.name):
                backend = backend_type()
                backend.install(0, strip(8, 8, 1))
                shooter = placed(backend, 0, 10, 10)
                hidden = placed(backend, 0, 10, 10, frame=DISABLED_FRAME)
                visible = placed(backend, 0, 12, 12)
                self.assertIs(shooter.collision([hidden, visible]), visible)

    def test_enabled_targets_still_collide(self):
        for backend_type in BACKENDS:
            with self.subTest(backend_type.name):
                backend = backend_type()
                backend.install(0, strip(8, 8, 1))
                shooter = placed(backend, 0, 10, 10)
                near = placed(backend, 0, 17, 17)
                far = placed(backend, 0, 18, 10)
                self.assertIs(shooter.collision([near]), near)
                self.assertIsNone(shooter.collision([far]))


if __name__ == "__main__":
    unittest.main()
