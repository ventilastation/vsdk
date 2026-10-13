"""Desktop host for the original C game, independent of MicroPython's build.

Only the receive thread calls the engine. The renderer receives an immutable
frame copy, and audio/control commands use the normal host dispatcher.
"""
import ctypes
import importlib.util
from pathlib import Path

FRAME_BYTES = 256 * 54 * 3
_engine = None


class Ventilagon:
    def __init__(self, path=None):
        if path is None:
            builder = Path(__file__).resolve().parents[1] / "tools" / "build_ventilagon.py"
            spec = importlib.util.spec_from_file_location("build_ventilagon", builder)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            path = module.build()
        self.lib = ctypes.CDLL(str(path))
        for name, args, result in (
            ("enter", [ctypes.c_uint32], None),
            ("exit", [], None),
            ("update", [ctypes.c_uint32, ctypes.c_int], None),
            ("is_idle", [], ctypes.c_int),
            ("sending", [], ctypes.c_char_p),
            ("frame", [], ctypes.c_void_p),
        ):
            fn = getattr(self.lib, "ventilagon_host_" + name)
            fn.argtypes, fn.restype = args, result
        self.active = False

    def commands(self):
        while True:
            line = self.lib.ventilagon_host_sending()
            if line is None:
                return
            yield line

    def handle(self, args, present, dispatch, status):
        if not args:
            raise ValueError("ventilagon command needs an operation")
        op = args[0]
        if op == b"enter" and len(args) == 2:
            self.lib.ventilagon_host_enter(int(args[1]))
            self.active = True
        elif op == b"tick" and len(args) == 3:
            if not self.active:
                raise RuntimeError("Ventilagon is not active; enter it before ticking")
            elapsed, buttons = int(args[1]), int(args[2])
            if not 0 <= elapsed <= 250000 or not 0 <= buttons <= 255:
                raise ValueError("invalid Ventilagon time/input")
            self.lib.ventilagon_host_update(elapsed, buttons)
            present(ctypes.string_at(self.lib.ventilagon_host_frame(), FRAME_BYTES))
        elif op == b"exit" and len(args) == 1:
            self.lib.ventilagon_host_exit()
            self.active = False
        else:
            raise ValueError("invalid ventilagon command: %r" % (args,))
        for line in self.commands():
            command, *command_args = line.split()
            dispatch(command, command_args)
        idle = bool(self.lib.ventilagon_host_is_idle())
        # Repeat this tiny status on presentation so a reconnect cannot lose
        # the game-over state while MicroPython resets its input parser.
        status(b"ventilagon_idle %d\n" % idle)


def handle(args, present, dispatch, status):
    global _engine
    if _engine is None:
        _engine = Ventilagon()
    _engine.handle(args, present, dispatch, status)
