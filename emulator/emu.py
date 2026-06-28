import subprocess, platform
import comms
import sys
from itertools import cycle
from pygletengine import PygletEngine


led_count = 54

# Mode flags (the board IP, when connecting to hardware, is the first positional arg):
#   (default)      run the local desktop MicroPython as the frame source and render it
#   --remote       connect to a real board (e.g. prboom-go streaming POV frames over
#                  TCP) and render the received frames here; no local MicroPython
#   --no-display   connect to a real board for button input only; render nothing
#                  (the physical spinning LEDs are the display)
no_display = "--no-display" in sys.argv
remote = "--remote" in sys.argv

# Spawn the local desktop MicroPython only when it is our frame source.
spawn_upy = not (no_display or remote)
# Render the POV window unless explicitly headless.
enable_display = not no_display

UPY_ROOT = "../apps/micropython"
UPY_EXEC = "micropython.exe" if platform.system() == "Windows" else "micropython"

try:
    if spawn_upy:
        upy = subprocess.Popen([UPY_EXEC, "-X", "heapsize=8m", "main.py", "--platform=desktop"], cwd=UPY_ROOT)
    PygletEngine(led_count, comms.send, enable_display)
finally:
    comms.shutdown()
    if spawn_upy:
        upy.kill()
