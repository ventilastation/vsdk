"""Game discovery for the launcher.

Games are folders under games/<group>/<name>/ with a code/ directory.
An optional meta.json tunes how a game appears in the menu:

    {
      "title": "Vyruss",        // menu label; default is the folder name,
                                  // prettified (see prettify_name())
      "menu_strip": "...",       // menu.rom strip name; default <group>/<name>/menu.png
      "menu_frames": 2,          // frame count of the menu strip (animated icons)
      "menu_frame": 0,           // frame shown while idle in the menu
      "order": 10,               // menu position, ascending; default 1000
      "hidden": true             // moves the game into the Tech Demos group
                                  // instead of its usual games/<group> one
    }

The launcher merges discover_game_entries()/discover_groups() with its
static (native app / system scene) entries via build_menu_options(), so
adding a game to the console is just adding its folder: no launcher edit, no
menu yaml edit (tools/generate_roms.py picks the menu.png up through the
game_menu_strips expansion). The "demos" folder and any "hidden" game never
join their normal games/<group> listing -- see discover_tech_demo_entries().
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

# games/demos/* never gets its own top-level tile (see discover_groups());
# its games only ever surface through discover_tech_demo_entries().
TECH_DEMOS_FOLDER = "demos"


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


def prettify_name(name):
    """Fallback menu label for a game folder with no explicit meta title."""
    words = [word for word in name.replace("_", " ").replace("-", " ").split() if word]
    return " ".join(word[0].upper() + word[1:] for word in words)


def _game_entry(group_name, name, game_path):
    """Return (meta, (order, slug, strip, frame, title)) for one game
    folder; callers decide whether it belongs in their listing."""
    meta = _read_meta(game_path + "/meta.json")
    slug = group_name + "." + name
    strip = meta.get("menu_strip", group_name + "/" + name + "/menu.png")
    frame = meta.get("menu_frame", 0)
    order = meta.get("order", DEFAULT_ORDER)
    title = meta.get("title") or prettify_name(name)
    return meta, (order, slug, strip, frame, title)


def discover_game_entries(games_root=None, group=None):
    """Return visible games as (order, slug, menu strip name, frame, title)
    tuples, unsorted; callers merge them with their own entries and sort by
    order. Pass group to scope the walk to one games/<group>/ folder --
    otherwise every folder (including "demos") is walked."""
    root = games_root if games_root is not None else GAMES_ROOT
    entries = []
    if group is not None:
        group_names = [group]
    else:
        try:
            group_names = sorted(os.listdir(root))
        except OSError:
            return entries

    for group_name in group_names:
        group_path = root + "/" + group_name
        if not _isdir(group_path):
            continue
        for name in sorted(os.listdir(group_path)):
            game_path = group_path + "/" + name
            if not _isdir(game_path + "/code"):
                continue
            meta, entry = _game_entry(group_name, name, game_path)
            if meta.get("hidden"):
                continue
            entries.append(entry)

    return entries


def discover_groups(games_root=None):
    """Return sorted [(group_name, [(order, slug, strip, frame, title), ...]
    ), ...] for every non-empty games/<group>/ folder except "demos"."""
    root = games_root if games_root is not None else GAMES_ROOT
    try:
        group_names = sorted(os.listdir(root))
    except OSError:
        return []

    groups = []
    for group_name in group_names:
        if group_name == TECH_DEMOS_FOLDER:
            continue
        if not _isdir(root + "/" + group_name):
            continue
        entries = discover_game_entries(root, group=group_name)
        if entries:
            groups.append((group_name, sorted(entries)))
    return groups


def discover_tech_demo_entries(games_root=None):
    """Unfinished games ("hidden": true, from any group) plus every game
    under games/demos/ -- the pool for the launcher's synthetic Tech Demos
    group. Unlike discover_game_entries(), hidden games ARE included here;
    that's what "hidden" now means."""
    root = games_root if games_root is not None else GAMES_ROOT
    entries = []
    try:
        group_names = sorted(os.listdir(root))
    except OSError:
        return entries

    for group_name in group_names:
        group_path = root + "/" + group_name
        if not _isdir(group_path):
            continue
        for name in sorted(os.listdir(group_path)):
            game_path = group_path + "/" + name
            if not _isdir(game_path + "/code"):
                continue
            meta, entry = _game_entry(group_name, name, game_path)
            if group_name != TECH_DEMOS_FOLDER and not meta.get("hidden"):
                continue
            entries.append(entry)

    return entries


def build_menu_options(static_entries, discovered_entries=()):
    """Merge static (order, slug, strip, frame, title) entries with already
    -discovered ones and return sorted (slug, strip, frame, title) menu
    options."""
    entries = list(static_entries) + list(discovered_entries)
    entries.sort()
    return [(slug, strip, frame, title) for _order, slug, strip, frame, title in entries]
