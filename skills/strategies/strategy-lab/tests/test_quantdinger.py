"""Explicitly synthetic OFFLINE fixtures; never platform integration evidence."""

import copy
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "quantdinger.py"
LAB_ROOT = MODULE_PATH.parents[1]
STRATEGIES_ROOT = LAB_ROOT / "strategies"
RESEARCH_PATH = STRATEGIES_ROOT / "spy-close-research" / "research.py"
spec = importlib.util.spec_from_file_location("offline_quantdinger", MODULE_PATH)
qd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qd)
BASE = "http://offline.invalid"
PARAMS = {"ma_period": 50, "target_pct": 0.95}
CODE = "context.params.get('ma_period', 50)\ncontext.params.get('target_pct', 0.95)"
MANIFEST = {"markets": ["USStock"], "drivingFrequency": "1d", "directionMode": "long_only"}
DECLARED = [
    {"name": "ma_period", "type": "integer", "min": 2, "max": 250,
     "step": 1, "default": 50, "optimizable": True},
    {"name": "target_pct", "type": "percent", "min": 0, "max": 1,
     "step": 0.05, "default": 0.95, "optimizable": True},
]


def args(**overrides):
    parsed = qd.build_parser().parse_args([
        "trade", "--strategy-dir", "offline-case", "--start", "2023-01-01",
        "--end", "2025-12-31", "--capital", "10000", "--commission", "0.0005",
        "--slippage", "0.0005", "--max-drawdown-pct", "50",
        "--search", "ma_period:20:80:20",
    ])
    for key, value in overrides.items():
        setattr(parsed, key, value)
    return parsed


def run_wrapper(return_pct=20, drawdown=-10, params=None, run_id=11):
    values = dict(PARAMS if params is None else params)
    return {"runId": run_id, "jobId": "offline-backtest", "params": values,
            "run": {"id": run_id, "source_id": 7, "user_id": "offline-owner",
                    "params": dict(values), "start_date": "2023-01-01",
                    "end_date": "2025-12-31", "commission": 0.0005,
                    "slippage": 0.0005, "market": "USStock", "symbol": "SPY",
                    "market_type": "spot",
                    "manifest": {"leverageAllowed": False, "maxLeverage": 1},
                    "timeframe": "1d", "initial_capital": 10000, "result": {
                        "dataProvenance": {"kind": "market", "source": "synthetic/offline"},
                        "totalReturn": return_pct, "sharpeRatio": 1.2,
                        "maxDrawdown": drawdown, "totalExecutions": 10,
                        "executionAssumptions": {
                            "fundingMode": "not_modeled", "leverageEnabled": False,
                            "exchangeEquityProducts": [],
                        }}}}


def source_detail(**overrides):
    detail = {"id": 7, "user_id": "offline-owner", "code": CODE, "name": "offline-case",
              "asset_type": "script", "visibility": "private", "status": "draft",
              "metadata": {"strategy_manifest": dict(MANIFEST)},
              "param_schema": {"params": copy.deepcopy(DECLARED)}}
    detail.update(overrides)
    return detail


def bar(day):
    return {"time": int(dt.datetime(2024, 1, day, tzinfo=dt.timezone.utc).timestamp()),
            "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}


class OfflineDecisions(unittest.TestCase):
    def test_wrapper_metrics_and_csv_use_platform_result(self):
        wrapper = run_wrapper()
        evaluation = qd.evaluate_candidate(wrapper, max_drawdown_pct=50)
        self.assertEqual(evaluation["status"], qd.PASS)
        row = qd._comparison_row("baseline", wrapper, evaluation)
        self.assertEqual(row["totalReturn"], 20)
        self.assertEqual(row["runId"], 11)

    def test_baseline_with_no_candidates_is_kept(self):
        decision = qd.select_candidate(run_wrapper(), [], max_drawdown_pct=50)
        self.assertEqual(decision["classification"], "baseline-kept")
        self.assertEqual(decision["recommendedParams"], PARAMS)

    def test_six_selection_branches(self):
        cases = [
            (run_wrapper(), [run_wrapper(10)], "baseline-kept"),
            (run_wrapper(40, -60), [run_wrapper(10)], "candidate"),
            (run_wrapper(40, -60), [run_wrapper(10, -70)], "no-qualified-candidate"),
            (run_wrapper(), [run_wrapper(float("nan"))], "insufficient-evidence"),
            (run_wrapper(40, -60), [run_wrapper(None)], "insufficient-evidence"),
            (run_wrapper(), [run_wrapper(30, 1)], "baseline-kept"),
        ]
        for baseline, candidates, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(qd.select_candidate(baseline, candidates,
                                 max_drawdown_pct=50)["classification"], expected)

    def test_unknown_cost_identity_funding_and_params(self):
        for field in ("source_id", "user_id", "start_date", "commission", "params"):
            candidate = run_wrapper(30)
            del candidate["run"][field]
            self.assertEqual(qd.select_candidate(run_wrapper(), [candidate],
                             max_drawdown_pct=50)["classification"], "insufficient-evidence")
        candidate = run_wrapper(30)
        candidate["run"]["result"]["executionAssumptions"] = {"fundingMode": "not_modeled"}
        self.assertEqual(qd.evaluate_candidate(candidate, max_drawdown_pct=50)["status"], qd.UNKNOWN)


class OfflineAdditionalContracts(unittest.TestCase):
    def test_real_wire_provenance_required_not_fixture_or_unknown(self):
        for provenance in (None, {}, {"kind": "fixture", "source": "offline"}):
            wrapper = run_wrapper()
            wrapper["run"]["result"]["dataProvenance"] = provenance
            self.assertEqual(qd.evaluate_candidate(wrapper, max_drawdown_pct=50)["status"], qd.UNKNOWN)
        wrapper = run_wrapper()
        wrapper["run"]["symbol"] = "BTC"
        self.assertNotEqual(qd.evaluate_candidate(wrapper, max_drawdown_pct=50)["status"], qd.PASS)

    def test_missing_leverage_must_not_default_to_false(self):
        wrapper = run_wrapper()
        del wrapper["run"]["result"]["executionAssumptions"]["leverageEnabled"]
        self.assertEqual(qd.evaluate_candidate(wrapper, max_drawdown_pct=50)["status"], qd.UNKNOWN)

    def test_spot_unlevered_equity_funding_needs_all_evidence(self):
        def funding(wrapper):
            evaluation = qd.evaluate_candidate(wrapper, max_drawdown_pct=50)
            return next(item for item in evaluation["checks"]
                        if item["check"] == "fundingAndExposure")

        cases = {
            "contractMarketType": lambda row: row.update(market_type="contract"),
            "fundingMarketType": lambda row: row.update(market_type="funding"),
            "missingMarketType": lambda row: row.pop("market_type"),
            "leverageEnabled": lambda row: row["result"]["executionAssumptions"].update(
                leverageEnabled=True),
            "manifestLeverageAllowed": lambda row: row.update(
                manifest={"leverageAllowed": True, "maxLeverage": 2}),
            "missingManifest": lambda row: row.pop("manifest"),
            "cryptoMarket": lambda row: row.update(market="Crypto"),
            "cryptoContract": lambda row: row.update(market="Crypto", market_type="contract"),
            "otherSymbol": lambda row: row.update(symbol="QQQ"),
        }
        for name, case in cases.items():
            with self.subTest(case=name):
                wrapper = run_wrapper()
                case(wrapper["run"])
                self.assertEqual(funding(wrapper)["status"], qd.UNKNOWN)
        self.assertEqual(
            funding(run_wrapper()),
            {"check": "fundingAndExposure", "status": qd.PASS,
             "detail": "notApplicableSpotEquity"},
        )

    def test_readback_exact_run_id_and_complete_params_via_consumer(self):
        for change in ({"id": 99}, {"params": {**PARAMS, "unexpected": 1}},
                       {"initial_capital": 5000}):
            row = run_wrapper()["run"]
            row.update(change)
            responses = {"backtest_submit": {"jobId": "offline-bt"}, "backtest_get": row,
                         "backtest_history": {"items": [{"id": 11}]}}
            with patch.object(qd, "call_data", side_effect=lambda operation, **kw: responses[operation]), \
                 patch.object(qd, "poll_job", return_value={"status": "succeeded", "result": {"runId": 11}}):
                with self.subTest(change=change), self.assertRaises(qd.LabError):
                    qd.run_backtest(source_id=7, start="2023-01-01", end="2025-12-31",
                                    capital=10000, commission=0.0005, slippage=0.0005,
                                    params=PARAMS, base_url=BASE, token="offline", budget=qd.Budget())

    def test_readback_decimal_string_capital_matches_via_consumer(self):
        row = run_wrapper()["run"]
        row["initial_capital"] = "10000.00000000"
        responses = {"backtest_submit": {"jobId": "offline-bt"}, "backtest_get": row,
                     "backtest_history": {"items": [{"id": 11}]}}
        with patch.object(qd, "call_data", side_effect=lambda operation, **kw: responses[operation]) as calls, \
             patch.object(qd, "poll_job", return_value={"status": "succeeded", "result": {"runId": 11}}):
            result = qd.run_backtest(
                source_id=7, start="2023-01-01", end="2025-12-31", capital=10000.0,
                commission=0.0005, slippage=0.0005, params=PARAMS,
                base_url=BASE, token="offline", budget=qd.Budget())
        self.assertEqual(result["runId"], 11)
        self.assertEqual(result["run"]["initial_capital"], "10000.00000000")
        self.assertEqual(calls.call_args_list[0].kwargs["body"]["initialCapital"], 10000.0)
        self.assertEqual([call.args[0] for call in calls.call_args_list],
                         ["backtest_submit", "backtest_get", "backtest_history"])

    def test_readback_invalid_capital_is_contract_failure_via_consumer(self):
        for change in ({"initial_capital": 5000}, {"initial_capital": 10000.5},
                       {"initial_capital": "10000.50000000"}, {"initial_capital": "invalid"},
                       {}, {"initial_capital": None}, {"initial_capital": float("nan")},
                       {"initial_capital": float("inf")}, {"initial_capital": "-inf"}):
            row = run_wrapper()["run"]
            del row["initial_capital"]
            row.update(change)
            responses = {"backtest_submit": {"jobId": "offline-bt"}, "backtest_get": row,
                         "backtest_history": {"items": [{"id": 11}]}}
            with self.subTest(change=change), \
                 patch.object(qd, "call_data", side_effect=lambda operation, **kw: responses[operation]), \
                 patch.object(qd, "poll_job", return_value={"status": "succeeded", "result": {"runId": 11}}):
                with self.assertRaises(qd.LabError) as caught:
                    qd.run_backtest(
                        source_id=7, start="2023-01-01", end="2025-12-31", capital=10000.0,
                        commission=0.0005, slippage=0.0005, params=PARAMS,
                        base_url=BASE, token="offline", budget=qd.Budget())
                self.assertEqual(caught.exception.exit_code, qd.EXIT_CONTRACT)
                self.assertEqual(caught.exception.message, "backtest.capitalMismatch")

    def test_baseline_expected_params_not_hidden_by_wrapper(self):
        wrapper = run_wrapper()
        wrapper["run"]["params"] = {"ma_period": 20, "target_pct": 0.95}
        self.assertEqual(qd.select_candidate(wrapper, [], max_drawdown_pct=50)["classification"],
                         "insufficient-evidence")

    def test_run_count_guard_and_failed_post_not_retried(self):
        budget = qd.Budget()
        kwargs = dict(source_id=7, start="2023-01-01", end="2025-12-31", capital=10000,
                      commission=0.0005, slippage=0.0005, parameter_space=[], config={},
                      base_url=BASE, token="offline", budget=budget)
        with patch.object(qd, "call_data", side_effect=qd.LabError(qd.EXIT_BUDGET, "http.timeout")) as calls:
            with self.assertRaises(qd.LabError):
                qd.evolve_once(**kwargs)
            with self.assertRaises(qd.LabError):
                qd.evolve_once(**kwargs)
        calls.assert_called_once()
        self.assertEqual(budget.evolution_runs, 1)

    def test_unknown_estimate_cannot_be_interpreted_as_zero(self):
        for estimate in ({"folds": 4}, {"backtestRuns": float("nan"), "relativeUnits": 1},
                         {"backtestRuns": -1, "relativeUnits": 1}):
            with patch.object(qd, "call_data", return_value=estimate):
                with self.subTest(estimate=estimate), self.assertRaises(qd.LabError):
                    qd.estimate_evolution(parameter_space=[], config={"folds": 4},
                                         base_url=BASE, token="offline", budget=qd.Budget())

    def test_strategy_files_and_reports_symlink_escape_without_disk_writes(self):
        root = Path("/offline-lab")
        case = root / "case"
        for escaped in (case / "strategy.py", case / "config.json", case / "reports"):
            def resolve(path, *unused, **kwargs):
                return Path("/outside") if path == escaped else path
            with patch.object(Path, "resolve", autospec=True, side_effect=resolve), \
                 patch.object(Path, "is_file", return_value=True), \
                 patch.object(Path, "is_dir", return_value=True):
                with self.subTest(escaped=escaped), self.assertRaises(qd.LabError):
                    qd.resolve_strategy_dir(str(case), root)
        with self.assertRaises(qd.LabError):
            qd.resolve_strategy_dir("/outside/case", root)

    def test_whitelist_origin_paths_status_and_no_redirects(self):
        with patch.object(qd, "_http_call") as http:
            for base in ("http://user:pass@offline.invalid", "http://offline.invalid/api",
                         "http://offline.invalid#fragment", "http://offline.invalid?token=offline"):
                with self.subTest(base=base), self.assertRaises(qd.LabError):
                    qd.request_json("human_klines", base_url=base)
            with self.assertRaises(qd.LabError):
                qd.request_json("backtest_job", base_url=BASE, token="offline",
                                path_values={"jobId": "../escape"})
        http.assert_not_called()
        for status in (401, 403, 500):
            with self.subTest(status=status), self.assertRaises(qd.LabError):
                qd.parse_envelope("human_klines", status, {"code": 1, "data": []})
        self.assertIsNone(qd._NoRedirect().redirect_request(None, None, 302, "", {}, BASE))

    def test_research_200_row_minimum_and_repeatable_statistics_offline(self):
        path = RESEARCH_PATH
        research_spec = importlib.util.spec_from_file_location("offline_research", path)
        research = importlib.util.module_from_spec(research_spec)
        research_spec.loader.exec_module(research)
        with self.assertRaises(research.CLI.LabError):
            research.validate_rows([bar(1)])
        rows = [{**bar(1), "time": bar(1)["time"] + day * 86400, "close": 10 + day / 100,
                 "high": 20} for day in range(200)]
        research.validate_rows(rows)
        self.assertEqual(research.compute_statistics(rows), research.compute_statistics(copy.deepcopy(rows)))

    def test_strategy_dir_resolution_follows_strategies_root_layout(self):
        strategies_root = STRATEGIES_ROOT
        self.assertEqual(qd.STRATEGIES_ROOT.resolve(), strategies_root.resolve())
        sample = strategies_root / "spy-ma-smoke"
        self.assertTrue(sample.is_dir())
        self.assertFalse((strategies_root.parent / "spy-ma-smoke").exists())
        self.assertEqual(
            qd.resolve_strategy_dir(str(sample)).resolve(), sample.resolve()
        )
        for refused in (
            strategies_root.parent / "spy-ma-smoke",
            strategies_root / "nested-case" / "deeper-case",
            strategies_root.parent.parent / "outside-case",
        ):
            with self.subTest(refused=refused), self.assertRaises(qd.LabError):
                qd.resolve_strategy_dir(str(refused))

    def test_strategy_dir_resolution_accepts_new_instance_root_only(self):
        """New instance root is honoured; the two rejected layouts stay rejected."""
        strategies_root = STRATEGIES_ROOT
        sample = strategies_root / "spy-ma-smoke"
        resolved = qd.resolve_strategy_dir(str(sample))
        self.assertEqual(resolved, sample.resolve())
        # A research instance under the same root is not rejected for the path:
        # it only lacks the trade-only files the guard demands.
        with self.assertRaises(qd.LabError) as caught:
            qd.resolve_strategy_dir(str(strategies_root / "spy-close-research"))
        self.assertNotEqual(caught.exception.message, "strategyDir.outsideStrategiesRoot")
        rejected = (
            LAB_ROOT / "spy-ma-smoke",
            LAB_ROOT / "spy-close-research",
            strategies_root.parent / "spy-ma-smoke",
            strategies_root.parent / "spy-close-research",
            strategies_root / "nested" / "case",
            LAB_ROOT.parent / "spy-ma-smoke",
            LAB_ROOT.parent.parent / "outside-case",
        )
        for refused in rejected:
            with self.subTest(refused=refused), self.assertRaises(qd.LabError):
                qd.resolve_strategy_dir(str(refused))

    def test_research_sample_points_at_shared_lab_cli(self):
        path = RESEARCH_PATH
        research_spec = importlib.util.spec_from_file_location("offline_research_paths", path)
        research = importlib.util.module_from_spec(research_spec)
        research_spec.loader.exec_module(research)
        self.assertEqual(
            research.SCRIPTS_DIR.resolve(),
            (MODULE_PATH.parents[1] / "scripts").resolve(),
        )
        self.assertTrue((research.SCRIPTS_DIR / "quantdinger.py").is_file())

    def test_research_sample_resolves_strategies_root_and_cli_from_its_own_dir(self):
        research_spec = importlib.util.spec_from_file_location(
            "offline_research_layout", RESEARCH_PATH
        )
        research = importlib.util.module_from_spec(research_spec)
        research_spec.loader.exec_module(research)
        self.assertEqual(
            research.STRATEGIES_ROOT.resolve(), STRATEGIES_ROOT.resolve()
        )
        self.assertEqual(
            research.SCRIPTS_DIR.resolve(),
            (LAB_ROOT / "scripts").resolve(),
        )


class OfflineSource(unittest.TestCase):
    def save(self, detail, **kwargs):
        def fake(operation, **request):
            if operation == "compile_source":
                return {"manifest": MANIFEST, "backtestRangePolicy": {"maxSelectedDays": 2000}}
            if operation == "create_source":
                return {"id": 7}
            if operation == "source_detail":
                return detail
            self.fail(operation)
        with patch.object(qd, "call_data", side_effect=fake) as calls:
            try:
                return qd.save_source(code=CODE, name="offline-case", description="offline",
                                      template_key="strategy_v2_single_ma", base_url=BASE,
                                      token="offline", **kwargs)
            finally:
                self.calls = calls.call_args_list

    def test_reuse_validates_all_private_source_fields(self):
        for change in ({"visibility": "public"}, {"status": "published"},
                       {"asset_type": "other"}, {"metadata": {}}, {"user_id": None},
                       {"metadata": {"strategy_manifest": {"markets": ["Crypto"]},
                                     "param_schema": DECLARED}}):
            with self.subTest(change=change), self.assertRaises(qd.LabError):
                self.save(source_detail(**change), source_id=7)
        self.assertFalse(any(call.args[0] == "create_source" for call in self.calls))

    def test_create_metadata_mismatch_rereads_once_never_recreates(self):
        with self.assertRaises(qd.LabError):
            self.save(source_detail(metadata={}))
        operations = [call.args[0] for call in self.calls]
        self.assertEqual(operations.count("create_source"), 1)
        self.assertEqual(operations.count("source_detail"), 2)

    def test_prepare_checks_manifest_before_create(self):
        def fake(operation, **kwargs):
            return {"public_config": {"billing_enabled": False},
                    "script_templates": {"items": [{"key": "strategy_v2_single_ma"}]},
                    "compile_source": {"manifest": {**MANIFEST, "markets": ["Crypto"]},
                                       "backtestRangePolicy": {}},
                    "create_source": {"id": 7}, "source_detail": source_detail()}[operation]
        with patch.object(qd, "call_data", side_effect=fake) as calls:
            with self.assertRaises(qd.LabError):
                qd._prepare_source(code=CODE, args=args(), base_url=BASE, token="offline")
        self.assertNotIn("create_source", [call.args[0] for call in calls.call_args_list])


class OfflineMarketData(unittest.TestCase):
    def test_end_cursor_and_strictly_decreasing_pages(self):
        request = Mock(side_effect=[[bar(3), bar(2)], [bar(1)], []])
        result = qd.fetch_klines(base_url=BASE, start="2024-01-01", end="2024-01-03",
                                 request=request)
        first = request.call_args_list[0].kwargs["params"]
        self.assertEqual(first["before_time"], bar(3)["time"] + 86400)
        cursors = [call.kwargs["params"]["before_time"] for call in request.call_args_list]
        self.assertTrue(all(right < left for left, right in zip(cursors, cursors[1:])))
        self.assertEqual([item["time"] for item in result], [bar(i)["time"] for i in (1, 2, 3)])

    def test_bad_bar_is_failure_not_silently_dropped(self):
        for bad in ({**bar(1), "close": float("nan")}, {"time": "invalid"},
                    {**bar(1), "high": 1}, {**bar(1), "time": float("inf")}):
            with self.subTest(bad=bad), self.assertRaises(qd.LabError):
                qd.fetch_klines(base_url=BASE, request=Mock(return_value=[bar(2), bad]))

    def test_four_page_hard_limit(self):
        request = Mock(side_effect=[[bar(i)] for i in (4, 3, 2, 1)] + [[]])
        with self.assertRaises(qd.LabError):
            qd.fetch_klines(base_url=BASE, max_pages=5, request=request)
        self.assertEqual(request.call_count, 0)

    def test_total_180_second_budget(self):
        clock = [0.0]
        def fake(*unused, **kwargs):
            clock[0] += 100
            return [bar(3 if clock[0] == 100 else 2)]
        with patch.object(qd.time, "monotonic", side_effect=lambda: clock[0]):
            with self.assertRaises(qd.LabError) as caught:
                qd.fetch_klines(base_url=BASE, request=fake)
        self.assertEqual(caught.exception.exit_code, qd.EXIT_BUDGET)
        self.assertEqual(clock[0], 200)

    def test_empty_and_repeated_pages_and_time_units(self):
        self.assertEqual(qd.fetch_klines(base_url=BASE, request=Mock(return_value=[])), [])
        request = Mock(return_value={"klines": [bar(1)]})
        self.assertEqual(len(qd.fetch_klines(data_api="agent", base_url=BASE,
                                          request=request)), 1)
        self.assertLessEqual(request.call_count, 2)
        for value in (bar(1)["time"], bar(1)["time"] * 1000, "2024-01-01T08:00:00+08:00"):
            self.assertEqual(qd.parse_bar_time(value).timestamp(), bar(1)["time"])


class OfflineInputsAndPrivacy(unittest.TestCase):
    def test_nonfinite_search_and_fractional_integer_rejected(self):
        for text in ("ma_period:nan:80:20", "ma_period:20:inf:20", "ma_period:20:80:nan"):
            with self.subTest(text=text), self.assertRaises(qd.LabError):
                qd._parse_search(text)
        with self.assertRaises(qd.LabError):
            qd.build_parameter_space(DECLARED,
                [{"name": "ma_period", "min": 20.5, "max": 80, "step": 0.5}], PARAMS, CODE)

    def test_nonfinite_trade_inputs_and_invalid_budgets(self):
        for key in ("capital", "commission", "slippage", "max_drawdown_pct"):
            with self.subTest(key=key), self.assertRaises(qd.LabError):
                qd._validate_trade_args(args(**{key: float("nan")}))
        for change in ({"trials": 0}, {"folds": 3}, {"max_evolution_runs": 0},
                       {"max_relative_units": -1}, {"wall_seconds": float("nan")},
                       {"method": "tpe", "trials": 23}):
            with self.subTest(change=change), self.assertRaises(qd.LabError):
                qd._evolution_config(args(**change))

    def test_trade_command_reports_explicit_source_id_only(self):
        explicit = qd._trade_command(args(source_id=4))
        self.assertIn("--source-id 4", explicit)
        self.assertLess(explicit.index("--strategy-dir offline-case"),
                        explicit.index("--source-id 4"))
        self.assertLess(explicit.index("--source-id 4"), explicit.index("--start 2023-01-01"))
        default = qd._trade_command(args())
        self.assertNotIn("--source-id", default)
        for text in (explicit, default):
            for token in ("--strategy-dir offline-case", "--start 2023-01-01",
                          "--end 2025-12-31", "--capital 10000.0", "--commission 0.0005",
                          "--slippage 0.0005", "--objective totalReturn",
                          "--max-drawdown-pct 50.0", "--method grid", "--trials 4",
                          "--folds 4", "--max-evolution-runs 8", "--max-relative-units 8",
                          "--wall-seconds 1200.0", "--search ma_period:20:80:20"):
                self.assertIn(token, text)

    def test_source_parameter_consumption_not_comment_or_string(self):
        for code in ("# context.params.get('ma_period', 50)",
                     '"context.params.get(\'ma_period\', 50)"'):
            with self.assertRaises(qd.LabError):
                qd.build_parameter_space(DECLARED, [qd._parse_search("ma_period:20:80:20")],
                                         PARAMS, code)

    def test_declared_rows_without_optimizable_flag_build_search_space(self):
        declared = [{key: value for key, value in row.items() if key != "optimizable"}
                    for row in DECLARED]
        rows = qd.build_parameter_space(declared, [qd._parse_search("ma_period:20:80:20")],
                                        PARAMS, CODE)
        self.assertEqual(rows[0], {"name": "ma_period", "type": "integer",
                                   "min": 20, "max": 80, "step": 20})
        self.assertEqual(rows[1], {"name": "target_pct", "type": "percent",
                                   "min": 0.95, "max": 0.95, "step": 0.05})
        with self.assertRaises(qd.LabError) as caught:
            qd.build_parameter_space([{**DECLARED[0], "optimizable": False}],
                                     [qd._parse_search("ma_period:20:80:20")],
                                     {"ma_period": 50}, CODE)
        self.assertEqual(caught.exception.message, "parameter.notOptimizable")

    def test_reports_do_not_serialize_sensitive_nested_fields(self):
        report = {"title": "offline", "identifiers": {"sourceId": 7, "user_id": "PRIVATE_OWNER",
                  "token": "PRIVATE_TOKEN"}, "recommendedParams": {"ma_period": 50,
                  "password": "PRIVATE_PASSWORD"}, "summary": "Bearer abc.def.ghi",
                  "headers": {"Authorization": "PRIVATE_HEADER"}}
        with patch.object(qd, "_atomic_write") as writes:
            qd.write_report(Path("offline-case"), report=report,
                            comparison_rows=[{"role": "baseline", "params":
                                              json.dumps({"token": "PRIVATE_CSV_TOKEN"})}])
        text = "\n".join(call.args[1] for call in writes.call_args_list)
        self.assertNotIn("PRIVATE_", text)
        self.assertNotIn("abc.def.ghi", text)

    def test_import_has_no_file_or_network_io(self):
        isolated = importlib.util.module_from_spec(spec)
        with patch("urllib.request.OpenerDirector.open") as network, \
             patch.object(Path, "read_text") as read, patch.object(Path, "write_text") as write:
            spec.loader.exec_module(isolated)
        network.assert_not_called()
        read.assert_not_called()
        write.assert_not_called()

    def test_whitelist_and_business_envelopes(self):
        with self.assertRaises(qd.LabError):
            qd.request_json("/api/auth/login", base_url=BASE)
        self.assertEqual(qd.parse_envelope("human_klines", 200, {"code": 1, "data": []}), [])
        self.assertEqual(qd.parse_envelope("agent_klines", 200, {"code": 0, "data": {}}), {})
        with self.assertRaises(qd.LabError):
            qd.parse_envelope("human_klines", 200, {"code": 0, "data": []})


class OfflineOrchestration(unittest.TestCase):
    """Real run_trade/run_backtest/evolve_once consumers with an offline backend."""

    def execute_trade(self, *, top=None, baseline=None, state="succeeded", estimates=None,
                      scope="declared", declared=None, changes=None, actual=6):
        self.operations = []
        self.submissions = []
        self.evolution_bodies = []
        self.estimate_bodies = []
        self.saved_report = None
        estimate_rows = iter(estimates or [{"backtestRuns": 6, "relativeUnits": 6, "folds": 4}])
        base = baseline or run_wrapper()
        def fake(operation, **request):
            self.operations.append(operation)
            body = request.get("body", {})
            if operation == "public_config":
                return {"billing_enabled": False}
            if operation == "script_templates":
                return {"items": [{"key": "strategy_v2_single_ma"}]}
            if operation == "compile_source":
                return {"manifest": MANIFEST, "backtestRangePolicy": {"maxSelectedDays": 2000}}
            if operation == "create_source":
                return {"id": 7}
            if operation == "source_detail":
                return source_detail()
            if operation == "backtest_submit":
                self.submissions.append(copy.deepcopy(body))
                return {"jobId": "offline-bt-" + str(len(self.submissions))}
            if operation == "backtest_get":
                submitted = self.submissions[-1]
                wrapper = copy.deepcopy(base) if len(self.submissions) == 1 else run_wrapper(
                    30 if submitted["params"]["ma_period"] == 20 else 10,
                    params=submitted["params"], run_id=10 + len(self.submissions))
                wrapper["run"]["id"] = 10 + len(self.submissions)
                return wrapper["run"]
            if operation == "backtest_history":
                return {"items": [{"id": 10 + len(self.submissions)}]}
            if operation == "evolution_parameter_space":
                return {"scope": scope, "parameters": DECLARED if declared is None else declared}
            if operation == "evolution_estimate":
                self.estimate_bodies.append(copy.deepcopy(body))
                return next(estimate_rows)
            if operation == "evolution_run":
                self.evolution_bodies.append(copy.deepcopy(body))
                return {"jobId": "offline-evo"}
            if operation == "evolution_jobs":
                return {"items": [{"jobId": "offline-evo"}]}
            self.fail(operation)
        def poll(operation, job_id, **unused):
            if operation == "backtest_job":
                return {"status": "succeeded", "result": {"runId": 10 + len(self.submissions)}}
            return {"status": state, "progress": {"failure": {"messageKey": "offline.failed",
                    "dominantReason": "offline", "reasonCounts": {"offline": 1},
                    "actualBacktestRuns": actual}}, "result": {"source": {"id": 7},
                    "summary": {"actualBacktestRuns": actual, "recommended": True,
                                "maxDrawdown": 1, "selectionObjective": "oosCompoundedReturn"},
                    "selection": {"objective": "oosCompoundedReturn", "blindUsedForSelection": False},
                    "topCandidates": [] if top is None else top}}
        def capture(strategy_dir, **kwargs):
            self.saved_report = copy.deepcopy(kwargs)
        with patch.object(qd, "resolve_strategy_dir", return_value=Path("offline-case")), \
             patch.object(Path, "read_text", return_value=CODE), \
             patch.object(qd, "_read_json", return_value=PARAMS), \
             patch.dict(qd.os.environ, {"QUANTDINGER_BASE_URL": BASE, "QUANTDINGER_JWT": "offline"}, clear=True), \
             patch.object(qd, "call_data", side_effect=fake), \
             patch.object(qd, "poll_job", side_effect=poll), \
             patch.object(qd, "write_report", side_effect=capture):
            return qd.run_trade(args(**(changes or {})))

    def test_empty_and_baseline_only_candidates_keep_and_persist_baseline(self):
        for top in ([], [{"params": PARAMS}]):
            with self.subTest(top=top):
                self.assertEqual(self.execute_trade(top=top), 0)
                self.assertEqual(self.saved_report["report"]["classification"], "baseline-kept")
                self.assertEqual(len(self.submissions), 2)
                self.assertEqual(self.submissions[-1]["params"], PARAMS)
                ids = self.saved_report["report"]["identifiers"]
                self.assertNotEqual(ids["baselineRunId"], ids["finalRunId"])

    def test_candidate_dedup_final_persist_and_effective_plan(self):
        top = [{"params": PARAMS}, {"params": {"ma_period": 20}},
               {"params": {"ma_period": 20}}]
        self.assertEqual(self.execute_trade(top=top, estimates=[
            {"backtestRuns": 20, "relativeUnits": 20}, {"backtestRuns": 4, "relativeUnits": 4}]), 0)
        self.assertEqual(len(self.submissions), 3)
        self.assertTrue(all(item["persist"] for item in self.submissions))
        self.assertTrue(all(item["params"]["target_pct"] == 0.95 for item in self.submissions))
        self.assertEqual(self.evolution_bodies[0]["config"], self.estimate_bodies[-1]["config"])
        self.assertEqual(self.evolution_bodies[0]["parameterSpace"], self.estimate_bodies[-1]["parameterSpace"])
        self.assertEqual(self.saved_report["report"]["budget"]["evolutionRuns"], 1)
        self.assertEqual(self.saved_report["report"]["budget"]["fullPeriodGroups"], 2)
        self.assertEqual(self.saved_report["report"]["budget"]["outerBacktestJobs"], 3)

    def test_estimate_over_budget_stops_after_three_without_run(self):
        with self.assertRaises(qd.LabError) as caught:
            self.execute_trade(estimates=[{"backtestRuns": 100, "relativeUnits": 100}] * 3)
        self.assertEqual(caught.exception.exit_code, qd.EXIT_BUDGET)
        self.assertEqual(len(self.estimate_bodies), 3)
        self.assertFalse(self.evolution_bodies)
        self.assertTrue(all(item["config"]["folds"] == 4 for item in self.estimate_bodies))

    def test_failed_cancelled_interrupted_submit_once_and_preserve_diagnostics(self):
        for state in ("failed", "cancelled", "workerInterrupted"):
            with self.subTest(state=state), self.assertRaises(qd.LabError) as caught:
                self.execute_trade(state=state)
            self.assertEqual(len(self.evolution_bodies), 1)
            self.assertEqual(len(self.submissions), 1)
            self.assertEqual(caught.exception.details["reasonCounts"], {"offline": 1})
            self.assertEqual(self.saved_report["report"]["budget"]["internalBacktestRunsReported"], 6)

    def test_actual_over_budget_or_unknown_never_rechecks_or_recommends(self):
        for actual in (9, None):
            with self.subTest(actual=actual), self.assertRaises(qd.LabError):
                self.execute_trade(actual=actual, top=[{"params": {"ma_period": 20}}])
            self.assertEqual(len(self.submissions), 1)
            self.assertEqual(len(self.evolution_bodies), 1)

    def test_skips_do_not_evolve_and_still_check_baseline(self):
        for options in ({"scope": "none"}, {"declared": []},
                        {"declared": [{**row, "optimizable": False} for row in DECLARED]},
                        {"changes": {"search": []}}, {"changes": {"skip_evolution": True}}):
            with self.subTest(options=options):
                self.assertEqual(self.execute_trade(**options), 0)
                self.assertFalse(self.evolution_bodies)
                self.assertEqual(self.saved_report["report"]["classification"], "skipped")
                self.assertTrue(self.saved_report["report"]["reason"])
        self.assertEqual(self.execute_trade(baseline=run_wrapper(None),
                                           changes={"skip_evolution": True}), qd.EXIT_EVIDENCE)

    def test_no_qualified_or_unknown_no_final_run(self):
        self.assertEqual(self.execute_trade(baseline=run_wrapper(20, -60)), 0)
        self.assertEqual(self.saved_report["report"]["classification"], "no-qualified-candidate")
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(self.execute_trade(baseline=run_wrapper(None)), qd.EXIT_EVIDENCE)
        self.assertEqual(len(self.submissions), 1)

    def test_declared_rows_without_optimizable_flag_run_evolution(self):
        declared = [{key: value for key, value in row.items() if key != "optimizable"}
                    for row in DECLARED]
        self.assertEqual(self.execute_trade(declared=declared), 0)
        self.assertTrue(self.evolution_bodies)
        self.assertEqual(self.evolution_bodies[0]["parameterSpace"][0],
                         {"name": "ma_period", "type": "integer",
                          "min": 20, "max": 80, "step": 20})
        report = self.saved_report
        self.assertIsNotNone(report)
        self.assertEqual(report["report"]["classification"], "baseline-kept")

    def test_baseline_missing_spot_evidence_stops_insufficient(self):
        wrapper = run_wrapper()
        del wrapper["run"]["market_type"]
        self.assertEqual(self.execute_trade(baseline=wrapper), qd.EXIT_EVIDENCE)
        report = self.saved_report
        self.assertIsNotNone(report)
        self.assertEqual(report["report"]["reason"], "baselineEvidenceUnknown")


class OfflinePolling(unittest.TestCase):
    def test_deadline_before_poll_cancels_exact_id_then_gets_once(self):
        request = Mock(return_value=(200, {"code": 1, "data": {"status": "cancelled"}}))
        with patch.object(qd, "request_json", request):
            with self.assertRaises(qd.LabError) as caught:
                qd.poll_job("backtest_job", "offline-id", base_url=BASE, token="offline",
                            deadline=10, monotonic_fn=lambda: 10, cancel_operation="backtest_cancel")
        self.assertEqual([call.args[0] for call in request.call_args_list],
                         ["backtest_cancel", "backtest_job"])
        for call in request.call_args_list:
            self.assertEqual(call.kwargs["path_values"], {"jobId": "offline-id"})
        self.assertEqual(caught.exception.details["readBackStatus"], "cancelled")
        self.assertNotEqual(caught.exception.details["remoteStopped"], "True")

    def test_subsecond_remaining_budget_reaches_http_timeout(self):
        with patch.object(qd, "_http_call", return_value=b'{"code":1,"data":{"status":"succeeded"}}') as http:
            qd.poll_job("backtest_job", "offline-id", base_url=BASE, token="offline",
                        deadline=10, monotonic_fn=lambda: 9.75)
        self.assertLessEqual(http.call_args.args[-1], 0.25)

    def test_http_auth_failure_once_no_fallback(self):
        for status in (401, 403):
            with patch.object(qd, "_http_call", side_effect=qd.LabError(qd.EXIT_AUTH, f"http.{status}")) as http:
                with self.assertRaises(qd.LabError) as caught:
                    qd.fetch_klines(base_url=BASE, data_api="agent", token="offline")
            self.assertEqual(caught.exception.exit_code, qd.EXIT_AUTH)
            http.assert_called_once()


if __name__ == "__main__":
    unittest.main()
