#!/usr/bin/env python3
"""games/demos/povstress has no menu.png at all (the only game in the whole
catalog missing one) -- a diagnostic/hazard-stripe badge fits its job better
than a generic wordmark frame. Uses make_menu_icons.py's badge() helper."""

from pathlib import Path

from make_menu_icons import badge

OUTPUT = Path(__file__).resolve().parents[4] / "games" / "demos" / "povstress" / "menu.png"


def main():
    image = badge(
        text="STRESS", card_fill=(22, 16, 2, 210), card_outline=(180, 150, 10, 255),
        glow_rgb=(255, 210, 30), text_top=(255, 245, 190), text_bottom=(220, 170, 10),
        outline_rgb=(35, 26, 4), accent_rgb=(255, 210, 30), max_text_width=58,
    )
    image.save(OUTPUT)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
