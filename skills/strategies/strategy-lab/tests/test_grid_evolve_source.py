"""Tests for the parameterised grid-evolution strategy source generator.

The generator is the reusable asset: switching to another contract must be a
parameter change, never a code change.  These tests pin the contract that
makes that possible and that keeps the two frozen constraints honest.

The searchable dimensions are ``grid_lower`` / ``grid_upper`` /
``grid_gap_pct``; the cell count is derived and the frozen bands are enforced
by the runtime resolver.  Bound search ranges are per-contract inputs.
"""

import ast
import importlib.util
import sys
import unittest
from pathlib import Path

_LAB = Path(__file__).resolve().parents[1]
_SCRIPTS = _LAB / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ge = _load("offline_grid_evolution", _SCRIPTS / "grid_evolution.py")
ges = _load("offline_grid_evolve_source", _SCRIPTS / "grid_evolve_source.py")

PUMP_RANGES = {"grid_lower": (0.0012, 0.0016, 0.0001), "grid_upper": (0.005, 0.011, 0.0005)}
JUP_RANGES = {"grid_lower": (0.09, 0.12, 0.005), "grid_upper": (0.5, 0.65, 0.01)}


def _generate(instrument="Crypto:PUMP/USDT@swap", lower=0.00147, upper=0.008984,
              gap_pct=1.5, ranges=None, **kwargs):
    return ges.generate_evolve_source(instrument=instrument, lower=lower, upper=upper,
                                      gap_pct=gap_pct, search_ranges=ranges or PUMP_RANGES,
                                      **kwargs)


class TestGeneratedSourceShape(unittest.TestCase):
    def setUp(self):
        self.source, self.manifest = _generate(timeframe="1h", cell_id="PUMPUSDT-EVOLVE")
        self.tree = ast.parse(self.source)

    def test_source_parses(self):
        self.assertIsInstance(self.tree, ast.Module)

    def test_single_handle_data_definition(self):
        names = [n.name for n in self.tree.body if isinstance(n, ast.FunctionDef)]
        self.assertEqual(names.count("handle_data"), 1)
        self.assertEqual(names.count("_evolve_handle_data"), 1)

    def test_no_duplicate_module_assignments(self):
        assigns = [n.targets[0].id for n in self.tree.body
                   if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)]
        self.assertEqual({a for a in assigns if assigns.count(a) > 1}, set())

    def test_initialize_never_reads_params(self):
        # Platform contract: context.params is unavailable in initialize and
        # initialize is not called at runtime.  Reading it there silently
        # disables the whole search.
        initialize = [n for n in self.tree.body
                      if isinstance(n, ast.FunctionDef) and n.name == "initialize"][0]
        self.assertNotIn("context.params", ast.get_source_segment(self.source, initialize))

    def test_handle_data_applies_parameters_first(self):
        handle = [n for n in self.tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "handle_data"][0]
        segment = ast.get_source_segment(self.source, handle)
        self.assertLess(segment.index("_evolve_apply"),
                        segment.index("_evolve_handle_data"))

    def test_rebuild_is_keyed_on_the_applied_signature_not_on_float_arrays(self):
        # Regression 1: the first generator compared only the cell count, so a
        # changed grid_lower with an unchanged count left the grid untouched.
        # Regression 2 (2026-11-05): comparing upper0 against the rebuilt
        # CELL_UPPER[-1] fails bit-equality for ~half of (L, U, N) and tore
        # the grid down on EVERY bar (0 matched pairs vs 1278 measured).
        apply_fn = [n for n in self.tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "_evolve_apply"][0]
        segment = ast.get_source_segment(self.source, apply_fn)
        self.assertIn("signature = (lower0, upper0, count)", segment)
        self.assertIn("signature != EVOLVE_SIGNATURE", segment)
        # the platform sandbox rejects getattr (strategyV2 undefinedGlobal)
        self.assertNotIn("getattr(", self.source)
        self.assertNotIn("CELL_UPPER[-1]", segment.split("signature =")[1])
        self.assertNotIn("CELL_LOWER[0]", segment.split("signature =")[1])

    def test_rebuild_happens_once_per_signature_in_a_simulated_run(self):
        # Execute the generated _evolve_apply against a fake context for many
        # bars and count rebuilds; parameter sets that previously triggered
        # the per-bar rebuild must now rebuild exactly once.
        import math as _math
        start = self.source.index("EVOLVE_GAP_MIN_PCT =")
        end = self.source.index("def _evolve_handle_data")
        for lower, upper, gap in ((0.001, 0.0065, 1.2), (0.0011, 0.0075, 0.9),
                                  (0.00147, 0.008984, 1.5)):
            class _G:
                pass
            g_obj = _G()
            namespace = {"math": _math, "g": g_obj,
                         "CELL_LOWER": [lower], "CELL_UPPER": [upper],
                         "CELL_ROLES": [], "CELL_BUDGET_PCTS": [], "ARM_ORDER": []}
            exec(self.source[start:end], namespace)  # noqa: S102 - offline test
            rebuilds = 0
            original = namespace["_evolve_build"]

            def counting_build(*args, _orig=original):
                nonlocal rebuilds
                rebuilds += 1
                return _orig(*args)
            namespace["_evolve_build"] = counting_build

            class _Ctx:
                params = {"grid_lower": lower, "grid_upper": upper, "grid_gap_pct": gap}
            for _ in range(50):
                namespace["_evolve_apply"](_Ctx())
            self.assertEqual(rebuilds, 1, (lower, upper, gap))

    def test_param_declarations_present_and_match_the_rows(self):
        for name in ("grid_lower", "grid_upper", "grid_gap_pct"):
            self.assertIn(f"# @param {name} ", self.source)
        rows = {row["name"]: row for row in ges.build_param_space(self.manifest)}
        self.assertEqual(set(rows), {"grid_lower", "grid_upper", "grid_gap_pct"})
        self.assertAlmostEqual(rows["grid_gap_pct"]["min"], ge.GAP_MIN_PCT, places=9)
        self.assertAlmostEqual(rows["grid_gap_pct"]["max"], ge.GAP_MAX_PCT, places=9)
        self.assertEqual(rows["grid_gap_pct"]["type"], "number")

    def test_the_spacing_band_is_the_declared_sampling_domain(self):
        rows = {row["name"]: row for row in ges.build_param_space(self.manifest)}
        self.assertEqual(rows["grid_gap_pct"]["min"], ge.GAP_MIN_PCT)
        self.assertEqual(rows["grid_gap_pct"]["max"], ge.GAP_MAX_PCT)

    def test_bound_ranges_come_from_the_caller(self):
        rows = {row["name"]: row for row in ges.build_param_space(self.manifest)}
        self.assertEqual((rows["grid_lower"]["min"], rows["grid_lower"]["max"]), (0.0012, 0.0016))
        self.assertIn("range=0.0012:0.0016:0.0001", self.source)

    def test_declarations_parse_with_the_platform_regex(self):
        # Regression 2026-11-05: step 7.35e-05 was read by the platform as 7.35
        # and grid_lower collapsed to one value (parameterRangeOutsideDeclaration).
        import re
        platform_range = re.compile(
            r"range\s*=\s*(-?\d+(?:\.\d+)?)\s*:\s*(-?\d+(?:\.\d+)?)\s*:\s*(-?\d+(?:\.\d+)?)")
        source, manifest = _generate(ranges={"grid_lower": (0.000735, 0.002205, 7.35e-05),
                                             "grid_upper": (0.004492, 0.013476, 0.0004492)})
        for name, spec in manifest["parameter_declarations"].items():
            line = next(l for l in source.splitlines() if l.startswith(f"# @param {name} "))
            self.assertNotIn("e-", line)
            low, high, step = (float(x) for x in platform_range.search(line).groups())
            self.assertAlmostEqual(low, spec["min"], places=12)
            self.assertAlmostEqual(high, spec["max"], places=12)
            self.assertAlmostEqual(step, spec["step"], places=12)

    def test_an_inverted_range_is_rejected(self):
        with self.assertRaises(ValueError):
            _generate(ranges={"grid_lower": (0.002, 0.001, 0.0001),
                              "grid_upper": (0.005, 0.011, 0.0005)})

    def test_the_count_is_not_a_search_dimension(self):
        rows = {row["name"] for row in ges.build_param_space(self.manifest)}
        self.assertNotIn("grid_count", rows)

    def test_the_count_cap_is_still_enforced_in_the_runtime(self):
        # The 200-cell cap must survive inside the resolver even though the
        # count is no longer a sampled dimension.
        self.assertIn(f"EVOLVE_GRID_MAX_COUNT = {ge.GRID_MAX_COUNT}",
                      self.source)
        self.assertIn("EVOLVE_GRID_MAX_COUNT", self.source)

    def test_manifest_records_the_executed_geometry(self):
        geometry = self.manifest["executed_geometry"]
        self.assertEqual(geometry["N"], 122)
        self.assertAlmostEqual(geometry["g_pct"], 1.4948187, places=5)
        self.assertTrue(ge.verify_geometry({
            "L": geometry["L"], "U": geometry["U"], "N": geometry["N"],
            "g_pct": geometry["g_pct"],
        })["ok"])


class TestContractAgnosticReuse(unittest.TestCase):
    def test_a_different_contract_is_a_parameter_change_only(self):
        first, manifest_a = _generate()
        second, manifest_b = _generate(instrument="Crypto:JUP/USDT@swap", lower=0.1069,
                                       upper=0.578, ranges=JUP_RANGES)
        self.assertNotEqual(first, second)
        # same template, same declared names, same frozen spacing band
        self.assertEqual(manifest_a["template_sha256"], manifest_b["template_sha256"])
        self.assertEqual(list(manifest_a["parameter_declarations"]),
                         list(manifest_b["parameter_declarations"]))
        self.assertEqual(manifest_a["parameter_declarations"]["grid_gap_pct"]["min"],
                         manifest_b["parameter_declarations"]["grid_gap_pct"]["min"])

    def test_every_contract_gets_a_feasible_geometry(self):
        for instrument, lower, upper in (
            ("Crypto:PUMP/USDT@swap", 0.00147, 0.008984),
            ("Crypto:JUP/USDT@swap", 0.1069, 0.578),
            ("Crypto:AAVE/USDT@swap", 57.71, 385.86),
            ("Crypto:SUI/USDT@swap", 0.5479, 4.1844),
        ):
            for gap in (0.45, 0.9, 1.5):
                ranges = {"grid_lower": (lower * 0.9, lower * 1.1, lower * 0.05),
                          "grid_upper": (upper * 0.9, upper * 1.1, upper * 0.05)}
                _, manifest = _generate(instrument=instrument, lower=lower, upper=upper,
                                        gap_pct=gap, ranges=ranges)
                geometry = manifest["executed_geometry"]
                self.assertGreaterEqual(geometry["g_pct"], ge.GAP_MIN_PCT - 1e-9)
                self.assertLessEqual(geometry["g_pct"], ge.GAP_MAX_PCT + 1e-9)
                self.assertLessEqual(geometry["N"], ge.GRID_MAX_COUNT)

    def test_a_too_tight_spacing_moves_itself_and_is_disclosed(self):
        # Requesting the tightest spacing derives more cells than the cap
        # allows, so the spacing must move up and say so.
        _, manifest = _generate(gap_pct=0.45)
        geometry = manifest["executed_geometry"]
        self.assertEqual(geometry["adjustment"], "gap_raised_to_n_max")
        self.assertEqual(geometry["N"], ge.GRID_MAX_COUNT)
        self.assertGreaterEqual(geometry["g_pct"], ge.GAP_MIN_PCT - 1e-9)
        self.assertLessEqual(geometry["g_pct"], ge.GAP_MAX_PCT + 1e-9)

    def test_a_too_wide_spacing_moves_itself_and_is_disclosed(self):
        _, manifest = _generate(gap_pct=5.0)
        geometry = manifest["executed_geometry"]
        self.assertEqual(geometry["adjustment"], "gap_lowered_to_n_min")
        self.assertGreaterEqual(geometry["g_pct"], ge.GAP_MIN_PCT - 1e-9)
        self.assertLessEqual(geometry["g_pct"], ge.GAP_MAX_PCT + 1e-9)


class TestRuntimeParity(unittest.TestCase):
    """The sandbox runtime block must behave like the library resolver."""

    def test_the_library_resolver_moves_the_spacing_not_the_count(self):
        resolved = ge.resolve_from_gap(0.00147, 0.008984, 0.45)
        self.assertEqual(resolved.adjustment, "gap_raised_to_n_max")
        self.assertEqual(resolved.count, ge.GRID_MAX_COUNT)
        self.assertGreaterEqual(resolved.gap_pct, ge.GAP_MIN_PCT - 1e-9)
        self.assertLessEqual(resolved.gap_pct, ge.GAP_MAX_PCT + 1e-9)

    def test_runtime_resolver_matches_the_library(self):
        source, _ = _generate(gap_pct=1.5)
        namespace: dict = {}
        # extract the runtime block, constants included, for an offline comparison
        start = source.index("EVOLVE_GAP_MIN_PCT =")
        end = source.index("def _evolve_apply")
        exec("import math\n" + source[start:end], namespace)  # noqa: S102 - offline test
        for lower, upper, requested in (
            (0.00147, 0.008984, 1.5),
            (0.00147, 0.008984, 0.45),
            (0.00147, 0.008984, 0.5),
            (0.0019, 0.0105, 1.2),
            (0.1069, 0.578, 0.8),
            (57.71, 385.86, 1.45),
        ):
            count, gap, low, high = namespace["_evolve_resolve"](lower, upper, requested)
            library = ge.resolve_from_gap(lower, upper, requested)
            self.assertEqual(count, library.count)
            self.assertAlmostEqual(gap, library.gap_pct, places=9)
            self.assertEqual((low, high), library.feasible_window)

    def test_runtime_build_matches_the_library_arrays(self):
        source, _ = _generate(gap_pct=1.5)
        namespace: dict = {}
        start = source.index("def _evolve_build")
        end = source.index("def _evolve_apply")
        exec("import math\n" + source[start:end], namespace)  # noqa: S102 - offline test
        lower, upper, roles, pcts, arm_order = namespace["_evolve_build"](
            0.00147, 0.008984, 122)
        arrays = ge.build_geometry_arrays(0.00147, 0.008984, 122)
        self.assertEqual(roles, arrays["roles"])
        self.assertEqual(arm_order, arrays["arm_order"])
        for produced, expected in zip(lower, arrays["lower"]):
            self.assertAlmostEqual(produced, expected, places=15)
        for produced, expected in zip(pcts, arrays["pcts"]):
            self.assertAlmostEqual(produced, expected, places=15)


if __name__ == "__main__":
    unittest.main()
