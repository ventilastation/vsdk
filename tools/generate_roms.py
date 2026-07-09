import os
import sys
import struct
import yaml

from pathlib import Path
from itertools import zip_longest, chain
from numpy import sin, cos, pi, ndarray, array, uint8
from PIL import Image, ImageChops

TRANSPARENT = (255, 0, 255)
ROOT_DIR = Path(__file__).resolve().parent.parent
GAMES_ROOT = ROOT_DIR / "games"
SYSTEM_ROOT = ROOT_DIR / "system"
ROMS_FOLDER = ROOT_DIR / "apps" / "micropython" / "roms"
SEARCH_ROOTS = (GAMES_ROOT, SYSTEM_ROOT)

os.makedirs(ROMS_FOLDER, exist_ok=True)

def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

"""Reproject a *.png into polar form: for each of n_ang angles, the RGBI
sequence of the n_led LEDs along that ray."""
def reproject(image, n_led=54, n_ang=256):
    src = array(image)
    dst = ndarray((n_led, n_ang, 4), uint8)

    wx, wy, dim = src.shape

    center_x = int((wx-1)/2)
    center_y = int((wy-1)/2)
    rad = min(center_x, center_y)   # radius the image sweeps inside the frame

    for m in range(0,n_ang):
        for n in range(0,n_led):
            x = center_x + int(rad * (n+1)/n_led * cos(m * 2*pi/n_ang)) 
            y = center_y + int(rad * (n+1)/n_led * sin(m * 2*pi/n_ang))
            dst[n, m] = src[x,y,0:4]

    return Image.fromarray(dst)


#vugo [[
# ('moregrass.png', {'frames': 4}), 
# ('monchito_runs.png', {'frames': 4}), 
# ('obstacles.png', {'frames': 2}), 
# ('bushes.png', {'frames': 4}), 
# ('nube8bit.png', {'frames': 1}), 
# ('bluesky.png', {'frames': 1, 'radius': 54, 'process': 'reproject'})]]


def _relative_to(path, root):
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def rom_name_for_folder(folder):
    games = _relative_to(folder, GAMES_ROOT)
    if games is not None and len(games.parts) >= 2 and games.parts[-1] == "images":
        return ".".join(games.parts[:-1])

    system = _relative_to(folder, SYSTEM_ROOT)
    if system is not None and len(system.parts) >= 2 and system.parts[-1] == "images":
        return system.parts[-2]

    return folder.parts[-1]


def generate_rom(folder, palettegroups, spritedef_path):
    rom_name = rom_name_for_folder(folder)
    rom_filename = Path(ROMS_FOLDER) / (rom_name + ".rom")
    rom_timestamp = rom_filename.stat().st_mtime if rom_filename.exists() else 0
    src_filenames = (folder / filename for group in palettegroups for filename, _ in group)

    if all(f.stat().st_mtime <= rom_timestamp for f in chain(src_filenames,[spritedef_path])):
        # print("Skipping", rom_name, file=sys.stderr)
        return
    print("Generating", rom_name, file=sys.stderr)

    rom_strips = []
    palettes = []
    attributes = {}

    for palnumber, group in enumerate(palettegroups):
        images = {}
        images_opts = {}

        for filename, file_opts in group:
            image = Image.open(folder / filename).convert("RGBA")
            if file_opts.get("process") == "reproject":
                print("    Reprojecting", filename, file=sys.stderr)
                image = reproject(image, n_led=file_opts["radius"])
            images[filename] = image
            images_opts[filename] = file_opts

        workspace_size = (
            max(i.width for i in images.values()),
            sum(i.height for i in images.values())
        )

        workspace = Image.new("RGBA", workspace_size, (0,0,0,255))

        y = 0
        for fn, i in images.items():
            workspace.alpha_composite(i, (0, y))
            y += i.height
            opts = images_opts[fn]
            frames = opts["frames"]
            if frames > 255:
                frames = 255
            width = i.width // frames
            attributes[fn] = (width, i.height, frames, palnumber)

        def fill_palette(palette):
            """If less that 256 colors, fill up to 255 with black + 1 magenta."""
            black = [0,0,0]
            magenta = [255,0,255]
            entries_missing = (765-len(palette))//3 
            return palette + entries_missing * black + magenta

        workspace_paletted = workspace.convert("RGB").quantize(dither=0, colors=255)
        palette = workspace_paletted.getpalette()

        full_palette = fill_palette(palette)


        pal_raw = []
        for r, g, b in grouper(full_palette, 3):
            quad = bytearray((255, b, g, r))
            pal_raw.append(quad)


        palettes.append(b"".join(pal_raw))

        y = 0
        for fn, i in images.items():
            print("    Processing", fn, file=sys.stderr)
            bitmask = ImageChops.invert(i.getchannel(3).convert("1"))
            i_paletted = workspace_paletted.crop((0, y, i.width, y + i.height))
            y += i.height
            i_paletted.paste(255, mask=bitmask)

            b = i_paletted.transpose(Image.ROTATE_270).tobytes()
            filename = images_opts[fn].get("id", fn.rsplit("/", 1)[-1])
            frames, palette = attributes[fn][2:4]
            width = i.width // frames
            if width > 255:
                width = 255
            attrs = (width, i.height, frames, palette)
            attrbytes = bytes(attrs)

            var_name = filename.rsplit(".", 1)[0].replace(".", "_") + "_data"
            if var_name.startswith("0") or var_name.startswith("1"):
                var_name = "_" + var_name

            fnb = filename.encode("utf-8")
            pascal_filename = struct.pack("B", len(fnb)) + fnb
            rom_strips.append(pascal_filename + attrbytes + b)
        
    with open(rom_filename, "wb") as rom:
        offset = 4 + len(rom_strips) * 4 + len(palettes) * 4
        rom.write(struct.pack("<HH", len(rom_strips), len(palettes)))

        for strip in rom_strips:
            rom.write(struct.pack("<L", offset))
            offset += len(strip)
        for palette in palettes:
            rom.write(struct.pack("<L", offset))
            offset += len(palette)
            
        for strip in rom_strips:
            rom.write(strip)

        for palette in palettes:
            rom.write(palette)



STRIPEDEF_FILENAME = "__images__.yaml"

def _game_menu_strip_items(spritedef_path):
    """Expand a `game_menu_strips: true` item into one strip per
    games/<group>/<name>/menu.png, so the menu ROM no longer needs a
    hand-maintained list. Strip ids match ventilastation/catalog.py's
    default menu_strip; frame counts come from each game's meta.json
    ("menu_frames", default 1)."""
    import json

    items = []
    images_dir = spritedef_path.parent
    for menu_png in sorted(GAMES_ROOT.glob("*/*/menu.png")):
        game_dir = menu_png.parent
        frames = 1
        meta_path = game_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                frames = int(meta.get("menu_frames", 1))
            except (ValueError, TypeError) as error:
                raise ValueError(f"{meta_path}: {error}")
        relative = os.path.relpath(menu_png, images_dir)
        strip_id = menu_png.relative_to(GAMES_ROOT).as_posix()
        items.append((relative, {"frames": frames, "id": strip_id}))
    return items

def _normalize_item(item, source_path, palettegroup_index, item_index):
    if not isinstance(item, dict):
        raise ValueError(
            f"{source_path}: palette group {palettegroup_index} item {item_index} must be a mapping"
        )

    inline_kinds = [kind for kind in ("strip", "fullscreen") if kind in item]
    if len(inline_kinds) != 1:
        raise ValueError(
            f"{source_path}: palette group {palettegroup_index} item {item_index} "
            "must define exactly one of 'strip' or 'fullscreen'"
        )

    item_type = inline_kinds[0]
    filename = item.get(item_type)
    if not isinstance(filename, str) or not filename:
        raise ValueError(
            f"{source_path}: palette group {palettegroup_index} item {item_index} needs a non-empty {item_type} filename"
        )

    frames = item.get("frames", 1)
    if not isinstance(frames, int) or frames < 1:
        raise ValueError(
            f"{source_path}: palette group {palettegroup_index} item {item_index} has invalid frames {frames!r}"
        )

    options = {"frames": frames}
    if "id" in item:
        strip_id = item.get("id")
        if not isinstance(strip_id, str) or not strip_id:
            raise ValueError(
                f"{source_path}: palette group {palettegroup_index} item {item_index} has invalid id {strip_id!r}"
            )
        options["id"] = strip_id
    if item_type == "fullscreen":
        radius = item.get("radius", 54)
        if not isinstance(radius, int) or radius < 1:
            raise ValueError(
                f"{source_path}: palette group {palettegroup_index} item {item_index} has invalid radius {radius!r}"
            )
        options["radius"] = radius
        options["process"] = "reproject"

    return filename, options

def load_palettegroups(spritedef_path):
    data = yaml.safe_load(spritedef_path.read_text()) or {}
    palettegroup_defs = data.get("palettegroups")

    if palettegroup_defs is None:
        palettegroup_defs = data.get("stripes")

    if isinstance(palettegroup_defs, dict):
        group_entries = list(palettegroup_defs.items())
    elif isinstance(palettegroup_defs, list):
        group_entries = [
            (f"palette{palettegroup_index + 1}", group)
            for palettegroup_index, group in enumerate(palettegroup_defs)
        ]
    else:
        raise ValueError(
            f"{spritedef_path}: top-level 'palettegroups' must be a mapping "
            "or legacy 'stripes' must be a list"
        )

    palettegroups = []
    for palettegroup_index, (group_name, group) in enumerate(group_entries):
        if not isinstance(group, list):
            raise ValueError(
                f"{spritedef_path}: palette group {group_name!r} must be a list"
            )
        normalized_group = []
        for item_index, item in enumerate(group):
            if isinstance(item, dict) and item.get("game_menu_strips"):
                normalized_group.extend(_game_menu_strip_items(spritedef_path))
                continue
            normalized_group.append(
                _normalize_item(item, spritedef_path, group_name, item_index)
            )
        palettegroups.append(normalized_group)
    return palettegroups

for search_root in SEARCH_ROOTS:
    if not search_root.exists():
        continue
    for root, dirs, files in search_root.walk(on_error=print):
        if STRIPEDEF_FILENAME in files:
            spritedef_path = root / STRIPEDEF_FILENAME
            palettegroups = load_palettegroups(spritedef_path)
            generate_rom(root, palettegroups, spritedef_path)
