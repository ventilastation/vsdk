stripes = [
    palettegroup(
        fullscreen("game-center0.png", radius=32),
        fullscreen("game-center1.png", radius=24),
        fullscreen("game-center2.png", radius=16),

    ),
    palettegroup(
        strip("ship-sprite-sheet.png", frames = 6*2),
        strip("ship-sprite-gray.png", frames = 2),
    ),
    palettegroup(
        strip("driller-sheet.png", frames=7*2),
        strip("chiller-sheet.png", frames=6*2),
        strip("bully-sheet.png", frames=5*2),
        strip("spiraler-sheet.png", frames=8*2),
    ),
    palettegroup(
        strip("bala.png", frames=4),
    ),
    palettegroup(
        strip("explosion.png", frames=6),
    ),
    palettegroup(
        strip("numerals.png", frames=12),
    ),
    palettegroup(
        strip("charset.png", frames=256),
        strip("tesrahc.png", frames=256)
    ),
]
