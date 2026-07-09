from ventilastation.runtime import get_platform


def _display():
    return get_platform().display


def init(num_pixels, *hw_config):
    return _display().init(num_pixels, *hw_config)


def set_palettes(palette):
    return _display().set_palettes(palette)


def getaddress(sprite_num):
    return _display().getaddress(sprite_num)


def set_gamma_mode(mode):
    return _display().set_gamma_mode(mode)


def set_column_offset(offset):
    return _display().set_column_offset(offset)


def get_column_offset():
    return _display().get_column_offset()


def set_imagestrip(number, stripmap):
    return _display().set_imagestrip(number, stripmap)


def update():
    return _display().update()


def last_turn_duration():
    return _display().last_turn_duration()
