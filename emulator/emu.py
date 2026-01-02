import subprocess, platform
import comms
import sys
from itertools import cycle
from pygletengine import PygletEngine


led_count = 54

enable_display = False if "--no-display" in sys.argv else True

UPY_ROOT = "../apps/micropython"
UPY_EXEC = "micropython.exe" if platform.system() == "Windows" else "micropython"

try:
    if enable_display:
        upy = subprocess.Popen([UPY_EXEC, "-X", "heapsize=8m", "main.py"], cwd=UPY_ROOT)  
    PygletEngine(led_count, comms.send, enable_display)
finally:
    comms.shutdown()
    if enable_display:
        upy.kill()
