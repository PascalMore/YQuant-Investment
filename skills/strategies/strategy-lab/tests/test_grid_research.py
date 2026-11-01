"""Synthetic OFFLINE tests for the grid research trio (Design-06-002 V1.3 §5-§8).

Frozen assertion set: build_cells parameterization/leap years/wire endDate,
derive_geometry, margin_metrics, Sharpe matrix, cross_liquidation state machine,
audit continuity, carrier formats. Everything is synthetic and offline:
no network, no credentials, no strategy import/execution, no real report dirs.
"""

import ast
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import tempfile
import unittest
from unittest import mock

_LAB = Path(__file__).resolve().parents[1]
_MODULE_PATH = _LAB / "scripts" / "grid_research.py"
_STRATEGY_PATH = _LAB / "strategies" / "neutral-grid-four-window-v1" / "strategy.py"

if not _MODULE_PATH.is_file():
    raise AssertionError("required grid_research implementation is missing")
_spec = importlib.util.spec_from_file_location("offline_grid_research", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)

ANCHOR = dt.datetime(2026, 10, 31, tzinfo=dt.timezone.utc)


def utc(y, m, d, hh=0, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def daily(o, c, low, high, day):
    return {
        "open_time_utc": iso(utc(*day)),
        "close_time_utc": iso(utc(*day) + dt.timedelta(days=1)),
        "open": o,
        "close": c,
        "low": low,
        "high": high,
        "provenance_ok": True,
    }


# --- Freeze initial constants from the neutral-grid template (Design §6) ---
TEMPLATE_HASH = hashlib.sha256(
    (_LAB / "strategies" / "neutral-grid-pumpusdt" / "strategy.py").read_bytes()
).hexdigest()


def _read(path):
    return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------- build_cells


class BuildCellsTests(unittest.TestCase):
    """Design §8 item 1: parameterization, dedupe, calendar math, leap years, rejection."""

    def test_default_matrix_sixteen_unique_cells(self):
        cells = gr.build_cells()
        self.assertEqual(16, len(cells))
        ids = [c["cell_id"] for c in cells]
        self.assertEqual(16, len(set(ids)))
        expected = [
            "%s-W%d" % (sym, w)
            for sym in ("PUMPUSDT", "AAVEUSDT", "JUPUSDT", "SUIUSDT")
            for w in (1, 2, 3, 4)
        ]
        self.assertEqual(expected, ids)


    def test_default_windows_match_spec_table(self):
        by_id = {c["cell_id"]: c for c in gr.build_cells()}
        spec_windows = {
            "PUMPUSDT-W1": (utc(2026, 7, 31), utc(2026, 10, 31), 8832),
            "PUMPUSDT-W2": (utc(2026, 4, 30), utc(2026, 7, 31), 8832),
            "PUMPUSDT-W3": (utc(2026, 1, 31), utc(2026, 4, 30), 8544),
            "PUMPUSDT-W4": (utc(2025, 10, 31), utc(2026, 1, 31), 8832),
        }
        for cell_id, (start, end, bars) in spec_windows.items():
            cell = by_id[cell_id]
            self.assertEqual(start, cell["start_utc"], cell_id)
            self.assertEqual(end, cell["end_utc"], cell_id)
            self.assertEqual(bars, cell["expected_15m_bars"], cell_id)
            self.assertEqual(
                (end - start).total_seconds() / 900,
                cell["expected_15m_bars"],
                cell_id,
            )


    def test_explicit_contracts_and_windows_not_default_hardcoded(self):
        cells = gr.build_cells(
            contracts=["XYZUSDT"],
            windows_spec=[
                {"start_utc": utc(2025, 3, 1), "end_utc": utc(2025, 6, 1)},
                {"start_utc": utc(2024, 12, 1), "end_utc": utc(2025, 3, 1)},
            ],
            anchor_utc=utc(2025, 6, 1),
        )
        self.assertEqual(["XYZUSDT-W1", "XYZUSDT-W2"], [c["cell_id"] for c in cells])
        self.assertEqual(utc(2025, 3, 1), cells[0]["start_utc"])
        self.assertEqual(8832, cells[0]["expected_15m_bars"])  # 92 days * 96
        self.assertEqual(8640, cells[1]["expected_15m_bars"])  # 90 days * 96

    def test_rejects_empty_duplicate_and_undropped_anchor(self):
        w = {"start_utc": utc(2026, 7, 31), "end_utc": utc(2026, 10, 31)}
        with self.assertRaises(ValueError):  # empty contract list
            gr.build_cells(contracts=[])
        with self.assertRaises(ValueError):  # duplicate contract
            gr.build_cells(contracts=["PUMPUSDT", "PUMPUSDT"])
        with self.assertRaises(ValueError):  # overlapping windows
            gr.build_cells(
                contracts=["PUMPUSDT"],
                windows_spec=[w, {"start_utc": utc(2026, 9, 1), "end_utc": utc(2026, 12, 1)}],
            )
        with self.assertRaises(ValueError):  # anchor not a reached UTC midnight
            gr.build_cells(anchor_utc=utc(2026, 10, 31, 7, 30))
        # Duplicate anchor-time overlap (start == anchor) is frozen-matrix semantics,
        # asserted via the default table in test_default_windows_match_spec_table.


    def test_anchor_calendar_month_subtraction_and_month_end_truncation(self):
        cells = gr.build_cells(
            contracts=["ABCUSDT"],
            windows_spec=None,
            anchor_utc=utc(2025, 8, 31),  # anchor on a month end
        )
        # W1: 2025-08-31 - 3 months -> 2025-05-31 (same day exists)
        self.assertEqual(utc(2025, 5, 31), cells[0]["start_utc"])
        # W2: 2025-08-31 - 6 months -> 2025-02-28 (Feb has no 31st -> month-end truncation)
        self.assertEqual(utc(2025, 2, 28), cells[1]["start_utc"])
        # W3: 2025-08-31 - 9 months -> 2024-11-30 (Nov has 30 days -> truncation)
        self.assertEqual(utc(2024, 11, 30), cells[2]["start_utc"])


    def test_leap_year_february_truncation(self):
        def starts(anchor_y):
            cells = gr.build_cells(
                contracts=["LUSDT"],
                anchor_utc=utc(anchor_y, 8, 31),
            )
            return [c["start_utc"] for c in cells]

        # 2028-08-31 minus 6 months -> 2028-02-29 (leap year keeps day 29)
        self.assertIn(utc(2028, 2, 29), starts(2028))
        # 2027-08-31 minus 6 months -> 2027-02-28 (non-leap year truncates)
        self.assertIn(utc(2027, 2, 28), starts(2027))
        # Frozen anchor 2026-10-31 minus 6 months -> 2026-04-30 (30-day month)
        w2 = {c["cell_id"]: c for c in gr.build_cells()}["PUMPUSDT-W2"]
        self.assertEqual(utc(2026, 4, 30), w2["start_utc"])


    def test_wire_end_date_is_day_before_half_open_end(self):
        by_id = {c["cell_id"]: c for c in gr.build_cells()}
        expected_end = {
            "PUMPUSDT-W1": "2026-10-30",
            "PUMPUSDT-W2": "2026-07-30",
            "PUMPUSDT-W3": "2026-04-29",
            "PUMPUSDT-W4": "2026-01-30",
        }
        for cell_id, api_end in expected_end.items():
            self.assertEqual(api_end, by_id[cell_id]["api_end_date"], cell_id)
            self.assertEqual(
                iso(by_id[cell_id]["end_utc"] - dt.timedelta(days=1))[:10],
                by_id[cell_id]["api_end_date"],
                cell_id,
            )


    def test_coverage_exact_set_identity_and_anomalies(self):
        start, end = utc(2026, 1, 1), utc(2026, 1, 1, 0, 45)
        identity = {"venue": "gate", "market_type": "swap", "contract": "XYZUSDT"}
        bars = [
            {"open_time_utc": iso(start + dt.timedelta(minutes=15 * i)),
             "close_time_utc": iso(start + dt.timedelta(minutes=15 * (i + 1))),
             "identity": dict(identity), "close": 100.0}
            for i in range(3)
        ]
        result = gr.check_coverage(bars, identity, start, end, 900)
        self.assertEqual("ok", result["status"])
        self.assertEqual(3, result["unique_count"])
        self.assertEqual(1, gr.check_coverage(bars[1:], identity, start, end, 900)["missing_count"])
        conflict = dict(bars[0], close=101.0)
        result = gr.check_coverage(bars + [conflict], identity, start, end, 900)
        self.assertEqual(1, result["duplicate_count"])
        self.assertEqual(1, result["conflicting_count"])
        changed = [dict(bar) for bar in bars]
        changed[1]["identity"] = dict(identity, market_type="spot")
        self.assertEqual(1, gr.check_coverage(changed, identity, start, end, 900)["identity_mismatch_count"])
        changed[2]["close_time_utc"] = iso(end + dt.timedelta(minutes=15))
        result = gr.check_coverage(changed, identity, start, end, 900)
        self.assertNotEqual("ok", result["status"])
        self.assertEqual(1, result["unclosed_count"])

    def test_reached_anchor_guard_is_separate_from_calendar_builder(self):
        future = utc(2028, 8, 31)
        self.assertEqual(4, len(gr.build_cells(["XYZUSDT"], anchor_utc=future)))
        with self.assertRaises(ValueError):
            gr.validate_run_anchor(future, ANCHOR)
        gr.validate_run_anchor(ANCHOR, ANCHOR)


# ------------------------------------------------------------ derive_geometry


def geometry_bars():
    """Twelve synthetic closed daily bars: low=90, high=94.5 (5% band) -> feasible N>=4, N=4."""
    bars = []
    base = dt.date(2025, 12, 20)
    for i in range(12):
        day = (base + dt.timedelta(days=i)).timetuple()[:3]
        bars.append(daily(92.0, 92.0, 90.0, 94.5, day))
    return bars


class DeriveGeometryTests(unittest.TestCase):

    def test_geometry_happy_path_frozen_example(self):
        start = utc(2026, 1, 1)
        result = gr.derive_geometry(geometry_bars(), start)
        self.assertEqual(90.0, result["L"])
        self.assertEqual(94.5, result["U"])
        # g(N)=100*((U/L)^(1/N)-1); g(3)=1.64>1.5 infeasible, g(4)=1.2272 feasible -> N=4.
        self.assertEqual(4, result["N"])
        expected_g = 100.0 * ((94.5 / 90.0) ** (1.0 / 4) - 1.0)
        self.assertAlmostEqual(expected_g, result["g_pct"], places=10)
        self.assertTrue(0.45 <= result["g_pct"] <= 1.5)
        self.assertEqual(5, result["grid_lines"])  # N + 1
        # SPEC §3.2: every continuous sample of 2..364 bars is short history.
        self.assertTrue(result["short_history"])
        self.assertEqual(12, result["training_count"])
        # Training uses only bars closed at or before window start.
        self.assertEqual(iso(utc(2025, 12, 31) + dt.timedelta(days=1)), result["training_end_utc"])


    def test_geometry_short_history_flag(self):
        bars = geometry_bars()[:5]
        result = gr.derive_geometry(bars, utc(2026, 1, 1))
        self.assertTrue(result["short_history"])
        self.assertEqual(5, result["training_count"])
        self.assertGreaterEqual(result["N"], 3)

    def test_geometry_rejections(self):
        start = utc(2026, 1, 1)
        with self.assertRaises(ValueError):  # fewer than two closed bars
            gr.derive_geometry(geometry_bars()[:1], start)
        with self.assertRaises(ValueError):  # internal gap in daily history
            gapped = geometry_bars()
            gapped[5]["open_time_utc"] = iso(utc(2025, 12, 25, 12))
            gr.derive_geometry(gapped, start)
        with self.assertRaises(ValueError):  # unknown provenance
            unproven = geometry_bars()
            unproven[3]["provenance_ok"] = False
            gr.derive_geometry(unproven, start)
        # Band too wide for any feasible N -> no-feasible-geometry, thresholds untouched.
        wide = geometry_bars()
        for bar in wide:
            bar["low"], bar["high"] = 1.0, 1000000.0
        result = gr.derive_geometry(wide, start)
        self.assertEqual("no-feasible-geometry", result.get("status"))
        self.assertEqual(200, result["n_max"])  # thresholds unchanged
        self.assertEqual(1.5, result["g_upper"])
        self.assertEqual(0.45, result["g_lower"])


    def test_geometry_uses_at_most_365_closed_bars(self):
        bars = []
        base = dt.date(2024, 6, 1)
        for i in range(500):
            day = (base + dt.timedelta(days=i)).timetuple()[:3]
            bars.append(daily(100, 100, 90.0, 121.8, day))
        result = gr.derive_geometry(bars, utc(2026, 1, 1))
        self.assertEqual(365, result["training_count"])


    def test_geometry_excludes_window_day_and_future_extremes(self):
        bars = geometry_bars()
        baseline = gr.derive_geometry(bars, utc(2026, 1, 1))
        future = daily(100, 100, 1, 1000000, (2026, 1, 1))
        result = gr.derive_geometry(bars + [future], utc(2026, 1, 1))
        for field in ("L", "U", "N", "training_count"):
            self.assertEqual(baseline[field], result[field])


# ------------------------------------------------------------- margin_metrics


METRIC_ROWS = [
    {"time": iso(utc(2026, 1, 1, 0, 15)), "equity": 1200.0},
    {"time": iso(utc(2026, 1, 1, 0, 30)), "equity": 900.0},
]


class MarginMetricsTests(unittest.TestCase):


    def test_metrics_1000_1200_900_frozen_example(self):
        result = gr.margin_metrics(METRIC_ROWS)
        self.assertEqual(-100.0, result["net_pnl"])
        self.assertAlmostEqual(-10.0, result["margin_return_pct"], places=10)
        self.assertAlmostEqual(1200.0, result["peak_equity"], places=10)
        self.assertAlmostEqual(25.0, result["max_drawdown_pct"], places=10)
        self.assertEqual("ok", result["status"])
        # Peak P(t)=max(1000, max E(s)) includes the initial margin floor.
        self.assertNotIn(None, [result["peak_equity"]])


    def test_metrics_na_reasons(self):
        bankrupt = [{"time": iso(utc(2026, 1, 1, 0, 15)), "equity": -50.0}]
        result = gr.margin_metrics(bankrupt)
        self.assertEqual("N/A", result["margin_return_pct"])
        self.assertIsNotNone(result.get("reason"))
        with self.assertRaises(ValueError):
            gr.margin_metrics([{"equity": 1000.0}])  # missing time field
        single = gr.margin_metrics([{"time": iso(utc(2026, 1, 1, 0, 15)), "equity": 1010.0}])
        self.assertEqual("N/A", single["sharpe"])  # fewer than two per-bar returns


# -------------------------------------------------------------------- sharpe


class SharpeTests(unittest.TestCase):


    def test_sharpe_happy_path_population_ddof_zero(self):
        times = [iso(utc(2026, 1, 1) + dt.timedelta(minutes=m)) for m in (15, 30, 45, 60)]
        equities = [1100.0, 1050.0, 1150.0, 1200.0]
        rows = [{"time": t, "equity": e} for t, e in zip(times, equities)]
        result = gr.margin_metrics(rows)
        returns = [
            equities[i] / equities[i - 1] - 1 for i in range(1, len(equities))
        ]
        expected = statistics.mean(returns) / statistics.pstdev(returns) * math.sqrt(35040)
        self.assertAlmostEqual(expected, result["sharpe"], places=8)
        self.assertEqual("ok", result["status"])


    def test_sharpe_anomaly_matrix_na_with_reasons(self):
        flat = [
            {"time": iso(utc(2026, 1, 1, 0, 15)), "equity": 1000.0},
            {"time": iso(utc(2026, 1, 1, 0, 30)), "equity": 1000.0},
        ]
        result = gr.margin_metrics(flat)
        self.assertEqual("N/A", result["sharpe"])
        self.assertIn("vol", result["reason"].lower())

        single = gr.margin_metrics([{"time": iso(utc(2026, 1, 1, 0, 15)), "equity": 1005.0}])
        self.assertEqual("N/A", single["sharpe"])

        negative = [
            {"time": iso(utc(2026, 1, 1, 0, 15)), "equity": 1200.0},
            {"time": iso(utc(2026, 1, 1, 0, 30)), "equity": -5.0},
            {"time": iso(utc(2026, 1, 1, 0, 45)), "equity": 900.0},
        ]
        result = gr.margin_metrics(negative)
        self.assertEqual("N/A", result["sharpe"])
        self.assertIsNotNone(result["reason"])

        with self.assertRaises(ValueError):
            gr.margin_metrics(
                [{"time": "not-a-time", "equity": 1000.0}, {"time": iso(utc(2026, 1, 1, 0, 30)), "equity": 1001.0}]
            )


    def test_compressed_curve_is_not_independent_verification(self):
        self.assertTrue(
            gr.COMPRESSED_EQUITY_LIMITATION is not None
            and "sharpe" in gr.COMPRESSED_EQUITY_LIMITATION.lower()
        )


    def test_sharpe_missing_bar_and_nonfinite_equity(self):
        missing = [dict(row) for row in METRIC_ROWS]
        missing[1]["time"] = iso(utc(2026, 1, 1, 0, 45))
        result = gr.margin_metrics(missing)
        self.assertEqual("N/A", result["sharpe"])
        self.assertIn("bar", result["reason"])
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                gr.margin_metrics([dict(METRIC_ROWS[0], equity=value)])
        account_rows = [{"time": METRIC_ROWS[0]["time"],
                         "realized_net_pnl": 25.0, "unrealized_pnl": -5.0}]
        self.assertEqual(20.0, gr.margin_metrics(account_rows)["net_pnl"])
        nonpositive = gr.margin_metrics([dict(METRIC_ROWS[0], equity=-50.0)])
        self.assertGreater(nonpositive["raw_max_drawdown_pct"], 100.0)


# --------------------------------------------------------- cross_liquidation


SNAP_LONG = {
    "equity": 50.0,
    "q_long": 1.0,
    "q_short": 0.0,
    "avg_long": 100.0,
    "avg_short": 0.0,
    "mark_price": 100.0,
    "available_margin": None,
}


def snap(**overrides):
    snapshot = dict(SNAP_LONG)
    snapshot.update(overrides)
    return snapshot


class CrossLiquidationTests(unittest.TestCase):


    def test_long_only_downward_root(self):
        result = gr.cross_liquidation(snap(), 0.005, 0.0005)
        self.assertEqual("cross_linear_v1", result["formula_version"])
        self.assertAlmostEqual(50.0 / 0.9945, result["downward_liquidation_price"], places=8)
        self.assertIsNone(result["upward_liquidation_price"])
        self.assertLess(result["downward_liquidation_price"], 100.0)
        # An exactly representable zero residual is valid; record the actual residual.
        price = result["downward_liquidation_price"]
        expected_residual = abs(50.0 + (price - 100.0) - 0.005 * price - 0.0005 * price)
        self.assertEqual(expected_residual, result["residual_abs"])
        self.assertLessEqual(result["residual_abs"], result["residual_tol"])


    def test_short_only_upward_root(self):
        result = gr.cross_liquidation(
            snap(equity=50.0, q_long=0.0, q_short=1.0, avg_long=0.0, avg_short=100.0), 0.005, 0.0005
        )
        self.assertAlmostEqual(150.0 / 1.0055, result["upward_liquidation_price"], places=8)
        self.assertIsNone(result["downward_liquidation_price"])


    def test_hedged_equal_notional_has_upward_root(self):
        result = gr.cross_liquidation(
            snap(equity=1000.0, q_long=1.0, q_short=1.0, avg_long=100.0, avg_short=100.0), 0.005, 0.0005
        )
        self.assertIsNone(result["downward_liquidation_price"])
        self.assertAlmostEqual(-1000.0 / -0.011, result["upward_liquidation_price"], places=6)


    def test_sensitivity_mmr_shifts_root(self):
        base = gr.cross_liquidation(snap(), 0.005, 0.0005)
        low = gr.cross_liquidation(snap(), 0.004, 0.0005)
        high = gr.cross_liquidation(snap(), 0.006, 0.0005)
        self.assertLess(low["downward_liquidation_price"], base["downward_liquidation_price"])
        self.assertGreater(high["downward_liquidation_price"], base["downward_liquidation_price"])


    def test_a_near_zero_no_finite_solution_and_already_breached(self):
        # Exact-zero A: qL=201, qS=199, fee=0 -> (qL-qS) == mmr*(qL+qS) == 2.0.
        hedged = dict(equity=1300.0, q_long=201.0, q_short=199.0, avg_long=100.0, avg_short=100.0, mark_price=100.0)
        result = gr.cross_liquidation(hedged, 0.005, 0.0)
        self.assertEqual("no_finite_solution", result["status"])
        breached = dict(hedged, equity=200.0)  # B == 0 with A==0 -> already_breached
        result = gr.cross_liquidation(breached, 0.005, 0.0)
        self.assertEqual("already_breached", result["status"])


    def test_already_at_or_below_maintenance(self):
        result = gr.cross_liquidation(snap(equity=0.3), 0.005, 0.0005)
        self.assertEqual("already_at_or_below_maintenance", result["status"])


    def test_no_positive_solution_when_root_not_positive(self):
        # Healthy long: B>0, A>0 -> formal root negative -> no_positive_solution.
        result = gr.cross_liquidation(snap(equity=1000.0), 0.005, 0.0005)
        self.assertEqual("no_positive_solution", result["status"])
        self.assertIsNone(result["downward_liquidation_price"])


    def test_no_position_no_long_no_short_and_missing_fields(self):
        flat = snap(equity=1000.0, q_long=0.0, q_short=0.0, avg_long=0.0, avg_short=0.0)
        self.assertEqual("no_position", gr.cross_liquidation(flat, 0.005, 0.0005)["status"])
        long_only_missing_avg = snap(equity=50.0)
        del long_only_missing_avg["avg_long"]
        self.assertEqual("N/A", gr.cross_liquidation(long_only_missing_avg, 0.005, 0.0005)["status"])
        long_side = snap(equity=50.0, q_short=0.0)
        self.assertNotIn("no_long", str(long_side))

    def test_rejects_non_finite_inputs(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                gr.cross_liquidation(snap(equity=bad), 0.005, 0.0005)
            with self.assertRaises(ValueError):
                gr.cross_liquidation(snap(equity=50.0, mark_price=bad), 0.005, 0.0005)


    def test_price_proxy_and_unknown_margin_recorded(self):
        result = gr.cross_liquidation(snap(), 0.005, 0.0005)
        self.assertEqual("last_not_mark", result["price_proxy"])
        self.assertEqual("UNKNOWN", result["available_margin_status"])


# ------------------------------------------------- summarize_cells / audit


def cell_rows():
    return [
        {"cell_id": "PUMPUSDT-W1", "contract": "PUMPUSDT", "window": "W1", "margin_return_pct": 10.0, "sharpe": 1.2, "max_drawdown_pct": 5.0, "N": 50},
        {"cell_id": "PUMPUSDT-W2", "contract": "PUMPUSDT", "window": "W2", "margin_return_pct": None, "sharpe": 0.8, "max_drawdown_pct": 7.0, "N": 60},
        {"cell_id": "PUMPUSDT-W3", "contract": "PUMPUSDT", "window": "W3", "margin_return_pct": -5.0, "sharpe": None, "max_drawdown_pct": 9.0, "N": 70},
        {"cell_id": "PUMPUSDT-W4", "contract": "PUMPUSDT", "window": "W4", "margin_return_pct": 20.0, "sharpe": 1.0, "max_drawdown_pct": 6.0, "N": 80},
    ]


class SummarizeCellsTests(unittest.TestCase):


    def test_summary_row_structure_and_effective_means(self):
        summary = gr.summarize_cells(cell_rows())
        # One supplied contract summarizes to one row; the full frozen matrix gives four.
        self.assertEqual(1, len(summary))
        all_cells = [
            dict(cell, contract=contract, cell_id=f"{contract}-{cell['window']}")
            for contract in gr.DEFAULT_CONTRACTS for cell in cell_rows()
        ]
        self.assertEqual(4, len(gr.summarize_cells(all_cells)))
        row = summary[0]
        self.assertEqual("PUMPUSDT", row["contract"])
        # mean includes the losing window (-5) and excludes the N/A; n/4 shown.
        self.assertAlmostEqual(25.0 / 3.0, row["margin_return_pct_mean"], places=10)
        self.assertEqual(3, row["margin_return_pct_valid_count"])
        self.assertAlmostEqual(1.0, row["sharpe_mean"], places=10)
        self.assertEqual(3, row["sharpe_valid_count"])
        self.assertAlmostEqual(6.75, row["max_drawdown_pct_mean"], places=10)
        self.assertEqual(4, row["N_valid_count"])
        self.assertAlmostEqual((50 + 60 + 70 + 80) / 4.0, row["N_mean"], places=10)


    def test_summary_missing_cell_is_na_with_count(self):
        partial = [c for c in cell_rows() if c["window"] != "W3"]
        summary = gr.summarize_cells(partial)
        self.assertEqual(1, len(summary))
        self.assertEqual(3, summary[0]["windows_present"])
        self.assertEqual(1, summary[0]["windows_missing"])


def audit_logs(seqs, bankruptcy_at=None):
    """Build GRID_INIT/GRID_AUDIT/GRID_END controlled log lines (Design §6 fields)."""
    base = utc(2026, 1, 1, 10, 0)
    entries = [
        {
            "kind": "init",
            "schema": "GRID_INIT_V1",
            "cell": "PUMPUSDT-W1",
            "params": {"N": 50, "g_pct": 1.2},
            "training_summary": {"L": 90.0, "U": 121.8},
            "start_utc": iso(base),
            "end_utc": iso(base + dt.timedelta(minutes=15 * max(seqs))),
        }
    ]
    prev = None
    for i, seq in enumerate(seqs):
        equity = 0.0 if seq == bankruptcy_at else 1000.0 + seq
        entries.append(
            {
                "kind": "audit",
                "schema": "GRID_AUDIT_V1",
                "cell": "PUMPUSDT-W1",
                "seq": seq,
                "bar_open": iso(base + dt.timedelta(minutes=15 * i)),
                "bar_close": iso(base + dt.timedelta(minutes=15 * (i + 1))),
                "ohlcv_units": {"price": "USDT", "volume": "base"},
                "ohlcv": {"open": 100.0, "high": 101.0, "low": 99.0,
                          "close": 100.0, "volume": 10000.0},
                "equity": equity,
                "q_long": 1.0,
                "q_short": 0.5,
                "avg_long": 100.0,
                "avg_short": 101.0,
                "gross": 150.0,
                "gross_to_equity": 150.0 / equity if equity > 0 else None,
                "reserved_open_notional": 10.0,
                "risk_action": "hold",
                "status_changes": 1,
                "peak_equity": max(1000.0, *(1000.0 + s for s in seqs[:i + 1] if s != bankruptcy_at)),
                "drawdown_pct": 100.0 if equity == 0 else 0.0,
                "previous_seq": prev,
            }
        )
        prev = seq
    entries.append(
        {
            "kind": "end",
            "schema": "GRID_END_V1",
            "cell": "PUMPUSDT-W1",
            "bars_total": len(seqs),
            "peak_equity": max(1000.0, *(1000.0 + s for s in seqs if s != bankruptcy_at)),
            "net_pnl": -1000.0 if seqs[-1] == bankruptcy_at else float(seqs[-1]),
            # Complete sufficient statistics (Design §6/§8-7), derived from the
            # same equity path as the AUDIT rows above; 0-equity bars invalidate.
            "max_drawdown_pct": 100.0 if bankruptcy_at in seqs else 0.0,
            "return_count": len([1 for left, right in zip(
                [0.0 if s == bankruptcy_at else 1000.0 + s for s in seqs],
                [0.0 if s == bankruptcy_at else 1000.0 + s for s in seqs][1:])
                if left > 0 and right > 0]),
            "return_sum": sum(right / left - 1 for left, right in zip(
                [0.0 if s == bankruptcy_at else 1000.0 + s for s in seqs],
                [0.0 if s == bankruptcy_at else 1000.0 + s for s in seqs][1:])
                if left > 0 and right > 0),
            "return_square_sum": sum((right / left - 1) ** 2 for left, right in zip(
                [0.0 if s == bankruptcy_at else 1000.0 + s for s in seqs],
                [0.0 if s == bankruptcy_at else 1000.0 + s for s in seqs][1:])
                if left > 0 and right > 0),
            "return_valid": bool(seqs) and all(
                s != bankruptcy_at for s in seqs),
            "risk_breach_observed": False,
        }
    )
    return ["%s %s" % (e.pop("schema"), json.dumps(e, sort_keys=True)) for e in entries]


def audit_equity_path(equities):
    """Construct synthetic statistics independently; never call production metric code."""
    logs = audit_logs(list(range(1, len(equities) + 1)))
    peaks = [max(1000.0, *equities[:index + 1]) for index in range(len(equities))]
    drawdowns = [100 * (peak - equity) / peak for peak, equity in zip(peaks, equities)]
    changes = [right / left - 1 for left, right in zip(equities, equities[1:])
               if left > 0 and right > 0]
    for index, (equity, peak, drawdown) in enumerate(zip(equities, peaks, drawdowns), 1):
        audit = json.loads(logs[index].split(" ", 1)[1])
        audit.update(equity=equity, peak_equity=peak, drawdown_pct=drawdown,
                     gross_to_equity=150.0 / equity if equity > 0 else None)
        logs[index] = "GRID_AUDIT_V1 " + json.dumps(audit, sort_keys=True)
    end = json.loads(logs[-1].split(" ", 1)[1])
    end.update(net_pnl=equities[-1] - 1000.0, peak_equity=peaks[-1],
               max_drawdown_pct=max(drawdowns), return_count=len(changes),
               return_sum=sum(changes), return_square_sum=sum(change * change for change in changes),
               return_valid=all(equity > 0 for equity in equities))
    logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
    return logs


class ReconcileAuditTests(unittest.TestCase):

    def _expected_times(self, n):
        base = utc(2026, 1, 1, 10, 0)
        return [iso(base + dt.timedelta(minutes=15 * i)) for i in range(1, n + 1)]


    def test_reconcile_happy_path(self):
        logs = audit_logs([1, 2, 3])
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("ok", result["status"])
        self.assertEqual(3, result["bars_checked"])
        self.assertEqual([], result["missing_bar_closes"])
        self.assertFalse(result["bankruptcy_skipped_callback"])
        self.assertEqual("GRID_INIT_V1", result["init_schema"])
        self.assertEqual("GRID_END_V1", result["end_schema"])


    def test_missing_bar_close_is_unknown_with_gap_list(self):
        logs = audit_logs([1, 2, 3])
        del logs[2]  # drop the seq=2 audit bar
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertIn(result["status"], ("unknown", "fail"))
        self.assertEqual(1, len(result["missing_bar_closes"]))


    def test_duplicate_seq_and_conflicting_time_rejected(self):
        logs = audit_logs([1, 2, 3])
        logs.insert(2, logs[2])  # duplicate seq=2 line
        with self.assertRaises(ValueError):
            gr.reconcile_audit(logs, "PUMPUSDT-W1")
        conflicting = audit_logs([1, 2, 3])
        parsed = json.loads(conflicting[2].split(" ", 1)[1])
        parsed["bar_close"] = iso(utc(2026, 1, 1, 12, 0))
        conflicting[2] = "GRID_AUDIT_V1 %s" % json.dumps(parsed, sort_keys=True)
        with self.assertRaises(ValueError):
            gr.reconcile_audit(conflicting, "PUMPUSDT-W1")


    def test_bankruptcy_skipped_callback_is_fail_not_crash(self):
        # Native bankruptcy branch skips later callbacks: seq 3 never gets a log line.
        logs = audit_logs([1, 2], bankruptcy_at=2)
        parsed_end = json.loads(logs[-1].split(" ", 1)[1])
        parsed_end["bars_total"] = 3  # native kept counting bars but callbacks stopped
        logs[-1] = "GRID_END_V1 %s" % json.dumps(parsed_end, sort_keys=True)
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("fail", result["status"])
        self.assertTrue(result["bankruptcy_skipped_callback"])
        self.assertTrue(result.get("audit_incomplete", False))

    def _assert_end_statistic_mismatch(self, field, value):
        logs = audit_logs([1, 2, 3])
        end = json.loads(logs[-1].split(" ", 1)[1])
        end[field] = value  # Only this well-typed, in-range END value is changed.
        logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertIn(result["status"], ("unknown", "fail"))
        self.assertNotEqual("pass", result["bar_close_audit"])
        self.assertIn("END " + field + " mismatch", result["reason"])
        self.assertEqual(3, result["bars_checked"])
        self.assertEqual([], result["missing_bar_closes"])

    def test_end_max_drawdown_legal_value_mismatch(self):
        self._assert_end_statistic_mismatch("max_drawdown_pct", 1.0)

    def test_end_return_count_legal_value_mismatch(self):
        self._assert_end_statistic_mismatch("return_count", 1)

    def test_end_return_sum_legal_value_mismatch(self):
        self._assert_end_statistic_mismatch("return_sum", 0.25)

    def test_end_return_square_sum_legal_value_mismatch(self):
        self._assert_end_statistic_mismatch("return_square_sum", 0.25)

    def test_end_return_valid_legal_value_mismatch(self):
        self._assert_end_statistic_mismatch("return_valid", False)

    def test_end_full_statistics_match_nonmonotonic_equity(self):
        logs = audit_equity_path([900.0, 1200.0, 840.0, 1100.0, 1000.0])
        end = json.loads(logs[-1].split(" ", 1)[1])
        self.assertEqual(30.0, end["max_drawdown_pct"])
        self.assertEqual(4, end["return_count"])
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("ok", result["status"])
        self.assertEqual("pass", result["bar_close_audit"])
        self.assertIsNone(result["reason"])
        self.assertFalse(result["audit_incomplete"])

    def test_end_float_statistics_tolerance_inside_and_outside(self):
        # Nonzero values exercise REL_TOL; zero values exercise ABS_TOL.
        for equities in ([1000.0, 1100.0, 1000.0], [1000.0, 1000.0, 1000.0]):
            for field in ("max_drawdown_pct", "return_sum", "return_square_sum"):
                for multiplier, accepted in ((0.5, True), (2.0, False)):
                    with self.subTest(equities=equities, field=field, multiplier=multiplier):
                        logs = audit_equity_path(equities)
                        end = json.loads(logs[-1].split(" ", 1)[1])
                        tolerance = max(gr.ABS_TOL, gr.REL_TOL * abs(end[field]))
                        end[field] += multiplier * tolerance
                        logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
                        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
                        if accepted:
                            self.assertEqual("ok", result["status"])
                            self.assertEqual("pass", result["bar_close_audit"])
                        else:
                            self.assertEqual("unknown", result["status"])
                            self.assertEqual("unknown", result["bar_close_audit"])
                            self.assertIn("END " + field + " mismatch", result["reason"])

    def test_first_bar_has_no_initial_margin_return(self):
        logs = audit_equity_path([900.0])
        end = json.loads(logs[-1].split(" ", 1)[1])
        self.assertEqual((0, 0, 0, True), tuple(end[field] for field in (
            "return_count", "return_sum", "return_square_sum", "return_valid")))
        self.assertEqual("ok", gr.reconcile_audit(logs, "PUMPUSDT-W1")["status"])
        # A fabricated initialization-to-first-bar return must not reconcile.
        end.update(return_count=1, return_sum=-0.1, return_square_sum=0.01)
        logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("unknown", result["status"])
        for field in ("return_count", "return_sum", "return_square_sum"):
            self.assertIn("END " + field + " mismatch", result["reason"])

    def test_nonpositive_equity_sticky_invalid_and_positive_adjacent_returns(self):
        for nonpositive in (0.0, -100.0):
            with self.subTest(nonpositive=nonpositive):
                logs = audit_equity_path([1000.0, 1100.0, nonpositive, 1200.0, 1320.0])
                end = json.loads(logs[-1].split(" ", 1)[1])
                self.assertEqual(2, end["return_count"])
                self.assertAlmostEqual(0.2, end["return_sum"])
                self.assertAlmostEqual(0.02, end["return_square_sum"])
                self.assertIs(end["return_valid"], False)
                result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
                self.assertEqual("fail", result["status"])
                self.assertEqual("fail", result["bar_close_audit"])
                self.assertIsNone(result["reason"])
                self.assertFalse(result["audit_incomplete"])
                for field, value in (("return_count", 3), ("return_sum", 0.4),
                                     ("return_square_sum", 0.04), ("return_valid", True)):
                    altered = dict(end, **{field: value})
                    result = gr.reconcile_audit(logs[:-1] + [
                        "GRID_END_V1 " + json.dumps(altered, sort_keys=True)], "PUMPUSDT-W1")
                    self.assertEqual("fail", result["status"])
                    self.assertEqual("fail", result["bar_close_audit"])
                    self.assertIn("END " + field + " mismatch", result["reason"])

    def test_nonpositive_first_bar_invalidates_without_return(self):
        for equities in ([0.0], [-250.0], [0.0, -250.0, 0.0, 1200.0, 1320.0]):
            with self.subTest(equities=equities):
                logs = audit_equity_path(equities)
                result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
                self.assertEqual("fail", result["status"])
                self.assertIsNone(result["reason"])
                end = json.loads(logs[-1].split(" ", 1)[1])
                end["return_valid"] = True
                logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
                self.assertIn("END return_valid mismatch",
                              gr.reconcile_audit(logs, "PUMPUSDT-W1")["reason"])

    def test_negative_equity_drawdown_over_100_parsed_and_not_clipped(self):
        logs = audit_equity_path([1000.0, -250.0, 1000.0])
        end = json.loads(logs[-1].split(" ", 1)[1])
        self.assertEqual(125.0, end["max_drawdown_pct"])
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("fail", result["status"])
        self.assertEqual("fail", result["bar_close_audit"])
        self.assertEqual(125.0, result["metrics"]["max_drawdown_pct"])
        self.assertIsNone(result["reason"])
        self.assertFalse(result["audit_incomplete"])
        end["max_drawdown_pct"] = 100.0
        logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("fail", result["status"])
        self.assertIn("END max_drawdown_pct mismatch", result["reason"])
        self.assertEqual(125.0, result["metrics"]["max_drawdown_pct"])

    def test_incomplete_audit_never_reconciles_statistics_from_subset(self):
        for missing_index in (1, 2, 3):
            for breach in (False, True):
                with self.subTest(missing_index=missing_index, breach=breach):
                    logs = audit_equity_path([1000.0, 1100.0, 1000.0])
                    if breach:
                        end = json.loads(logs[-1].split(" ", 1)[1])
                        end["risk_breach_observed"] = True
                        logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
                    del logs[missing_index]
                    result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
                    self.assertEqual("fail" if breach else "unknown", result["status"])
                    self.assertEqual("fail" if breach else "unknown", result["bar_close_audit"])
                    self.assertEqual([self._expected_times(3)[missing_index - 1]],
                                     result["missing_bar_closes"])
                    self.assertTrue(result["audit_incomplete"])
                    self.assertIn("missing expected bar closes", result["reason"])
                    for field in ("max_drawdown_pct", "return_count", "return_sum",
                                  "return_square_sum", "return_valid"):
                        self.assertNotIn("END " + field + " mismatch", result["reason"])
                    if breach:
                        self.assertIn("risk_breach_observed", result["reason"])

    def test_previous_seq_gap_does_not_attest_end_statistics(self):
        logs = audit_equity_path([1000.0, 1100.0, 1000.0])
        audit = json.loads(logs[2].split(" ", 1)[1])
        audit["previous_seq"] = None
        logs[2] = "GRID_AUDIT_V1 " + json.dumps(audit, sort_keys=True)
        end = json.loads(logs[-1].split(" ", 1)[1])
        end["return_count"] = 1
        logs[-1] = "GRID_END_V1 " + json.dumps(end, sort_keys=True)
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("unknown", result["status"])
        self.assertEqual("unknown", result["bar_close_audit"])
        self.assertIn("seq/previous_seq gap", result["reason"])
        self.assertNotIn("END return_count mismatch", result["reason"])

    def test_end_requires_full_sufficient_statistics(self):
        """Design §6/§8-7: END must carry five statistics plus risk_breach_observed."""
        for field in ("max_drawdown_pct", "return_count", "return_sum",
                      "return_square_sum", "return_valid", "risk_breach_observed"):
            logs = audit_logs([1, 2, 3])
            parsed = json.loads(logs[-1].split(" ", 1)[1])
            parsed.pop(field)
            logs[-1] = "GRID_END_V1 %s" % json.dumps(parsed, sort_keys=True)
            with self.assertRaises(ValueError):
                gr.reconcile_audit(logs, "PUMPUSDT-W1")

    def test_end_corrupted_statistics_rejected(self):
        """Design §8-7: type/range damage on END statistics is rejected."""
        expected = {"max_drawdown_pct": 0.0, "return_count": 2,
                    "return_sum": (1002.0 / 1001.0 - 1) + (1003.0 / 1002.0 - 1),
                    "return_square_sum": (1002.0 / 1001.0 - 1) ** 2 + (1003.0 / 1002.0 - 1) ** 2,
                    "return_valid": True, "risk_breach_observed": False}
        parsed = json.loads(audit_logs([1, 2, 3])[-1].split(" ", 1)[1])
        parsed.update(expected)
        logs = ["GRID_END_V1 %s" % json.dumps(parsed, sort_keys=True)] + audit_logs([1, 2, 3])[:-1]
        self.assertEqual("ok", gr.reconcile_audit(logs, "PUMPUSDT-W1")["status"])
        for field, bad in (("max_drawdown_pct", -1.0), ("return_count", 3.5),
                           ("return_count", -1), ("return_count", True),
                           ("return_valid", "yes"), ("risk_breach_observed", 1),
                           ("return_sum", float("nan"))):
            parsed = json.loads(audit_logs([1, 2, 3])[-1].split(" ", 1)[1])
            parsed.update(expected)
            parsed[field] = bad
            logs = ["GRID_END_V1 %s" % json.dumps(parsed, sort_keys=True)] + audit_logs([1, 2, 3])[:-1]
            with self.assertRaises(ValueError):
                gr.reconcile_audit(logs, "PUMPUSDT-W1")

    def test_reconcile_fails_when_breach_flag_survives_but_bar_recovered(self):
        """Design §6 '保留越限事实': retained risk_breach_observed=True must FAIL even
        if the closing bar's instantaneous equity/ratio/drawdown have recovered."""
        logs = audit_logs([1, 2, 3])
        parsed = json.loads(logs[1].split(" ", 1)[1])
        parsed["risk_breach_observed"] = True
        logs[1] = "GRID_AUDIT_V1 %s" % json.dumps(parsed, sort_keys=True)
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("fail", result["status"])
        self.assertIn("risk_breach_observed", result["reason"])
        self.assertEqual("fail", result["bar_close_audit"])
        # END breach fact is equally decisive.
        logs = audit_logs([1, 2, 3])
        parsed = json.loads(logs[-1].split(" ", 1)[1])
        parsed.update({"max_drawdown_pct": 0.0, "return_count": 2,
                       "return_sum": (1002.0 / 1001.0 - 1) + (1003.0 / 1002.0 - 1),
                       "return_square_sum": (1002.0 / 1001.0 - 1) ** 2 + (1003.0 / 1002.0 - 1) ** 2,
                       "return_valid": True, "risk_breach_observed": True})
        logs[-1] = "GRID_END_V1 %s" % json.dumps(parsed, sort_keys=True)
        result = gr.reconcile_audit(logs, "PUMPUSDT-W1")
        self.assertEqual("fail", result["status"])
        self.assertIn("risk_breach_observed", result["reason"])


    def test_prefix_and_required_fields_validation(self):
        logs = audit_logs([1, 2])
        bad_prefix = list(logs)
        parsed = json.loads(bad_prefix[1].split(" ", 1)[1])
        bad_prefix[1] = "GRID_AUDIT_V0 %s" % json.dumps(parsed, sort_keys=True)
        result = gr.reconcile_audit(bad_prefix, "PUMPUSDT-W1")
        self.assertIn(result["status"], ("fail", "unknown"))
        missing_field = list(logs)
        parsed = json.loads(missing_field[1].split(" ", 1)[1])
        parsed.pop("previous_seq")
        missing_field[1] = "GRID_AUDIT_V1 %s" % json.dumps(parsed, sort_keys=True)
        with self.assertRaises(ValueError):
            gr.reconcile_audit(missing_field, "PUMPUSDT-W1")


    def test_expected_boundaries_detect_truncated_edges_and_native_mismatch(self):
        cell = {"cell_id": "PUMPUSDT-W1", "start_utc": utc(2026, 1, 1, 10),
                "end_utc": utc(2026, 1, 1, 10, 45), "native_net_pnl": 3.0,
                "native_bars_total": 3, "native_peak_equity": 1003.0}
        logs = audit_logs([1, 2, 3])
        self.assertEqual("checked", gr.reconcile_audit(logs, cell)["native_reconciliation"])
        for index, missing in ((1, "2026-01-01T10:15:00Z"), (-2, "2026-01-01T10:45:00Z")):
            truncated = list(logs)
            del truncated[index]
            result = gr.reconcile_audit(truncated, cell)
            self.assertNotEqual("ok", result["status"])
            self.assertEqual([missing], result["missing_bar_closes"])
        result = gr.reconcile_audit(logs, dict(cell, native_net_pnl=999.0))
        self.assertNotEqual("ok", result["status"])
        self.assertIn("native_net_pnl", result["reason"])
        parsed = json.loads(logs[0].split(" ", 1)[1])
        del parsed["start_utc"]
        unbounded = ["GRID_INIT_V1 " + json.dumps(parsed)] + logs[1:]
        self.assertEqual("unknown", gr.reconcile_audit(unbounded, "PUMPUSDT-W1")["status"])

    def test_missing_seq_and_visible_risk_breach(self):
        logs = audit_logs([1, 2, 3])
        parsed = json.loads(logs[1].split(" ", 1)[1])
        parsed.pop("seq")
        with self.assertRaises(ValueError):
            gr.reconcile_audit([logs[0], "GRID_AUDIT_V1 " + json.dumps(parsed)] + logs[2:], "PUMPUSDT-W1")
        parsed = json.loads(logs[1].split(" ", 1)[1])
        parsed.update(gross=3003.0, gross_to_equity=3.0)
        breached = [logs[0], "GRID_AUDIT_V1 " + json.dumps(parsed)] + logs[2:]
        result = gr.reconcile_audit(breached, "PUMPUSDT-W1")
        self.assertEqual("fail", result["status"])
        self.assertEqual("fail", result["bar_close_audit"])
        self.assertEqual("unknown", result["event_audit"])
        self.assertEqual("not_observable", result["intrabar_tick_audit"])


# --------------------------------------------- manifest / carrier formats


class CarrierFormatTests(unittest.TestCase):
    """Design §8 item 8: synthetic carrier formats in a temp dir only."""


    def test_manifest_schema_and_state_machine(self):
        cells = gr.build_cells()
        manifest = gr.build_manifest(cells)
        self.assertEqual(1, manifest["schema_version"])
        self.assertEqual(16, len(manifest["items"]))
        allowed = {
            "planned", "prechecked", "submitting", "submitted", "succeeded",
            "history_insufficient", "insufficient_evidence", "failed",
            "not_submitted_due_to_stop",
        }
        for item in manifest["items"]:
            self.assertIn(item["status"], allowed)
            self.assertIsNone(item["job_id"])
            self.assertIsNone(item["run_id"])
            self.assertTrue(item.get("reason"))
            self.assertIn("idempotency_key", item)
            self.assertIn("body_digest", item)


    def test_manifest_json_refuses_nan_and_is_canonical(self):
        cells = gr.build_cells()
        manifest = gr.build_manifest(cells)
        text = gr.canonical_json(manifest)
        self.assertEqual(text, gr.canonical_json(json.loads(text)))
        self.assertNotIn("NaN", text)
        bad = {"value": float("nan")}
        with self.assertRaises(ValueError):
            gr.canonical_json(bad)
        canonical_two_keys = json.dumps({"a": 1, "b": 2}, sort_keys=True, separators=(",", ":"))
        self.assertEqual(canonical_two_keys, gr.canonical_json({"b": 2, "a": 1}))


    def test_comparison_and_cells_csv_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = gr.summarize_cells(cell_rows())
            gr.write_comparison_csv(summary, out / "comparison.csv")
            gr.write_cells_csv(cell_rows(), out / "cells.csv")
            self.assertEqual(5, len(_read(out / "comparison.csv").strip().splitlines()))  # 4 + header
            self.assertEqual(17, len(_read(out / "cells.csv").strip().splitlines()))  # 16 + header


    def test_cell_result_files_field_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            params = gr.write_cell_parameters(
                {
                    "cell_id": "PUMPUSDT-W1",
                    "L": 90.0,
                    "U": 121.8,
                    "g_pct": 1.53,
                    "N": 8,
                    "grid_lines": 9,
                    "generator_sha256": TEMPLATE_HASH,
                    "strategy_sha256": "b" * 64,
                },
                out / "CELL.parameters.json",
            )
            self.assertTrue((out / "CELL.parameters.json").exists())
            loaded = json.loads(_read(out / "CELL.parameters.json"))
            self.assertEqual(TEMPLATE_HASH, loaded["generator_sha256"])
            receipt = gr.build_null_receipt("PUMPUSDT-W1", "not submitted: offline test")
            self.assertIsNone(receipt["job_id"])
            self.assertIsNone(receipt["run_id"])
            self.assertTrue(receipt["reason"])
            self.assertIn("billing", receipt)
            json.loads(gr.canonical_json(params))


    def test_manifest_budget_roundtrip_and_stop_accounting(self):
        manifest = gr.build_manifest(gr.build_cells())
        usage = manifest["budgets"]["PUMPUSDT"]
        spent = gr.consume_budget(usage, outer_jobs=3, target_jobs=2,
                                  data_requests=7, elapsed_seconds=1500)
        self.assertEqual(0, usage["outer_jobs"])
        manifest["budgets"]["PUMPUSDT"] = spent
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research-manifest.json"
            gr.write_manifest(manifest, path)
            restored = gr.read_manifest(path)
            left = gr.budget_remaining(restored["budgets"]["PUMPUSDT"])
            self.assertEqual(5, left["outer_jobs"])
            self.assertEqual(2, left["target_jobs"])
            self.assertEqual(43, left["data_requests"])
            self.assertEqual(300, left["elapsed_seconds"])
            self.assertTrue(left["may_continue"])
        expired = gr.consume_budget(spent, elapsed_seconds=300)
        self.assertFalse(gr.budget_remaining(expired)["may_continue"])
        self.assertFalse(gr.budget_remaining(gr.consume_budget(spent, target_jobs=2))["may_continue"])
        self.assertFalse(gr.budget_remaining(gr.consume_budget(spent, evolution=1))["may_continue"])
        with self.assertRaises(ValueError):
            gr.budget_remaining({"outer_jobs": 0})
        budget = {"remaining_outer_jobs": 1, "remaining_data_requests": 1, "remaining_seconds": 1}
        self.assertTrue(gr.stop_decision("none", {"status": "absent"}, budget)["may_submit"])
        for state in ("unknown_after_replay", "failed", "cancelled", "workerInterrupted", "409", "401", "402"):
            self.assertFalse(gr.stop_decision(state, {"status": "absent"}, budget)["may_submit"])
        self.assertFalse(gr.stop_decision("none", {"status": "charged", "charged_amount": 1}, budget)["may_submit"])
        self.assertFalse(gr.stop_decision("none", {"status": "absent", "charged": 1}, budget)["may_submit"])

    def test_manifest_legal_transitions_and_group_stop(self):
        cells = gr.build_cells(["SYNTHETICUSDT"])
        for cell in cells:
            cell.update(strategy_sha256="a" * 64, generator_sha256="b" * 64,
                        parameters={"N": 7}, data_identity={"source": "synthetic"},
                        native_instrument="SYNTHETIC_ONLY_NOT_A_REAL_INSTRUMENT",
                        coverage={"status": "ok"})
        manifest = gr.build_manifest(cells)
        first = cells[0]["cell_id"]
        manifest = gr.transition_manifest(manifest, first, "prechecked", reason="synthetic")
        manifest = gr.transition_manifest(manifest, first, "submitting", reason="synthetic intent only")
        self.assertEqual(1, manifest["budgets"]["SYNTHETICUSDT"]["target_jobs"])
        manifest = gr.transition_manifest(manifest, first, "submitted", reason="synthetic receipt",
                                          job_id="synthetic-not-a-real-job")
        manifest = gr.transition_manifest(manifest, first, "succeeded", reason="synthetic result", run_id=1)
        self.assertEqual(1, manifest["items"][0]["run_id"])
        second, third = cells[1]["cell_id"], cells[2]["cell_id"]
        manifest = gr.transition_manifest(manifest, second, "failed", reason="synthetic failure")
        manifest = gr.transition_manifest(manifest, third, "prechecked", reason="synthetic")
        with self.assertRaises(ValueError):
            gr.transition_manifest(manifest, third, "submitting", reason="must stop")

    def test_manifest_transitions_digest_and_projection(self):
        cells = gr.build_cells()
        manifest = gr.build_manifest(cells)
        with self.assertRaises(ValueError):
            gr.transition_manifest(manifest, cells[0]["cell_id"], "succeeded", reason="not real")
        with self.assertRaises(ValueError):
            gr.transition_manifest(manifest, cells[0]["cell_id"], "prechecked", reason="missing source")
        updated = gr.transition_manifest(manifest, cells[0]["cell_id"], "history_insufficient", reason="synthetic listing boundary")
        self.assertEqual("planned", manifest["items"][0]["status"])
        self.assertEqual("history_insufficient", updated["items"][0]["status"])
        cells[0]["parameters"] = {"N": 7}
        self.assertNotEqual(manifest["items"][0]["body_digest"], gr.build_manifest(cells)["items"][0]["body_digest"])
        gr.validate_manifest(manifest)  # caller mutations cannot alter an existing plan
        tampered = json.loads(gr.canonical_json(manifest))
        tampered["items"][0]["identity"]["initial_margin"] = 10000
        with self.assertRaises(ValueError):
            gr.validate_manifest(tampered)
        with tempfile.TemporaryDirectory() as tmp:
            projected = gr.write_cell_parameters({"cell_id": "PUMPUSDT-W1", "N": 7,
                                                   "headers": {"Authorization": "synthetic-not-a-token"}},
                                                  Path(tmp) / "CELL.parameters.json")
            self.assertNotIn("headers", projected)

    def test_cell_result_metrics_volume_audit_carriers_roundtrip(self):
        """Design §7 frozen per-cell carriers: result/metrics/volume field projection
        and controlled audit log line files, synthetic only, temp dir only."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = gr.write_cell_result({
                "cell_id": "PUMPUSDT-W1", "margin_return_pct": -10.0,
                "sharpe": "N/A", "max_drawdown_pct": 25.0,
                "limitation": gr.COMPRESSED_EQUITY_LIMITATION,
                "net_pnl": -100.0, "peak_equity": 1200.0,
                "dropped": {"headers": {"Authorization": "synthetic-not-a-token"}},
            }, out / "CELL.result.json")
            self.assertNotIn("dropped", result)
            loaded = json.loads(_read(out / "CELL.result.json"))
            self.assertEqual("PUMPUSDT-W1", loaded["cell_id"])
            self.assertEqual(-100.0, loaded["net_pnl"])
            self.assertEqual("N/A", loaded["sharpe"])
            self.assertEqual(gr.COMPRESSED_EQUITY_LIMITATION, loaded["limitation"])
            metrics = gr.write_cell_metrics({
                "cell_id": "PUMPUSDT-W1", "formula_version": "margin_metrics_v1",
                "net_pnl": -100.0, "sharpe": "N/A", "reason": "zero volatility",
                "ddof": 0, "periods_per_year": 35040, "unknown": None,
                "extraneous": {"secret": "synthetic-not-a-token"},
            }, out / "CELL.metrics.json")
            self.assertNotIn("extraneous", metrics)
            # Unknown stays null+reason, not silently dropped: reason preserved.
            self.assertEqual("zero volatility", metrics["reason"])
            self.assertNotIn("unknown", metrics)
            loaded = json.loads(_read(out / "CELL.metrics.json"))
            self.assertEqual(35040, loaded["periods_per_year"])
            self.assertEqual("zero volatility", loaded["reason"])
            volume = gr.write_cell_volume({
                "cell_id": "PUMPUSDT-W1", "quote_volume": None,
                "quote_volume_reason": "official sum missing",
                "base_volume": 10000.0, "raw_v_contracts": 100.0,
                "quanto_multiplier": 0.01, "volume_unit": "base",
                "normalization_version": "gate_swap_base_v1",
                "coverage_status": "ok", "evidence_missing": False,
                "unsupported": {"payment": "data"},
            }, out / "CELL.volume.json")
            self.assertNotIn("unsupported", volume)
            loaded = json.loads(_read(out / "CELL.volume.json"))
            self.assertIsNone(loaded["quote_volume"])
            self.assertEqual("official sum missing", loaded["quote_volume_reason"])
            lines = [
                audit_logs([1, 2, 3])[0],
                "GRID_AUDIT_V1 " + json.dumps({"cell": "PUMPUSDT-W1", "seq": 1}, sort_keys=True),
                "GRID_END_V1 " + json.dumps({"cell": "PUMPUSDT-W1", "bars_total": 3}, sort_keys=True),
            ]
            gr.write_cell_audit(lines, out / "CELL.audit.jsonl")
            self.assertEqual(3, len(_read(out / "CELL.audit.jsonl").strip().splitlines()))
            self.assertEqual(lines, [line for line in _read(out / "CELL.audit.jsonl").splitlines() if line])

    def test_cell_receipt_append_only_roundtrip(self):
        """Design §7: receipt files append on read-back, never overwrite the original."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CELL.receipt.json"
            gr.append_cell_receipt({"cell_id": "PUMPUSDT-W1", "job_id": None,
                                    "run_id": None, "reason": "offline plan; not submitted",
                                    "billing": {"status": "absent"}}, path)
            first = json.loads(_read(path))
            self.assertIsNone(first["job_id"])
            self.assertTrue(first["reason"])
            gr.append_cell_receipt({"cell_id": "PUMPUSDT-W1", "job_id": "synthetic-not-a-real-job",
                                    "run_id": 1, "reason": "synthetic receipt", "billing": {"status": "absent"}},
                                   path)
            lines = _read(path).strip().splitlines()
            self.assertEqual(2, len(lines))
            self.assertEqual(first, json.loads(lines[0]))  # original entry preserved
            self.assertEqual("synthetic-not-a-real-job", json.loads(lines[1])["job_id"])

    def test_cell_carriers_reject_non_finite_values(self):
        """Canonical JSON discipline: carriers refuse NaN/Inf instead of serializing them."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for writer, payload in (
                (gr.write_cell_result, {"cell_id": "PUMPUSDT-W1", "sharpe": float("nan")}),
                (gr.write_cell_metrics, {"cell_id": "PUMPUSDT-W1", "net_pnl": float("inf")}),
                (gr.write_cell_volume, {"cell_id": "PUMPUSDT-W1", "base_volume": float("nan")}),
            ):
                with self.assertRaises(ValueError):
                    writer(payload, out / "probe.json")
            with self.assertRaises(ValueError):
                gr.write_cell_audit(["GRID_AUDIT_V1 " + json.dumps(
                    {"cell": "PUMPUSDT-W1", "equity": float("nan")}, sort_keys=True)],
                    out / "CELL.audit.jsonl")


# ------------------------------------------------- strategy source generator


class StrategySourceGeneratorTests(unittest.TestCase):
    """Generator tests: static source assertions only, never import/execute the strategy."""


    def test_generate_source_is_static_and_records_template_hash(self):
        source = gr.generate_strategy_source(cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH)
        self.assertIn("GRID_INIT_V1", source)
        self.assertIn("GRID_AUDIT_V1", source)
        self.assertIn("GRID_END_V1", source)
        self.assertIn("neutral-grid-pumpusdt/strategy.py", source)  # template path recorded
        # Deterministic generation.
        again = gr.generate_strategy_source(cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH)
        self.assertEqual(source, again)
        # Explicitly parameterized geometry overrides frozen defaults.
        custom = gr.generate_strategy_source(
            cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH, geometry={"L": 90.0, "U": 99.0, "N": 7}
        )
        self.assertIn("7", custom)
        self.assertNotEqual(source, custom)

    def test_strategy_file_contains_controlled_logs_risk_check_and_public_api_only(self):
        self.assertTrue(_STRATEGY_PATH.is_file(), "required generated strategy is missing")
        source = _read(_STRATEGY_PATH)
        self.assertIn("GRID_INIT_V1", source)
        self.assertIn("GRID_AUDIT_V1", source)
        self.assertIn("GRID_END_V1", source)
        for field in (
            "seq", "bar_open", "bar_close", "equity", "q_long", "q_short",
            "avg_long", "avg_short", "gross", "gross_to_equity",
            "reserved_open_notional", "risk_action", "status_changes",
            "peak_equity", "drawdown_pct", "previous_seq", "ohlcv_units",
        ):
            self.assertIn(field, source)
        # Risk capacity check: gross + reserved open orders, stop adding on breach.
        self.assertIn("reserved_open_notional", source)
        self.assertIn("risk_action", source)
        self.assertIn("cancel", source.lower())
        self.assertIn("2.5", source)  # gross ceiling constant
        # Public API only: no private context/portal/broker access.
        for forbidden in ("context._orders", "context.portal", "context._portal", "broker"):
            self.assertNotIn(forbidden, source)
        # No network or env access in strategy source.
        for lib in ("urllib", "requests", "socket", "os.environ", "subprocess"):
            self.assertNotIn(lib, source)
        # No out-of-band files pulled in.
        self.assertNotIn("open(", source)

    def test_geometry_values_native_roles_and_template_identity(self):
        geometry = {"L": 90.0, "U": 100.0, "N": 8}
        source = gr.generate_strategy_source(cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH,
                                             geometry=geometry)
        tree = ast.parse(source)
        constants = {node.targets[0].id: ast.literal_eval(node.value)
                     for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        self.assertEqual(TEMPLATE_HASH, constants["TEMPLATE_SHA256"])
        self.assertEqual(8, len(constants["CELL_LOWER"]))
        self.assertEqual(90.0, constants["CELL_LOWER"][0])
        self.assertEqual(100.0, constants["CELL_UPPER"][-1])
        self.assertAlmostEqual(1.0, sum(constants["CELL_BUDGET_PCTS"]))
        self.assertFalse(constants["DYNAMIC_ANCHOR"])
        self.assertFalse(constants["EVIDENCE_READY"])
        for low, high, role in zip(constants["CELL_LOWER"], constants["CELL_UPPER"],
                                   constants["CELL_ROLES"]):
            self.assertEqual("long_entry" if (low + high) / 2 < 95 else "short_entry", role)
        original = ast.parse(_read(_LAB / "strategies/neutral-grid-pumpusdt/strategy.py"))
        funcs = {node.name: ast.dump(node) for node in tree.body if isinstance(node, ast.FunctionDef)}
        original_funcs = {node.name: ast.dump(node) for node in original.body
                          if isinstance(node, ast.FunctionDef)}
        for name in ("_price", "_status", "_status_name", "_reconcile_initial", "_reconcile_cells",
                     "_place_exit", "_entry_price", "_arm_orders", "_close_all"):
            self.assertEqual(original_funcs[name], funcs[name], name)
        self.assertEqual(source, gr.generate_strategy_source(
            cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH, geometry=geometry))
        for bad in ("0" * 64, "not-a-hash"):
            with self.assertRaises(ValueError):
                gr.generate_strategy_source(cell="PUMPUSDT-W1", template_sha256=bad)
        for bad_geometry in ({"L": 0}, {"N": 2}, {"N": True}, {"U": float("nan")},
                             {"L": 90, "U": 90}, {"N": 200}):
            with self.assertRaises(ValueError):
                gr.generate_strategy_source(cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH,
                                            geometry=bad_geometry)

    def test_risk_and_audit_real_ast_structure(self):
        source = gr.generate_strategy_source(cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH)
        tree = ast.parse(source)
        funcs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        text = {name: ast.unparse(node) for name, node in funcs.items()}
        # Inspect the actual data flow; never exec/compile a strategy or a fake runtime.
        self.assertIn("context.portfolio.available_cash", text["_risk_snapshot"])
        self.assertIn("position.amount * price", text["_risk_snapshot"])
        self.assertNotIn("total_value", text["_risk_snapshot"])
        self.assertIn("get_positions()", text["_risk_snapshot"])
        self.assertIn("q_long + q_short", text["_risk_snapshot"])
        self.assertIn("target_quantity", text["_refresh_open_orders"])
        self.assertIn("filled_quantity", text["_refresh_open_orders"])
        self.assertIn("max(0.0,", text["_refresh_open_orders"])
        self.assertIn("_refresh_open_orders", text["after_trading_end"])
        self.assertIn("_risk_snapshot", text["after_trading_end"])
        self.assertIn("reserved_open_notional", text["_capacity_allows"])
        self.assertIn("candidate_notional", text["_capacity_allows"])
        self.assertIn("FEE_RATE + SLIPPAGE_RATE", text["_capacity_allows"])
        self.assertIn("GROSS_LIMIT * scenario_equity", text["_capacity_allows"])
        self.assertIn("scenario_low", text["_capacity_allows"])
        self.assertIn("scenario_high", text["_capacity_allows"])
        self.assertLess(text["_place_entry"].index("_capacity_allows"),
                        text["_place_entry"].index("order("))
        self.assertIn("_cancel_open_entries()", text["_observe_risk"])
        self.assertIn("g.stop_adding = True", text["_observe_risk"])
        self.assertIn("_close_all", text["_observe_risk"])
        self.assertIn("gross / equity > GROSS_LIMIT", text["_observe_risk"])
        self.assertIn("context.current_dt", text["after_trading_end"])
        audit_keywords = {node.arg for node in ast.walk(funcs["after_trading_end"])
                          if isinstance(node, ast.keyword)}
        self.assertTrue({"bar_open", "bar_close", "ohlcv", "ohlcv_units", "previous_seq"}
                        <= audit_keywords)
        # Only sandbox-compatible JSON/datetime imports; no private object traversal.
        self.assertEqual({"json", "datetime"}, {node.names[0].name for node in tree.body
                                                if isinstance(node, ast.Import)})
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertFalse(node.attr.startswith("_"), ast.unparse(node))
        self.assertIn("EVIDENCE_READY", text["initialize"])
        self.assertIn("raise ValueError", text["initialize"])

    def test_five_files_and_frozen_example_are_real(self):
        directory = _STRATEGY_PATH.parent
        self.assertEqual({"README.md", "spec.md", "config.json", "research.py", "strategy.py"},
                         {entry.name for entry in directory.iterdir() if entry.is_file()})
        config = json.loads(_read(directory / "config.json"))
        self.assertTrue(config)
        self.assertTrue(all(type(value) in (int, float) and math.isfinite(value)
                            for value in config.values()))
        self.assertEqual(1000, config["initial_margin"])
        self.assertEqual(10, config["leverage"])
        self.assertEqual(2.5, config["gross_limit"])
        self.assertEqual(_read(_STRATEGY_PATH), gr.generate_strategy_source(
            cell="PUMPUSDT-W1", template_sha256=TEMPLATE_HASH))
        self.assertIn("G-01", _read(directory / "README.md"))
        self.assertIn("SPEC-06-002", _read(directory / "spec.md"))

    def test_cell_windows_are_not_replaced_by_w1(self):
        source = gr.generate_strategy_source(cell="SUIUSDT-W4", template_sha256=TEMPLATE_HASH)
        constants = {node.targets[0].id: ast.literal_eval(node.value)
                     for node in ast.parse(source).body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        self.assertEqual("SUIUSDT-W4", constants["CELL_ID"])
        self.assertEqual("2025-10-31T00:00:00Z", constants["START_UTC"])
        self.assertEqual("2026-01-31T00:00:00Z", constants["END_UTC"])
        self.assertIsNone(constants["INSTRUMENT"])
        self.assertEqual("unknown", constants["OHLCV_UNITS"]["volume"])
        with self.assertRaises(ValueError):
            gr.generate_strategy_source(cell="SUIUSDT-W5", template_sha256=TEMPLATE_HASH)

    def test_local_coordinator_anchor_guard_and_no_submission(self):
        path = _STRATEGY_PATH.with_name("research.py")
        spec = importlib.util.spec_from_file_location("offline_coordinator_test", path)
        assert spec is not None and spec.loader is not None
        coordinator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(coordinator)
        plan = coordinator.describe_plan(contracts=["SYNTHETICUSDT"], now_utc=ANCHOR)
        self.assertEqual(4, len(plan["manifest"]["items"]))
        self.assertFalse(plan["submission_implemented"])
        self.assertEqual(["G-01", "G-02", "G-03"], plan["unresolved_gates"])
        self.assertEqual("DEFERRED", plan["full_research_status"])
        with self.assertRaises(ValueError):
            coordinator.describe_plan(anchor_utc=utc(2027, 1, 1), now_utc=ANCHOR)
        with mock.patch.object(coordinator, "_load_calculations") as load, \
             mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as error:
                coordinator.main(["--execute"])
            self.assertEqual(3, error.exception.code)
            load.assert_not_called()
        # The local coordinator imports neither strategy.py nor the business CLI.
        imports = [node for node in ast.walk(ast.parse(_read(path)))
                   if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any("quantdinger" in ast.unparse(node) for node in imports))

    def test_example_output_does_not_overwrite_other_files(self):
        path = _STRATEGY_PATH.with_name("research.py")
        spec = importlib.util.spec_from_file_location("offline_output_test", path)
        assert spec is not None and spec.loader is not None
        coordinator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(coordinator)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "synthetic-source.py"
            with mock.patch("builtins.print"):
                self.assertEqual(0, coordinator.main(["--write-example", str(target)]))
            self.assertEqual(_read(_STRATEGY_PATH), _read(target))
            with self.assertRaises(FileExistsError):
                coordinator.main(["--write-example", str(target)])
            alternate = Path(temporary) / "alternate-source.py"
            with mock.patch("builtins.print"):
                coordinator.main(["--contracts", "SYNTHETICUSDT", "--anchor",
                                  "2026-08-31T00:00:00Z", "--write-example", str(alternate)])
            constants = {node.targets[0].id: ast.literal_eval(node.value)
                         for node in ast.parse(_read(alternate)).body
                         if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
            self.assertEqual("SYNTHETICUSDT-W1", constants["CELL_ID"])
            self.assertEqual("2026-05-31T00:00:00Z", constants["START_UTC"])
            self.assertEqual("2026-08-31T00:00:00Z", constants["END_UTC"])

    def test_stop_state_machine_pure_accounting(self):
        # Budget/stop pure accounting: unknown job terminal states stop submissions.
        result = gr.stop_decision(
            job_state="unknown_after_replay",
            billing={"status": "absent"},
            budget={"remaining_outer_jobs": 3, "remaining_data_requests": 10, "remaining_seconds": 100},
        )
        self.assertFalse(result["may_submit"])
        healthy = gr.stop_decision(
            job_state="none",
            billing={"status": "absent"},
            budget={"remaining_outer_jobs": 3, "remaining_data_requests": 10, "remaining_seconds": 100},
        )
        self.assertTrue(healthy["may_submit"])
        charged = gr.stop_decision(
            job_state="none",
            billing={"status": "charged", "charged_amount": 1.0},
            budget={"remaining_outer_jobs": 3, "remaining_data_requests": 10, "remaining_seconds": 100},
        )
        self.assertFalse(charged["may_submit"])


if __name__ == "__main__":
    unittest.main()
