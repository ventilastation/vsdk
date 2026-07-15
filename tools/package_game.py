#!/usr/bin/env python3
"""Build a distributable Ventilastation game package (.vs2).

Usage:
    python3 tools/package_game.py alecu/vyruss_vs2 [--output dist/]

Accepts <group>/<name>, <group>.<name>, or a path to the game directory.

A .vs2 package is a zip holding everything a game needs anywhere:

    meta.json                  launcher manifest (unchanged schema)
    menu.png                   menu icon source (editor/gallery display)
    code/**.py                 MicroPython sources (entry: code/<name>.py)
    roms/<group>.<name>.rom    compiled sprite rom -- the single source of
                               truth for images; no PNG sources travel
    menu-icon.rom              one-strip rom (icon + palette) merged into
                               the board's menu rom at install time
    sounds/*.mp3               played by the base; stripped before the
                               board (see emulator/package_manager.py)

mp3 members are STOREd (they're already compressed), everything else
deflates. Timestamps are pinned so repackaging an unchanged game is
byte-identical.
"""

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_roms
from generate_roms import GAMES_ROOT

# Any timestamp works as long as it is constant; zip can't store pre-1980.
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)


def resolve_game_dir(game):
    candidate = Path(game)
    if candidate.is_dir() and (candidate / "code").is_dir():
        return candidate.resolve()
    slug_parts = game.replace(".", "/").strip("/").split("/")
    if len(slug_parts) == 3 and slug_parts[0] == "games":
        slug_parts = slug_parts[1:]
    if len(slug_parts) != 2:
        raise SystemExit("expected <group>/<name>, got: %s" % game)
    game_dir = GAMES_ROOT / slug_parts[0] / slug_parts[1]
    if not (game_dir / "code").is_dir():
        raise SystemExit("not a game directory (no code/): %s" % game_dir)
    return game_dir


def _add_member(archive, arcname, data, compress_type=zipfile.ZIP_DEFLATED):
    info = zipfile.ZipInfo(arcname, date_time=_ZIP_DATE_TIME)
    info.compress_type = compress_type
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def build_package(game_dir, output_dir):
    game_dir = Path(game_dir)
    group, name = game_dir.parts[-2:]
    slug = "%s.%s" % (group, name)
    meta_path = game_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    package_path = output_dir / (slug + ".vs2")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        rom_path = None
        spritedef = game_dir / "images" / generate_roms.STRIPEDEF_FILENAME
        if spritedef.exists():
            rom_path = tmp / (slug + ".rom")
            palettegroups = generate_roms.load_palettegroups(spritedef)
            generate_roms.generate_rom(
                spritedef.parent, palettegroups, spritedef, rom_filename=rom_path)

        # A meta.json "menu_strip" override points at a strip that already
        # exists in the system menu rom; shipping an icon rom under that id
        # would clobber it at merge time, so only self-named icons travel.
        icon_path = None
        if (game_dir / "menu.png").exists() and "menu_strip" not in meta:
            icon_path = tmp / "menu-icon.rom"
            generate_roms.generate_menu_icon_rom(game_dir, icon_path)

        with zipfile.ZipFile(package_path, "w") as archive:
            _add_member(archive, "meta.json",
                        meta_path.read_bytes() if meta_path.exists() else b"{}")
            if (game_dir / "menu.png").exists():
                _add_member(archive, "menu.png", (game_dir / "menu.png").read_bytes())
            for source in sorted((game_dir / "code").rglob("*.py")):
                if "__pycache__" in source.parts:
                    continue
                arcname = "code/" + source.relative_to(game_dir / "code").as_posix()
                _add_member(archive, arcname, source.read_bytes())
            if rom_path is not None:
                _add_member(archive, "roms/" + rom_path.name, rom_path.read_bytes())
            if icon_path is not None:
                _add_member(archive, "menu-icon.rom", icon_path.read_bytes())
            sounds_dir = game_dir / "sounds"
            if sounds_dir.is_dir():
                for sound in sorted(sounds_dir.glob("*.mp3")):
                    _add_member(archive, "sounds/" + sound.name,
                                sound.read_bytes(), zipfile.ZIP_STORED)

    return package_path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("game", help="<group>/<name>, <group>.<name>, or a game directory")
    parser.add_argument("--output", default="dist", help="output directory (default: dist/)")
    args = parser.parse_args()

    package_path = build_package(resolve_game_dir(args.game), args.output)
    print(package_path)


if __name__ == "__main__":
    main()
