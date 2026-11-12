"""Bounded facade-only official BTC5m research; one continuous Rust state, no HTTP/trades."""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import resource
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

# Direct-file CLI execution uses this repository's packages, not another environment.
LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(LAB))
from history_input import iter_history_input  # noqa: E402
from history_metrics import (OFFSETS, COMPARISON_COLUMNS, CALIBRATION_COLUMNS, DAILY_COLUMNS,
                             aggregate)  # noqa: E402
from skills.data.unified_data.history_types import (HistoryRequest, DATASET_ROUNDS, DATASET_KLINES,
                                                   parse_utc, to_us)  # noqa: E402

BOT = ROOT / "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"
BINARY = BOT / "target/debug/btc_arb_history"
START = datetime(2026, 8, 10, tzinfo=timezone.utc)
END = datetime(2026, 11, 12, tzinfo=timezone.utc)
SPLIT = datetime(2026, 10, 10, tzinfo=timezone.utc)
REPORT_ROOT = ROOT / "data/reports/2026-11-12-btc5m-native-history-research"
SAMPLE_COLUMNS = ("round_id", "day", "partition", "offset", "at_ms", "starts_at_ms", "ends_at_ms",
                  "strike", "spot", "spot_at_ms", "secs_left", "samples", "sigma", "p_up",
                  "label", "label_available_at_us", "reason")
SOURCE_FILES = (LAB / "history_research.py", LAB / "history_metrics.py", LAB / "config.json",
                LAB / "history_input.py", BOT / "src/bot/arbitrage.rs",
                BOT / "src/bot/arbitrage/history.rs", BOT / "src/bin/btc_arb_history.rs", BINARY)
TRADE_NA = ("候选数", "成交数", "成交胜率", "净PnL", "年化", "Sharpe", "MDD", "Calmar", "换手", "IR")


def digest(path: Path) -> str:
    """Hash a named source/binary using bounded reads."""
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Create a new evidence file; conflicts are errors, never overwrites."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        stream.write("\n")


def write_csv(path: Path, columns: tuple, rows: list[dict]) -> None:
    """Create an explicit-column, raw-precision CSV with N/A for missing values."""
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "N/A" if row.get(key) is None else row[key] for key in columns})


def days_between(start: datetime, end: datetime) -> Iterator[datetime]:
    """Yield sorted UTC midnight day boundaries."""
    while start < end:
        yield start
        start += timedelta(days=1)


def day_events(bundle: Any, start: datetime, end: datetime, contexts: list[dict]) -> Iterator[dict]:
    """Consume a single facade day without SQLite, labels or future data in Rust inputs.

    The facade feature stream orders round-start features before ordered candles.
    Only round-sized metadata/strike maps are retained; all 86400 candles stream.
    """
    identities = {}
    for row in bundle.iter_metadata():
        identity = row.payload
        key = identity["round_id"]
        if key in identities:
            raise ValueError("duplicate round identity")
        identities[key] = row
    features = iter(bundle.iter_features())
    strikes = {}
    first_candle = None
    for row in features:
        if row.payload["dataset"] == DATASET_KLINES:
            first_candle = row
            break
        if row.payload["dataset"] != DATASET_ROUNDS or row.payload["round_id"] in strikes:
            raise ValueError("unexpected/duplicate round feature")
        strikes[row.payload["round_id"]] = row
    by_start = {}
    for key, identity in identities.items():
        at = identity.payload["starts_at_us"]
        if at in by_start:
            raise ValueError("duplicate official round slot")
        by_start[at] = key
    start_us, end_us = to_us(start.replace(tzinfo=None)), to_us(end.replace(tzinfo=None))
    requests = []
    for round_start in range(start_us, end_us, 300_000_000):
        key = by_start.get(round_start)
        identity, strike = identities.get(key), strikes.get(key)
        for offset in OFFSETS:
            now = round_start + offset * 1_000_000
            context = dict(round_id=key or f"missing-{round_start}", day=start.date().isoformat(),
                partition="IS" if start < SPLIT else "OOS", offset=offset, at_ms=now // 1000,
                starts_at_ms=round_start // 1000, ends_at_ms=(round_start + 300_000_000) // 1000,
                strike=None, spot=None, spot_at_ms=None, secs_left=300-offset, samples=0,
                sigma=None, p_up=None, label=None, label_available_at_us=None, reason="missing_identity")
            payload = None
            if identity is not None and strike is not None:
                if identity.payload["ends_at_us"] != round_start + 300_000_000:
                    raise ValueError("invalid round duration")
                context["strike"] = float(strike.payload["start_price"])
                context["reason"] = "identity_not_available"
                if max(identity.available_at_us, strike.available_at_us) <= now:
                    context["reason"] = "missing_spot"
                    payload = dict(type="value", symbol="BTCUSDT", round_id=key,
                        starts_at_ms=round_start // 1000, ends_at_ms=(round_start+300_000_000)//1000,
                        strike=context["strike"], identity_available_at_ms=identity.available_at_us//1000,
                        strike_available_at_ms=strike.available_at_us//1000)
            elif identity is not None:
                context["reason"] = "missing_strike"
            contexts.append(context)
            requests.append((now, payload, context))
    request_index = 0
    previous_close = None
    candles = itertools.chain(() if first_candle is None else (first_candle,), features)
    for row in candles:
        if row.payload["dataset"] != DATASET_KLINES:
            raise ValueError("round features after candles")
        closed = row.payload["close_exclusive_us"]
        if row.available_at_us != closed or closed % 1000 or (previous_close is not None and closed <= previous_close):
            raise ValueError("non-causal/nonordered event-time candle")
        while request_index < len(requests) and requests[request_index][0] < closed:
            # Missing the exact decision close is not replaced by stale prices.
            request_index += 1
        yield dict(at_ms=closed//1000, payload=dict(type="spot", symbol="BTCUSDT",
            price=float(row.payload["close"]), available_at_ms=closed//1000))
        while request_index < len(requests) and requests[request_index][0] == closed:
            _, payload, context = requests[request_index]
            if payload is not None:
                context["reason"] = "requested"
                yield dict(at_ms=closed//1000, payload=payload)
            request_index += 1
        previous_close = closed
    labels = {}
    for row in bundle.iter_labels():
        key = row.payload["round_id"]
        if key in labels:
            raise ValueError("duplicate label")
        if row.available_at_us < row.payload["ends_at_us"]:
            raise ValueError("label available before round end")
        labels[key] = row
    for context in contexts[-len(requests):]:
        label = labels.get(context["round_id"])
        if label is not None:
            if (label.payload["starts_at_us"] // 1000 != context["starts_at_ms"] or
                    label.payload["ends_at_us"] // 1000 != context["ends_at_ms"]):
                raise ValueError("label identity mismatch")
            context["label"] = label.payload["official_outcome"]
            context["label_available_at_us"] = label.available_at_us


def merge_values(contexts: list[dict], path: Path) -> None:
    """Join only actual requested rows to Rust results, rejecting drops/duplicates."""
    expected = {(row["round_id"], row["at_ms"]): row for row in contexts if row["reason"] == "requested"}
    with path.open(encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            key = value["round_id"], value["at_ms"]
            if key not in expected:
                raise ValueError("unexpected/duplicate Rust result")
            context = expected.pop(key)
            for field in ("starts_at_ms", "ends_at_ms", "strike", "secs_left"):
                if context[field] != value[field]:
                    raise ValueError("Rust identity drift")
            context.update(value)
    if expected:
        raise ValueError("missing Rust results")


def formatted(value: Any) -> str:
    """The sole fixed display formatter for all report tables."""
    return "N/A" if value is None else f"{value:.8f}" if isinstance(value, float) else str(value)


def render_report(comparison: list[dict], coverage: dict, latest: list[dict]) -> str:
    """Render report directly from the same raw rows exported to CSV."""
    columns = ("partition", "offset", "total", "binary", "draw", "direction_accuracy",
               "binary_brier", "binary_logloss", "brier_delta_vs05", "sigma_floor_ratio")
    lines = ["# BTC5m 官方历史固定参数研究", "", "状态：研究完成，独立 Verify 待执行。", "",
             "数据来源：Predict.fun 官方固定 start_price/标签；Binance Vision BTCUSDT 1s closed-candle close。",
             "可得性：event-time-proxy，仅理论事件时钟，不是严格 PIT 或实时 top-of-book；Chainlink/Binance 非同源。",
             "连续 Rust 状态从窗口首价初始化；窗前无预热；无拟合、调参、进化或事后偏移择优。", "",
             "```json", json.dumps(coverage, ensure_ascii=False, indent=2, default=str), "```", "",
             "## IS/OOS 固定六时点", "|"+"|".join(columns)+"|", "|"+"|".join("---" for _ in columns)+"|"]
    lines += ["|"+"|".join(formatted(row[key]) for key in columns)+"|" for row in comparison]
    lines += ["", "95%区间见 comparison.csv：UTC日整块1000次，PCG64(42)，分区独立重置、六时点共享索引，按分子/分母加权；linear分位数。",
              "方向准确率排除DRAW及abstain；二元Brier/log-loss含p=0.5但排除DRAW；兑付Brier另含DRAW=0.5。",
              "0.5概率和即时方向覆盖及共同方向分母对照均见comparison.csv；10bin校准见calibration.csv；日/月稳定性见daily/monthly.csv。",
              "basis_mean_bps/basis_abs_mean_bps为估值时Binance spot对固定官方strike的偏差，包含轮内真实价格移动，不是同刻纯跨源基差估计。",
              "高临近到期命中不代表可成交alpha；固定参数时间分段仅为稳定性诊断。", "", "## 最新两日诊断",
              "|"+"|".join(columns)+"|", "|"+"|".join("---" for _ in columns)+"|"]
    lines += ["|"+"|".join(formatted(row[key]) for key in columns)+"|" for row in latest]
    lines += ["", "## 不适用的交易指标"]
    lines += [f"- {key}：N/A（没有份额bid/ask、深度、费用和可成交执行链）。" for key in TRADE_NA]
    lines += ["", "## 复现与证据", "精确命令、as_of、原生exit、source/binary SHA见本次 evidence/research 运行目录 params.json/run.json/identities.json。",
              "源码依赖原A&S近似CDF，不替换为精确erf；模型向量与近似误差由独立参考及Tester检验。",
              "本地输出不等于Git提交、远程备份、交易授权或策略盈利。", ""]
    return "\n".join(lines)


def check_deadline(deadline: float) -> None:
    """Enforce wall time after facade scans/verification as well as event writes."""
    if time.monotonic() >= deadline:
        raise TimeoutError("research budget exceeded")


def run_research(client: Any, *, mode: str, as_of: datetime, evidence: Path, report: Path) -> dict:
    """Run one pilot or frozen full window, preserving partial evidence on failure."""
    end = START + timedelta(days=1) if mode == "pilot" else END
    budget = 300 if mode == "pilot" else 3600
    started = time.monotonic()
    deadline = started + budget
    evidence.mkdir(parents=True, exist_ok=False)
    if report.exists():
        raise FileExistsError("report already exists")
    identities = {str(path.relative_to(ROOT)): digest(path) for path in SOURCE_FILES}
    write_json(evidence / "identities.json", identities)
    write_json(evidence / "params.json", dict(mode=mode, start=START.isoformat(), end=end.isoformat(),
        split=SPLIT.isoformat(), as_of=as_of.isoformat(), budget_seconds=budget,
        offsets=OFFSETS, availability="event-time-proxy", config=json.loads((LAB/"config.json").read_text()),
        command=sys.argv, baseline_probe="OMITTED_BY_AUTHORIZATION", baseline="evidence/controller-baseline.json"))
    command = [str(BINARY), "--config", str(LAB/"config.json"), "--input", "-", "--output",
               str(evidence/"values.jsonl"), "--summary", str(evidence/"rust-summary.json"),
               "--from-ms", str(to_us(START.replace(tzinfo=None))//1000),
               "--to-ms", str(to_us(end.replace(tzinfo=None))//1000)]
    write_json(evidence / "command.json", command)
    contexts, manifests = [], []
    stream_hash = hashlib.sha256()
    seq, native_exit, failure = 0, None, None
    process = None
    initialization_seconds = time.monotonic() - started
    try:
        with (evidence/"rust-stderr.log").open("xb") as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            for day in days_between(START, end):
                check_deadline(deadline)
                day_started = time.monotonic()
                request = HistoryRequest(start_utc=day, end_utc=day+timedelta(days=1),
                    as_of_utc=as_of, availability_mode="event-time-proxy")
                bundle = iter_history_input(client, request)
                opened = time.monotonic()
                check_deadline(deadline)
                daily_hash, daily_events = hashlib.sha256(), 0
                for event in day_events(bundle, day, day+timedelta(days=1), contexts):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("research budget exceeded")
                    event.update(schema_version="btc-arb-history/1", seq=seq)
                    encoded = (json.dumps(event, separators=(",", ":"), allow_nan=False)+"\n").encode()
                    process.stdin.write(encoded)
                    stream_hash.update(encoded)
                    daily_hash.update(encoded)
                    seq += 1
                    daily_events += 1
                content = bundle.verify_consumed()
                verified_at = time.monotonic()
                window = bundle._window
                manifest = dict(day=day.date().isoformat(), verified=bundle.verified,
                    timings=dict(open_seconds=opened-day_started,
                                 consume_verify_seconds=verified_at-opened,
                                 total_seconds=verified_at-day_started),
                    content_sha256=content, content_manifest=bundle.content_manifest,
                    provenance_manifest=window.provenance_manifest, coverage=asdict(window.coverage),
                    missing=window.missing, pending=window.pending, conflicts=window.conflicts,
                    event_sha256=daily_hash.hexdigest(), events=daily_events,
                    assumptions=bundle.availability_assumptions)
                write_json(evidence/f"source-{day.date().isoformat()}.json", manifest)
                manifests.append(manifest)
                print(json.dumps(dict(day=manifest["day"], elapsed_seconds=round(time.monotonic()-started, 3),
                                     events=seq, verified=True)), flush=True)
                check_deadline(deadline)
            process.stdin.close()
            native_exit = process.wait(timeout=max(0.01, deadline-time.monotonic()))
        if native_exit != 0:
            raise ValueError("Rust native nonzero; inspect rust-stderr/summary")
        merge_values(contexts, evidence/"values.jsonl")
        dates = {partition: [day.date().isoformat() for day in days_between(START,end)
                            if (day < SPLIT) == (partition == "IS")] for partition in ("IS", "OOS")}
        comparison, calibration, daily, monthly = aggregate(contexts, dates)
        coverage = dict(mode=mode, start=START.isoformat(), end=end.isoformat(), split=SPLIT.isoformat(),
            days=len(manifests), expected_days=len(list(days_between(START,end))),
            theoretical_rounds=int((end-START).total_seconds())//300,
            theoretical_seconds=int((end-START).total_seconds()),
            theoretical_positions=int((end-START).total_seconds())//300*6,
            actual_positions=len(contexts), valued=sum(row["p_up"] is not None for row in contexts),
            missing_by_reason={reason: sum(row["reason"] == reason for row in contexts)
                               for reason in sorted({row["reason"] for row in contexts})},
            verified_days=len(manifests), events=seq, event_sha256=stream_hash.hexdigest(),
            elapsed_seconds=time.monotonic()-started, initialization_seconds=initialization_seconds,
            max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if coverage["actual_positions"] != coverage["theoretical_positions"]:
            raise ValueError("coverage denominator drift")
        write_csv(evidence/"samples.csv", SAMPLE_COLUMNS, contexts)
        write_csv(evidence/"comparison.csv", COMPARISON_COLUMNS, comparison)
        write_csv(evidence/"calibration.csv", CALIBRATION_COLUMNS, calibration)
        write_csv(evidence/"daily.csv", DAILY_COLUMNS, daily)
        write_csv(evidence/"monthly.csv", DAILY_COLUMNS, monthly)
        write_json(evidence/"coverage.json", coverage)
        write_json(evidence/"source-manifests.json", manifests)
        latest_contexts = [dict(row, partition=row["day"]) for row in contexts if row["day"] >= "2026-11-10"]
        latest_days = {day: [day] for day in ("2026-11-10", "2026-11-11")} if mode == "full" else {}
        latest, _, _, _ = aggregate(latest_contexts, latest_days)
        write_csv(evidence/"latest.csv", COMPARISON_COLUMNS, latest)
        if identities != {str(path.relative_to(ROOT)): digest(path) for path in SOURCE_FILES}:
            raise ValueError("source/binary changed during run")
        check_deadline(deadline)
        with report.open("x", encoding="utf-8") as output:
            output.write(render_report(comparison, coverage, latest))
        return coverage
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                native_exit = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                native_exit = process.wait()
        elif process is not None:
            native_exit = process.returncode
        write_json(evidence/"run.json", dict(complete=failure is None, failure=failure,
            native_exit=native_exit, verified_days=len(manifests), events=seq,
            event_sha256=stream_hash.hexdigest(), elapsed_seconds=time.monotonic()-started,
            max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))


def main(argv: list[str] | None = None) -> int:
    """Parse the narrow CLI before opening the existing authenticated read connection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pilot", "full"), required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    as_of = parse_utc(args.as_of).replace(tzinfo=timezone.utc)
    if as_of < END or as_of > datetime.now(timezone.utc):
        parser.error("as-of must cover the frozen window and not be in the future")
    evidence, report = args.evidence_dir.resolve(), args.report.resolve()
    expected_report = evidence/"report.md" if args.mode == "pilot" else REPORT_ROOT/"report.md"
    if (not evidence.is_relative_to(REPORT_ROOT/"evidence/research") or report != expected_report):
        parser.error("output outside authorized research subtree/report")
    if evidence.exists() or report.exists():
        parser.error("exclusive output already exists")
    from skills.data.unified_data.client import UnifiedDataClient
    from skills.data.unified_data.history_reader import Btc5mHistoryReader
    from skills.data.unified_data.storage import open_databases
    client = UnifiedDataClient(history_reader=Btc5mHistoryReader(open_databases().ud))
    try:
        coverage = run_research(client, mode=args.mode, as_of=as_of, evidence=evidence, report=report)
        print(json.dumps(coverage, default=str), flush=True)
        return 0
    except Exception as error:
        # No database URI/credentials or raw exception strings in console/evidence.
        print(f"research failed: {type(error).__name__}; partial evidence retained", file=sys.stderr)
        return 5 if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
