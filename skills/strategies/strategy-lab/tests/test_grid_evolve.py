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


import csv  # noqa: E402
import tempfile  # noqa: E402
from unittest import mock  # noqa: E402

import grid_evolve_source as ges  # noqa: E402
import grid_research as gr  # noqa: E402
import grid_stress_liquidation as gsl  # noqa: E402


class _FakeEvolutionPlatform:
    """Offline stand-in for the whole G1..G6 platform surface."""

    def __init__(self, declarations, candidates):
        self.declarations, self.candidates = declarations, candidates
        self.backtests, self.budget, self.paths = 0, 500, []

    def call(self, method, path, body=None, params=None):
        self.paths.append(path)
        if path.endswith("/compile"):
            return {"code": 1}
        if path.endswith("/create"):
            return {"code": 1, "data": {"id": 99}}
        if path.endswith("/parameter-space"):
            return {"data": {"parameters": [dict(spec, name=name)
                                            for name, spec in self.declarations.items()]}}
        if path.endswith("/strategy-evolution/run"):
            return {"data": {"jobId": "evo-1"}}
        raise AssertionError(f"unexpected platform call {method} {path}")

    def wait(self, path, *, poll_seconds, max_polls):
        return {"status": "succeeded", "result": {
            "summary": {}, "selection": {"recommended": True},
            "topCandidates": self.candidates}}

    def backtest(self, source_id, start, end, params, run, leverage=None):
        self.backtests += 1
        gap = params["grid_gap_pct"]
        breach = start.startswith("2025-11")  # W4 breaches, the others qualify
        return {"runId": 100 + self.backtests, "margin_return_pct": 10.0 + gap + self.backtests,
                "max_drawdown_pct": -50.0 if breach else -20.0, "sharpe": 1.5,
                "worst_gross_to_equity": 3.0 if breach else 1.0 + self.backtests / 100,
                "pairs": 40 + self.backtests, "liquidated": False,
                "executions": [{"client_order_id": f"grid-{cell}-x", "notional": 50.0 + cell}
                               for cell in (1, 2)]}


class TestG7Carriers(unittest.TestCase):
    ARGS = dict(contract="PUMPUSDT", instrument="Crypto:PUMP/USDT@swap", lower=0.00147,
                upper=0.008984, gap_pct=1.5, evolve_start="2025-08-03",
                evolve_end="2026-08-03", holdout_start="2026-08-03",
                holdout_end="2026-11-03")
    CANDIDATES = [{"number": 1, "score": 1.0, "params": {
        "grid_lower": 0.0015, "grid_upper": 0.009, "grid_gap_pct": 1.5}}]

    def _run(self, platform_candidates, baseline_dir=None, contract="PUMPUSDT"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        evidence = Path(tmp.name) / "evidence"
        ranges = {"lower_range": ev.default_range(0.00147),
                  "upper_range": ev.default_range(0.008984)}
        _, manifest = ges.generate_evolve_source(
            instrument=self.ARGS["instrument"], lower=0.00147, upper=0.008984, gap_pct=1.5,
            search_ranges={"grid_lower": ranges["lower_range"],
                           "grid_upper": ranges["upper_range"]}, cell_id="PUMPUSDT-EVOLVE")
        platform = _FakeEvolutionPlatform(manifest["parameter_declarations"],
                                          platform_candidates)
        with mock.patch.object(gsl, "_curl_json", side_effect=RuntimeError("offline")):
            record = ev.run_evolution(**dict(self.ARGS, contract=contract), **ranges,
                                      platform=platform,
                                      evidence=evidence, top=1, fallback_leverages=(),
                                      baseline_dir=baseline_dir,
                                      run={"capital": 1000.0, "commission": 0.0005,
                                           "slippage": 0.0005, "leverage": 10})
        return record, platform, evidence

    def test_g7_writes_the_three_carriers_without_extra_backtests(self):
        record, platform, evidence = self._run(self.CANDIDATES)
        self.assertEqual(record["g7"]["written"],
                         ["cells.csv", "cells-comparison.csv", "table-b-summary.md"])
        for name in record["g7"]["written"]:
            self.assertTrue((evidence / name).is_file(), name)
        # G3 two probes + one candidate x four windows + G6 holdout; G7 adds none.
        self.assertEqual(2 + 4 + 1, platform.backtests)
        with (evidence / "cells.csv").open(newline="", encoding="utf-8") as stream:
            rows = {row["cell_id"]: row for row in csv.DictReader(stream)}
        winner = ev.winner_of(record)
        by_window = {w["window"]: w for w in winner["windows"]}
        by_window["W1"] = record["holdout"]
        for label in ("W1", "W2", "W3", "W4"):
            row = rows[f"PUMPUSDT-{label}"]
            self.assertEqual(str(by_window[label]["runId"]), row["run_id"])
            self.assertAlmostEqual(by_window[label]["worst_gross_to_equity"],
                                   float(row["worst_gross_to_equity"]), places=12)
            self.assertNotEqual("N/A", row["downward_liquidation_price"])
        self.assertEqual("N/A", rows["AAVEUSDT-W1"]["worst_gross_to_equity"])
        summary = (evidence / "table-b-summary.md").read_text(encoding="utf-8")
        self.assertIn("51.5 (51.5/51.5/51.5/51.5)", summary)  # per-grid amount from executions
        self.assertIn("W1✓ W2✓ W3✓ W4⚠", summary)

    def test_g7_with_baseline_writes_the_comparison(self):
        _, _, baseline = self._run(self.CANDIDATES)
        record, _, evidence = self._run(self.CANDIDATES, baseline_dir=baseline)
        self.assertIn("table-b-evolved-vs-baseline.md", record["g7"]["written"])
        text = (evidence / "table-b-evolved-vs-baseline.md").read_text(encoding="utf-8")
        self.assertIn("| PUMPUSDT 基准 |", text)
        self.assertIn("| PUMPUSDT 进化 |", text)

    def test_g7_is_skipped_without_a_winner(self):
        record = {"contract": "PUMPUSDT", "winner_rank": None, "winner_leverage": None,
                  "leverage_tiers": [{"leverage": 10, "candidates": [], "winner_rank": None}]}
        with tempfile.TemporaryDirectory() as tmp:
            status = ev.write_table_carriers(record, Path(tmp), task_date="2026-11-06")
            self.assertEqual({"skipped": "no winner"}, status)
            self.assertEqual([], list(Path(tmp).iterdir()))

    def test_run_without_a_winner_records_no_g7_and_no_holdout(self):
        losing = [{"number": 1, "score": 1.0, "params": {
            "grid_lower": 0.0015, "grid_upper": 0.009, "grid_gap_pct": 1.5}}]
        with mock.patch.object(ev, "select_candidate", return_value=None):
            record, platform, evidence = self._run(losing)
        self.assertIsNone(record["winner_rank"])
        self.assertNotIn("holdout", record)
        self.assertEqual({"skipped": "no winner"}, record["g7"])
        self.assertEqual(2 + 4, platform.backtests)
        self.assertFalse((evidence / "cells.csv").exists())

    def test_non_frozen_contract_writes_a_single_contract_carrier(self):
        record, platform, evidence = self._run(self.CANDIDATES, contract="XRPUSDT")
        self.assertNotIn("skipped", record["g7"])
        self.assertEqual(["cells.csv", "cells-comparison.csv", "table-b-summary.md"],
                         record["g7"]["written"])
        with (evidence / "cells.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(["XRPUSDT"] * 4, [row["contract"] for row in rows])
        with (evidence / "cells-comparison.csv").open(newline="", encoding="utf-8") as stream:
            self.assertEqual(["XRPUSDT"], [row["contract"] for row in csv.DictReader(stream)])
        summary = (evidence / "table-b-summary.md").read_text(encoding="utf-8")
        self.assertEqual(1, sum(line.startswith("| XRPUSDT |") for line in summary.splitlines()))
        self.assertEqual(2 + 4 + 1, platform.backtests)

    def test_non_frozen_contract_with_baseline_writes_the_comparison(self):
        _, _, baseline = self._run(self.CANDIDATES, contract="XRPUSDT")
        record, _, evidence = self._run(self.CANDIDATES, baseline_dir=baseline,
                                        contract="XRPUSDT")
        self.assertIn("table-b-evolved-vs-baseline.md", record["g7"]["written"])
        text = (evidence / "table-b-evolved-vs-baseline.md").read_text(encoding="utf-8")
        self.assertIn("| XRPUSDT 基准 |", text)
        self.assertIn("| XRPUSDT 进化 |", text)
        self.assertEqual(4, sum(line.startswith("| W") for line in text.splitlines()))


class TestBaselineDirPrecheck(unittest.TestCase):
    """A bad --baseline-dir fails at G0, before any platform call."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.baseline = Path(tmp.name) / "baseline"
        self.baseline.mkdir()
        # Placeholder four-contract carriers: valid files with a PUMPUSDT row.
        gr.regen_carriers("2026-11-03T00:00:00Z", [], self.baseline)
        self.assertIsNone(gr.validate_baseline_dir(self.baseline, "PUMPUSDT"))

    def _assert_rejected(self, baseline_dir, contract="PUMPUSDT"):
        platform = _FakeEvolutionPlatform({}, [])
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence"
            with self.assertRaises(ev.EvolutionError) as caught:
                ev.run_evolution(**dict(TestG7Carriers.ARGS, contract=contract),
                                 lower_range=ev.default_range(0.00147),
                                 upper_range=ev.default_range(0.008984), platform=platform,
                                 evidence=evidence, top=1, fallback_leverages=(),
                                 baseline_dir=baseline_dir,
                                 run={"capital": 1000.0, "commission": 0.0005,
                                      "slippage": 0.0005, "leverage": 10})
            self.assertFalse(evidence.exists())  # no source generated or written
        self.assertTrue(str(caught.exception).startswith("G0 baseline-dir invalid: "))
        self.assertEqual(([], 0), (platform.paths, platform.backtests))
        return str(caught.exception)

    def test_missing_directory(self):
        self.assertIn("not found", self._assert_rejected(self.baseline / "nope"))

    def test_missing_carrier_file(self):
        (self.baseline / "table-b-summary.md").unlink()
        self.assertIn("table-b-summary.md", self._assert_rejected(self.baseline))

    def test_missing_contract_row(self):
        self.assertIn("XRPUSDT", self._assert_rejected(self.baseline, contract="XRPUSDT"))

    def test_cli_returns_nonzero_on_g0_failure(self):
        args = ["run", "--contract", "PUMPUSDT", "--instrument", "Crypto:PUMP/USDT@swap",
                "--lower", "0.00147", "--upper", "0.008984", "--gap-pct", "1.5",
                "--evolve-start", "2025-08-03", "--evolve-end", "2026-08-03",
                "--holdout-start", "2026-08-04", "--holdout-end", "2026-11-03",
                "--top", "1", "--fallback-leverages", "",
                "--baseline-dir", str(self.baseline / "nope")]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(ev.os.environ, {"QUANTDINGER_JWT": "offline-test"}), \
                mock.patch.object(ev.Platform, "call",
                                  side_effect=AssertionError("platform called")), \
                mock.patch.object(ev.Platform, "backtest",
                                  side_effect=AssertionError("platform called")):
            code = ev.main(args + ["--evidence-dir", str(Path(tmp) / "evidence")])
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
