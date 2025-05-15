stripes = [
    palettegroup(
        strip("moregrass.png", frames=4),
        strip("monchito_runs.png", frames=4),
        strip("obstacles.png", frames=2),
        strip("bushes.png", frames=4),
        strip("nube8bit.png", frames=1),
        fullscreen("bluesky.png"),
    )
]

stripes = [
    palettegroup(
        strip("disparo.png", frames=2),
        strip("explosion.png", frames=5),
        strip("explosion_nave.png", frames=4),
        strip("galaga.png", frames=12),
        strip("ll9.png", frames=4),
        strip("gameover.png"),
        strip("numerals.png", frames=12),
    ),
    palettegroup(
        fullscreen("tierra.png", radius=25),
    ),
    palettegroup(
        fullscreen("marte.png", radius=25),
    ),
    palettegroup(
        fullscreen("jupiter.png", radius=25),
    ),
    palettegroup(
        fullscreen("saturno.png", radius=50),
    ),
]