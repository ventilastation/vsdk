from ventilastation.director import comms
import uctypes
from urandom import randrange

sprite_data = bytearray(b"\0\0\0\xff\xff" * 100)
stripes = {}

def init(num_pixels):
    pass

def set_palettes(palette):
    comms.send(b"palette %d" % (len(palette)/ 1024),  palette)

def getaddress(sprite_num):
    return uctypes.addressof(sprite_data) + sprite_num * 5

def set_gamma_mode(_):
    return None

def set_imagestrip(n, stripmap):
    stripes[n] = stripmap
    comms.send(b"imagestrip %s %d" % (n, len(stripmap)), stripmap)

def update():
    comms.send(b"sprites", sprite_data)

def last_turn_duration():
    return 1234000 + randrange(1000)
