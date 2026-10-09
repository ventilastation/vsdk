"""tools/generate_web_runtime_bundle.py: what the web emulator's manifest and
bundle hold, and that a build with nothing changed rewrites nothing."""

import base64
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "generate_web_runtime_bundle_under_test", ROOT / "tools" / "generate_web_runtime_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTree:
    """A small repo laid out like vsdk, with the builder pointed at it and
    the ROM generator replaced by a stand-in that needs no numpy."""

    def __init__(self, use_git=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.builder = load_builder()
        self.builder.ROOT_DIR = self.root
        self.builder.MANIFEST_PATH = self.root / "web" / "runtime-manifest.json"
        self.builder.BUNDLE_PATH = self.root / "web" / "runtime-bundle.json"
        self.builder.ROMS_DIR = self.root / "apps" / "micropython" / "roms"
        self.rom_runs = 0
        games_root = self.root / "games"

        def generate_all():
            self.rom_runs += 1

        def rom_name_for_folder(folder):
            return ".".join(folder.relative_to(games_root).parts[:-1])

        fake_generate_roms = types.SimpleNamespace(generate_all=generate_all, rom_name_for_folder=rom_name_for_folder)
        self.builder.load_generate_roms = lambda: fake_generate_roms

        self.write(".gitignore", "*.mp3.wav\napps/micropython/roms/*.rom\nweb/runtime-*.json\n")
        self.write("web/index.html", "<!doctype html>\n")
        self.write("apps/micropython/main.py", "print('main')\n")
        self.write("apps/micropython/ventilastation/director.py", "director = 1\n")
        self.write("apps/micropython/roms/README.md", "generated ROMs land here\n")
        self.write("apps/micropython/roms/grp.game.rom", b"ROM-v1")
        self.write("apps/micropython/roms/grp.gone.rom", b"left behind by a deleted game")
        self.write("games/grp/game/meta.json", '{"title": "Game"}\n')
        self.write("games/grp/game/menu.png", b"\x89PNG menu")
        self.write("games/grp/game/code/game.py", "SPEED = 1\n")
        self.write("games/grp/game/code/songs/song.json", '{"notes": []}\n')
        self.write("games/grp/game/code/README.md", "notes for humans\n")
        self.write("games/grp/game/images/__images__.yaml", "palettegroups: {}\n")
        self.write("games/grp/game/images/ship.png", b"\x89PNG ship")
        self.write("games/grp/game/images/src/make_ship.py", "import PIL\n")
        self.write("games/grp/game/sounds/boom.mp3", b"ID3 boom")
        self.write("games/grp/game/sounds/boom.mp3.wav", b"RIFF decoded cache")
        self.write("system/menu/meta.json", "{}\n")
        self.write("system/menu/code/menu.py", "MENU = 1\n")
        if use_git:
            self.git("init", "-q")
            self.git("add", "-A")

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def manifest(self):
        return json.loads(self.builder.MANIFEST_PATH.read_text())

    def bundle(self):
        entries = json.loads(self.builder.BUNDLE_PATH.read_text())["files"]
        return {entry["path"]: base64.b64decode(entry["base64"]) for entry in entries}

    def cleanup(self):
        self.tmp.cleanup()


@unittest.skipUnless(shutil.which("git"), "needs git")
class ContentsTests(unittest.TestCase):
    def setUp(self):
        self.tree = FakeTree()
        self.assertTrue(self.tree.builder.build())

    def tearDown(self):
        self.tree.cleanup()

    def test_manifest_lists_runtime_files_roms_and_assets(self):
        self.assertEqual(self.tree.manifest()["files"], [
            "apps/micropython/main.py",
            "apps/micropython/ventilastation/director.py",
            "games/grp/game/code/game.py",
            "games/grp/game/code/songs/song.json",
            "games/grp/game/meta.json",
            "system/menu/code/menu.py",
            "system/menu/meta.json",
            "apps/micropython/roms/grp.game.rom",
            "games/grp/game/images/__images__.yaml",
            "games/grp/game/images/ship.png",
            "games/grp/game/menu.png",
            "games/grp/game/sounds/boom.mp3",
        ])

    def test_bundle_holds_what_the_worker_mounts(self):
        bundle = self.tree.bundle()
        self.assertEqual(bundle["games/grp/game/code/game.py"], b"SPEED = 1\n")
        self.assertEqual(bundle["apps/micropython/roms/grp.game.rom"], b"ROM-v1")
        self.assertIn("games/grp/game/code/songs/song.json", bundle)
        # Images and sounds are listed in the manifest and fetched on demand.
        for path in bundle:
            self.assertFalse(path.endswith((".png", ".yaml", ".mp3")), path)

    def test_ignored_files_and_orphan_roms_are_left_out(self):
        files = self.tree.manifest()["files"]
        self.assertNotIn("games/grp/game/sounds/boom.mp3.wav", files)
        self.assertNotIn("apps/micropython/roms/grp.gone.rom", files)
        self.assertNotIn("apps/micropython/roms/README.md", files)
        self.assertNotIn("games/grp/game/images/src/make_ship.py", files)
        self.assertNotIn("games/grp/game/code/README.md", files)

    def test_roms_are_brought_up_to_date_first(self):
        self.assertEqual(self.tree.rom_runs, 1)

    def test_a_new_uncommitted_game_is_included(self):
        self.tree.write("games/grp/new/code/new.py", "NEW = 1\n")
        self.tree.write("games/grp/new/meta.json", "{}\n")
        self.assertTrue(self.tree.builder.build())
        self.assertIn("games/grp/new/code/new.py", self.tree.bundle())

    def test_a_deleted_file_disappears(self):
        (self.tree.root / "games/grp/game/code/songs/song.json").unlink()
        self.assertTrue(self.tree.builder.build())
        self.assertNotIn("games/grp/game/code/songs/song.json", self.tree.manifest()["files"])


@unittest.skipUnless(shutil.which("git"), "needs git")
class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.tree = FakeTree()
        self.builder = self.tree.builder
        self.assertTrue(self.builder.build())

    def tearDown(self):
        self.tree.cleanup()

    def test_nothing_changed_rewrites_nothing(self):
        before = self.builder.BUNDLE_PATH.stat().st_mtime_ns
        self.assertFalse(self.builder.build())
        self.assertEqual(self.builder.BUNDLE_PATH.stat().st_mtime_ns, before)
        # The ROM step still runs: it has its own check.
        self.assertEqual(self.tree.rom_runs, 2)

    def test_touching_a_file_without_changing_it_rewrites_nothing(self):
        os.utime(self.tree.root / "games/grp/game/code/game.py")
        self.assertFalse(self.builder.build())

    def test_an_edit_is_picked_up(self):
        self.tree.write("games/grp/game/code/game.py", "SPEED = 2\n")
        self.assertTrue(self.builder.build())
        self.assertEqual(self.tree.bundle()["games/grp/game/code/game.py"], b"SPEED = 2\n")

    def test_a_rebuilt_rom_is_picked_up(self):
        self.tree.write("apps/micropython/roms/grp.game.rom", b"ROM-v2")
        self.assertTrue(self.builder.build())
        self.assertEqual(self.tree.bundle()["apps/micropython/roms/grp.game.rom"], b"ROM-v2")

    def test_a_new_image_only_changes_the_manifest(self):
        self.tree.write("games/grp/game/images/enemy.png", b"\x89PNG enemy")
        self.assertTrue(self.builder.build())
        self.assertIn("games/grp/game/images/enemy.png", self.tree.manifest()["files"])

    def test_a_missing_bundle_is_rebuilt(self):
        self.builder.BUNDLE_PATH.unlink()
        self.assertTrue(self.builder.build())
        self.assertTrue(self.builder.BUNDLE_PATH.is_file())

    def test_force_rewrites(self):
        self.assertTrue(self.builder.build(force=True))

    def test_no_temporary_files_are_left(self):
        self.tree.write("games/grp/game/code/game.py", "SPEED = 3\n")
        self.builder.build()
        self.assertEqual(sorted(p.name for p in (self.tree.root / "web").iterdir()),
                         ["index.html", "runtime-bundle.json", "runtime-manifest.json"])


class WithoutGitTests(unittest.TestCase):
    def test_falls_back_to_the_tree_minus_known_leftovers(self):
        tree = FakeTree(use_git=False)
        try:
            tree.builder.build()
            files = tree.manifest()["files"]
            self.assertIn("games/grp/game/code/game.py", files)
            self.assertIn("apps/micropython/roms/grp.game.rom", files)
            self.assertNotIn("games/grp/game/sounds/boom.mp3.wav", files)
        finally:
            tree.cleanup()


class MissingDependenciesTests(unittest.TestCase):
    def test_a_rom_generator_that_cannot_import_raises_missing_dependencies(self):
        builder = load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            builder.TOOLS_DIR = pathlib.Path(tmp)
            (builder.TOOLS_DIR / "generate_roms.py").write_text("import numpy_that_is_not_installed\n")
            saved = sys.modules.pop("generate_roms", None)
            try:
                with self.assertRaises(builder.MissingDependencies) as caught:
                    builder.generate_roms()
                self.assertIn("pip install -r requirements.txt", str(caught.exception))
                self.assertNotIn("generate_roms", sys.modules)
            finally:
                if saved is not None:
                    sys.modules["generate_roms"] = saved


if __name__ == "__main__":
    unittest.main()
