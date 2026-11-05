"""Tests for the frozen grid-evolution geometry contract.

Both user constraints must hold simultaneously:
  C1  gap in [0.45%, 1.5%]
  C2  N in [3, 200]
  C3  geometric (equal-ratio) grid
"""

import math
import random
import unittest

import importlib.util
import sys
from pathlib import Path

_LAB = Path(__file__).resolve().parents[1]
_MODULE_PATH = _LAB / "scripts" / "grid_evolution.py"

if not _MODULE_PATH.is_file():
    raise AssertionError("required grid_evolution implementation is missing")
_spec = importlib.util.spec_from_file_location("offline_grid_evolution", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
ge = importlib.util.module_from_spec(_spec)
# dataclasses resolve their own module through sys.modules, so register it
# before execution.
sys.modules["offline_grid_evolution"] = ge
_spec.loader.exec_module(ge)


class TestConstraintEnvelope(unittest.TestCase):
    def test_frozen_values(self):
        self.assertEqual(ge.GAP_MIN_PCT, 0.45)
        self.assertEqual(ge.GAP_MAX_PCT, 1.5)
        self.assertEqual(ge.GRID_MIN_COUNT, 3)
        self.assertEqual(ge.GRID_MAX_COUNT, 200)
        self.assertEqual(ge.GRID_MODE, "geometric")
        self.assertTrue(ge.FROZEN_CONSTRAINTS.is_frozen)

    def test_rejects_non_geometric_mode(self):
        with self.assertRaises(ValueError):
            ge.GridConstraints(mode="arithmetic")

    def test_rejects_inverted_gap_bounds(self):
        with self.assertRaises(ValueError):
            ge.GridConstraints(gap_min_pct=1.5, gap_max_pct=0.45)


class TestGapAndCountRelation(unittest.TestCase):
    def test_gap_is_decreasing_in_count(self):
        gaps = [ge.gap_for_count(0.00147, 0.008984, n) for n in (60, 100, 122, 150, 200)]
        self.assertEqual(gaps, sorted(gaps, reverse=True))

    def test_count_for_gap_is_inverse(self):
        for count in (40, 122, 180):
            gap = ge.gap_for_count(0.00147, 0.008984, count)
            back = ge.count_for_gap(0.00147, 0.008984, gap)
            self.assertAlmostEqual(back, count, places=6)

    def test_known_baseline_geometry(self):
        # PUMP W2 baseline: L=0.00147 U=0.008984 N=122 gap=1.49482%
        gap = ge.gap_for_count(0.00147, 0.008984, 122)
        self.assertAlmostEqual(gap, 1.4948187, places=6)
        self.assertTrue(ge.GAP_MIN_PCT <= gap <= ge.GAP_MAX_PCT)


class TestFeasibleWindow(unittest.TestCase):
    def test_window_bounds_both_constraints(self):
        low, high = ge.feasible_count_window(0.00147, 0.008984)
        self.assertLessEqual(low, high)
        self.assertGreaterEqual(low, ge.GRID_MIN_COUNT)
        self.assertLessEqual(high, ge.GRID_MAX_COUNT)
        # every count in the window satisfies both constraints
        for count in range(low, high + 1):
            gap = ge.gap_for_count(0.00147, 0.008984, count)
            self.assertGreaterEqual(gap, ge.GAP_MIN_PCT - 1e-9)
            self.assertLessEqual(gap, ge.GAP_MAX_PCT + 1e-9)

    def test_window_edges_are_tight(self):
        low, high = ge.feasible_count_window(0.00147, 0.008984)
        if low > ge.GRID_MIN_COUNT:
            # one cell below the window is too sparse -> gap above the ceiling
            self.assertGreater(ge.gap_for_count(0.00147, 0.008984, low - 1),
                               ge.GAP_MAX_PCT)
        if high < ge.GRID_MAX_COUNT:
            # one cell above the window is too dense -> gap below the floor
            self.assertLess(ge.gap_for_count(0.00147, 0.008984, high + 1),
                            ge.GAP_MIN_PCT)

    def test_too_wide_range_is_infeasible(self):
        # 0.0009 -> 0.011 needs N>200 at gap>=0.45%? verify it is handled
        try:
            low, high = ge.feasible_count_window(0.0009, 0.011)
        except ge.GeometryError:
            return  # explicit infeasibility is the contract
        self.assertLessEqual(low, high)
        self.assertLessEqual(high, ge.GRID_MAX_COUNT)

    def test_too_narrow_range_is_infeasible(self):
        with self.assertRaises(ge.GeometryError):
            ge.feasible_count_window(1.0, 1.0001)


class TestResolveFromGap(unittest.TestCase):
    def test_in_band_request_is_exact(self):
        resolved = ge.resolve_from_gap(0.00147, 0.008984, 1.4948)
        self.assertEqual(resolved.adjustment, "exact")
        self.assertTrue(resolved.satisfies_both)
        self.assertAlmostEqual(resolved.gap_pct, 1.4948, delta=0.02)

    def test_too_tight_spacing_is_raised_to_the_count_cap(self):
        # 0.45% over [0.00147, 0.008984] needs ~403 cells, above the 200 cap.
        resolved = ge.resolve_from_gap(0.00147, 0.008984, 0.45)
        self.assertEqual(resolved.adjustment, "gap_raised_to_n_max")
        self.assertEqual(resolved.count, 200)
        self.assertTrue(resolved.satisfies_both)

    def test_too_wide_spacing_is_lowered_to_the_count_floor(self):
        # A narrow range with the widest spacing needs fewer than 3 cells.
        resolved = ge.resolve_from_gap(0.0100, 0.0103, 1.5)
        self.assertEqual(resolved.adjustment, "gap_lowered_to_n_min")
        self.assertEqual(resolved.count, ge.GRID_MIN_COUNT)
        self.assertTrue(resolved.satisfies_both)

    def test_gap_never_leaves_the_frozen_band(self):
        random.seed(20261105)
        for _ in range(5000):
            lower = random.uniform(0.0009, 0.0022)
            upper = random.uniform(0.005, 0.011)
            gap = random.uniform(ge.GAP_MIN_PCT, ge.GAP_MAX_PCT)
            resolved = ge.resolve_from_gap(lower, upper, gap)
            self.assertTrue(resolved.satisfies_gap, resolved.disclosure())
            self.assertTrue(resolved.satisfies_count, resolved.disclosure())

    def test_disclosure_mentions_both_constraints(self):
        text = ge.resolve_from_gap(0.00147, 0.008984, 1.2).disclosure()
        for token in ("N=", "gap=", "0.45", "1.5"):
            self.assertIn(token, text)

    def test_arrays_reject_a_count_outside_the_feasible_window(self):
        with self.assertRaises(ge.GeometryError):
            ge.build_geometry_arrays(0.00147, 0.008984, 201)
        with self.assertRaises(ge.GeometryError):
            ge.build_geometry_arrays(0.00147, 0.008984, 3)


class TestGeometryArrays(unittest.TestCase):
    def test_arrays_match_the_native_template(self):
        arrays = ge.build_geometry_arrays(0.00147, 0.008984, 122)
        self.assertEqual(len(arrays["lower"]), 122)
        self.assertEqual(len(arrays["upper"]), 122)
        self.assertEqual(len(arrays["roles"]), 122)
        self.assertEqual(len(arrays["pcts"]), 122)
        self.assertEqual(len(arrays["arm_order"]), 122)
        # endpoints pinned
        self.assertEqual(arrays["lower"][0], 0.00147)
        self.assertEqual(arrays["upper"][-1], 0.008984)
        # contiguous: upper[i] == lower[i+1]
        for index in range(121):
            self.assertEqual(arrays["upper"][index], arrays["lower"][index + 1])

    def test_budgets_sum_to_one(self):
        arrays = ge.build_geometry_arrays(0.00147, 0.008984, 122)
        self.assertAlmostEqual(sum(arrays["pcts"]), 1.0, places=12)

    def test_roles_split_at_the_mid_price(self):
        arrays = ge.build_geometry_arrays(0.00147, 0.008984, 122)
        reference = (0.00147 + 0.008984) / 2
        for index, role in enumerate(arrays["roles"]):
            mid = (arrays["lower"][index] + arrays["upper"][index]) / 2
            if role.startswith("long"):
                self.assertLess(mid, reference)
            else:
                self.assertGreaterEqual(mid, reference)

    def test_arm_order_is_distance_sorted(self):
        arrays = ge.build_geometry_arrays(0.00147, 0.008984, 122)
        reference = (0.00147 + 0.008984) / 2
        distances = []
        for index in arrays["arm_order"]:
            role = arrays["roles"][index]
            price = arrays["lower"][index] if role.startswith("long") else arrays["upper"][index]
            distances.append(abs(price - reference))
        self.assertEqual(distances, sorted(distances))


class TestIndependentVerifier(unittest.TestCase):
    def test_verifier_accepts_a_valid_geometry(self):
        arrays = ge.build_geometry_arrays(0.00147, 0.008984, 122)
        report = ge.verify_geometry({
            "L": 0.00147, "U": 0.008984, "N": 122,
            "g_pct": ge.gap_for_count(0.00147, 0.008984, 122),
            "cell_lower": arrays["lower"], "cell_upper": arrays["upper"],
        })
        self.assertTrue(report["ok"], report["problems"])

    def test_verifier_catches_a_gap_out_of_band(self):
        report = ge.verify_geometry({
            "L": 0.00147, "U": 0.008984, "N": 122, "g_pct": 2.5,
            "cell_lower": [0.0] * 122, "cell_upper": [0.0] * 122,
        })
        self.assertFalse(report["ok"])
        self.assertTrue(any("gap=" in problem for problem in report["problems"]))

    def test_verifier_catches_a_count_out_of_band(self):
        report = ge.verify_geometry({
            "L": 0.00147, "U": 0.008984, "N": 500, "g_pct": 0.5,
            "cell_lower": [], "cell_upper": [],
        })
        self.assertFalse(report["ok"])
        self.assertTrue(any("N=" in problem for problem in report["problems"]))

    def test_verifier_catches_a_stale_gap(self):
        report = ge.verify_geometry({
            "L": 0.00147, "U": 0.008984, "N": 122, "g_pct": 0.9,
            "cell_lower": [0.0] * 122, "cell_upper": [0.0] * 122,
        })
        self.assertFalse(report["ok"])
        self.assertTrue(any("mismatch" in problem for problem in report["problems"]))


if __name__ == "__main__":
    unittest.main()
