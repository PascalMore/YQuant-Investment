"""Offline tests for the grid-evolution driver's judging and selection rules.

The selection rule is frozen (Pascal 2026-11-05): a candidate is eligible
when qualified windows >= 50% of the selection windows and no window went
bankrupt; the highest mean window return among eligible candidates wins.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location("offline_grid_evolve", _SCRIPTS / "grid_evolve.py")
ev = importlib.util.module_from_spec(_spec)
sys.modules["offline_grid_evolve"] = ev
_spec.loader.exec_module(ev)


def _window(label, ret, mdd, ge_ratio, liquidated=False):
    metrics = {"window": label, "margin_return_pct": ret, "max_drawdown_pct": mdd,
               "worst_gross_to_equity": ge_ratio, "liquidated": liquidated}
    metrics["qualification"], metrics["reasons"] = ev.judge_window(metrics)
    return metrics


def _candidate(rank, *windows):
    return {"rank": rank, "windows": list(windows)}


class TestJudgeWindow(unittest.TestCase):
    def test_inside_the_envelope_is_qualified(self):
        self.assertEqual(ev.judge_window(_window("W2", 10, -20, 1.5))[0], "qualified")

    def test_thresholds_are_strictly_greater(self):
        self.assertEqual(_window("W2", 10, -35.0, 2.0)["qualification"], "qualified")
        self.assertEqual(_window("W2", 10, -35.01, 2.0)["qualification"], "risk-breach")
        self.assertEqual(_window("W2", 10, -35.0, 2.01)["qualification"], "risk-breach")

    def test_bankruptcy_is_named_in_the_reasons(self):
        window = _window("W2", -100, -100, 50, liquidated=True)
        self.assertEqual(window["qualification"], "risk-breach")
        self.assertIn("破产强平", window["reasons"])

    def test_missing_metric_is_insufficient_evidence(self):
        self.assertEqual(_window("W2", None, -10, 1.0)["qualification"],
                         "insufficient-evidence")


class TestSelectCandidate(unittest.TestCase):
    def test_half_qualified_without_bankruptcy_is_eligible(self):
        candidate = _candidate(1, _window("W2", 10, -20, 1.0), _window("W3", 5, -30, 1.0),
                               _window("W4", 20, -40, 1.0), _window("W5", 3, -50, 3.0))
        self.assertIs(ev.select_candidate([candidate]), candidate)
        self.assertEqual(candidate["qualified_windows"], 2)

    def test_below_half_is_not_eligible(self):
        candidate = _candidate(1, _window("W2", 10, -20, 1.0), _window("W3", 5, -40, 1.0),
                               _window("W4", 20, -40, 1.0), _window("W5", 3, -50, 3.0))
        self.assertIsNone(ev.select_candidate([candidate]))

    def test_any_bankrupt_window_disqualifies(self):
        candidate = _candidate(1, _window("W2", 10, -20, 1.0), _window("W3", 5, -20, 1.0),
                               _window("W4", 20, -20, 1.0),
                               _window("W5", -100, -100, 80, liquidated=True))
        self.assertIsNone(ev.select_candidate([candidate]))
        self.assertEqual(candidate["bankrupt_windows"], ["W5"])

    def test_highest_mean_return_among_eligible_wins(self):
        low = _candidate(1, _window("W2", 10, -20, 1.0), _window("W3", 10, -20, 1.0))
        high = _candidate(2, _window("W2", 30, -20, 1.0), _window("W3", 30, -40, 1.0))
        ineligible = _candidate(3, _window("W2", 500, -90, 9.0), _window("W3", 500, -90, 9.0))
        self.assertIs(ev.select_candidate([low, high, ineligible]), high)


class TestQuarterlyWindows(unittest.TestCase):
    def test_twelve_months_split_into_w2_to_w5_newest_first(self):
        self.assertEqual(ev.quarterly_windows("2025-08-03", "2026-08-03", first_label=2), [
            ("W2", "2026-05-03", "2026-08-03"), ("W3", "2026-02-03", "2026-05-03"),
            ("W4", "2025-11-03", "2026-02-03"), ("W5", "2025-08-03", "2025-11-03")])

    def test_a_partial_quarter_is_rejected(self):
        with self.assertRaises(ev.EvolutionError):
            ev.quarterly_windows("2025-08-10", "2026-08-03", first_label=2)


class TestDefaultRange(unittest.TestCase):
    def test_platform_default_is_half_to_one_and_a_half_times_baseline(self):
        low, high, step = ev.default_range(0.00147)
        self.assertAlmostEqual(low, 0.000735)
        self.assertAlmostEqual(high, 0.002205)
        self.assertAlmostEqual(step, (0.002205 - 0.000735) / ev.DEFAULT_RANGE_STEPS)

    def test_the_v2_lower_bound_is_inside_the_default_range(self):
        low, high, _ = ev.default_range(0.00147)
        self.assertTrue(low <= 0.0019 <= high)


class _FakePlatform:
    """Returns window metrics that depend only on the leverage."""

    def __init__(self, by_leverage):
        self.by_leverage, self.calls = by_leverage, []

    def backtest(self, source_id, start, end, params, run, leverage=None):
        self.calls.append(leverage)
        ret, mdd, ge_ratio = self.by_leverage[leverage]
        return {"runId": len(self.calls), "margin_return_pct": ret, "max_drawdown_pct": mdd,
                "worst_gross_to_equity": ge_ratio, "pairs": 1, "liquidated": False,
                "executions": []}


class TestJudgeCandidate(unittest.TestCase):
    WINDOWS = [("W2", "a", "b"), ("W3", "b", "c")]
    CANDIDATE = {"rank": 1, "trial": 3, "params": {}, "platform_score": 1.0, "geometry": {}}

    def test_every_window_is_backtested_at_the_requested_leverage(self):
        platform = _FakePlatform({6: (10.0, -20.0, 1.2)})
        judged = ev.judge_candidate(platform, 13, self.CANDIDATE, self.WINDOWS, {}, 6)
        self.assertEqual(platform.calls, [6, 6])
        self.assertEqual(judged["leverage"], 6)
        self.assertTrue(all(w["qualification"] == "qualified" for w in judged["windows"]))

    def test_the_input_candidate_is_not_mutated_across_tiers(self):
        platform = _FakePlatform({10: (10.0, -50.0, 5.0), 6: (8.0, -20.0, 1.2)})
        first = ev.judge_candidate(platform, 13, self.CANDIDATE, self.WINDOWS, {}, 10)
        second = ev.judge_candidate(platform, 13, self.CANDIDATE, self.WINDOWS, {}, 6)
        self.assertIsNone(ev.select_candidate([first]))
        self.assertIs(ev.select_candidate([second]), second)
        self.assertNotIn("windows", self.CANDIDATE)


class TestWindowMetrics(unittest.TestCase):
    def test_canonical_gross_is_the_equity_curve_peak(self):
        metrics = ev.window_metrics({
            "runId": 7, "totalReturn": 12.5, "maxDrawdown": -8.0, "sharpeRatio": 2.0,
            "gridMatchedTradeCount": 40, "liquidated": False,
            "equityCurve": [{"grossExposure": 0.4}, {"grossExposure": -1.7},
                            {"grossExposure": 1.1}]})
        self.assertEqual(metrics["worst_gross_to_equity"], 1.7)
        self.assertEqual((metrics["runId"], metrics["pairs"]), (7, 40))


if __name__ == "__main__":
    unittest.main()
