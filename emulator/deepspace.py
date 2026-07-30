EMPTY_PIXELS = 16
PIXELS = 54
ROWS = 256 - EMPTY_PIXELS
GAMMA = 0.28

empty = [PIXELS] * EMPTY_PIXELS
deepspace = empty + [
    int(PIXELS * pow(float(n) / ROWS, 1/GAMMA) + 0.5)
    for n in range(ROWS-1, -1, -1)
]

# VS2 uses the whole 0..255 depth range, with Y=0 exactly on the outermost
# LED and increasing Y moving inward. The legacy table above stays untouched
# for V1 games and the starfield.
vs2_deepspace = [
    int((PIXELS - 1) * pow(float(255 - y) / 255, 1/GAMMA) + 0.5)
    for y in range(256)
]
# print(deepspace)
