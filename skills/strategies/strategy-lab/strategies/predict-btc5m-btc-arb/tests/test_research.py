"""Synthetic, offline recovery regressions; not real-market evidence or Verify."""

import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

INSTANCE = Path(__file__).resolve().parents[1]
ROOT = INSTANCE.parents[4]
BOT = ROOT / "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


research = load(INSTANCE / "research.py", "btc5m_research_test")
launcher = load(INSTANCE / "tests/offline_exec.py", "btc5m_launcher_test")


def bar(at=1794204000, close=101.0):
    return {"time": at, "open": 100.0, "high": 103.0, "low": 99.0,
            "close": close, "volume": 0.0}


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="btc5m-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.argv = ["--rust-bin", str(BOT / "target/debug/btc_arb_replay"),
                     "--evidence-dir", str(self.directory / "evidence"), "--no-publish"]
        self.args = research.parse_args(self.argv)
        self.budget = research.Budget(max_requests=50, wall_seconds=1800)
        for target in ("resolve_agent_token", "agent_call"):
            guard = mock.patch.object(research._quantdinger, target,
                                      side_effect=AssertionError("network/token forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        guard = mock.patch.object(research, "check_documents",
                                  side_effect=AssertionError("HTTP forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_root_and_absolute_arguments(self):
        self.assertEqual(research.PROJECT_ROOT, ROOT)
        parsed = research.parse_args(["--rust-bin", "bin", "--evidence-dir", "destination"])
        self.assertEqual(parsed.rust_bin, str(ROOT / "bin"))
        self.assertEqual(parsed.evidence_dir, str(ROOT / "destination"))
        self.assertEqual(Path(str(launcher.__file__)).resolve().parents[6], ROOT)

    def test_page_duplicate_normalized_seconds_milliseconds(self):
        first = bar()
        second = dict(first, time=first["time"] * 1000)
        seen, counts, pages = {}, {}, []
        research.check_page({"klines": [first, second]}, pages, seen, counts)
        research.check_page({"klines": [first]}, pages, seen, counts)
        self.assertEqual(counts, {"raw_count": 3, "duplicate_count": 2})
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(pages), 2)

    def test_every_ohlcv_conflict_same_and_cross_page(self):
        for field in ("open", "high", "low", "close", "volume"):
            for cross in (False, True):
                with self.subTest(field=field, cross=cross):
                    original = bar()
                    changed = dict(original, **{field: original[field] + 0.1})
                    seen, counts, pages = {}, {}, []
                    if cross:
                        research.check_page({"klines": [original]}, pages, seen, counts)
                    with self.assertRaisesRegex(research.ResearchError, "ohlc.conflict"):
                        research.check_page({"klines": [changed] if cross else [original, changed]},
                                            pages, seen, counts)
                    self.assertEqual(counts["conflict_count"], 1)

    def test_alignment_rejects_minutes_seconds_microseconds(self):
        for timestamp in (1794204060, 1794204240, 1794204001,
                          "2026-11-09T06:00:00.000001Z"):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(research.ResearchError, "barNotAligned"):
                    research.check_page({"klines": [dict(bar(), time=timestamp)]}, [])

    def test_invalid_ohlcv_and_zero_volume(self):
        research.check_page({"klines": [bar()]}, [])
        for changed in (dict(bar(), volume=True), dict(bar(), close=float("nan")),
                        dict(bar(), volume=-1), dict(bar(), high=0)):
            with self.assertRaises(research.ResearchError):
                research.check_page({"klines": [changed]}, [])

    def synthetic_pairs(self):
        start = int(research.parse_utc(self.args.start_utc, "start").timestamp())
        end = int(research.parse_utc(self.args.end_utc, "end").timestamp())
        bars = [bar(at, 100.0 + (at // 300) % 3) for at in range(start - 300, end, 300)]
        rows = [{"event_type": "value", "available_at_ms": at * 1000,
                 "p_up": 0.6, "sigma": 0.001} for at in range(start, end, 300)]
        return bars, rows

    def test_all_planned_boundaries_split_and_tail(self):
        bars, rows = self.synthetic_pairs()
        samples = research.pair_samples(bars, rows, self.args)
        self.assertEqual(len(samples), 288)
        self.assertEqual(samples[143]["partition"], "IS")
        self.assertEqual(samples[144]["partition"], "OOS")
        self.assertEqual(samples[-1]["reason"], "label_missing")
        self.assertEqual(samples[-1]["partition"], "excluded")
        self.assertNotIn("cross_split", samples[-1]["reason"])
        for sample in samples[:-1]:
            self.assertAlmostEqual(sample["brier"], (0.6 - sample["proxy_label"]) ** 2)
            self.assertAlmostEqual(sample["baseline_brier"], (0.5 - sample["proxy_label"]) ** 2)

    def test_missing_bar_left_join_and_missing_value_failure(self):
        bars, rows = self.synthetic_pairs()
        full = research.pair_samples(bars, rows, self.args)
        del bars[20]
        samples = research.pair_samples(bars, rows, self.args)
        self.assertEqual([s["t_utc"] for s in samples], [s["t_utc"] for s in full])
        self.assertIn("bar_missing", samples[20]["reason"])
        bars, rows = self.synthetic_pairs()
        del rows[20]
        with self.assertRaisesRegex(research.ResearchError, "rust.valueMissing"):
            research.pair_samples(bars, rows, self.args)

    def test_proxy_trade_and_equity_are_na_and_fixture_not_counted(self):
        samples = research.pair_samples(*self.synthetic_pairs(), self.args)
        comparison = research.build_comparison(samples, self.args)
        self.assertEqual(len(comparison), 114)
        for row in comparison:
            if row["evidence_type"] != "real-proxy":
                self.assertEqual(row["value"], "N/A")
            elif row["metric"] in ("candidate_count", "trade_count"):
                self.assertEqual((row["value"], row["reason"]), ("N/A", "proxy_only"))
            elif row["metric"] == "net_pnl":
                self.assertEqual((row["value"], row["reason"]),
                                 ("N/A", "no_real_account_equity"))

    def test_raw_unique_mutually_exclusive_coverage_counts(self):
        bars, _ = self.synthetic_pairs()
        seen, counts = {}, {"raw_count": 0, "duplicate_count": 0, "conflict_count": 0}
        raw = bars + [bars[0], bar(bars[-1]["time"] + 300), bar(bars[-1]["time"] + 600)]
        research.check_page({"klines": raw}, [], seen, counts)
        coverage = research.build_coverage(bars, self.args, dict(counts, raw_seen=seen), self.budget)
        self.assertEqual(coverage["raw_count"], coverage["unique_count"] + coverage["duplicate_count"])
        self.assertEqual(coverage["unique_count"], sum(coverage[key] for key in
                         ("closed_count", "excluded_range_count", "excluded_future_count", "excluded_unclosed_count")))
        without_raw = research.build_coverage(bars, self.args, {}, self.budget)
        self.assertIsNone(without_raw["raw_count"])
        self.assertIsNone(without_raw["unique_count"])

    def test_atomic_writer_refuses_existing_and_symlink(self):
        target = self.directory / "existing"
        target.write_text("original")
        link = self.directory / "link"
        link.symlink_to(target)
        for path in (target, link):
            for writer in (lambda: research.write_json(path, {}),
                           lambda: research.write_csv(path, [], ["column"]),
                           lambda: research.write_text(path, "replacement")):
                with self.assertRaises(FileExistsError):
                    writer()
        self.assertEqual(target.read_text(), "original")

    def test_main_collision_precedes_fetch_and_retains_original(self):
        destination = Path(self.args.evidence_dir)
        destination.mkdir()
        sentinel = destination / "parameters.json"
        sentinel.write_text("original")
        with mock.patch.object(research, "fetch_bars", side_effect=AssertionError("too early")):
            self.assertEqual(research.main(self.argv), 64)
        self.assertEqual(sentinel.read_text(), "original")

    def test_main_parameters_precede_business_and_exit_three(self):
        def work(args, directory, budget, commands):
            payload = json.loads((directory / "parameters.json").read_text())
            self.assertEqual(payload["parameters"]["warmup_prices"], 21)
            return 3
        with mock.patch.object(research, "research", side_effect=work):
            self.assertEqual(research.main(self.argv), 3)
        self.assertEqual(json.loads((Path(self.args.evidence_dir) / "commands.json").read_text())[
            "research_exit_code"], 3)

    def test_main_failure_keeps_native_code_and_final_command_index(self):
        with mock.patch.object(research, "research", side_effect=research.ResearchError(5, "timeout")):
            self.assertEqual(research.main(self.argv), 5)
        saved = json.loads((Path(self.args.evidence_dir) / "commands.json").read_text())
        self.assertEqual(saved["research_exit_code"], 5)
        self.assertEqual(saved["request_count"], 0)

    def test_rust_success_failure_and_timeout_logs_env_fds(self):
        for result in (0, 2, 3, 5, 64, "timeout"):
            with self.subTest(result=result):
                directory = self.directory / str(result)
                directory.mkdir()
                calls = []
                effect = subprocess.TimeoutExpired(["binary"], 1, output=b"partial") if result == "timeout" else None
                completed = subprocess.CompletedProcess([], 0 if result == "timeout" else result,
                                                        "out", "err")
                with mock.patch.object(research.subprocess, "run", return_value=completed,
                                       side_effect=effect) as run:
                    arguments = (Path(self.args.rust_bin), "proxy", INSTANCE / "config.json",
                                 directory / "input", directory / "output", directory / "summary",
                                 0, 1000, self.budget, calls)
                    if result == "timeout":
                        with self.assertRaises(research.ResearchError) as caught:
                            research.run_rust(*arguments)
                        self.assertEqual(caught.exception.exit_code, 5)
                    else:
                        self.assertEqual(research.run_rust(*arguments)["exit_code"], result)
                    self.assertEqual(run.call_args.kwargs["env"], {"LANG": "C.UTF-8", "TZ": "UTC"})
                    self.assertTrue(run.call_args.kwargs["close_fds"])
                self.assertTrue((directory / "command-1.log").is_file())
                self.assertEqual(len(calls), 1)
                self.assertIn("ended_at_utc", calls[0])

    def test_archived_availability_timestamp_and_sources_preserved(self):
        source = self.directory / "availability.json"
        original = {"checked_at_utc": "2020-01-01T00:00:00Z", "sources": [{"status": "200"}], "rows": []}
        source.write_text(json.dumps(original))
        self.args.availability_file = str(source)
        result = research.review_availability(self.args)
        self.assertEqual(result["checked_at_utc"], original["checked_at_utc"])
        self.assertEqual(result["sources"], original["sources"])
        self.assertEqual(result["historical_command_logs"], "NOT_CAPTURED")
        self.assertEqual(len(result["checked_files"]), 5)

    def test_request_injection_refuses_conflict_before_merge(self):
        args = self.args
        params = {"market": "Crypto", "symbol": "BTCUSDT", "timeframe": "5m", "limit": 500}
        replies = [({"klines": [bar()]}, {}), ({"klines": [dict(bar(), close=102.0)]}, {})]
        def fetch(**kwargs):
            request = kwargs["request"]
            request("agent_klines", base_url="offline.invalid", token="offline", params=params, timeout=1)
            request("agent_klines", base_url="offline.invalid", token="offline", params=params, timeout=1)
            self.fail("conflicting later page reached client merge")
        with mock.patch.dict(os.environ, {"QUANTDINGER_BASE_URL": "offline.invalid"}), \
             mock.patch.object(research._quantdinger, "resolve_agent_token", return_value="offline"), \
             mock.patch.object(research._quantdinger, "agent_call", side_effect=replies), \
             mock.patch.object(research._quantdinger, "fetch_klines", side_effect=fetch):
            with self.assertRaisesRegex(research.ResearchError, "ohlc.conflict"):
                research.fetch_from_agent(args, self.budget)

    def test_offline_raw_pages_conflict_and_ohlc_mismatch(self):
        archive = self.directory / "ohlc.json"
        pages = self.directory / "pages.json"
        archive.write_text(json.dumps({"schema_version": research.SCHEMA_VERSION, "bars": [bar()]}))
        self.args.ohlc_file, self.args.raw_pages_file = str(archive), str(pages)
        pages.write_text(json.dumps({"pages": [{"klines": [bar(), dict(bar(), close=102.0)]}]}))
        with self.assertRaisesRegex(research.ResearchError, "ohlc.conflict"):
            research.fetch_bars(self.args, self.budget)
        pages.write_text(json.dumps({"pages": [{"klines": [dict(bar(), close=102.0)]}]}))
        with self.assertRaisesRegex(research.ResearchError, "rawPagesMismatch"):
            research.fetch_bars(self.args, self.budget)

    def test_research_maps_native_errors_and_invalid_success(self):
        bars, _ = self.synthetic_pairs()
        for native, expected in ((2, 2), (64, 64), (5, 2), (3, 2)):
            with self.subTest(native=native):
                directory = self.directory / f"native-{native}"
                directory.mkdir()
                with mock.patch.object(research, "fetch_bars", return_value=(bars, {})), \
                     mock.patch.object(research, "check_documents", return_value=[]), \
                     mock.patch.object(research, "run_rust", return_value={
                         "exit_code": native, "summary": {}, "stdout": "", "stderr": ""}):
                    with self.assertRaises(research.ResearchError) as caught:
                        research.research(self.args, directory, self.budget, [])
                    self.assertEqual(caught.exception.exit_code, expected)

    def test_missing_summary_and_nonempty_input_empty_output_rejected(self):
        bars, _ = self.synthetic_pairs()
        directory = self.directory / "empty-output"
        directory.mkdir()
        with mock.patch.object(research, "fetch_bars", return_value=(bars, {})), \
             mock.patch.object(research, "check_documents", return_value=[]), \
             mock.patch.object(research, "run_rust", return_value={
                 "exit_code": 3, "summary": {"schema_version": research.REPLAY_SCHEMA_VERSION}}):
            with self.assertRaisesRegex(research.ResearchError, "rust.outputMissing"):
                research.research(self.args, directory, self.budget, [])

    def test_published_delivery_matches_real_archive_and_memory_carriers(self):
        import csv
        import hashlib

        archive = ROOT / "data/reports/2026-11-10-predict-btc5m-m2"
        evidence = archive / "evidence/recovery-01/research"
        published = INSTANCE / "reports"
        if not evidence.is_dir():
            self.skipTest("real archived research has not been produced; no fixture substitution")
        coverage = json.loads((evidence / "coverage.json").read_text())
        commands = json.loads((evidence / "commands.json").read_text())
        self.assertEqual(commands["research_exit_code"], 3)
        for field in ("request_count", "qd_request_count", "document_request_count"):
            self.assertEqual(commands[field], 0)
        self.assertTrue(coverage["research_completed"])
        for name in ("coverage.json", "events.csv", "proxy-samples.csv", "comparison.csv"):
            self.assertEqual((evidence / name).read_bytes(), (published / name).read_bytes())
        for name in ("ohlc.json", "raw-pages.json"):
            self.assertEqual((evidence / name).read_bytes(), (archive / "evidence" / name).read_bytes())
        report = (published / "report.md").read_bytes()
        fix = archive / "evidence/report-fix-01"
        publication = json.loads((fix / "publication.json").read_text())
        self.assertEqual((fix / "before/report.md").read_bytes(),
                         (evidence / "report-preview.md").read_bytes())
        self.assertEqual(report, (fix / "report-preview.md").read_bytes())
        self.assertEqual(hashlib.sha256(report).hexdigest(), publication["report_sha256"])
        self.assertIn(hashlib.sha256(report).hexdigest(), (archive / "report.md").read_text())
        self.assertEqual(coverage["source_hashes"]["research.py"],
                         research.digest(fix / "before/research.py"))
        self.assertEqual(coverage["source_hashes"]["research.py"],
                         publication["original_producer_sha256"])
        self.assertEqual(research.digest(INSTANCE / "research.py"),
                         publication["current_renderer_sha256"])
        original = json.loads((archive / "evidence/availability.json").read_text())
        reviewed = json.loads((evidence / "availability.json").read_text())
        for field in ("checked_at_utc", "sources", "rows"):
            self.assertEqual(reviewed[field], original[field])
        with (evidence / "proxy-samples.csv").open() as handle:
            samples = list(csv.DictReader(handle))
        with (evidence / "comparison.csv").open() as handle:
            comparison = list(csv.DictReader(handle))
        bars = json.loads((evidence / "ohlc.json").read_text())["bars"]
        closes = {row["time"]: row["close"] for row in bars}
        keys = [research.parse_utc(row["t_utc"], "time") for row in samples]
        expected = list(range(int(research.parse_utc(self.args.start_utc, "start").timestamp()),
                              int(research.parse_utc(self.args.end_utc, "end").timestamp()), 300))
        self.assertEqual([int(moment.timestamp()) for moment in keys], expected)
        self.assertEqual(samples[-1]["reason"], "label_missing")
        for partition, count_field in (("IS", "is_count"), ("OOS", "oos_count")):
            selected = [row for row in samples if row["partition"] == partition]
            self.assertGreater(len(selected), 0)
            self.assertEqual(len(selected), coverage[count_field])
            for row in selected:
                timestamp = int(research.parse_utc(row["t_utc"], "time").timestamp())
                current, following = closes[timestamp - 300], closes[timestamp]
                label = 1 if following > current else 0 if following < current else 0.5
                self.assertEqual(float(row["proxy_label"]), label)
                self.assertAlmostEqual(float(row["brier"]), (float(row["p_up"]) - label) ** 2)
            metrics = {row["metric"]: row for row in comparison
                       if row["evidence_type"] == "real-proxy" and row["partition"] == partition}
            self.assertEqual(int(metrics["sample_count"]["value"]), len(selected))
            self.assertAlmostEqual(float(metrics["brier"]["value"]),
                                   sum(float(row["brier"]) for row in selected) / len(selected))
            for metric in ("candidate_count", "trade_count", "net_pnl", "annualized_return_pct",
                           "sharpe", "max_drawdown_pct", "calmar", "turnover_pct", "information_ratio"):
                self.assertEqual(metrics[metric]["value"], "N/A")
        fixture = archive / "evidence/recovery-01/cli"
        self.assertGreater((fixture / "fixture-output.jsonl").stat().st_size, 0)
        for negative in ("negative-live", "negative-rpc"):
            self.assertFalse((fixture / f"{negative}-output.jsonl").exists())
            self.assertFalse((fixture / f"{negative}-summary.json").exists())
        print("delivery_audit=" + json.dumps({"plan_count": len(samples),
              "is_count": coverage["is_count"], "oos_count": coverage["oos_count"],
              "raw_count": coverage["raw_count"], "unique_count": coverage["unique_count"],
              "closed_count": coverage["closed_count"], "comparison_rows": len(comparison),
              "report_sha256": hashlib.sha256(report).hexdigest()}))

    def test_actual_launcher_from_empty_cwd_fixture_and_negative_arguments(self):
        for option in (None, "--live", "--rpc-url"):
            with self.subTest(option=option):
                directory = self.directory / (option or "fixture").replace("--", "")
                directory.mkdir()
                cwd = directory / "cwd"
                cwd.mkdir()
                output, summary = directory / "output.jsonl", directory / "summary.json"
                command = [sys.executable, str(INSTANCE / "tests/offline_exec.py"),
                           "--rust-bin", str((BOT / "target/debug/btc_arb_replay").relative_to(ROOT)),
                           "--mode", "replay", "--config", str((INSTANCE / "tests/fixtures/replay-config.json").relative_to(ROOT)),
                           "--input", str((INSTANCE / "tests/fixtures/round-events.jsonl").relative_to(ROOT)),
                           "--output", str(output), "--summary", str(summary),
                           "--from-ms", "1794197400000", "--to-ms", "1794290400000"]
                if option:
                    command.append("--extra=" + option)
                completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                           env={"LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
                                                "TMPDIR": tempfile.gettempdir()}, close_fds=True, check=False)
                self.assertIn('"socket_control_errno": 1', completed.stdout)
                self.assertIn('"inherited_fds": []', completed.stdout)
                self.assertIn('"cwd_empty": true', completed.stdout)
                if option:
                    self.assertEqual(completed.returncode, 64, completed.stderr)
                    self.assertFalse(output.exists())
                    self.assertFalse(summary.exists())
                else:
                    self.assertIn(completed.returncode, (0, 3), completed.stderr)
                    self.assertGreater(output.stat().st_size, 0)
                    self.assertEqual(json.loads(summary.read_text())["schema_version"], research.REPLAY_SCHEMA_VERSION)

    def test_launcher_closes_inheritable_fd_before_exec(self):
        descriptor = os.open(self.directory / "descriptor", os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, descriptor)
        os.set_inheritable(descriptor, True)
        # The original child branch verifies every >=3 descriptor is closed before exec.
        result = launcher.FilteredRunner.run([str(BOT / "target/debug/btc_arb_replay"), "--version"],
                                            str(self.directory), {"LANG": "C.UTF-8", "TZ": "UTC"})
        self.assertEqual(result.returncode, 0)
        os.fstat(descriptor)  # Only the child descriptors were closed.


class ReportRenderingTests(unittest.TestCase):
    """Pure report regressions against preserved real carriers; no new research."""

    def setUp(self):
        import csv
        import socket

        self.archive = ROOT / "data/reports/2026-11-10-predict-btc5m-m2"
        self.evidence = self.archive / "evidence/recovery-01/research"
        for owner, name in ((research, "fetch_bars"), (research, "run_rust"),
                            (research, "check_documents"), (research, "research"),
                            (research._quantdinger, "agent_call"),
                            (research._quantdinger, "resolve_agent_token"),
                            (socket, "socket")):
            guard = mock.patch.object(owner, name, side_effect=AssertionError("I/O forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        self.parameters = json.loads((self.evidence / "parameters.json").read_text())
        self.args = research.argparse.Namespace(**self.parameters["parameters"])
        self.coverage = json.loads((self.evidence / "coverage.json").read_text())
        self.availability = json.loads((self.evidence / "availability.json").read_text())
        self.execution = json.loads((self.evidence / "commands.json").read_text())
        with (self.evidence / "comparison.csv").open() as handle:
            self.comparison = list(csv.DictReader(handle))
        with (self.evidence / "proxy-samples.csv").open() as handle:
            self.samples = list(csv.DictReader(handle))

    def render(self):
        return research.render_report(
            self.args, self.coverage, self.samples, self.comparison,
            {"entrance": self.parameters["entrance"]}, [],
            parameters=self.parameters, availability=self.availability,
            execution=self.execution)

    def test_report_f1_all_twenty_na_reasons_and_valued_rows(self):
        report = research.render_report(self.args, self.coverage, self.samples,
                                        self.comparison, {"entrance": "ohlc-file"}, [])
        cells = {}
        for line in report.splitlines():
            if line.startswith("| ") and (" (IS) |" in line or " (OOS) |" in line):
                columns = [cell.strip() for cell in line.strip("|").split("|")]
                cells[columns[0]] = columns[1:]
        self.assertEqual(len(cells), 38)
        reasons = dict.fromkeys(("candidate_count", "trade_count"), "proxy_only")
        reasons.update(dict.fromkeys(("net_pnl", "interval_return_pct", "annualized_return_pct",
                                      "sharpe", "max_drawdown_pct", "calmar", "turnover_pct",
                                      "information_ratio"), "no_real_account_equity"))
        checked = 0
        for row in self.comparison:
            if row["evidence_type"] != "real-proxy":
                continue
            rendered = cells[f"{row['metric']} ({row['partition']})"]
            self.assertEqual(rendered[:2], [row["value"], row["caliber"]])
            if row["metric"] in reasons:
                with self.subTest(partition=row["partition"], metric=row["metric"]):
                    self.assertEqual(row["reason"], reasons[row["metric"]])
                    self.assertEqual(rendered[2:], [reasons[row["metric"]]])
                checked += 1
        self.assertEqual(checked, 20)

    def test_report_f2_context_sources_parameters_budgets_and_stress(self):
        report = self.render()
        for text in ("fixture：纯软件行为证据", "real-proxy：真实闭合 OHLC",
                     "real-market：未执行", "历史声明", "仅本地核查", "not_verified",
                     "成交/费用/流动性/极端冲击压力测试：本轮不适用，未执行",
                     "无真实份额盘口、成交和账户权益", "完整研究墙钟（commands.json）",
                     "coverage.elapsed_seconds=0.008", "不是完整墙钟", "非本次重跑研究"):
            self.assertIn(text, report)
        for field in ("checked_at_utc", "reviewed_at_utc", "historical_command_logs"):
            self.assertIn(str(self.availability[field]), report)
        for row in self.availability["local_rows"]:
            self.assertIn(json.dumps(row, ensure_ascii=False, sort_keys=True), report)
        for row in self.availability["checked_files"]:
            self.assertIn(json.dumps(row, ensure_ascii=False, sort_keys=True), report)
        for row in self.availability["sources"]:
            self.assertIn(json.dumps(row, ensure_ascii=False, sort_keys=True), report)
        for key, value in self.parameters["strategy_parameters"].items():
            unit = " USDT" if key == "order_usd" else ""
            self.assertIn(f"| {key} | {value}{unit} |", report)
        for field in ("request_count", "qd_request_count", "document_request_count",
                      "elapsed_seconds", "research_exit_code"):
            self.assertIn(f"{field}={self.execution[field]}", report)
        for field in ("max_pages", "max_data_requests", "wall_seconds"):
            self.assertIn(f"{field}={getattr(self.args, field)}", report)
        unchanged = copy.deepcopy(self.execution)
        sampled = dict(self.execution, timing_scope="render_point", research_exit_code="NOT_FINAL")
        report = research.render_report(
            self.args, self.coverage, self.samples, self.comparison, {}, [],
            parameters=self.parameters, availability=self.availability, execution=sampled)
        self.assertIn("截至渲染点采样，非完整终态墙钟", report)
        self.assertNotIn("完整研究墙钟（commands.json）", report)
        self.assertEqual(self.execution, unchanged)

    def test_report_f3_index_relative_links_timestamp_hash_and_boundaries(self):
        import re

        report_path = INSTANCE / "reports/report.md"
        index_path = self.archive / "report.md"
        body = report_path.read_bytes()
        moment = dt.datetime.now(dt.timezone.utc)
        generated = research.iso(moment)
        index = research.render_index(index_path, report_path, research.digest(report_path),
                                      self.evidence, generated)
        links = re.findall(r"\]\(([^)]+)\)", index)
        self.assertGreaterEqual(len(links), 2)
        for link in links:
            self.assertFalse(Path(link).is_absolute())
            self.assertTrue((index_path.parent / link).resolve().exists())
        self.assertEqual((index_path.parent / links[0]).resolve(), report_path)
        self.assertIn(f"generated_at_utc: {generated}", index)
        self.assertEqual(research.parse_utc(generated, "generated"), moment)
        self.assertIn(research.hashlib.sha256(body).hexdigest(), index)
        for text in ("run3555", "未验收", "insufficient-evidence", "exit3", "待", "Verify/Review"):
            self.assertIn(text, index)
        self.assertNotIn("| 指标 |", index)
        self.assertNotIn(str(ROOT), index)


if __name__ == "__main__":
    unittest.main()
