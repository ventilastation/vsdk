# Sprite ROMs from the older generators

Real records written before the strip header stored width and frame count
minus one (docs/internals/rom-format.md). `tests/test_romformat.py` and
`tests/test_menurom.py` load them to check that ROMs already on consoles --
game packages installed before the change -- keep loading with the right
sizes and pixels. Never regenerate these: their point is that a current
generator can't produce them.

| File | Where its records come from |
|---|---|
| `preglyph.rom` | The ROMs in `web/runtime-bundle.json` at commit 350e897, built before strips carried a glyph trailer (most records have none). |
| `preswitch.rom` | `tools/generate_roms.py` as of a8204a1, the last commit before "Store strip width and frame count minus one". |
| `preswitch-menu-icon.rom` | The same generator's `generate_menu_icon_rom()` for `games/demos/tutorial_game`: a game package's `menu-icon.rom`. |

`preglyph.rom` and `preswitch.rom` each gather one strip of every kind the
old encoding could hold: a genuinely 255-wide image and a full-circle one
(both width byte 255), a 256-glyph font clamped to frames byte 255 next to
a real 255-frame strip, a sheet with leftover columns, a glyph table and a
plain strip. Each record is copied byte for byte from its source ROM with
its palette; only the record's palette index byte is changed, to point at
that palette's copy.

`expected.json` lists each strip's true width, height and frame count (from
its source PNG and `__images__.yaml`), its glyph table, and the SHA-256 of
its pixel data. When the fixtures were made, the `preswitch.rom` pixels were
byte-identical to what the current generator writes for the same images.
