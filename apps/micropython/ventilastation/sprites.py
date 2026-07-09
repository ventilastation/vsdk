"""Facade over the active platform's sprite backend.

`Sprite` is resolved through a module __getattr__ so importing this module
never binds to a backend prematurely: the class always comes from whatever
platform is configured at access time.
"""

from ventilastation.runtime import get_platform
from ventilastation import api_guard


def _claim():
    api_guard.claim("sprites", "ventilastation.sprites")


_claim()


def _sprites_backend():
    return get_platform().sprites


def reset_sprites():
    _claim()
    return _sprites_backend().reset_sprites()


def set_imagestrip(number, stripmap):
    _claim()
    return _sprites_backend().set_imagestrip(number, stripmap)


def __getattr__(name):
    if name == "Sprite":
        _claim()
        return _sprites_backend().Sprite
    raise AttributeError(name)
