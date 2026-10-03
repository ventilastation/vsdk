"""tools/stamp_web_versions.py: publishing writes one cache-busting version
into every module URL of the published copy."""

import importlib.util
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("stamp_web_versions", ROOT / "tools" / "stamp_web_versions.py")
stamp_web_versions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stamp_web_versions)

ANY_VERSION = re.compile(r"\?v=([^\"'`)\s]+)")


class RealSourcesTests(unittest.TestCase):
    """Stamping a copy of the real web/ pages and modules, so a renamed
    constant or a new kind of ?v= fails here rather than at deploy time."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)
        for path in (ROOT / "web").iterdir():
            if path.is_file() and path.suffix in stamp_web_versions.STAMPED_SUFFIXES:
                shutil.copy(path, self.out / path.name)
        self.version = stamp_web_versions.stamp(self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_literal_version_is_the_build_version(self):
        found = set()
        for path in self.out.iterdir():
            for value in ANY_VERSION.findall(path.read_text(encoding="utf-8")):
                if not value.startswith("${"):
                    found.add(value)
        self.assertEqual(found, {self.version})

    def test_interpolated_versions_come_from_stamped_constants(self):
        for path in self.out.iterdir():
            text = path.read_text(encoding="utf-8")
            for name in stamp_web_versions.INTERPOLATED_VERSION.findall(text):
                self.assertIn('const %s = "%s";' % (name, self.version), "\n".join(
                    p.read_text(encoding="utf-8") for p in self.out.iterdir()))

    def test_web_itself_is_untouched(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn(self.version, source)


class StampTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)
        (self.out / "index.html").write_text('<script src="./app.js?v=20260101a"></script>\n')
        (self.out / "app.js").write_text(
            'import "./util.js?v=1";\n'
            + "".join('const %s = "old";\n' % name for name in stamp_web_versions.VERSION_CONSTANTS)
            + "const url = `./worker.js?v=${WORKER_SCRIPT_VERSION}`;\n")
        (self.out / "vendor").mkdir()
        (self.out / "vendor" / "lib.js").write_text('load("./x.js?v=upstream");\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_versions_follow_the_published_content(self):
        first = stamp_web_versions.stamp(self.out)
        self.assertIn("./app.js?v=%s" % first, (self.out / "index.html").read_text())
        app = (self.out / "app.js").read_text()
        self.assertIn("./util.js?v=%s" % first, app)
        self.assertIn('const WORKER_SCRIPT_VERSION = "%s";' % first, app)
        self.assertIn("${WORKER_SCRIPT_VERSION}", app)
        (self.out / "util.js").write_text("export const changed = true;\n")
        self.assertNotEqual(stamp_web_versions.stamp(self.out), first)

    def test_vendor_files_keep_their_own_versions(self):
        stamp_web_versions.stamp(self.out)
        self.assertIn("?v=upstream", (self.out / "vendor" / "lib.js").read_text())

    def test_an_unknown_interpolated_constant_fails(self):
        with open(self.out / "app.js", "a") as app:
            app.write("const other = `./x.js?v=${SOME_NEW_VERSION}`;\n")
        with self.assertRaises(SystemExit):
            stamp_web_versions.stamp(self.out)

    def test_a_missing_constant_fails(self):
        (self.out / "app.js").write_text('import "./util.js?v=1";\n')
        with self.assertRaises(SystemExit):
            stamp_web_versions.stamp(self.out)

    def test_refuses_to_stamp_the_source_tree(self):
        with self.assertRaises(SystemExit):
            stamp_web_versions.main([str(ROOT / "web")])


if __name__ == "__main__":
    unittest.main()
