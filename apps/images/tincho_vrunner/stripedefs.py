stripes = [
    palettegroup(
        # personajes:
        strip("tincho_palante.png", frames=6),
        strip("tincho_patras.png", frames=6),

        # túneles:
        strip("suelo.png", frames=1),
        strip("damero.png", frames=2),

        # props:
        strip("props.png", frames=3),

        # fondos, parches, etc:
        strip("centro.png", frames=1),
        fullscreen("negro.png"),
        fullscreen("tincho_pescando.png"),
    )
]
