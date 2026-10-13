"""Exercise real presentation/command code without opening a window or audio."""
import ast
import importlib.util
from pathlib import Path
import sys
import shutil
import socket
import subprocess
import tempfile
import time
import traceback
import types
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'emulator'))
sys.path.insert(0, str(ROOT / 'apps/micropython'))
from build_ventilagon import build
from ventilastation.input_parser import InputParser
import ventilagon_native


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HostIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.engine = ventilagon_native.Ventilagon(build(output_dir=cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_desktop_raw_frame_survives_update_and_clears_on_exit(self):
        import povrender
        frames, audio, status = [], [], []
        tree = ast.parse((ROOT / 'emulator/comms.py').read_text())
        dispatch = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'dispatch_command')
        namespace = {name: getattr(povrender, name) for name in (
            'set_voom_frame_rgb', 'clear_voom_frame', 'clear_vs2_scene', 'set_spritedata')}
        namespace.update(send=status.append, arduino_send=lambda line: audio.append(('arduino', line)),
            traceback=traceback,
            playsound=lambda line: audio.append(('sound', line)),
            playmusic=lambda name, *args: audio.append(('music', name)))
        exec(compile(ast.Module(body=[dispatch], type_ignores=[]), str(ROOT/'emulator/comms.py'), 'exec'), namespace)
        class Conn:
            def read(self, length):
                self_test.assertEqual(length, 500)
                return b'\0\0\0\xff\xff' * 100
        self_test = self
        connection = Conn()
        saved_engine = ventilagon_native._engine
        saved_modules = {name: sys.modules.get(name) for name in ('ventilastation.director', 'uctypes', 'urandom')}
        def send(line, data=b''):
            frames.append(line)
            command, *args = line.split()
            namespace['dispatch_command'](connection, command, args)
        fake_comms = types.SimpleNamespace(send=send, was_new_connection=lambda: False)
        sys.modules['ventilastation.director'] = types.SimpleNamespace(comms=fake_comms)
        sys.modules['uctypes'] = types.SimpleNamespace()
        sys.modules['urandom'] = types.SimpleNamespace(randrange=lambda n: 0)
        ventilagon_native._engine = self.engine
        try:
            display = load_file('ventilagon_remote', ROOT/'apps/micropython/ventilastation/remotepov.py')
            send(b'ventilagon enter 123')
            send(b'ventilagon tick 30000 2')
            expected = povrender._voom_frame_rgb
            self.assertIsNotNone(expected)
            self.assertTrue(any(expected))
            display.prepare_frame(types.SimpleNamespace(raw_frame=True))
            display.update()
            self.assertEqual(povrender._voom_frame_rgb, expected)
            self.assertNotIn(b'sprites', frames)
            self.assertIn(('music', b'off'), audio)
            self.assertIn(b'ventilagon_idle 0\n', status)
            send(b'ventilagon exit')
            display.prepare_frame(types.SimpleNamespace())
            display.update()
            self.assertIsNone(povrender._voom_frame_rgb)
            self.assertEqual(frames[-1], b'sprites')
        finally:
            ventilagon_native._engine = saved_engine
            for name, module in saved_modules.items():
                if module is None: sys.modules.pop(name, None)
                else: sys.modules[name] = module

    def test_idle_status_does_not_consume_input_or_queue_control_commands(self):
        parser = InputParser()
        for chunk in (b'*\x03', b'\x20\x01ventila', b'gon_idle 1\nexit\n'):
            parser.feed(chunk)
        self.assertEqual((parser.joy1, parser.joy2, parser.extra), (3, 32, 1))
        self.assertTrue(parser.ventilagon_idle)
        self.assertEqual(parser.pop_command(), 'exit')
        self.assertIsNone(parser.pop_command())
        parser.feed(b'ventilagon_idle 0\n')
        self.assertFalse(parser.ventilagon_idle)
        parser.feed(b'ventilagon_idle 1\n')
        parser.reset()
        self.assertFalse(parser.ventilagon_idle)
        parser.feed(b'ventilagon_error missing C library\n')
        self.assertEqual(parser.ventilagon_error, 'missing C library')
        self.assertIsNone(parser.pop_command())
        parser.reset()
        self.assertIsNone(parser.ventilagon_error)

    @unittest.skipUnless(shutil.which('micropython'), 'desktop MicroPython not installed')
    def test_real_desktop_scene_and_native_host_over_tcp(self):
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        # Give this child an isolated port without changing the production API.
        source = '''
import sys, usocket, utime
sys.path.insert(0, '../..')
_lookup = usocket.getaddrinfo
def lookup(host, port):
    return _lookup('127.0.0.1', %d if port == 5005 else port)
class SocketProxy:
    getaddrinfo = staticmethod(lookup)
    def __getattr__(self, name):
        return getattr(usocket, name)
sys.modules['usocket'] = SocketProxy()
sys.modules['socket'] = sys.modules['usocket']
from ventilastation.director import configure_runtime, director, comms
runtime = configure_runtime('desktop')
while runtime.platform.comms.conn is None:
    comms.receive(1)
    utime.sleep_ms(5)
from games.alecu.ventilagon_game.code.ventilagon_game import VentilagonIdle
director.push(VentilagonIdle())
for n in range(150):
    director.step_once()
    utime.sleep_ms(30)
'''
        child = subprocess.Popen([shutil.which('micropython'), '-X', 'heapsize=8m', '-c', source % port],
            cwd=ROOT/'apps/micropython', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        conn = stream = None
        try:
            until = time.monotonic() + 5
            while conn is None:
                try:
                    conn = socket.create_connection(('127.0.0.1', port), timeout=3)
                except ConnectionRefusedError:
                    if child.poll() is not None:
                        self.fail(child.stdout.read().decode())
                    if time.monotonic() >= until:
                        self.fail('desktop MicroPython did not listen')
                    time.sleep(0.02)
            stream = conn.makefile('rb')
            entered = exited = False
            ticks = 0
            buttons = []
            pixels, lines = [], []
            for _ in range(2000):
                line = stream.readline()
                self.assertTrue(line, 'desktop scene terminated unexpectedly')
                command, *args = line.split()
                if command == b'palette': stream.read(int(args[0]) * 1024)
                elif command == b'imagestrip': stream.read(int(args[1]))
                elif command == b'ventilagon':
                    self.engine.handle(args, pixels.append,
                        lambda cmd, cmd_args: lines.append((cmd, cmd_args)), conn.sendall)
                    if args[0] == b'enter': entered = True
                    if args[0] == b'exit': exited = True
                    if args[0] == b'tick':
                        ticks += 1
                        buttons.append(int(args[2]))
                        if ticks == 1: conn.sendall(bytes((42, 2, 0, 0)))
                        if ticks == 10: conn.sendall(bytes((42, 0, 0, 1)))
                elif command == b'sprites':
                    stream.read(500)
                    if not entered: conn.sendall(bytes((42, 16, 0, 0)))
                    else:
                        self.assertTrue(exited, 'legacy sprites overwrote the active game')
                        break
            self.assertTrue(entered and exited)
            # Exit input crosses an asynchronous TCP connection. Linux can
            # deliver it after another presentation frame (e.g. delayed ACKs),
            # so require a prompt exit without assuming same-frame delivery.
            self.assertGreaterEqual(ticks, 10)
            self.assertLessEqual(ticks, 12)
            self.assertIn(2, buttons, 'right input never reached the native game')
            self.assertEqual(len(pixels), ticks)
            self.assertEqual(len(pixels[-1]), 256 * 54 * 3)
            self.assertTrue(any(pixels[-1]))
            self.assertIn((b'arduino', [b'stop']), lines)
        finally:
            if stream: stream.close()
            if conn: conn.close()
            child.terminate()
            child.communicate(timeout=5)

    def test_invalid_or_out_of_lifecycle_native_commands_surface(self):
        self.engine.handle([b'exit'], lambda _: None, lambda *_: None, lambda _: None)
        for args in ([b'tick', b'30000', b'0'], [b'tick', b'-1', b'0'], [b'unknown']):
            with self.assertRaises((RuntimeError, ValueError)):
                self.engine.handle(args, lambda _: None, lambda *_: None, lambda _: None)

    def test_host_errors_become_scene_errors(self):
        from ventilastation import ventilagon_host
        saved = ventilagon_host.get_platform
        ventilagon_host.get_platform = lambda: types.SimpleNamespace(
            comms=types.SimpleNamespace(ventilagon_error=lambda: 'missing C library'))
        try:
            with self.assertRaisesRegex(RuntimeError, 'Native Ventilagon: missing C library'):
                ventilagon_host.tick()
        finally:
            ventilagon_host.get_platform = saved


if __name__ == '__main__':
    unittest.main()
