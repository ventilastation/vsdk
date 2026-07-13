import builtins
import io
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))


class _FakeFS:
    """Minimal in-memory stand-in for the one file boot.py touches."""

    def __init__(self, files=None):
        self.files = dict(files or {})

    def stat(self, path):
        if path not in self.files:
            raise OSError("no such file")
        return (0,) * 10

    def open(self, path, mode):
        buf = io.StringIO()
        fs = self

        class _Writer:
            def __enter__(self):
                return buf

            def __exit__(self, *exc):
                fs.files[path] = buf.getvalue()
                return False

        return _Writer()


def _install_fakes(main_py_exists):
    fs = _FakeFS({"main.py": "# real app"} if main_py_exists else {})

    uos = types.ModuleType("uos")
    uos.stat = fs.stat
    sys.modules["uos"] = uos

    return fs


class BootStubTests(unittest.TestCase):
    def setUp(self):
        for name in ("uos", "boot"):
            sys.modules.pop(name, None)
        self._real_open = builtins.open

    def tearDown(self):
        for name in ("uos", "boot"):
            sys.modules.pop(name, None)
        builtins.open = self._real_open

    def _patch_open(self, fs):
        builtins.open = fs.open

    def test_writes_stub_main_py_when_none_exists(self):
        fs = _install_fakes(main_py_exists=False)
        self._patch_open(fs)

        import boot  # noqa: F401

        self.assertIn("main.py", fs.files)
        self.assertIn("vsdk_recovery", fs.files["main.py"])
        self.assertIn("vsdk_recovery.run()", fs.files["main.py"])

    def test_leaves_existing_main_py_untouched(self):
        fs = _install_fakes(main_py_exists=True)
        self._patch_open(fs)

        import boot  # noqa: F401

        self.assertEqual(fs.files["main.py"], "# real app")


if __name__ == "__main__":
    unittest.main()
