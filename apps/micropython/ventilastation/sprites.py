"""Facade over the active platform's sprite backend.

`Sprite` is resolved through a module __getattr__ so importing this module
never binds to a backend prematurely: the class always comes from whatever
platform is configured at access time.
"""

from ventilastation.runtime import get_platform


def _sprites_backend():
    return get_platform().sprites


def reset_sprites():
    return _sprites_backend().reset_sprites()


def set_imagestrip(number, stripmap):
    return _sprites_backend().set_imagestrip(number, stripmap)


def __getattr__(name):
    if name == "Sprite":
        return _sprites_backend().Sprite
    raise AttributeError(name)
