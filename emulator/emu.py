import subprocess, platform
import comms
import sys
from itertools import cycle
from pygletengine import PygletEngine


led_count = 54

# --no-display: connect to real hardware over WiFi for button input only.
# The physical LEDs are the display, so no local subprocess or renderer is needed.
no_display = "--no-display" in sys.argv

UPY_ROOT = "../apps/micropython"
UPY_EXEC = "micropython.exe" if platform.system() == "Windows" else "micropython"

try:
    if not no_display:
        upy = subprocess.Popen([UPY_EXEC, "-X", "heapsize=8m", "main.py", "--platform=desktop"], cwd=UPY_ROOT)
    PygletEngine(led_count, comms.send, not no_display)
finally:
    comms.shutdown()
    if not no_display:
        upy.kill()
