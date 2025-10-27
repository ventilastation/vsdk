stripes = [
    palettegroup(
        # personajes:
        strip("vvv.png", frames=1),

        # túneles:
        strip("suelo.png", frames=1),
        strip("damero.png", frames=2),
        strip("suelo_dof.png", frames=3),

        # fondos, parches, etc:
        strip("centro.png", frames=1),
        fullscreen("negro.png"),
        fullscreen("full.png"),
    )
]
