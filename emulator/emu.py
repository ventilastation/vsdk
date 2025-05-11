import subprocess, platform
import comms
import sys
from itertools import cycle
from pygletengine import PygletEngine


led_count = 54
#if len(sys.argv) >= 2:
    #led_count = int(sys.argv[1])


display = False if "--no-display" in sys.argv else True

UPY_ROOT = "../apps/micropython"
UPY_EXEC = "micropython.exe" if platform.system() == "Windows" else "micropython"

try:
    if display:
        upy = subprocess.Popen([UPY_EXEC, "-X", "heapsize=8m", "main.py"], cwd=UPY_ROOT)  
    PygletEngine(led_count, comms.send, display)
finally:
    comms.shutdown()
    if display:
        upy.kill()
