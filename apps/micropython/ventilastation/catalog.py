"""Game discovery for the launcher.

Games are folders under games/<group>/<name>/ with a code/ directory.
An optional meta.json tunes how a game appears in the menu:

    {
      "title": "Vyruss",        // informational, not rendered yet
      "menu_strip": "...",       // menu.rom strip name; default <group>/<name>/menu.png
      "menu_frames": 2,          // frame count of the menu strip (animated icons)
      "menu_frame": 0,           // frame shown while idle in the menu
      "order": 10,               // menu position, ascending; default 1000
      "hidden": true             // keep the game installed but off the menu
    }

The launcher merges discover_games() with its static (native app / system
scene) entries, so adding a game to the console is just adding its folder:
no launcher edit, no menu yaml edit (tools/generate_roms.py picks the
menu.png up through the game_menu_strips expansion).
"""

try:
    import ujson as json
except ImportError:
    import json

try:
    import uos as os
except ImportError:
    import os

from ventilastation.app_loader import GAMES_ROOT

DEFAULT_ORDER = 1000


def _isdir(path):
    try:
        return bool(os.stat(path)[0] & 0x4000)
    except OSError:
        return False


def _read_meta(path):
    try:
        with open(path) as handle:
            meta = json.load(handle)
        if isinstance(meta, dict):
            return meta
    except (OSError, ValueError):
        pass
    return {}


def discover_game_entries(games_root=None):
    """Return visible games as (order, slug, menu strip name, frame) tuples,
    unsorted; callers merge them with their own entries and sort by order."""
    root = games_root if games_root is not None else GAMES_ROOT
    entries = []
    try:
        groups = sorted(os.listdir(root))
    except OSError:
        return entries

    for group in groups:
        group_path = root + "/" + group
        if not _isdir(group_path):
            continue
        for name in sorted(os.listdir(group_path)):
            game_path = group_path + "/" + name
            if not _isdir(game_path + "/code"):
                continue
            meta = _read_meta(game_path + "/meta.json")
            if meta.get("hidden"):
                continue
            slug = group + "." + name
            strip = meta.get("menu_strip", group + "/" + name + "/menu.png")
            frame = meta.get("menu_frame", 0)
            order = meta.get("order", DEFAULT_ORDER)
            entries.append((order, slug, strip, frame))

    return entries


def build_menu_options(static_entries, games_root=None):
    """Merge static (order, slug, strip, frame) entries (native apps, system
    scenes) with the discovered games and return sorted (slug, strip, frame)
    menu options."""
    entries = list(static_entries) + discover_game_entries(games_root)
    entries.sort()
    return [(slug, strip, frame) for _order, slug, strip, frame in entries]
