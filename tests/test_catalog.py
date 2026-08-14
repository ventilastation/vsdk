import os
import pathlib
import sys
import tempfile
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "micropython"))

# catalog.py pulls in app_loader -> director, whose production runtime uses
# MicroPython's uos/utime modules. Supply their small compatible surface for
# this CPython unit test (mirrors tests/test_native_apps.py).
sys.modules.setdefault("uos", os)
if "utime" not in sys.modules:
    utime = types.ModuleType("utime")
    utime.ticks_ms = lambda: int(time.monotonic() * 1000)
    utime.ticks_add = lambda value, delta: value + delta
    utime.ticks_diff = lambda value, other: value - other
    utime.sleep_ms = lambda value: time.sleep(value / 1000)
    sys.modules["utime"] = utime

from ventilastation import catalog


def _make_game(root, group, name, meta=None, code=True):
    game_dir = pathlib.Path(root) / group / name
    if code:
        (game_dir / "code").mkdir(parents=True)
    else:
        game_dir.mkdir(parents=True)
    if meta is not None:
        import json
        (game_dir / "meta.json").write_text(json.dumps(meta))


class DiscoverGameEntriesTests(unittest.TestCase):
    def test_scopes_to_one_group_and_skips_hidden(self):
        with tempfile.TemporaryDirectory() as root:
            _make_game(root, "alecu", "vyruss", {"order": 10, "title": "Vyruss"})
            _make_game(root, "alecu", "wip", {"hidden": True})
            _make_game(root, "other", "aaa", {"order": 5})

            entries = catalog.discover_game_entries(root, group="alecu")

        self.assertEqual(entries, [(10, "alecu.vyruss", "alecu/vyruss/menu.png", 0, "Vyruss")])

    def test_default_title_is_prettified_from_the_folder_name(self):
        with tempfile.TemporaryDirectory() as root:
            _make_game(root, "other", "villalugano_games", {})

            entries = catalog.discover_game_entries(root, group="other")

        self.assertEqual(entries[0][4], "Villalugano Games")

    def test_ignores_folders_without_a_code_directory(self):
        with tempfile.TemporaryDirectory() as root:
            _make_game(root, "alecu", "vyruss", {"order": 1})
            _make_game(root, "alecu", "not_a_game", meta=None, code=False)

            entries = catalog.discover_game_entries(root, group="alecu")

        self.assertEqual([slug for _o, slug, _s, _f, _t in entries], ["alecu.vyruss"])


class DiscoverGroupsTests(unittest.TestCase):
    def test_excludes_the_demos_folder_and_empty_groups(self):
        with tempfile.TemporaryDirectory() as root:
            _make_game(root, "alecu", "vyruss", {"order": 1})
            _make_game(root, "demos", "input_demo", {})
            _make_game(root, "other", "wip", {"hidden": True})

            groups = catalog.discover_groups(root)

        self.assertEqual([name for name, _entries in groups], ["alecu"])

    def test_group_entries_are_sorted_by_order(self):
        with tempfile.TemporaryDirectory() as root:
            _make_game(root, "alecu", "second", {"order": 20})
            _make_game(root, "alecu", "first", {"order": 10})

            groups = dict(catalog.discover_groups(root))

        self.assertEqual([slug for _o, slug, _s, _f, _t in groups["alecu"]],
                          ["alecu.first", "alecu.second"])


class DiscoverTechDemoEntriesTests(unittest.TestCase):
    def test_includes_hidden_games_from_any_group_and_all_of_demos(self):
        with tempfile.TemporaryDirectory() as root:
            _make_game(root, "alecu", "vyruss", {"order": 1})
            _make_game(root, "alecu", "wip", {"hidden": True, "title": "WIP"})
            _make_game(root, "demos", "input_demo", {"title": "Input Demo"})
            _make_game(root, "demos", "povstress", {"hidden": True, "title": "POV Stress"})

            entries = catalog.discover_tech_demo_entries(root)

        self.assertEqual(sorted(slug for _o, slug, _s, _f, _t in entries), [
            "alecu.wip", "demos.input_demo", "demos.povstress",
        ])

    def test_does_not_include_non_hidden_games_outside_demos(self):
        with tempfile.TemporaryDirectory() as root:
            _make_game(root, "alecu", "vyruss", {"order": 1})

            entries = catalog.discover_tech_demo_entries(root)

        self.assertEqual(entries, [])


class BuildMenuOptionsTests(unittest.TestCase):
    def test_merges_and_sorts_by_order_then_drops_it(self):
        static_entries = [(2, "tutorial_vs2", "menu.png", 10, "Tutorial")]
        discovered = [(1, "group:emulators", "menu.png", 0, "Emulators")]

        options = catalog.build_menu_options(static_entries, discovered)

        self.assertEqual(options, [
            ("group:emulators", "menu.png", 0, "Emulators"),
            ("tutorial_vs2", "menu.png", 10, "Tutorial"),
        ])


if __name__ == "__main__":
    unittest.main()
