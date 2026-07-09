from ventilastation.director import comms
import uctypes
from urandom import randrange
import gc

sprite_data = bytearray(b"\0\0\0\xff\xff" * 100)
stripes = {}
_palette = None
vs2_scene_data = None

def init(num_pixels, *hw_config):
    pass

def set_palettes(palette):
    global _palette
    # NOTE 2bam: This keeps making the emulator run out of memory. I'm guessing
    # it's not the case in the actual platform so I added a collect here.
    # Please, remove if it's no-bueno.
    gc.collect()
    _palette = palette
    comms.send(b"palette %d" % (len(palette) / 1024), palette)

def getaddress(sprite_num):
    return uctypes.addressof(sprite_data) + sprite_num * 5

def set_gamma_mode(_):
    return None

column_offset = 0

def set_column_offset(offset):
    global column_offset
    column_offset = offset % 256

def get_column_offset():
    return column_offset

def set_imagestrip(n, stripmap):
    print("remotepov: set_imagestrip %s (%d bytes)" % (n, len(stripmap)))
    stripes[n] = stripmap
    comms.send(b"imagestrip %s %d" % (n, len(stripmap)), stripmap)

def prepare_frame(scene):
    global vs2_scene_data
    if getattr(scene, "_vs_declared_api", None) != "vs2":
        vs2_scene_data = None
        return
    import vs2
    vs2_scene_data = vs2.export_scene_payload(scene)

def _resend_all():
    print("remotepov: resend_all palette=%s strips=%s" % (_palette is not None, list(stripes.keys())))
    if _palette is not None:
        comms.send(b"palette %d" % (len(_palette) / 1024), _palette)
        print("remotepov: palette sent (%d bytes)" % len(_palette))
    for n, stripmap in stripes.items():
        comms.send(b"imagestrip %s %d" % (n, len(stripmap)), stripmap)
        print("remotepov: imagestrip %s sent (%d bytes)" % (n, len(stripmap)))
    print("remotepov: resend_all done")

def update():
    if comms.was_new_connection():
        print("remotepov: new connection detected, resending all")
        _resend_all()
    comms.send(b"sprites", sprite_data)
    if vs2_scene_data is not None:
        comms.send(b"vs2_scene %d" % len(vs2_scene_data), vs2_scene_data)

def last_turn_duration():
    return 1234000 + randrange(1000)
