"""Unit tests for the stress-test liquidation solver.

Synthetic and offline: a hand-built grid, a mocked MMR source and a temporary
report directory. No network, no credentials, no real report directory.
"""

import csv
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

_LAB = Path(__file__).resolve().parents[1]
_MODULE_PATH = _LAB / "scripts" / "grid_stress_liquidation.py"

if not _MODULE_PATH.is_file():
    raise AssertionError("required grid_stress_liquidation implementation is missing")
_spec = importlib.util.spec_from_file_location("offline_grid_stress_liquidation",
                                                _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
gsl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gsl)


def synthetic_grid(lower, upper, roles, pcts):
    """Build the grid dict the solver consumes."""
    return {"lower": list(lower), "upper": list(upper),
            "roles": list(roles), "pcts": list(pcts)}


def constant_resolver(mmr):
    """Resolver that always returns one fixed MMR tier."""
    resolver = gsl.MmrResolver(fetcher=lambda url: {"data": {"brackets": [{
        "symbol": "TEST", "updateTime": 0, "riskBrackets": [{
            "bracketSeq": 1, "bracketNotionalFloor": 0, "bracketNotionalCap": 10 ** 9,
            "bracketMaintenanceMarginRate": mmr,
            "cumFastMaintenanceAmount": 0}]}]}})
    return resolver


class ParseGridTests(unittest.TestCase):

    def test_reads_the_frozen_constants_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strategy.py"
            path.write_text(
                "CELL_LOWER = [1.0, 2.0]\n"
                "CELL_UPPER = [2.0, 3.0]\n"
                "CELL_ROLES = ['long_entry', 'short_entry']\n"
                "CELL_BUDGET_PCTS = [0.5, 0.5]\n"
                "def handle_data():\n    raise SystemExit('must not run')\n")
            grid = gsl.parse_grid(path)
        self.assertEqual([1.0, 2.0], grid["lower"])
        self.assertEqual([2.0, 3.0], grid["upper"])
        self.assertEqual(["long_entry", "short_entry"], grid["roles"])
        self.assertEqual([0.5, 0.5], grid["pcts"])

    def test_missing_constant_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strategy.py"
            path.write_text("CELL_LOWER = [1.0]\n")
            with self.assertRaises(ValueError):
                gsl.parse_grid(path)


class SideEntriesTests(unittest.TestCase):

    def test_long_uses_cell_lower_short_uses_cell_upper(self):
        grid = synthetic_grid([1.0, 2.0, 3.0], [2.0, 3.0, 4.0],
                              ["long_entry", "short_entry", "long_entry"],
                              [0.5, 0.25, 0.25])
        longs, shorts = gsl.side_entries(grid)
        self.assertEqual([(1.0, 5000.0), (3.0, 2500.0)], longs)
        self.assertEqual([(3.0, 2500.0)], shorts)


class WalkTests(unittest.TestCase):

    def test_long_side_root_matches_the_closed_form(self):
        # One long order of 10000 quote notional filled at price 100 ->
        # 100 units.  E0=1000, N=10000, MMR=1%, close fee f=0.05%.
        #   E(p) = 1000 - 10000 + 100p ;  MM(p) = (mmr+f)*100p
        #   100p(1 - mmr - f) = 9000  ->  p = 9000/(100*(1-0.01-0.0005))
        # The root sits below the single entry, so the position is liquidated
        # before the ladder is filled: the zone is below-L.
        entries = [(100.0, 10000.0)]
        result = gsl.walk(entries, True, equity0=1000.0, mmr=0.01)
        expected = 9000.0 / (100.0 * (1.0 - 0.01 - 0.0005))
        self.assertAlmostEqual(expected, result["root"], places=12)
        self.assertEqual("below-L", result["zone"])
        self.assertEqual(1, result["fills"])

    def test_long_side_root_inside_a_multi_level_ladder(self):
        # Two long orders: 4000 quote notional at price 100 and 6000 at 90.
        # After the first fill: N=4000, Q=40 units.
        #   E(p) = 1000 - 4000 + 40p ; MM(p) = (mmr+f)*40p
        #   40p(1 - mmr - f) = 3000 -> p = 3000/(40*0.9895) = 75.83 .. below 90
        # so the root is reached only after both fills:
        #   N=10000, Q=40+66.67=106.67 units
        #   E(p) = 1000 - 10000 + 106.67p ; 106.67p(1-mmr-f) = 9000
        entries = [(100.0, 4000.0), (90.0, 6000.0)]
        result = gsl.walk(entries, True, equity0=1000.0, mmr=0.01)
        quantity = 4000.0 / 100.0 + 6000.0 / 90.0
        expected = 9000.0 / (quantity * (1.0 - 0.01 - 0.0005))
        self.assertAlmostEqual(expected, result["root"], places=12)
        self.assertEqual(2, result["fills"])
        self.assertEqual("below-L", result["zone"])

    def test_short_side_root_is_above_the_ladder(self):
        # One short order of 10000 quote notional sold at price 100.
        #   E(p) = 1000 + 10000 - 100p ;  MM(p) = (mmr+f)*100p
        #   100p(1+mmr+f) = 11000  ->  p = 11000/(100*1.0105)
        entries = [(100.0, 10000.0)]
        result = gsl.walk(entries, False, equity0=1000.0, mmr=0.01)
        expected = 11000.0 / (100.0 * (1.0 + 0.01 + 0.0005))
        self.assertAlmostEqual(expected, result["root"], places=12)
        self.assertEqual("above-U", result["zone"])

    def test_no_root_when_equity_stays_above_maintenance(self):
        # One long order of 500 with E0=1000: the equity floor is 500, so the
        # position can never be liquidated on the way down.
        entries = [(100.0, 500.0)]
        result = gsl.walk(entries, True, equity0=1000.0, mmr=0.01)
        self.assertIsNone(result["root"])
        self.assertEqual("no-root", result["zone"])

    def test_walk_rejects_an_empty_ladder(self):
        with self.assertRaises(ValueError):
            gsl.walk([], True)

    def test_leverage_one_long_side_has_no_root(self):
        # At leverage 1 the long side notional equals E0, so the equity floor
        # is 0 and the position never reaches the maintenance requirement.
        # The close fee belongs to the requirement factor (MF = mmr + f), so
        # the equity floor stays at E0 - N = 0 and the segment still carries no
        # admissible positive root: the zone is no-root, not below-L.
        grid = synthetic_grid([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
                              [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5],
                              ["long_entry"] * 4 + ["short_entry"] * 4,
                              [0.25] * 8)
        result = gsl.solve_cell(grid, symbol="TEST", leverage=1.0,
                                resolver=constant_resolver(0.01))
        self.assertEqual("no-root", result["down"]["zone"])
        self.assertIsNone(result["down"]["root"])
        # The short side still has a root: its equity grows with the price.
        self.assertIsNotNone(result["up"]["root"])
        self.assertEqual("above-U", result["up"]["zone"])

    def test_close_fee_term_moves_the_long_root_up(self):
        # 2026-11-04 F-term correction: the close fee is charged on the
        # liquidation notional, so it enters the requirement factor
        # (MF = mmr + f) and the equity side stays gross:
        # E(p) = E0 - N + p*Q against MM(p) = MF*p*Q.  A larger fee raises the
        # requirement, so the long liquidation happens EARLIER and the root
        # moves UP by the analytic factor f/(1 - mmr - f).  The zone must not
        # change.
        entries = [(100.0, 10000.0)]
        without = gsl.walk(entries, True, equity0=1000.0, mmr=0.01,
                           close_fee_rate=0.0)
        with_fee = gsl.walk(entries, True, equity0=1000.0, mmr=0.01,
                            close_fee_rate=0.0005)
        self.assertGreater(with_fee["root"], without["root"])
        expected_ratio = 0.0005 / (1.0 - 0.01 - 0.0005)
        self.assertAlmostEqual(expected_ratio,
                               (with_fee["root"] - without["root"]) / without["root"],
                               places=12)
        self.assertEqual(without["zone"], with_fee["zone"])

    def test_close_fee_term_moves_the_short_root_down(self):
        # Mirror case: on the short side the fee also enters the requirement,
        # so the upward liquidation happens EARLIER and the root moves DOWN by
        # f/(1 + mmr + f).
        entries = [(100.0, 10000.0)]
        without = gsl.walk(entries, False, equity0=1000.0, mmr=0.01,
                           close_fee_rate=0.0)
        with_fee = gsl.walk(entries, False, equity0=1000.0, mmr=0.01,
                            close_fee_rate=0.0005)
        self.assertLess(with_fee["root"], without["root"])
        expected_ratio = -0.0005 / (1.0 + 0.01 + 0.0005)
        self.assertAlmostEqual(expected_ratio,
                               (with_fee["root"] - without["root"]) / without["root"],
                               places=12)
        self.assertEqual(without["zone"], with_fee["zone"])

    def test_close_fee_is_charged_exactly_once(self):
        # The fee belongs to the requirement factor (MF = mmr + f) and must
        # not be subtracted from the equity side a second time: the long root
        # is (N - E0) / (Q * (1 - mmr - f)).
        entries = [(100.0, 10000.0)]
        result = gsl.walk(entries, True, equity0=1000.0, mmr=0.01,
                          close_fee_rate=0.0005)
        expected = (10000.0 - 1000.0) / (100.0 * (1.0 - 0.01 - 0.0005))
        self.assertAlmostEqual(expected, result["root"], places=12)

    def test_close_fee_shifts_the_leverage_ten_root_by_about_5e_4(self):
        # 2026-11-04 F-term correction, leverage-10 caliber: removing the
        # duplicated fee term moves the root by a relative ~5e-4 and must not
        # move it by the ~1e-3 of a doubled fee.  The zone must not change.
        entries = [(100.0, 10000.0)]
        without = gsl.walk(entries, True, equity0=1000.0, mmr=0.01,
                           close_fee_rate=0.0)
        with_fee = gsl.walk(entries, True, equity0=1000.0, mmr=0.01,
                            close_fee_rate=0.0005)
        relative = (with_fee["root"] - without["root"]) / without["root"]
        self.assertGreater(relative, 0.0)
        self.assertLess(abs(relative), 1e-3)
        self.assertAlmostEqual(0.0005 / (1.0 - 0.01 - 0.0005), relative,
                               places=12)
        self.assertEqual(without["zone"], with_fee["zone"])

    def test_a_root_at_or_below_zero_is_not_a_liquidation(self):
        # A liquidation price must be strictly positive.  The long ladder is
        # levered far past the equity, so the algebraic root falls at or below
        # zero: there is no admissible liquidation price.
        entries = [(100.0, 100000.0)]
        result = gsl.walk(entries, True, equity0=1000.0, mmr=0.01)
        self.assertIsNone(result["root"])
        self.assertEqual("no-root", result["zone"])

    def test_zone_below_ladder_for_a_falling_price_below_every_entry(self):
        # A long ladder whose entries all sit far above the root price.
        entries = [(100.0, 9000.0), (110.0, 100.0)]
        result = gsl.walk(entries, True, equity0=1000.0, mmr=0.01)
        self.assertIsNotNone(result["root"])
        self.assertLess(result["root"], 100.0)
        self.assertEqual("below-L", result["zone"])


class SolveCellTests(unittest.TestCase):

    def test_fills_are_counted_and_zones_are_correct(self):
        # 8 cells: 4 long (lower ladder) and 4 short (upper ladder).
        lower = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]
        upper = [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5]
        roles = ["long_entry"] * 4 + ["short_entry"] * 4
        pcts = [0.125] * 8
        grid = synthetic_grid(lower, upper, roles, pcts)
        result = gsl.solve_cell(grid, symbol="TEST",
                                resolver=constant_resolver(0.01))
        self.assertEqual(4, result["n_long"])
        self.assertEqual(4, result["n_short"])
        self.assertEqual(5000.0, result["long_notional"])
        self.assertEqual(5000.0, result["short_notional"])
        self.assertIn(result["down"]["zone"], ("in-ladder", "below-L"))
        self.assertIn(result["up"]["zone"], ("in-ladder", "above-U"))
        self.assertEqual(0.01, result["down"]["mmr"])
        self.assertEqual(0.01, result["up"]["mmr"])

    def test_roots_are_consistent_with_the_walk_of_the_same_side(self):
        lower = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]
        upper = [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5]
        grid = synthetic_grid(lower, upper,
                              ["long_entry"] * 4 + ["short_entry"] * 4,
                              [0.125] * 8)
        resolver = constant_resolver(0.01)
        result = gsl.solve_cell(grid, symbol="TEST", resolver=resolver)
        longs, shorts = gsl.side_entries(grid)
        down = gsl.walk(longs, True, equity0=1000.0, mmr=0.01,
                        close_fee_rate=0.0005)
        self.assertAlmostEqual(down["root"], result["down"]["root"], places=12)
        up = gsl.walk(shorts, False, equity0=1000.0, mmr=0.01,
                      close_fee_rate=0.0005)
        self.assertAlmostEqual(up["root"], result["up"]["root"], places=12)

    def test_solve_cell_rejects_an_empty_symbol(self):
        # The brackets tier is a per-symbol contract: an empty symbol must not
        # silently query ``brackets?symbol=`` (an unrelated default table with
        # a wrong tier) or fall through to the default gradient. Fail closed.
        grid = synthetic_grid([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
                              [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5],
                              ["long_entry"] * 4 + ["short_entry"] * 4,
                              [0.125] * 8)
        with self.assertRaises(ValueError) as caught:
            gsl.solve_cell(grid, resolver=constant_resolver(0.01))
        self.assertIn("symbol is required for MMR resolution", str(caught.exception))
        with self.assertRaises(ValueError):
            gsl.solve_cell(grid, symbol="   ", resolver=constant_resolver(0.01))
        # The resolver entry points carry the same guard (no silent request,
        # no default-gradient fallback on a missing key).
        for symbol in ("", "   "):
            with self.assertRaises(ValueError):
                gsl.fetch_mmr(symbol, 100.0, resolver=constant_resolver(0.01))
        with self.assertRaises(ValueError):
            constant_resolver(0.01).candidates("")

    def test_pure_long_grid_short_side_needs_no_mmr_request(self):
        # AAVEUSDT-style full-window pure-long grid: every window cell is a
        # long entry, so the short side holds no position and is solved as
        # no_position without any MMR request.
        grid = synthetic_grid([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
                              [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5],
                              ["long_entry"] * 8, [0.125] * 8)

        def exploding_fetcher(url):
            raise AssertionError("no MMR request may be issued for an empty side")

        resolver = gsl.MmrResolver(fetcher=exploding_fetcher)
        result = gsl.solve_cell(grid, symbol="AAVEUSDT", resolver=resolver)
        self.assertEqual(8, result["n_long"])
        self.assertEqual(0, result["n_short"])
        self.assertIsNone(result["up"]["root"])
        self.assertEqual("no_position", result["up"]["zone"])
        self.assertEqual(0, result["up"]["fills"])
        self.assertIsNone(result["up"]["mmr"])
        # The long side is still solved normally.
        self.assertIn(result["down"]["zone"], ("in-ladder", "below-L"))
        self.assertEqual(0.01, result["down"]["mmr"])


class MmrResolverTests(unittest.TestCase):

    def test_native_platform_field_wins(self):
        resolver = gsl.MmrResolver(native={"maintenanceMarginRate": 0.008},
                                   fetcher=lambda url: {"data": {"brackets": [{
                                       "riskBrackets": [{
                                           "bracketSeq": 1,
                                           "bracketNotionalFloor": 0,
                                           "bracketNotionalCap": 10 ** 9,
                                           "bracketMaintenanceMarginRate": 0.02}]}]}})
        tier = resolver.select("TEST", 1000.0)
        self.assertEqual(0.008, tier["mmr"])
        self.assertEqual("platform-native", tier["source"])

    def test_binance_tier_is_selected_by_notional(self):
        payload = {"data": {"brackets": [{
            "updateTime": 1, "riskBrackets": [
                {"bracketSeq": 1, "bracketNotionalFloor": 0,
                 "bracketNotionalCap": 5000,
                 "bracketMaintenanceMarginRate": 0.01},
                {"bracketSeq": 2, "bracketNotionalFloor": 5000,
                 "bracketNotionalCap": 10000,
                 "bracketMaintenanceMarginRate": 0.015}]}]}}
        resolver = gsl.MmrResolver(fetcher=lambda url: payload)
        self.assertEqual(0.01, resolver.select("TEST", 4999.0)["mmr"])
        self.assertEqual(0.015, resolver.select("TEST", 5000.0)["mmr"])
        self.assertEqual(0.015, resolver.select("TEST", 9999.0)["mmr"])
        self.assertEqual("binance-brackets", resolver.select("TEST", 100.0)["source"])

    def test_default_gradient_when_the_endpoint_is_unreachable(self):
        def failing(url):
            raise RuntimeError("network down")

        resolver = gsl.MmrResolver(fetcher=failing)
        low = resolver.select("TEST", 10_000.0)
        high = resolver.select("TEST", 25_000.0)
        self.assertEqual(0.01, low["mmr"])
        self.assertEqual(0.015, high["mmr"])
        self.assertEqual("default-tier", low["source"])
        self.assertEqual("default MMR tier (binance unreachable)", low["reason"])

    def test_default_gradient_when_the_response_has_no_brackets(self):
        resolver = gsl.MmrResolver(fetcher=lambda url: {"data": {"brackets": []}})
        self.assertEqual("default-tier", resolver.select("TEST", 100.0)["source"])

    def test_fetch_mmr_uses_the_resolver(self):
        resolver = constant_resolver(0.012)
        tier = gsl.fetch_mmr("TEST", 100.0, resolver=resolver)
        self.assertEqual(0.012, tier["mmr"])


class ReportTableTests(unittest.TestCase):

    REPORT = """# 报告

## 2. 表 A

| 合约 | 窗口 | 收益% | 强平价 | 敞口/权益峰值 |
|---|---|---|---|---|
| JUPUSDT | W1 | 1.0 | N/A | 1.31 |
| PUMPUSDT | W1 | 2.0 | N/A | 0.93 |

## 3. 表 B
"""

    def test_columns_are_located_by_header_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            path.write_text(self.REPORT)
            table = gsl.report_table_a(path)
        self.assertEqual(1.31, table[("JUPUSDT", "W1")]["worst_gross_to_equity"])
        self.assertEqual(0.93, table[("PUMPUSDT", "W1")]["worst_gross_to_equity"])

    def test_missing_table_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            path.write_text("# 无表\n")
            with self.assertRaises(ValueError):
                gsl.report_table_a(path)


class SyncReportTests(unittest.TestCase):

    def test_table_a_liquidation_column_is_split_and_filled(self):
        report = ("# 报告\n\n## 2. 表 A\n\n"
                  "| 合约 | 窗口 | 收益% | 强平价 | 敞口/权益峰值 |\n"
                  "|---|---|---|---|---|\n"
                  "| JUPUSDT | W1 | 1.0 | N/A | 1.31 |\n\n"
                  "## 3. 表 B\n\n正文\n\n## 4. 结束\n")
        cells = [{"contract": "JUPUSDT", "window": "W1",
                  "downward_liquidation_price": 0.18153116347081905,
                  "upward_liquidation_price": 0.5830400881483845}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            path.write_text(report)
            gsl.sync_report_table_a(path, cells)
            text = path.read_text()
        self.assertIn("多头强平价", text)
        self.assertIn("空头强平价", text)
        self.assertIn("0.18153116347081905", text)
        self.assertIn("0.5830400881483845", text)
        self.assertNotIn("| N/A | 0 |", text)

    def test_table_a_keeps_the_other_columns_untouched(self):
        report = ("# 报告\n\n## 2. 表 A\n\n"
                  "| 合约 | 窗口 | 收益% | 强平价 | 敞口/权益峰值 |\n"
                  "|---|---|---|---|---|\n"
                  "| JUPUSDT | W1 | 1.0 | N/A | 1.31 |\n\n"
                  "## 3. 表 B\n\n正文\n\n## 4. 结束\n")
        cells = [{"contract": "JUPUSDT", "window": "W1",
                  "downward_liquidation_price": 0.5, "upward_liquidation_price": 0.6}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            path.write_text(report)
            gsl.sync_report_table_a(path, cells)
            text = path.read_text()
        self.assertIn("| 1.0 | 0.5 | 0.6 | 1.31 |", text)


class BackfillTests(unittest.TestCase):

    def _report_dir(self, directory):
        report_dir = Path(directory) / "topic"
        evidence = report_dir / "evidence"
        evidence.mkdir(parents=True)
        (report_dir / "report.md").write_text(
            "# 报告\n\n## 2. 表 A\n\n"
            "| 合约 | 窗口 | 收益% | 强平价 | 敞口/权益峰值 |\n"
            "|---|---|---|---|---|\n"
            "| JUPUSDT | W1 | 1.0 | N/A | 1.31 |\n\n"
            "## 3. 表 B\n\n正文\n\n## 4. 结束\n")
        with (evidence / "cells.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "task_date", "anchor_utc", "cell_id", "contract", "window",
                "L", "U", "g_pct", "N", "margin_return_pct", "sharpe",
                "max_drawdown_pct", "downward_liquidation_price",
                "upward_liquidation_price", "status", "reason", "job_id",
                "run_id", "tool_status", "research_status", "qualification",
                "frequency_seconds", "expected_bars", "start_utc", "end_utc"])
            writer.writeheader()
            writer.writerow({
                "task_date": "2026-11-03", "anchor_utc": "2026-11-03T00:00:00Z",
                "cell_id": "JUPUSDT-W1", "contract": "JUPUSDT", "window": "W1",
                "L": "1.0", "U": "1.8", "g_pct": "1.5", "N": "8",
                "margin_return_pct": "1.0", "sharpe": "1.0",
                "max_drawdown_pct": "-2.0",
                "downward_liquidation_price": "N/A",
                "upward_liquidation_price": "N/A",
                "status": "completed", "reason": "platform native Path B",
                "job_id": "", "run_id": "41", "tool_status": "backtest_succeeded",
                "research_status": "completed", "qualification": "qualified",
                "frequency_seconds": "3600", "expected_bars": "2208",
                "start_utc": "2026-08-03T00:00:00Z",
                "end_utc": "2026-11-03T00:00:00Z"})
        return report_dir, evidence

    def _strategies(self, directory):
        """Frozen geometry for the whole 4x4 matrix, so the carrier skeleton
        (16 planned cells) can be laid from the anchor."""
        strategies = Path(directory) / "strategies"
        for contract in gsl.gr.DEFAULT_CONTRACTS:
            for window in ("W1", "W2", "W3", "W4"):
                cell_dir = strategies / f"{contract}-{window}-1h"
                cell_dir.mkdir(parents=True)
                (cell_dir / "strategy.py").write_text(
                    "CELL_LOWER = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]\n"
                    "CELL_UPPER = [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5]\n"
                    "CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', "
                    "'long_entry', 'short_entry', 'short_entry', 'short_entry', "
                    "'short_entry']\n"
                    "CELL_BUDGET_PCTS = [0.125, 0.125, 0.125, 0.125, 0.125, "
                    "0.125, 0.125, 0.125]\n")
        return strategies

    def test_backfill_writes_the_carriers_and_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir, evidence = self._report_dir(directory)
            strategies = self._strategies(directory)
            result = gsl.backfill(report_dir, "2026-11-03T00:00:00Z",
                                  resolver=constant_resolver(0.01),
                                  strategy_dir=strategies)
            self.assertTrue((evidence / "cells.csv").exists())
            self.assertTrue((evidence / "cells-comparison.csv").exists())
            self.assertTrue((evidence / "table-b-summary.md").exists())
            with (evidence / "cells.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(16, len(rows))
            solved = [row for row in rows if row["status"] == "completed"]
            self.assertEqual(1, len(solved))
            self.assertIsNotNone(float(solved[0]["downward_liquidation_price"]))
            self.assertIn("多头强平价", (report_dir / "report.md").read_text())
            # The archived row carried N/A for both columns; both are reported.
            self.assertEqual(2, len(result["errata"]))

    def test_backfill_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir, evidence = self._report_dir(directory)
            strategies = self._strategies(directory)
            gsl.backfill(report_dir, "2026-11-03T00:00:00Z",
                         resolver=constant_resolver(0.01),
                         strategy_dir=strategies)
            first = (evidence / "cells.csv").read_text()
            second_result = gsl.backfill(report_dir, "2026-11-03T00:00:00Z",
                                         resolver=constant_resolver(0.01),
                                         strategy_dir=strategies)
            self.assertEqual(first, (evidence / "cells.csv").read_text())
            note = (evidence / "liquidation-backfill-2026-11-04.md").read_text()
            self.assertEqual(1, note.count(gsl.NOTE_START))
            self.assertEqual(1, note.count(gsl.NOTE_END))
            # The second pass solves the same carrier, so no difference is
            # reported against the archived values.
            self.assertEqual([], second_result["errata"])


class ArchivedSnapshotTests(unittest.TestCase):

    NOTE = ("# 强平价回填\n\n"
            "| cell | runId | worst快照时间 | worst G/E | worst名义(USDT) | MMR | "
            "多头强平价 | 空头强平价 | status |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| JUPUSDT-W1 | 41 | 2026-11-03T03:00:00Z | 1.2386 | 0.00 | 1.0000% | "
            "0.04703132919163824 | N/A | ok |\n"
            "| PUMPUSDT-W1 | 42 | 2026-09-16T01:00:00Z | 0.8735 | 0.00 | 1.0000% | "
            "N/A | N/A | no_positive_solution |\n"
            "\n" + gsl.NOTE_START + "\n## 压力测试口径重算\n\n"
            "| cell | 多头格/空头格 | 多头名义 | 空头名义 | 下行根 | 触发时成交格数 | "
            "下行区域 | 上行根 | 触发时成交格数 | 上行区域 | 下行MMR | 上行MMR |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            "| JUPUSDT-W1 | 79/35 | 6930 | 3070 | 0.181531163471 | 43 | in-ladder | "
            "0.583040088148 | 35 | above-U | 1.0000% | 1.0000% |\n"
            + gsl.NOTE_END + "\n")

    def test_reads_only_the_records_above_the_stress_section(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.md"
            path.write_text(self.NOTE)
            archived = gsl.archived_snapshot_values(path)
        self.assertEqual(0.04703132919163824,
                         archived[("JUPUSDT", "W1")]["down"])
        self.assertIsNone(archived[("JUPUSDT", "W1")]["up"])
        self.assertIsNone(archived[("PUMPUSDT", "W1")]["down"])
        # The stress table's own row must not be read as an archived record.
        self.assertEqual(2, len(archived))

    def test_errata_reports_the_difference_without_deleting_the_archive(self):
        cells = [{"contract": "JUPUSDT", "window": "W1",
                  "downward_liquidation_price": 0.18153116347081905,
                  "upward_liquidation_price": 0.5830400881483845}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.md"
            path.write_text(self.NOTE)
            archived = gsl.archived_snapshot_values(path)
            errata = gsl._snapshot_errata(archived, cells)
            gsl._append_erratum(path, errata)
            text = path.read_text()
        self.assertEqual(2, len(errata))
        self.assertIn("0.04703132919163824", text)
        self.assertIn("0.18153116347081905", text)
        # The archived table itself is preserved.
        self.assertIn("| JUPUSDT-W1 | 41 | 2026-11-03T03:00:00Z |", text)
        self.assertEqual(1, text.count(gsl.ERRATA_START))
        self.assertEqual(1, text.count(gsl.ERRATA_END))

    def test_errata_block_is_rewritten_in_place(self):
        cells = [{"contract": "JUPUSDT", "window": "W1",
                  "downward_liquidation_price": 0.18153116347081905,
                  "upward_liquidation_price": 0.5830400881483845}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.md"
            path.write_text(self.NOTE)
            archived = gsl.archived_snapshot_values(path)
            errata = gsl._snapshot_errata(archived, cells)
            gsl._append_erratum(path, errata)
            gsl._append_erratum(path, errata)
            text = path.read_text()
        self.assertEqual(1, text.count(gsl.ERRATA_START))
        self.assertEqual(1, text.count(gsl.ERRATA_END))


class RealDataSmokeTests(unittest.TestCase):
    """The published carrier values must be reproducible from the frozen geometry."""

    STRATEGIES = _LAB / "strategies"

    def _solver(self, contract, window, mmr):
        resolver = gsl.MmrResolver(fetcher=lambda url: {"data": {"brackets": [{
            "symbol": contract, "updateTime": 0, "riskBrackets": [
                {"bracketSeq": 1, "bracketNotionalFloor": 0,
                 "bracketNotionalCap": 10 ** 9,
                 "bracketMaintenanceMarginRate": mmr,
                 "cumFastMaintenanceAmount": 0}]}]}})
        grid = gsl.parse_grid(
            self.STRATEGIES / f"{contract}-{window}-1h" / "strategy.py")
        return gsl.solve_cell(grid, symbol=contract, resolver=resolver)

    def test_jup_w1_matches_the_published_estimate(self):
        # 2026-11-04 F-term correction: the close fee is charged exactly once,
        # inside the requirement factor MF = mmr + f, and the equity side stays
        # gross (E(p) = E0 - N + p*Q against MM(p) = MF*p*Q).
        result = self._solver("JUPUSDT", "W1", 0.01)
        self.assertAlmostEqual(0.181531, result["down"]["root"], places=6)
        self.assertAlmostEqual(0.583040, result["up"]["root"], places=6)

    def test_pump_w1_matches_the_published_estimate(self):
        result = self._solver("PUMPUSDT", "W1", 0.01)
        self.assertAlmostEqual(0.00246968, result["down"]["root"], places=8)
        self.assertAlmostEqual(0.00898206, result["up"]["root"], places=8)


if __name__ == "__main__":
    unittest.main()
