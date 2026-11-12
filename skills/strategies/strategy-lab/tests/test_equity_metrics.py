"""Zero-drift tests for the shared equity metrics helper (SPEC-07-001 M2 §12).

The helper was extracted from ``grid_research.margin_metrics``. The oracle
below is a verbatim copy of that function's body as it was before the
extraction, so the comparison is against the original behaviour and not
against the new implementation. The oracle is test-only: it is never used by
the production path.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import math
import statistics
import unittest
from pathlib import Path

_LAB = Path(__file__).resolve().parents[1]
_HELPER_PATH = _LAB / "scripts" / "equity_metrics.py"
_GRID_PATH = _LAB / "scripts" / "grid_research.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"required implementation is missing: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_helper = _load(_HELPER_PATH, "offline_equity_metrics")
_grid = _load(_GRID_PATH, "offline_grid_research")

UTC = dt.timezone.utc


# --------------------------------------------------------------- oracle ---

INITIAL_MARGIN = 1000.0
COMPRESSED_EQUITY_LIMITATION = (
    "Compressed equity cannot independently verify full equal-frequency Sharpe or MDD."
)
NA = "N/A"


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: finite number required")
    if not math.isfinite(value):
        raise ValueError(f"{name}: non-finite number")
    return float(value)


def _time(value):
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid UTC timestamp") from exc
    if not isinstance(value, dt.datetime) or value.utcoffset() != dt.timedelta(0):
        raise ValueError("timezone-aware UTC timestamp required")
    return value.astimezone(UTC)


def _iso(value):
    return _time(value).isoformat().replace("+00:00", "Z")


def legacy_margin_metrics(bar_close_rows, frequency_seconds=3600):
    """A verbatim copy of grid_research.margin_metrics before the extraction."""
    equities, times = [], []
    for row in bar_close_rows:
        if "time" not in row:
            raise ValueError("missing time")
        times.append(_time(row["time"]))
        if "equity" in row:
            equity = _finite(row["equity"], "equity")
        else:
            equity = INITIAL_MARGIN + _finite(row["realized_net_pnl"], "realized_net_pnl")
            equity += _finite(row["unrealized_pnl"], "unrealized_pnl")
        equities.append(_finite(equity, "computed equity"))
    peak, maximum_dd = INITIAL_MARGIN, 0.0
    peak_time = trough_time = None
    for timestamp, equity in zip(times, equities):
        if equity > peak:
            peak, peak_time = equity, _iso(timestamp)
        drawdown = (peak - equity) / peak * 100
        if drawdown > maximum_dd:
            maximum_dd, trough_time = drawdown, _iso(timestamp)
    frequency = int(frequency_seconds)
    missing = any((right - left).total_seconds() != frequency
                  for left, right in zip(times, times[1:]))
    reasons = []
    if not equities:
        reasons.append("empty equity sample")
    if missing:
        reasons.append("missing/duplicate/non-native bar")
    if any(equity <= 0 for equity in equities):
        reasons.append("nonpositive equity")
    valid_equity = bool(equities) and not missing and min(equities) > 0
    returns = [right / left - 1 for left, right in zip(equities, equities[1:])
               if left > 0]
    sharpe = NA
    if len(returns) < 2:
        reasons.append("insufficient return samples")
    if returns and statistics.pstdev(returns) == 0:
        reasons.append("zero volatility")
    if valid_equity and len(returns) >= 2 and statistics.pstdev(returns) > 0:
        periods_per_year = 365 * (86400 // frequency)
        sharpe = statistics.mean(returns) / statistics.pstdev(returns) * math.sqrt(periods_per_year)
    return {"status": "ok" if valid_equity else NA,
            "reason": "; ".join(reasons) or None,
            "net_pnl": equities[-1] - INITIAL_MARGIN if equities else NA,
            "margin_return_pct": 100 * (equities[-1] / INITIAL_MARGIN - 1)
            if valid_equity else NA,
            "peak_equity": peak,
            "max_drawdown_pct": maximum_dd if equities and not missing else NA,
            "raw_max_drawdown_pct": maximum_dd if equities else None,
            "peak_time": peak_time, "trough_time": trough_time,
            "sharpe": sharpe, "return_count": len(returns), "bar_count": len(equities),
            "risk_free": 0, "ddof": 0,
            "periods_per_year": 365 * (86400 // frequency),
            "limitation": COMPRESSED_EQUITY_LIMITATION}


# ---------------------------------------------------------------- cases ---

def rows_from_equities(equities, frequency=900, start="2026-01-01T00:00:00Z"):
    """Build the grid-style rows the wrapper takes."""
    moment = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    rows = []
    for index, equity in enumerate(equities):
        rows.append({"time": (moment + dt.timedelta(seconds=index * frequency)).isoformat(),
                     "equity": equity})
    return rows


class LegacyOracleTests(unittest.TestCase):
    """The wrapper must match the original function exactly."""

    CASES = [
        ("empty", [], 3600),
        ("single", [1100.0], 3600),
        ("two", [1100.0, 1050.0], 900),
        ("three", [1100.0, 1050.0, 1150.0], 900),
        ("four", [1100.0, 1050.0, 1150.0, 1200.0], 900),
        ("flat", [1100.0, 1100.0, 1100.0], 900),
        ("positive", [1100.0, 1200.0, 1300.0], 3600),
        ("zero", [1100.0, 0.0, 1300.0], 3600),
        ("negative", [1100.0, -50.0, 1300.0], 3600),
    ]

    def test_the_wrapper_matches_the_legacy_function_on_every_case(self):
        for name, equities, frequency in self.CASES:
            with self.subTest(case=name):
                rows = rows_from_equities(equities, frequency=frequency)
                expected = legacy_margin_metrics(rows, frequency)
                actual = _grid.margin_metrics(rows, frequency)
                self.assertEqual(actual, expected)

    def test_the_frequencies_the_original_accepts(self):
        rows = rows_from_equities([1100.0, 1050.0, 1150.0, 1200.0], frequency=900)
        for frequency in (300, 900, 3600, 1000, 86401):
            with self.subTest(frequency=frequency):
                expected = legacy_margin_metrics(rows, frequency)
                actual = _grid.margin_metrics(rows, frequency)
                self.assertEqual(actual, expected)

    def test_the_values_the_original_converts(self):
        rows = rows_from_equities([1100.0, 1050.0, 1150.0, 1200.0], frequency=900)
        for frequency in ("900", 900.9, True, 0, -1):
            with self.subTest(frequency=frequency):
                expected = self._capture(lambda: legacy_margin_metrics(rows, frequency))
                actual = self._capture(lambda: _grid.margin_metrics(rows, frequency))
                self.assertEqual(actual, expected)

    def test_the_equity_backfill_path_is_unchanged(self):
        rows = [
            {"time": "2026-01-01T00:00:00Z",
             "realized_net_pnl": 100.0, "unrealized_pnl": -20.0},
            {"time": "2026-01-01T01:00:00Z",
             "realized_net_pnl": 150.0, "unrealized_pnl": 0.0},
            {"time": "2026-01-01T02:00:00Z",
             "realized_net_pnl": -30.0, "unrealized_pnl": 5.0},
        ]
        expected = legacy_margin_metrics(rows, 3600)
        actual = _grid.margin_metrics(rows, 3600)
        self.assertEqual(actual, expected)

    def test_an_explicit_equity_wins_over_the_backfill(self):
        rows = [
            {"time": "2026-01-01T00:00:00Z", "equity": 1050.0,
             "realized_net_pnl": 999.0, "unrealized_pnl": 999.0},
            {"time": "2026-01-01T01:00:00Z", "equity": 1150.0},
        ]
        expected = legacy_margin_metrics(rows, 3600)
        actual = _grid.margin_metrics(rows, 3600)
        self.assertEqual(actual, expected)

    def test_the_failures_are_unchanged(self):
        cases = [
            ([{"equity": 1.0}], "missing time"),
            ([{"time": "not-a-time"}], "invalid UTC timestamp"),
            ([{"time": "2026-01-01T00:00:00+01:00"}],
             "timezone-aware UTC timestamp required"),
            ([{"time": "2026-01-01T00:00:00Z", "equity": float("nan")}],
             "equity: non-finite number"),
            ([{"time": "2026-01-01T00:00:00Z", "equity": float("inf")}],
             "equity: non-finite number"),
            ([{"time": "2026-01-01T00:00:00Z", "equity": True}],
             "equity: finite number required"),
        ]
        for rows, message in cases:
            with self.subTest(rows=rows):
                expected = self._capture(lambda: legacy_margin_metrics(rows, 3600))
                actual = self._capture(lambda: _grid.margin_metrics(rows, 3600))
                self.assertEqual(actual, expected)
                self.assertIn(message, str(actual))

    def test_a_non_native_interval_is_reported_the_same_way(self):
        rows = [
            {"time": "2026-01-01T00:00:00Z", "equity": 1050.0},
            {"time": "2026-01-01T00:00:30Z", "equity": 1100.0},
        ]
        expected = legacy_margin_metrics(rows, 3600)
        actual = _grid.margin_metrics(rows, 3600)
        self.assertEqual(actual, expected)
        self.assertIn("missing/duplicate/non-native bar", actual["reason"])

    @staticmethod
    def _capture(call):
        try:
            return ("ok", call())
        except Exception as exc:  # noqa: BLE001 - the type and text are the oracle
            return ("error", type(exc).__name__, str(exc))


class HelperTests(unittest.TestCase):
    """The shared helper, on its own terms."""

    def test_the_shared_keys_are_present(self):
        rows = [(dt.datetime(2026, 1, 1, tzinfo=UTC), 1050.0),
                (dt.datetime(2026, 1, 1, 0, 15, tzinfo=UTC), 1100.0)]
        metrics = _helper.equity_metrics(
            rows, initial_capital=1000.0, frequency_seconds=900,
            limitation="test-limitation")
        self.assertEqual(set(metrics), {
            "status", "reason", "net_pnl", "return_pct", "peak_equity",
            "max_drawdown_pct", "raw_max_drawdown_pct", "peak_time",
            "trough_time", "sharpe", "return_count", "bar_count", "risk_free",
            "ddof", "periods_per_year", "limitation"})
        self.assertEqual(metrics["net_pnl"], 100.0)
        self.assertAlmostEqual(metrics["return_pct"], 10.0, places=12)
        self.assertEqual(metrics["limitation"], "test-limitation")
        self.assertEqual(metrics["periods_per_year"], 365 * (86400 // 900))

    def test_the_frozen_vector_from_the_design(self):
        """Capital 1000, four equities, frequency 900: the frozen Sharpe."""
        rows = [(dt.datetime(2026, 1, 1, tzinfo=UTC) + dt.timedelta(seconds=900 * index),
                 equity)
                for index, equity in enumerate((1100.0, 1050.0, 1150.0, 1200.0))]
        metrics = _helper.equity_metrics(
            rows, initial_capital=1000.0, frequency_seconds=900, limitation="x")
        self.assertAlmostEqual(metrics["sharpe"], 100.15527470614849, places=9)
        self.assertEqual(metrics["net_pnl"], 200.0)
        self.assertAlmostEqual(metrics["return_pct"], 19.999999999999996, places=12)
        self.assertAlmostEqual(metrics["max_drawdown_pct"], 4.545454545454546, places=12)

    def test_summary_net_pnl_adds_capital_once_without_second_fee_deduction(self):
        """runtime::Summary::equity is realized-fees+unrealized, not account NAV."""
        capital, realized, fees, unrealized = 200.0, 10.0, 2.0, 3.0
        summary_net_pnl = realized - fees + unrealized
        start = dt.datetime(2026, 1, 1, tzinfo=UTC)
        rows = [(start, capital),
                (start + dt.timedelta(seconds=300), capital + summary_net_pnl)]
        metrics = _helper.equity_metrics(rows, initial_capital=capital,
                                         frequency_seconds=300, limitation="fixture-only")
        self.assertEqual(metrics["net_pnl"], summary_net_pnl)
        self.assertNotEqual(metrics["net_pnl"], summary_net_pnl - fees)
        self.assertEqual(metrics["peak_equity"], capital + summary_net_pnl)

    def test_an_empty_sample_keeps_the_original_diagnostics(self):
        metrics = _helper.equity_metrics(
            [], initial_capital=1000.0, frequency_seconds=900, limitation="x")
        self.assertEqual(metrics["status"], NA)
        self.assertEqual(metrics["reason"],
                         "empty equity sample; insufficient return samples")
        self.assertEqual(metrics["net_pnl"], NA)
        self.assertEqual(metrics["return_pct"], NA)
        self.assertIsNone(metrics["raw_max_drawdown_pct"])
        self.assertIsNone(metrics["peak_time"])

    def test_a_nonpositive_equity_keeps_its_raw_diagnostics(self):
        rows = [(dt.datetime(2026, 1, 1, tzinfo=UTC), 1000.0),
                (dt.datetime(2026, 1, 1, 0, 15, tzinfo=UTC), 0.0)]
        metrics = _helper.equity_metrics(
            rows, initial_capital=1000.0, frequency_seconds=900, limitation="x")
        self.assertEqual(metrics["status"], NA)
        self.assertIn("nonpositive equity", metrics["reason"])
        self.assertEqual(metrics["net_pnl"], -1000.0)
        # The original keeps the raw drawdown even when the equity is not
        # positive; the headline drawdown is only withheld when the sample is
        # missing a bar.
        self.assertEqual(metrics["max_drawdown_pct"], 100.0)
        self.assertEqual(metrics["raw_max_drawdown_pct"], 100.0)
        self.assertEqual(metrics["return_pct"], NA)


if __name__ == "__main__":
    unittest.main()
