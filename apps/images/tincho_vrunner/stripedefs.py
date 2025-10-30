stripes = [
    palettegroup(
        # personajes:
        strip("tincho_palante.png", frames=4),
        strip("tincho_patras.png", frames=4),

        # túneles:
        strip("suelo.png", frames=1),
        strip("damero.png", frames=2),
        strip("suelo_dof.png", frames=3),

        # fondos, parches, etc:
        strip("centro.png", frames=1),
        fullscreen("negro.png"),
        fullscreen("tincho_pescando.png"),
    )
]
