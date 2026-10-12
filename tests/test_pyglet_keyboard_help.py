"""Exercise native help input routing without requiring a display or gamepads."""
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import sys
import types

layout = json.loads(Path('web/keyboard-layout.json').read_text())
names = {'ESCAPE', 'Q', 'F1', 'F2', 'F3', 'F4', 'F5', 'U', 'LCTRL', 'RCTRL',
         'LCOMMAND', 'RCOMMAND', 'LMETA', 'RMETA', 'MOD_CTRL', 'MOD_COMMAND'}
for entry in layout['keys']:
    names.update([entry['symbol']] + entry.get('aliases', []))
key = types.SimpleNamespace(**{name: index for index, name in enumerate(sorted(names), 1)})
key.KeyStateHandler = lambda: defaultdict(bool)

class EventTarget:
    def event(self, handler):
        return handler
    def push_handlers(self, *args):
        pass
    def get_controllers(self):
        return []

pyglet = types.ModuleType('pyglet')
pyglet.window = types.ModuleType('pyglet.window')
pyglet.window.key = key
pyglet.event = types.SimpleNamespace(EVENT_HANDLED=True)
pyglet.app = types.SimpleNamespace(exit=lambda: None)
pyglet.input = types.SimpleNamespace(controller=types.SimpleNamespace(add_mappings_from_file=lambda path: None),
                                   ControllerManager=EventTarget)
sys.modules.update({'pyglet': pyglet, 'pyglet.window': pyglet.window, 'comms': types.ModuleType('comms')})
draw = types.ModuleType('pyglet2x.pygletdraw')
draw.window = EventTarget()
draw.keyboard_diagram = types.SimpleNamespace(key_state=None)
draw.active_overlay = None
draw.OVERLAY_HELP = 'help'
def dismiss():
    was_open = draw.active_overlay is not None
    draw.active_overlay = None
    return was_open
def toggle():
    draw.active_overlay = None if draw.active_overlay else draw.OVERLAY_HELP
draw.dismiss_overlay = dismiss
draw.toggle_help_overlay = toggle
for name in ('compare_scene_renderers', 'toggle_scene_renderer', 'toggle_settings_overlay'):
    setattr(draw, name, lambda: None)
package = types.ModuleType('pyglet2x')
package.pygletdraw = draw
sys.modules.update({'pyglet2x': package, 'pyglet2x.pygletdraw': draw})
sys.path.insert(0, 'emulator')
spec = importlib.util.spec_from_file_location('native_inputs', 'emulator/pyglet2x/inputs.py')
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)
inputs.init_inputs()
assert draw.keyboard_diagram.key_state is inputs.keys
inputs.on_key_press(key.F1, 0)
inputs.keys[key.SPACE] = True
assert inputs.encode_input_val() == (0, 0, 0, False)
inputs.keys[key.ESCAPE] = True
inputs.on_key_press(key.ESCAPE, 0)
assert draw.active_overlay is None
assert inputs.encode_input_val() == (0, 0, 0, False)
inputs.on_key_press(key.ESCAPE, 0)  # Autorepeat after help has closed.
assert inputs.encode_input_val() == (0, 0, 0, False)
inputs.keys[key.ESCAPE] = False
inputs.keys[key.SPACE] = False
inputs.encode_input_val()
inputs.keys[key.SPACE] = True
assert inputs.encode_input_val() == (16, 0, 0, False)
inputs.keys[key.ESCAPE] = True
inputs.on_key_press(key.ESCAPE, 0)
assert inputs.encode_input_val() == (16, 0, 0, True)
print('Native help previews keys, quarantines held input and consumes closing Escape/autorepeat')
