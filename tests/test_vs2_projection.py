"""Tests for vs2.projection.

projection.py is deliberately standalone: no dependency on vs2/__init__.py
(which needs `utime`/MicroPython shims to import) or on any other vs2
module, since the desktop and browser renderers import it directly. So this
test loads it by file path rather than as `vs2.projection`, to prove that
independence rather than assume it.
"""

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


projection = _load_module(
    "vs2_projection_standalone",
    ROOT / "apps" / "micropython" / "vs2" / "projection.py",
)

# The reference table this module must reproduce byte for byte. Ported
# straight from calculate_deepspace() in
# hardware/rotor/modules/povdisplay/gpu.c; also available pre-ported at
# emulator/deepspace.py (a namespace package under ROOT, importable with no
# __init__.py) as `vs2_deepspace`. Compute it independently here too, so the
# test doesn't just compare projection.py against a second copy of itself.
_PIXELS = 54
_GAMMA = 0.28
REFERENCE_VS2_DEEPSPACE = [
    int((_PIXELS - 1) * pow(float(255 - y) / 255, 1 / _GAMMA) + 0.5)
    for y in range(256)
]


def _is_monotonic(curve):
    non_decreasing = all(curve[i] <= curve[i + 1] for i in range(len(curve) - 1))
    non_increasing = all(curve[i] >= curve[i + 1] for i in range(len(curve) - 1))
    return non_decreasing or non_increasing


class ByteIdentityTests(unittest.TestCase):
    """The check that keeps every existing game pixel-identical."""

    def test_vs1_tunnel_matches_hand_ported_reference(self):
        self.assertEqual(bytes(REFERENCE_VS2_DEEPSPACE), bytes(projection.VS1_TUNNEL))

    def test_vs1_tunnel_matches_emulator_deepspace_module(self):
        from emulator.deepspace import vs2_deepspace

        self.assertEqual(len(vs2_deepspace), 256)
        self.assertEqual(bytes(vs2_deepspace), bytes(projection.VS1_TUNNEL))

    def test_vs1_tunnel_is_tunnel_default_gamma(self):
        # Same construction the module uses, called fresh here to prove
        # VS1_TUNNEL wasn't hand-tweaked after being built.
        self.assertEqual(bytes(projection.tunnel(gamma=0.28)), bytes(projection.VS1_TUNNEL))

    def test_tunnel_alias_is_vs1_tunnel(self):
        self.assertEqual(projection.TUNNEL, projection.VS1_TUNNEL)


class CurveShapeTests(unittest.TestCase):
    def test_curve_is_256_bytes(self):
        self.assertIs(type(projection.VS1_TUNNEL), bytes)
        self.assertEqual(len(projection.VS1_TUNNEL), 256)

    def test_hud_is_256_bytes(self):
        self.assertIs(type(projection.HUD), bytes)
        self.assertEqual(len(projection.HUD), 256)

    def test_tunnel_builds_256_bytes_for_arbitrary_params(self):
        curve = projection.tunnel(gamma=0.5, near=3, far=200)
        self.assertIs(type(curve), bytes)
        self.assertEqual(len(curve), 256)

    def test_hud_is_identity_curve(self):
        self.assertEqual(bytes(projection.HUD), bytes(range(256)))


class MonotonicityTests(unittest.TestCase):
    def test_vs1_tunnel_is_monotonic(self):
        self.assertTrue(_is_monotonic(projection.VS1_TUNNEL))

    def test_family_is_monotonic_across_params(self):
        cases = [
            dict(gamma=0.28, near=0, far=53),
            dict(gamma=1.0, near=0, far=53),
            dict(gamma=0.28, near=0, far=26),
            dict(gamma=0.05, near=0, far=53),
            dict(gamma=2.5, near=0, far=53),
            dict(gamma=0.5, near=10, far=200),
            dict(gamma=2.0, near=255, far=0),
            dict(gamma=0.28, near=53, far=53),  # near == far: constant, trivially monotonic
        ]
        for kwargs in cases:
            curve = projection.tunnel(**kwargs)
            self.assertTrue(_is_monotonic(curve), f"not monotonic for {kwargs}")

    def test_near_greater_than_far_inverts_direction(self):
        forward = projection.tunnel(gamma=0.28, near=0, far=53)
        inverted = projection.tunnel(gamma=0.28, near=53, far=0)

        # Forward: outer row (index 0) is the deep end (high value), and it
        # decreases toward the near end (index 255).
        self.assertEqual(forward[0], 53)
        self.assertEqual(forward[255], 0)
        self.assertTrue(all(forward[i] >= forward[i + 1] for i in range(255)))

        # Inverted: near/far swapped flips the direction end to end, while
        # staying monotonic (now non-decreasing instead of non-increasing).
        self.assertEqual(inverted[0], 0)
        self.assertEqual(inverted[255], 53)
        self.assertTrue(all(inverted[i] <= inverted[i + 1] for i in range(255)))

    def test_gamma_one_is_a_flat_linear_ramp(self):
        curve = projection.tunnel(gamma=1.0, near=0, far=255)
        # depth = (255 - y) / 255, value = 255 * depth -> value == 255 - y
        for y in (0, 1, 64, 128, 200, 255):
            self.assertEqual(curve[y], 255 - y)


class InverseTests(unittest.TestCase):
    def test_to_depth_round_trips_through_vs1_tunnel(self):
        curve = projection.VS1_TUNNEL
        for row in range(0, 54):
            depth = projection.to_depth(row, curve)
            self.assertEqual(
                curve[depth], row,
                f"to_depth({row}) -> {depth}, but curve[{depth}] = {curve[depth]}",
            )

    def test_to_depth_round_trips_through_inverted_curve(self):
        curve = projection.tunnel(gamma=0.28, near=53, far=0)
        for row in range(0, 54):
            depth = projection.to_depth(row, curve)
            self.assertEqual(curve[depth], row)

    def test_to_depth_on_identity_curve_is_identity(self):
        for row in (0, 1, 100, 254, 255):
            self.assertEqual(projection.to_depth(row, projection.HUD), row)

    def test_to_depth_defaults_to_vs1_tunnel(self):
        self.assertEqual(
            projection.to_depth(26),
            projection.to_depth(26, projection.VS1_TUNNEL),
        )

    def test_to_depth_clamps_out_of_range_rows(self):
        curve = projection.VS1_TUNNEL  # values span 0..53 only, decreasing
        # A row above the curve's max clamps to the near/outer edge (index 0).
        self.assertEqual(projection.to_depth(999, curve), 0)
        # A row below the curve's min clamps to the opposite (far) edge.
        self.assertEqual(projection.to_depth(-999, curve), 255)

    def test_to_depth_ties_resolve_to_first_match_in_table_order(self):
        # VS1_TUNNEL's tail is a long run of zeros (rounding flattens the
        # curve near the inner rim); to_depth(0) must return the first
        # (outermost) index in that run, not just any of them.
        curve = projection.VS1_TUNNEL
        first_zero = next(i for i, v in enumerate(curve) if v == 0)
        self.assertEqual(projection.to_depth(0, curve), first_zero)


class PortabilityTests(unittest.TestCase):
    """projection.py must be importable with no other vs2 module and no
    hardware/MicroPython-only shims, since desktop and browser renderers
    import it directly."""

    def test_module_has_no_vs2_package_imports(self):
        source = (ROOT / "apps" / "micropython" / "vs2" / "projection.py").read_text()
        for line in source.splitlines():
            stripped = line.strip()
            self.assertFalse(
                stripped.startswith("import vs2") or stripped.startswith("from vs2"),
                f"projection.py must not import from the vs2 package: {stripped!r}",
            )
            self.assertFalse(
                stripped.startswith("import utime") or stripped.startswith("import uos"),
                f"projection.py must not need MicroPython-only shims: {stripped!r}",
            )


if __name__ == "__main__":
    unittest.main()
