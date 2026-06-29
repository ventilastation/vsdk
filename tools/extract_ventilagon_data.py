#!/usr/bin/env python3
"""Generate ventilagon_data.py from the on-hardware C source (the source of truth).

Super Ventilagon ships twice: as C on the spinning rotor
(hardware/rotor/modules/povdisplay/ventilagon/) and as a MicroPython port that runs
in the desktop + web emulators (ventilastation/ventilagon_emu.py). The bulky, easy-to-
mistype data tables (bit-pattern levels, the precomputed rotation table, the credits
font) must stay byte-identical between the two. Rather than hand-copy them, this script
parses the C and emits ventilagon_data.py, so the C remains the single source of truth.

Run it whenever the C data tables change:

    python tools/extract_ventilagon_data.py

The game *logic* (drift calculators, section timing/sounds, state machine) is small and
readable, so it is hand-ported in ventilagon_emu.py rather than extracted here.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
C_DIR = os.path.join(ROOT, "hardware", "rotor", "modules", "povdisplay", "ventilagon")
OUT = os.path.join(ROOT, "apps", "micropython", "ventilastation", "ventilagon_data.py")


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def read(name):
    with open(os.path.join(C_DIR, name), "r") as f:
        return strip_comments(f.read())


def parse_byte_token(tok):
    tok = tok.strip()
    if tok.startswith("0b"):
        return int(tok[2:], 2)
    if tok.startswith("0x"):
        return int(tok[2:], 16)
    return int(tok)


def parse_byte_array(text, name):
    """Return the list of byte values from `const byte <name>[] = { ... };`."""
    m = re.search(r"const\s+byte\s+%s\s*\[\s*\]\s*=\s*\{([^}]*)\}" % re.escape(name), text)
    if not m:
        raise ValueError("byte array %r not found" % name)
    body = m.group(1)
    return [parse_byte_token(t) for t in body.split(",") if t.strip()]


def parse_patterns(levels_c):
    """Return {pattern_name: [rows...]} parsed from `PATTERN <name>[] = { count, rows };`.

    The C stores the row count as the first element; the emulator computes len() instead,
    so we drop it and keep exactly `count` rows (matching pattern_randomize/next_row).
    """
    patterns = {}
    for m in re.finditer(r"PATTERN\s+(\w+)\s*\[\s*\]\s*=\s*\{([^}]*)\}", levels_c):
        name = m.group(1)
        vals = [parse_byte_token(t) for t in m.group(2).split(",") if t.strip()]
        count = vals[0]
        rows = vals[1 : 1 + count]
        if len(rows) != count:
            raise ValueError("pattern %s: declared %d rows, found %d" % (name, count, len(rows)))
        patterns[name] = rows
    return patterns


def parse_pattern_levels(levels_c):
    """Return {patterns_levelN: [pattern_name, ...]} (ordered)."""
    result = {}
    for m in re.finditer(
        r"const\s+byte\s*\*\s*const\s+(\w+)\s*\[\s*\]\s*=\s*\{([^}]*)\}", levels_c
    ):
        name = m.group(1)
        members = [t.strip() for t in m.group(2).split(",") if t.strip()]
        result[name] = members
    return result


def parse_levels(levels_c):
    """Return ordered list of level dicts from the `const Level levelN = {...};` lines."""
    levels = []
    for m in re.finditer(r"const\s+Level\s+(\w+)\s*=\s*\{([^}]*)\}", levels_c):
        fields = [f.strip() for f in m.group(2).split(",")]
        # step_delay, block_height, rotation_speed, song, color, bg1, bg2,
        # patterns_list, elements_in(...), &drift
        song = fields[3].strip().strip('"')
        levels.append(
            {
                "name": m.group(1),
                "step_delay": int(fields[0]),
                "block_height": int(fields[1]),
                "rotation_speed": int(fields[2]),
                "song": song,
                "color": int(fields[4], 16),
                "bg1": int(fields[5], 16),
                "bg2": int(fields[6], 16),
                "patterns": fields[7].strip(),
                "drift": fields[9].lstrip("&").strip(),
            }
        )
    return levels


def parse_level_order(levels_c):
    """Return the ordered list of level names from `const Level* const levels[] = {...}`."""
    m = re.search(r"const\s+Level\s*\*\s*const\s+levels\s*\[\s*\]\s*=\s*\{([^}]*)\}", levels_c)
    members = [t.strip().lstrip("&") for t in m.group(1).split(",")]
    return [x for x in members if x and x != "NULL"]


def fmt_bytes(values):
    return "bytes([\n" + _wrap(values) + "\n])"


def _wrap(values, per_line=12):
    lines = []
    for i in range(0, len(values), per_line):
        chunk = values[i : i + per_line]
        lines.append("    " + ", ".join(str(v) for v in chunk) + ",")
    return "\n".join(lines)


def main():
    transformations_c = read("transformations.c")
    text_bitmap_c = read("text_bitmap.c")
    levels_c = read("levels.c")

    transformations = parse_byte_array(transformations_c, "transformations")
    text_bitmap = parse_byte_array(text_bitmap_c, "text_bitmap")

    if len(transformations) != 768:
        raise ValueError("transformations: expected 768 bytes, got %d" % len(transformations))
    if len(text_bitmap) != 1536:
        raise ValueError("text_bitmap: expected 1536 bytes, got %d" % len(text_bitmap))

    patterns = parse_patterns(levels_c)
    pattern_levels = parse_pattern_levels(levels_c)
    levels = parse_levels(levels_c)
    level_order = parse_level_order(levels_c)

    out = []
    out.append('"""Super Ventilagon data tables.')
    out.append("")
    out.append("GENERATED by tools/extract_ventilagon_data.py from the rotor C source")
    out.append("(hardware/rotor/modules/povdisplay/ventilagon/). Do not edit by hand;")
    out.append("re-run the extractor so the emulator port stays in sync with the firmware.")
    out.append('"""')
    out.append("")
    out.append("# Precomputed row transformations: 12 rotations/mirrors x 64 row values.")
    out.append("transformations = " + fmt_bytes(transformations))
    out.append("")
    out.append("# Credits scroller font: 256 glyphs x 6 columns, one bit per pixel.")
    out.append("text_bitmap = " + fmt_bytes(text_bitmap))
    out.append("")
    out.append("# Each pattern is a list of 6-bit wall rows (the leading C count is dropped).")
    out.append("patterns = {")
    for name in sorted(patterns):
        rows = patterns[name]
        out.append("    %r: [%s]," % (name, ", ".join("0b" + format(r, "06b") for r in rows)))
    out.append("}")
    out.append("")
    out.append("# Ordered pattern pools selected per level.")
    out.append("pattern_levels = {")
    for name, members in pattern_levels.items():
        out.append("    %r: [%s]," % (name, ", ".join(repr(x) for x in members)))
    out.append("}")
    out.append("")
    out.append("# Levels in play order. Colors are 0xRRGGBBAA (alpha ignored by the emulator).")
    out.append("levels = [")
    by_name = {lv["name"]: lv for lv in levels}
    for lname in level_order:
        lv = by_name[lname]
        out.append("    {")
        out.append("        'name': %r," % lv["name"])
        out.append("        'step_delay': %d," % lv["step_delay"])
        out.append("        'block_height': %d," % lv["block_height"])
        out.append("        'rotation_speed': %d," % lv["rotation_speed"])
        out.append("        'song': %r," % lv["song"])
        out.append("        'color': 0x%08x," % lv["color"])
        out.append("        'bg1': 0x%08x," % lv["bg1"])
        out.append("        'bg2': 0x%08x," % lv["bg2"])
        out.append("        'patterns': %r," % lv["patterns"])
        out.append("        'drift': %r," % lv["drift"])
        out.append("    },")
    out.append("]")
    out.append("")

    with open(OUT, "w") as f:
        f.write("\n".join(out))

    print("wrote %s" % os.path.relpath(OUT, ROOT))
    print(
        "  %d transformations, %d font bytes, %d patterns, %d pools, %d levels"
        % (len(transformations), len(text_bitmap), len(patterns), len(pattern_levels), len(levels))
    )


if __name__ == "__main__":
    sys.exit(main())
