"""Target display geometry shared by V2 services and host-side tests.

The matching firmware definition is ``povdisplay/display_geometry.h``.  Keep
both tiny target definitions together when adding a display variant; game code
only consumes ``vs2.display.width`` and ``.height``.
"""

DISPLAY_WIDTH = 256
DISPLAY_HEIGHT = 54
