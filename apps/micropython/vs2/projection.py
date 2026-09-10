"""vs2.projection — projection curves: depth <-> LED row.

A projection is a 256-entry table mapping a world-space depth (0..255) to
the LED row it should be drawn on. This module builds those tables and
inverts them; it holds no hardware state and imports nothing else in the
repo, so the desktop emulator and the browser renderer can import it
directly, exactly like device code does.

    vs2.HUD          # identity: Y is already an LED index, 0..255
    vs2.VS1_TUNNEL    # the historical curve: tunnel(gamma=0.28)
    vs2.TUNNEL        # alias for VS1_TUNNEL

    vs2.tunnel(gamma=0.28, near=0, far=53)

``FULLSCREEN`` is a rendering mode, not a curve, and does not live here.

Building a curve calls ``pow()`` 256 times — cheap once, not free in a
hot loop. Build it once (e.g. store it on a layer) and reuse the table.
"""

ROWS = 256


def tunnel(gamma=0.28, near=0, far=53):
    """Build a 256-entry ``bytes`` LUT mapping depth to LED row.

    Row ``y`` (the table index, 0..255) is read as the depth fraction::

        depth = (255 - y) / 255

    so index 0 is the farthest sample and index 255 is the nearest. The
    fraction is warped by ``gamma`` and interpolated between ``near`` and
    ``far``::

        table[y] = near + (far - near) * depth ** (1 / gamma)

    truncated the same way the historical table was: add 0.5, then
    truncate — round-half-up on values that are never negative.

    ``gamma`` controls curvature: ``0.28`` (the V1 value) crowds most of
    the world into the outer rows, a deep, foreshortened tunnel; ``1.0``
    spreads depth evenly, a flat plane seen edge-on.

    ``near``/``far`` choose which LED rows the depth range lands on.
    ``near=0, far=26`` occupies only the inner half of a 53-row bar;
    ``near > far`` (e.g. ``near=53, far=0``) is legal and inverts the
    curve's direction — it stays monotonic, just decreasing instead of
    increasing.

    ``tunnel(gamma=0.28)`` (the defaults: ``near=0, far=53``) reproduces
    ``vs2_deepspace`` from ``calculate_deepspace()`` in
    ``hardware/rotor/modules/povdisplay/gpu.c`` byte for byte; that
    specific table is exported below as ``VS1_TUNNEL``.
    """
    exponent = 1.0 / gamma
    span = far - near
    last = ROWS - 1
    table = bytearray(ROWS)
    for y in range(ROWS):
        depth = float(last - y) / last
        value = near + span * pow(depth, exponent) + 0.5
        # near/far are documented to stay within 0..255 (a curve is a
        # uint8_t[256]); clamp defensively so a stray call can't wrap
        # instead of silently corrupting a display row.
        if value < 0:
            value = 0
        elif value > 255:
            value = 255
        table[y] = int(value)
    return bytes(table)


def _identity():
    return bytes(range(ROWS))


#: The historical V1 curve. Must stay byte-identical to gpu.c's
#: ``vs2_deepspace`` so every existing game keeps rendering pixel-identical.
VS1_TUNNEL = tunnel(gamma=0.28)

#: Alias — pre-VS2 code (and the name in general use) just says ``TUNNEL``.
TUNNEL = VS1_TUNNEL

#: Y is already an LED index: HUD layers project straight through.
HUD = _identity()


def to_depth(row, curve=VS1_TUNNEL):
    """Invert a curve: given an LED row, return the world depth (0..255)
    that projects onto it.

    ``curve`` must be monotonic, which every curve ``tunnel()`` builds is
    (weakly — rounding can repeat a value across a few rows). Binary
    search over the 256-entry table, so this is O(log 256) regardless of
    how ``row`` sits in range; a ``row`` outside the curve's span clamps
    to the nearest end.

    Ties — several depths rounding to the same row — resolve to the first
    depth (in table order) that reaches ``row``, i.e. the near edge, in
    table order, of that row's span.
    """
    lo, hi = 0, len(curve) - 1
    increasing = curve[lo] <= curve[hi]
    while lo < hi:
        mid = (lo + hi) // 2
        reached = curve[mid] >= row if increasing else curve[mid] <= row
        if reached:
            hi = mid
        else:
            lo = mid + 1
    return lo
