#!/usr/bin/env python3
"""SPY 2024 close-to-close research sample.

The script fetches real platform OHLCV bars, computes the daily return
statistics frozen in ``spec.md`` and writes ``reports/latest.csv`` plus
``reports/report.md``.  It never trades, never evolves parameters and always
performs a real fetch: the second run does not reuse the first CSV.

Run from the repository root:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib.util
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Optional

RESEARCH_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = RESEARCH_DIR.parent
SCRIPTS_DIR = STRATEGIES_ROOT.parent / "scripts"
REPORTS_DIR = RESEARCH_DIR / "reports"

MARKET = "USStock"
SYMBOL = "SPY"
TIMEFRAME = "1D"
START = "2024-01-01"
END = "2024-12-31"
BEFORE_TIME = "2025-01-01T00:00:00Z"
ANNUALIZATION = 252
MIN_ROWS = 200
MAX_PAGES = 4
PAGE_TIMEOUT = 180.0
MAX_REQUEST_SECONDS = 180.0

EXIT_OK = 0
EXIT_CONTRACT = 2
EXIT_EVIDENCE = 3
EXIT_AUTH = 4
EXIT_BUDGET = 5
EXIT_USAGE = 64


def _load_cli_module() -> Any:
    """Load the single-file CLI by path so no package is created for it."""
    path = SCRIPTS_DIR / "quantdinger.py"
    spec = importlib.util.spec_from_file_location("strategy_lab_quantdinger", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = _load_cli_module()


def _before_time_seconds(text: str = BEFORE_TIME) -> int:
    """Return the unix-second cursor used to page backwards from the window end."""
    moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return int(moment.timestamp())


def _local_now_iso() -> str:
    """Current time in Asia/Shanghai (UTC+08:00), used for the extraction stamp."""
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )


def compute_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the frozen daily-return statistics over the requested window."""
    closes = [float(row["close"]) for row in rows]
    returns = [
        (right / left) - 1.0 for left, right in zip(closes, closes[1:])
    ]
    mean_return = statistics.fmean(returns) if returns else float("nan")
    std_return = statistics.stdev(returns) if len(returns) > 1 else float("nan")
    annualized_volatility = std_return * math.sqrt(ANNUALIZATION)
    return {
        "sampleCount": len(rows),
        "returnObservations": len(returns),
        "meanDailyReturn": mean_return,
        "stdDailyReturn": std_return,
        "annualizedVolatility": annualized_volatility,
        "firstClose": closes[0] if closes else None,
        "lastClose": closes[-1] if closes else None,
        "closeChangePct": (
            ((closes[-1] / closes[0]) - 1.0) * 100.0 if len(closes) > 1 else None
        ),
    }


def validate_rows(rows: list[dict[str, Any]]) -> None:
    """Fail loudly when the fetched window is empty or violates the contract."""
    if not rows:
        raise CLI.LabError(EXIT_EVIDENCE, "research.noRows")
    if len(rows) < MIN_ROWS:
        raise CLI.LabError(
            EXIT_EVIDENCE, "research.tooFewRows", rows=len(rows), minimum=MIN_ROWS
        )
    times = [int(row["time"]) for row in rows]
    if times != sorted(times) or len(set(times)) != len(times):
        raise CLI.LabError(EXIT_EVIDENCE, "research.timeOrderInvalid")
    for row in rows:
        if float(row["close"]) <= 0:
            raise CLI.LabError(EXIT_EVIDENCE, "research.closeNotPositive")
        if float(row["volume"]) < 0:
            raise CLI.LabError(EXIT_EVIDENCE, "research.negativeVolume")
        if not (
            float(row["high"]) >= max(float(row["open"]), float(row["close"]))
            and float(row["low"]) <= min(float(row["open"]), float(row["close"]))
        ):
            raise CLI.LabError(EXIT_EVIDENCE, "research.ohlcInvalid")


def fetch_window(data_api: str) -> list[dict[str, Any]]:
    """Fetch the fixed window with the explicitly selected platform entry point."""
    base_url = os.environ.get("QUANTDINGER_BASE_URL") or ""
    if not base_url:
        raise CLI.LabError(EXIT_USAGE, "baseUrl.missing")
    token = (
        os.environ.get("QUANTDINGER_JWT")
        if data_api == CLI.HUMAN
        else os.environ.get("QUANTDINGER_AGENT_TOKEN")
    )
    rows = CLI.fetch_klines(
        data_api=data_api,
        market=MARKET,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start=START,
        end=END,
        base_url=base_url,
        token=token or None,
        max_pages=MAX_PAGES,
        timeout=PAGE_TIMEOUT,
    )
    validate_rows(rows)
    return rows


def write_latest_csv(rows: list[dict[str, Any]]) -> Path:
    """Write the standardised window CSV without an extraction timestamp."""
    path = REPORTS_DIR / "latest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["time", "timeUtc", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})
    os.replace(tmp, path)
    return path


def write_report(
    *, data_api: str, rows: list[dict[str, Any]], stats: dict[str, Any]
) -> Path:
    """Write the research report with source, window, metrics and limits."""
    path = REPORTS_DIR / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    endpoint = (
        "/api/indicator/kline"
        if data_api == CLI.HUMAN
        else "/api/agent/v1/klines"
    )
    lines = [
        "# spy-close-research 报告",
        "",
        f"- extractedAt (Asia/Shanghai): {_local_now_iso()}",
        f"- dataApi: {data_api}",
        f"- endpoint: QuantDinger {endpoint}（底层供应商未由该接口披露）",
        f"- market/symbol/timeframe: {MARKET}/{SYMBOL}/{TIMEFRAME}",
        f"- requestedWindow: {START} .. {END}（UTC 日期边界，美股交易日）",
        f"- actualFirstTimeUtc: {rows[0]['timeUtc']}",
        f"- actualLastTimeUtc: {rows[-1]['timeUtc']}",
        f"- sampleCount: {stats['sampleCount']}（最小要求 {MIN_ROWS}）",
        "",
        "## 统计口径",
        "",
        "- 日收益 = 连续交易日 close 比值减 1。",
        "- 均值 = 算术平均；标准差 = 样本标准差（ddof=1）。",
        f"- 年化波动率 = 样本标准差 × sqrt({ANNUALIZATION})。",
        "",
        "## 指标",
        "",
        f"- meanDailyReturn: {stats['meanDailyReturn']:.10f}",
        f"- stdDailyReturn: {stats['stdDailyReturn']:.10f}",
        f"- annualizedVolatility: {stats['annualizedVolatility']:.10f}",
        f"- firstClose: {stats['firstClose']:.6f}",
        f"- lastClose: {stats['lastClose']:.6f}",
        f"- closeChangePct: {stats['closeChangePct']:.6f}",
        "",
        "## 限制",
        "",
        "- 平台未在接口层披露底层数据供应商，来源只写 QuantDinger 实际 endpoint。",
        "- 周末与节假日不构成数据缺口；首末为实际交易日期，未补任何虚拟 bar。",
        "- 数据为平台缓存/历史序列，不代表实时成交。",
        "- 本研究不含任何交易、参数优化或平台研究条目。",
        "- latest.csv 不写提取时间，便于两次运行直接比对。",
        "",
        "## 复现",
        "",
        "```text",
        "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human",
        "```",
    ]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="research.py",
        description="Fetch real SPY 2024 daily bars and report return statistics.",
    )
    parser.add_argument("--data-api", choices=[CLI.HUMAN, CLI.AGENT], default=CLI.HUMAN)
    args = parser.parse_args(argv)
    try:
        rows = fetch_window(args.data_api)
        stats = compute_statistics(rows)
        csv_path = write_latest_csv(rows)
        report_path = write_report(data_api=args.data_api, rows=rows, stats=stats)
        print(
            json.dumps(
                {
                    "rows": stats["sampleCount"],
                    "meanDailyReturn": stats["meanDailyReturn"],
                    "stdDailyReturn": stats["stdDailyReturn"],
                    "annualizedVolatility": stats["annualizedVolatility"],
                    "firstTimeUtc": rows[0]["timeUtc"],
                    "lastTimeUtc": rows[-1]["timeUtc"],
                    "csv": str(csv_path),
                    "report": str(report_path),
                },
                ensure_ascii=False,
            )
        )
        return EXIT_OK
    except CLI.LabError as exc:
        print(exc.summary(), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
