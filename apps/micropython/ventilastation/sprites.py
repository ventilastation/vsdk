from ventilastation.runtime import get_platform


def _sprites_backend():
    return get_platform().sprites


def reset_sprites():
    return _sprites_backend().reset_sprites()


def set_imagestrip(number, stripmap):
    return _sprites_backend().set_imagestrip(number, stripmap)


Sprite = _sprites_backend().Sprite
