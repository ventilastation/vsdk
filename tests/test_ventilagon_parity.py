#!/usr/bin/env python3
"""Parity / regression guard for the Super Ventilagon MicroPython port.

The port (ventilagon_emu.py) must stay faithful to the rotor C it mirrors. Exact RNG
parity with glibc rand() is impossible, so instead we pin the *deterministic* pieces:
the generated data tables, the transformation table's identity block, collision math,
and a headless gameplay smoke run. Run after changing the port or re-extracting data:

    python tests/test_ventilagon_parity.py
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))

from games.alecu.ventilagon_game.code import ventilagon_data as data
from games.alecu.ventilagon_game.code import ventilagon_emu as v


def test_data_tables():
    assert len(data.transformations) == 768, len(data.transformations)
    assert len(data.text_bitmap) == 1536, len(data.text_bitmap)
    # Rotation 0 / no mirror is the identity block: transformations[b] == b for 0..63.
    for b in range(64):
        assert data.transformations[b] == b, (b, data.transformations[b])
    # Every wall row is 6-bit; every pattern is non-empty.
    for name, rows in data.patterns.items():
        assert rows, name
        for r in rows:
            assert 0 <= r < 64, (name, r)
    # Pools reference real patterns; levels reference real pools + drift fns.
    for pool in data.pattern_levels.values():
        for pname in pool:
            assert pname in data.patterns, pname
    assert len(data.levels) == 6


def test_levels_build():
    g = v.Game()
    assert len(g.levels) == 6
    for lv in g.levels:
        assert lv["pool"] and lv["num_patterns"] == len(lv["pool"])
        assert callable(lv["drift"])


def test_collision():
    g = v.Game()
    # Force a known board: a wall bit only in column 0 at ROW_SHIP.
    for n in range(v.NUM_ROWS):
        g.buffer[n] = 0
    g.first_row = 0
    g.buffer[v.ROW_SHIP] = 0b000001  # column 0 only
    g.nave_calibrate = 0
    # pos mapping to column 0 (subdegrees 0..1364) collides; column 1 (1365..) does not.
    assert g.board_colision(0, v.ROW_SHIP) is True
    assert g.board_colision(v.SUBDEGREES // 6 + 10, v.ROW_SHIP) is False


def test_transform_is_permutation():
    # Each 64-entry rotation block must be a permutation of 0..63 (no lost rows).
    t = data.transformations
    for block in range(12):
        base = block * 64
        seen = sorted(t[base : base + 64])
        assert seen == list(range(64)), block


def test_gameplay_smoke():
    random.seed(123)
    g = v.Game()
    g.enter()
    states = []
    for _ in range(4000):
        g.now += 5000
        g.current_state.loop(g.now)
        if not states or states[-1] != g.current_state.name:
            states.append(g.current_state.name)
        frame = g.render_frame()
        assert len(frame) == 256 * v.LED_COUNT * 3
    assert "RUNNING GAME" in states


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print("ventilagon parity: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
