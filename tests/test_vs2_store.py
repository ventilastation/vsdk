"""Tests for ``vs2.store`` -- see docs/vs2-behaviors-proposal.md, "vs2.store".

Every test runs against a throwaway directory containing only a "games"
marker (so Store's project-root detection resolves exactly the way it does
on-device or under the desktop emulator) instead of the real repo checkout,
so nothing here ever writes into the actual working tree.
"""

import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
# Import store.py directly rather than as "vs2.store" -- it is a standalone
# module with no dependency on vs2/__init__.py, and going through the vs2
# package would drag in its director/runtime imports (and their uos/utime
# shims) for no reason a store test needs.
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython", "vs2"))

from ventilastation import api_guard
from store import MAX_BYTES, Store


@contextlib.contextmanager
def _project_dir():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.mkdir(os.path.join(tmp, "games"))
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(old_cwd)


class StoreTests(unittest.TestCase):
    def setUp(self):
        api_guard.reset()

    def tearDown(self):
        api_guard.reset()

    # -- laziness -----------------------------------------------------

    def test_untouched_store_performs_no_filesystem_access(self):
        with _project_dir():
            api_guard.begin_app("games.probe", "vs2")
            with mock.patch("builtins.open", side_effect=AssertionError("open() called")), \
                 mock.patch("os.stat", side_effect=AssertionError("os.stat() called")), \
                 mock.patch("os.mkdir", side_effect=AssertionError("os.mkdir() called")), \
                 mock.patch("os.rename", side_effect=AssertionError("os.rename() called")):
                Store()  # construct and never touch it -- a game that never
                # references vs2.store must trigger none of these.

    # -- failure survival -----------------------------------------------

    def test_corrupt_file_falls_back_to_in_memory_and_keeps_running(self):
        with _project_dir():
            api_guard.begin_app("games.corrupt", "vs2")
            os.mkdir("saves")
            with open("saves/games.corrupt.json", "w") as handle:
                handle.write("{not valid json")

            store = Store()
            self.assertEqual(dict(store.items()), {})  # survives the corrupt read
            store["ok"] = True
            store.save()  # and can still save afterwards

            with open("saves/games.corrupt.json") as handle:
                self.assertEqual(json.load(handle), {"ok": True})

    def test_missing_directory_falls_back_to_in_memory_and_keeps_running(self):
        with _project_dir():
            api_guard.begin_app("games.missingdir", "vs2")
            self.assertFalse(os.path.isdir("saves"))

            store = Store()
            self.assertEqual(len(store), 0)
            self.assertEqual(store.get("hiscore", 0), 0)
            store["hiscore"] = 7  # the game keeps running and can still write

    def test_readonly_filesystem_falls_back_to_in_memory_and_keeps_running(self):
        with _project_dir():
            api_guard.begin_app("games.readonly", "vs2")
            store = Store()
            store["score"] = 10

            real_open = open

            def guarded_open(path, mode="r", *args, **kwargs):
                if any(flag in mode for flag in ("w", "a", "+")):
                    raise OSError(30, "Read-only file system")
                return real_open(path, mode, *args, **kwargs)

            with mock.patch("os.mkdir", side_effect=OSError(30, "Read-only file system")), \
                 mock.patch("builtins.open", side_effect=guarded_open):
                store.save()  # must not raise

            # in-memory store is still fully working, and nothing landed on disk
            self.assertEqual(store["score"], 10)
            store["score"] = 11
            self.assertEqual(store["score"], 11)
            self.assertFalse(os.path.isdir("saves"))

    # -- save() semantics -----------------------------------------------

    def test_save_twice_with_no_change_writes_once(self):
        with _project_dir():
            api_guard.begin_app("games.savetwice", "vs2")
            store = Store()
            store["x"] = 1
            with mock.patch("os.rename", wraps=os.rename) as renamed:
                store.save()
                store.save()
                self.assertEqual(renamed.call_count, 1)

            # a further change makes it dirty again, and that one does write
            store["x"] = 2
            with mock.patch("os.rename", wraps=os.rename) as renamed:
                store.save()
                self.assertEqual(renamed.call_count, 1)

    def test_size_cap_raises_only_from_save(self):
        with _project_dir():
            api_guard.begin_app("games.bigsave", "vs2")
            store = Store()
            store["blob"] = "x" * (MAX_BYTES + 100)  # setting it never raises

            with self.assertRaises(ValueError):
                store.save()

            # the oversized value survives in memory -- save() failing to
            # persist it does not crash or discard it
            self.assertEqual(len(store["blob"]), MAX_BYTES + 100)
            self.assertFalse(os.path.isdir("saves"))

    # -- round-tripping ---------------------------------------------------

    def test_round_trips_a_nested_document(self):
        with _project_dir():
            api_guard.begin_app("games.roundtrip", "vs2")
            document = {
                "hiscore": 42,
                "name": "ace",
                "song": {"tempo": 120, "notes": [1, 2, 3], "loop": True},
                "flags": [True, False, None],
            }
            store = Store()
            for key, value in document.items():
                store[key] = value
            store.save()

            reloaded = Store()  # fresh instance -- forces a real disk read
            self.assertEqual(dict(reloaded.items()), document)

    # -- naming and scoping -----------------------------------------------

    def test_path_comes_from_app_slug_and_rebinds_on_app_switch(self):
        with _project_dir():
            api_guard.begin_app("alecu.vixeous", "vs2")
            store = Store()
            store["hiscore"] = 1
            store.save()

            api_guard.begin_app("alecu.other", "vs2")
            self.assertEqual(len(store), 0)  # rebound to the other app's own, empty store
            store["hiscore"] = 2
            store.save()

            self.assertTrue(os.path.isfile("saves/alecu.vixeous.json"))
            self.assertTrue(os.path.isfile("saves/alecu.other.json"))
            with open("saves/alecu.vixeous.json") as handle:
                self.assertEqual(json.load(handle), {"hiscore": 1})
            with open("saves/alecu.other.json") as handle:
                self.assertEqual(json.load(handle), {"hiscore": 2})

    def test_writes_nothing_inside_games_directory(self):
        with _project_dir() as tmp:
            api_guard.begin_app("games.nogames", "vs2")
            store = Store()
            store["x"] = 1
            store.save()

            games_dir = os.path.join(tmp, "games")
            written = [
                os.path.join(root, name)
                for root, _dirs, files in os.walk(games_dir)
                for name in files
            ]
            self.assertEqual(written, [])
            self.assertTrue(os.path.isfile(os.path.join(tmp, "saves", "games.nogames.json")))

    def test_no_active_app_stays_in_memory_and_save_is_a_safe_no_op(self):
        with _project_dir():
            self.assertIsNone(api_guard.current_app())
            store = Store()
            store["x"] = 1  # never raises even with nothing to name the file after
            store.save()  # a safe no-op -- nothing to write against
            self.assertFalse(os.path.isdir("saves"))
            self.assertEqual(store["x"], 1)


if __name__ == "__main__":
    unittest.main()
