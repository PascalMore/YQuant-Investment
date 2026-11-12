"""Predict.fun BTC5m: the first real-data research (SPEC-07-001 M2 §11–§12).

The script is a thin I/O layer. It reads closed OHLC bars from QuantDinger's
existing agent route, turns them into a local event stream, calls the shared
Rust decision core for the model values, pairs the values with a direction
proxy label, and writes the carriers.

It does not compute a probability, an EWMA or an entry: those live in the
Rust core, so there is one implementation of the model. It does not claim a
strategy result: with no historical share book and no official settlement
labels, the run is a proxy study whose verdict is ``insufficient-evidence``.

Two data entrances, mutually exclusive:

- the default: the QuantDinger agent route, read only;
- ``--ohlc-file``: an archived OHLC file, read locally with no token and no
  HTTP at all, for offline reproduction.

Neither entrance writes anything outside the chosen evidence directory, and
neither creates a platform job, backtest, source or evolution.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = LAB_ROOT.parents[2]
INSTANCE_ROOT = Path(__file__).resolve().parent

UTC = dt.timezone.utc
SCHEMA_VERSION = "btc5m-research/1"
REPLAY_SCHEMA_VERSION = "btc-arb-replay/1"

SYMBOL = "BTCUSDT"
MARKET = "Crypto"
TIMEFRAME = "5m"
SOURCE_NAME = "QuantDinger Agent"
VENUE = "UNKNOWN"
PRODUCT = "UNKNOWN"
MODEL_SOURCE = "QuantDinger-proxy"
LABEL_TYPE = "ohlc-direction-proxy"

# Exit codes, following the lab's existing contract.
EXIT_OK = 0
EXIT_CONTRACT = 2
EXIT_EVIDENCE = 3
EXIT_AUTH = 4
EXIT_BUDGET = 5
EXIT_USAGE = 64

NA = "N/A"

# The official documentation this round may read, in order, once each.
DOCUMENT_URLS = (
    "https://docs.predict.fun/developers/chainlink-price-markets",
    "https://dev.predict.fun/trading/fees",
    "https://dev.predict.fun/trading/order-lifecycle",
)

# The comparison carrier's metrics, in the frozen order.
COMPARISON_METRICS = (
    "sample_count", "tie_count", "p_up_mean", "p_up_min", "p_up_max",
    "sigma_min", "sigma_max", "brier", "baseline_brier", "candidate_count",
    "trade_count", "net_pnl", "interval_return_pct", "annualized_return_pct",
    "sharpe", "max_drawdown_pct", "calmar", "turnover_pct",
    "information_ratio",
)

# The unit of each metric, in the same order.
COMPARISON_UNITS = (
    "count", "count", "probability", "probability", "probability",
    "second^-0.5", "second^-0.5", "score", "score", "count", "count",
    "USDT", "percent", "percent", "ratio", "percent", "ratio", "percent",
    "ratio",
)

# The evidence columns of the comparison carrier.
EVIDENCE_COLUMNS = ("fixture", "real-proxy", "real-market")
PARTITIONS = ("IS", "OOS")


class ResearchError(Exception):
    """A failure that stops the run with a known exit code."""

    def __init__(self, exit_code: int, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.exit_code = exit_code
        self.code = code
        self.detail = detail


def _load_module(path: Path, name: str):
    """Load a sibling script by file path, without touching sys.path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ResearchError(EXIT_CONTRACT, "module.missing", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_quantdinger = _load_module(LAB_ROOT / "scripts" / "quantdinger.py", "offline_quantdinger")


# ------------------------------------------------------------- arguments ---

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="research.py",
        description="Predict.fun BTC5m real-data research (proxy study).")
    parser.add_argument("--rust-bin", required=True,
                        help="The built btc_arb_replay binary.")
    parser.add_argument("--evidence-dir", required=True,
                        help="Where to write the evidence carriers.")
    parser.add_argument("--data-api", default="agent", choices=("agent",),
                        help="The QuantDinger data entrance.")
    parser.add_argument("--start-utc", default="2026-11-09T06:00:00Z")
    parser.add_argument("--split-utc", default="2026-11-09T18:00:00Z")
    parser.add_argument("--end-utc", default="2026-11-10T06:00:00Z")
    parser.add_argument("--as-of-utc", default="2026-11-10T06:00:00Z")
    parser.add_argument("--frequency-seconds", type=int, default=300)
    parser.add_argument("--warmup-prices", type=int, default=21)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--max-data-requests", type=int, default=50)
    parser.add_argument("--wall-seconds", type=int, default=1800)
    parser.add_argument("--initial-capital", type=float, default=200.0)
    parser.add_argument("--ohlc-file", default=None,
                        help="Use an archived OHLC file instead of the network.")
    parser.add_argument("--raw-pages-file")
    parser.add_argument("--availability-file")
    parser.add_argument("--no-publish", action="store_true",
                        help="Write only to the evidence directory.")
    args = parser.parse_args(argv)
    validate_args(args)
    return args


def validate_args(args: argparse.Namespace) -> None:
    """Check the window and the numbers before anything is fetched."""
    if args.frequency_seconds <= 0 or 86400 % args.frequency_seconds != 0:
        raise ResearchError(EXIT_USAGE, "frequency.invalid",
                             str(args.frequency_seconds))
    if args.frequency_seconds != 300:
        raise ResearchError(EXIT_USAGE, "frequency.unsupported",
                             "the proxy path only supports 300 seconds")
    if not (isinstance(args.initial_capital, float)
            and math.isfinite(args.initial_capital)
            and args.initial_capital > 0):
        raise ResearchError(EXIT_USAGE, "initialCapital.invalid")
    if args.warmup_prices <= 0:
        raise ResearchError(EXIT_USAGE, "warmup.invalid")
    if args.max_pages < 1 or args.max_pages > 2:
        raise ResearchError(EXIT_USAGE, "maxPages.outOfRange")
    if args.max_data_requests < 1 or args.max_data_requests > 50:
        raise ResearchError(EXIT_USAGE, "maxDataRequests.outOfRange")
    if args.wall_seconds < 1 or args.wall_seconds > 1800:
        raise ResearchError(EXIT_USAGE, "wallSeconds.outOfRange")
    start = parse_utc(args.start_utc, "start")
    split = parse_utc(args.split_utc, "split")
    end = parse_utc(args.end_utc, "end")
    as_of = parse_utc(args.as_of_utc, "asOf")
    if not (start < split < end <= as_of):
        raise ResearchError(EXIT_USAGE, "window.invalid")
    if as_of.minute or as_of.second or as_of.microsecond:
        raise ResearchError(EXIT_USAGE, "asOf.notAligned")
    for moment in (start, split, end, as_of):
        if moment.second or moment.microsecond or moment_of(moment, args.frequency_seconds) != moment:
            raise ResearchError(EXIT_USAGE, "window.notAligned")
    if args.warmup_prices != 21:
        raise ResearchError(EXIT_USAGE, "warmup.notFrozen")
    for name in ("rust_bin", "evidence_dir", "ohlc_file", "raw_pages_file", "availability_file"):
        value = getattr(args, name)
        if value:
            path = Path(value)
            setattr(args, name, str(path if path.is_absolute() else PROJECT_ROOT / path))


def parse_utc(text: str, label: str) -> dt.datetime:
    """Parse a UTC timestamp that must carry its offset."""
    raw = str(text).strip()
    if not raw.endswith("Z") and not raw.endswith("+00:00"):
        raise ResearchError(EXIT_USAGE, f"{label}.timezoneRequired")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchError(EXIT_USAGE, f"{label}.invalid") from exc
    if parsed.tzinfo is None:
        raise ResearchError(EXIT_USAGE, f"{label}.timezoneRequired")
    return parsed.astimezone(UTC)


def moment_of(moment: dt.datetime, frequency_seconds: int) -> dt.datetime:
    """The aligned boundary at or before the moment."""
    epoch = int(moment.timestamp())
    return dt.datetime.fromtimestamp(epoch - epoch % frequency_seconds, tz=UTC)


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- budget ---

class Budget:
    """The request and wall-clock budget of this run."""

    def __init__(self, *, max_requests: int, wall_seconds: int) -> None:
        self.max_requests = max_requests
        self.wall_seconds = wall_seconds
        self.started = time.monotonic()
        self.requests = 0
        self.qd_requests = 0
        self.document_requests = 0

    @property
    def deadline(self) -> float:
        # Thirty seconds are kept back to write the result out.
        return self.started + self.wall_seconds - 30

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def check(self) -> None:
        if self.remaining() <= 0:
            raise ResearchError(EXIT_BUDGET, "budget.wallClockExceeded")
        if self.requests >= self.max_requests:
            raise ResearchError(EXIT_BUDGET, "budget.dataRequestsExceeded")

    def take(self, kind: str) -> None:
        self.check()
        self.requests += 1
        if kind == "qd":
            self.qd_requests += 1
        else:
            self.document_requests += 1

    def timeout(self) -> float:
        return max(0.1, min(30.0, self.remaining()))


# ------------------------------------------------------------ data fetch ---

def fetch_bars(args: argparse.Namespace, budget: Budget) -> tuple[list[dict], dict]:
    """Read the closed bars, from the archive or from the agent route."""
    if args.ohlc_file:
        bars, meta = read_ohlc_file(Path(args.ohlc_file))
        seen: dict[int, tuple] = {}
        pages: list[dict] = []
        counts = {"raw_count": 0, "duplicate_count": 0, "conflict_count": 0}
        if args.raw_pages_file:
            archived = json.loads(Path(args.raw_pages_file).read_text(encoding="utf-8"))
            for page in archived["pages"]:
                check_page(page, pages, seen, counts)
            fetch_start = parse_utc(args.start_utc, "start").timestamp() - (
                args.warmup_prices + 1) * args.frequency_seconds
            last_open = parse_utc(args.end_utc, "end").timestamp() - args.frequency_seconds
            expected = {key: value for key, value in seen.items() if fetch_start <= key < last_open}
            actual = {bar["time"]: tuple(bar[field] for field in
                      ("open", "high", "low", "close", "volume")) for bar in bars
                      if fetch_start <= bar["time"] < last_open}
            if actual != expected:
                raise ResearchError(EXIT_CONTRACT, "ohlc.rawPagesMismatch")
            meta.update(counts, raw_seen=seen, raw_pages=pages)
        else:
            meta.update(raw_count=None, duplicate_count=None, conflict_count=None)
        check_page({"klines": bars}, [], {}, {})
        return bars, meta
    return fetch_from_agent(args, budget)


def read_ohlc_file(path: Path) -> tuple[list[dict], dict]:
    """Read an archived OHLC file. No token, no HTTP, no clock."""
    if not path.is_file():
        raise ResearchError(EXIT_USAGE, "ohlcFile.missing", str(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchError(EXIT_CONTRACT, "ohlcFile.invalid", str(exc)) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ResearchError(EXIT_CONTRACT, "ohlcFile.schemaInvalid")
    bars = payload.get("bars")
    if not isinstance(bars, list):
        raise ResearchError(EXIT_CONTRACT, "ohlcFile.barsInvalid")
    check_page({"klines": bars}, [], {}, {})
    normalised = []
    for bar in bars:
        normalised.append({
            "time": int(_quantdinger.parse_bar_time(bar["time"]).timestamp()),
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar["volume"]),
        })
    meta = {
        "source": payload.get("source", SOURCE_NAME),
        "market": payload.get("market", MARKET),
        "symbol": payload.get("symbol", SYMBOL),
        "timeframe": payload.get("timeframe", TIMEFRAME),
        "venue": payload.get("venue", VENUE),
        "product": payload.get("product", PRODUCT),
        "entrance": "ohlc-file",
        "document_requests": 0,
    }
    return normalised, meta


def fetch_from_agent(args: argparse.Namespace, budget: Budget) -> tuple[list[dict], dict]:
    """Read the bars from the QuantDinger agent route, through the existing client.

    The token comes from the existing single-key resolver. Nothing else is
    read from the environment, and the token never reaches the argv, the
    carriers or the logs.
    """
    base_url = os.environ.get("QUANTDINGER_BASE_URL") or ""
    if not base_url:
        raise ResearchError(EXIT_USAGE, "baseUrl.missing")
    token = _quantdinger.resolve_agent_token()
    if not token:
        raise ResearchError(EXIT_AUTH, "auth.missing")
    start = parse_utc(args.start_utc, "start")
    end = parse_utc(args.end_utc, "end")
    as_of = parse_utc(args.as_of_utc, "asOf")
    fetch_start = start - dt.timedelta(
        seconds=(args.warmup_prices + 1) * args.frequency_seconds)

    raw_pages: list[dict] = []
    seen_bars: dict[int, tuple] = {}
    page_counts = {"raw_count": 0, "duplicate_count": 0, "conflict_count": 0}

    def checked_request(operation: str, *, base_url: str, token: str | None,
                        params: dict, timeout: float) -> Any:
        """The request the existing client makes, with the page checked."""
        if operation != "agent_klines":
            raise ResearchError(EXIT_CONTRACT, "http.operationNotAllowed", operation)
        if params.get("market") != MARKET or params.get("symbol") != SYMBOL:
            raise ResearchError(EXIT_CONTRACT, "http.requestScope")
        if params.get("timeframe") != TIMEFRAME:
            raise ResearchError(EXIT_CONTRACT, "http.requestScope")
        if int(params.get("limit", 0)) > 500:
            raise ResearchError(EXIT_CONTRACT, "http.pageLimit")
        budget.take("qd")
        data, _headers = _quantdinger.agent_call(
            operation, base_url=base_url, token=token, params=params,
            timeout=min(30.0, timeout))
        page = check_page(data, raw_pages, seen_bars, page_counts)
        return page

    try:
        rows = _quantdinger.fetch_klines(
            data_api="agent",
            market=MARKET,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start=fetch_start.date().isoformat(),
            end=(end - dt.timedelta(milliseconds=1)).date().isoformat(),
            base_url=base_url,
            token=token,
            max_pages=args.max_pages,
            request=checked_request,
            timeout=budget.timeout(),
        )
    except _quantdinger.LabError as exc:
        raise ResearchError(exit_of(exc), exc.code, exc.detail or "") from exc

    bars = []
    for row in rows:
        bars.append({
            "time": int(row["time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    meta = {
        "source": SOURCE_NAME,
        "market": MARKET,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "venue": VENUE,
        "product": PRODUCT,
        "entrance": "quantdinger-agent",
        "raw_pages": raw_pages,
        **page_counts,
        "raw_seen": seen_bars,
        "as_of": as_of,
        "fetch_start": fetch_start,
    }
    return bars, meta


def exit_of(exc: Any) -> int:
    """Map a lab error onto this script's exit codes."""
    code = getattr(exc, "code", "")
    if code.startswith("auth.") or code in ("http.401", "http.403"):
        return EXIT_AUTH
    if code.startswith("budget."):
        return EXIT_BUDGET
    if code.startswith("usage."):
        return EXIT_USAGE
    return EXIT_CONTRACT


def check_page(data: Any, raw_pages: list[dict],
               seen: dict[int, tuple] | None = None,
               counts: dict | None = None) -> Any:
    """Check one raw page before the client sees it.

    The page is recorded without its headers and without the whole envelope:
    only the business fields and the source fields are kept.
    """
    seen = {} if seen is None else seen
    counts = {} if counts is None else counts
    rows = data.get("klines") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ResearchError(EXIT_CONTRACT, "data.klinesInvalid")
    for row in rows:
        if not isinstance(row, dict):
            raise ResearchError(EXIT_CONTRACT, "data.invalidBar")
        try:
            moment = _quantdinger.parse_bar_time(row.get("time", row.get("timestamp")))
        except _quantdinger.LabError as error:
            raise ResearchError(EXIT_CONTRACT, "data.invalidTime", str(error)) from error
        for field in ("open", "high", "low", "close", "volume"):
            number = row.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ResearchError(EXIT_CONTRACT, "data.invalidBar")
            if not math.isfinite(float(number)):
                raise ResearchError(EXIT_CONTRACT, "data.invalidBar")
        low = float(row["low"])
        high = float(row["high"])
        open_ = float(row["open"])
        close = float(row["close"])
        volume = float(row["volume"])
        if volume < 0:
            raise ResearchError(EXIT_CONTRACT, "data.invalidBar")
        if not (low <= min(open_, close) <= max(open_, close) <= high):
            raise ResearchError(EXIT_CONTRACT, "data.invalidBar")
        if open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
            raise ResearchError(EXIT_CONTRACT, "data.invalidBar")
        key = int(moment.timestamp())
        if moment.microsecond or key % 300:
            raise ResearchError(EXIT_CONTRACT, "data.barNotAligned")
        values = (open_, high, low, close, volume)
        counts["raw_count"] = counts.get("raw_count", 0) + 1
        if key in seen:
            if seen[key] != values:
                counts["conflict_count"] = counts.get("conflict_count", 0) + 1
                raise ResearchError(EXIT_CONTRACT, "ohlc.conflict", str(key))
            counts["duplicate_count"] = counts.get("duplicate_count", 0) + 1
        else:
            seen[key] = values
    raw_pages.append({"row_count": len(rows), "klines": rows})
    return data


# ------------------------------------------------------------- coverage ---

def build_coverage(bars: list[dict], args: argparse.Namespace,
                   meta: dict, budget: Budget) -> dict:
    """Count what the data covers, against the declared window."""
    start = parse_utc(args.start_utc, "start")
    split = parse_utc(args.split_utc, "split")
    end = parse_utc(args.end_utc, "end")
    as_of = parse_utc(args.as_of_utc, "asOf")
    frequency = args.frequency_seconds
    # The earliest bar open the window needs: the warm-up closes start one
    # bar before the first warm-up close.
    fetch_start = start - dt.timedelta(
        seconds=(args.warmup_prices + 1) * frequency)
    last_open = end - dt.timedelta(seconds=frequency)

    expected = []
    moment = fetch_start
    while moment < last_open:
        expected.append(int(moment.timestamp()))
        moment += dt.timedelta(seconds=frequency)

    unique: dict[int, tuple] = {}
    check_page({"klines": bars}, [], unique, {})
    raw_seen = meta.get("raw_seen")
    source_seen = raw_seen if raw_seen is not None else unique
    included = {}
    excluded_future = excluded_unclosed = excluded_range = 0
    for key, values in source_seen.items():
        opened = dt.datetime.fromtimestamp(key, tz=UTC)
        closed = opened + dt.timedelta(seconds=frequency)
        if opened > as_of:
            excluded_future += 1
        elif closed > as_of:
            excluded_unclosed += 1
        elif opened < fetch_start or opened >= last_open:
            excluded_range += 1
        else:
            included[key] = values
    closed_count = len(included)
    unique = included

    observed = sorted(unique)
    missing = [value for value in expected if value not in unique]
    missing_ranges = []
    for value in missing:
        start_utc = iso(dt.datetime.fromtimestamp(value, tz=UTC))
        if missing_ranges and missing_ranges[-1]["end_utc"] == start_utc:
            missing_ranges[-1]["end_utc"] = iso(
                dt.datetime.fromtimestamp(value + frequency, tz=UTC))
        else:
            missing_ranges.append({
                "start_utc": start_utc,
                "end_utc": iso(dt.datetime.fromtimestamp(value + frequency, tz=UTC)),
            })

    # The warm-up count and the evaluation boundary count are counted on the
    # closing boundary, not on the bar's open.
    warmup_count = sum(
        1 for value in observed
        if dt.datetime.fromtimestamp(value, tz=UTC) + dt.timedelta(seconds=frequency) < start)
    evaluation_boundaries = [
        value for value in observed
        if start <= dt.datetime.fromtimestamp(value, tz=UTC) + dt.timedelta(seconds=frequency) < end]
    coverage = {
        "schema_version": SCHEMA_VERSION,
        "parameters": {
            "start_utc": iso(start),
            "split_utc": iso(split),
            "end_utc": iso(end),
            "as_of_utc": iso(as_of),
            "frequency_seconds": frequency,
            "warmup_prices": args.warmup_prices,
            "max_pages": args.max_pages,
            "max_data_requests": args.max_data_requests,
            "wall_seconds": args.wall_seconds,
            "initial_capital": args.initial_capital,
            "fetch_open_start_utc": iso(fetch_start),
        },
        "source": meta.get("source", SOURCE_NAME),
        "venue": VENUE,
        "product": PRODUCT,
        "fetch_start_utc": iso(fetch_start),
        "expected_bars": len(expected),
        "raw_count": meta.get("raw_count"),
        "unique_count": len(raw_seen) if raw_seen is not None else None,
        "closed_count": closed_count,
        "excluded_future_count": excluded_future,
        "excluded_unclosed_count": excluded_unclosed,
        "excluded_range_count": excluded_range,
        "duplicate_count": meta.get("duplicate_count"),
        "conflict_count": meta.get("conflict_count"),
        "raw_count_reason": "none" if raw_seen is not None else "raw_pages_missing",
        "missing_ranges": missing_ranges,
        "warmup_count": warmup_count,
        "evaluation_boundary_count": len(evaluation_boundaries),
        "is_count": 0,
        "oos_count": 0,
        "tie_count": 0,
        "cross_split_count": 0,
        "coverage_complete": observed == expected,
        "request_count": budget.requests,
        "elapsed_seconds": round(time.monotonic() - budget.started, 3),
        "research_verdict": "insufficient-evidence",
        "reasons": [],
    }
    return coverage


# ------------------------------------------------------------ rust proxy ---

def build_proxy_input(bars: list[dict], args: argparse.Namespace) -> list[dict]:
    """Turn the closed bars into the local event stream the Rust core reads.

    The warm-up bars are included as spot observations only: the volatility
    has to see them to be warm at the first evaluation boundary. A value is
    only asked for inside the evaluation window.
    """
    start = parse_utc(args.start_utc, "start")
    end = parse_utc(args.end_utc, "end")
    fetch_start = start - dt.timedelta(
        seconds=(args.warmup_prices + 1) * args.frequency_seconds)
    frequency = args.frequency_seconds
    rows = []
    seq = 0
    unique_bars = {bar["time"]: bar for bar in bars}
    for bar in sorted(unique_bars.values(), key=lambda item: item["time"]):
        opened = dt.datetime.fromtimestamp(bar["time"], tz=UTC)
        closed = opened + dt.timedelta(seconds=frequency)
        at_ms = int(closed.timestamp() * 1000)
        if not (opened >= fetch_start and closed < end):
            continue
        rows.append({
            "schema_version": REPLAY_SCHEMA_VERSION,
            "event_id": f"spot:{at_ms}",
            "event_at_ms": at_ms,
            "available_at_ms": at_ms,
            "seq": seq,
            "source": "quantdinger:agent_klines",
            "evidence_type": "real-proxy",
            "payload": {
                "type": "spot",
                "symbol": SYMBOL,
                "price": bar["close"],
                "model_source": MODEL_SOURCE,
            },
        })
        seq += 1
        if not (start <= closed < end):
            # A warm-up bar: the core needs the price, not a valuation.
            continue
        rows.append({
            "schema_version": REPLAY_SCHEMA_VERSION,
            "event_id": f"value:{at_ms}",
            "event_at_ms": at_ms,
            "available_at_ms": at_ms,
            "seq": seq,
            "source": "quantdinger:agent_klines",
            "evidence_type": "real-proxy",
            "payload": {
                "type": "value",
                "symbol": SYMBOL,
                "strike": bar["close"],
                "horizon_secs": 300,
            },
        })
        seq += 1
    return rows


def run_rust(binary: Path, mode: str, config_path: Path, input_path: Path,
             output_path: Path, summary_path: Path, from_ms: int,
             to_ms: int, budget: Budget, records: list[dict] | None = None) -> dict:
    """Run only the absolute local binary, preserving every native result."""
    import tempfile

    binary = binary.resolve()
    if not binary.is_file():
        raise ResearchError(EXIT_USAGE, "rustBin.missing", str(binary))
    budget.check()
    command = [str(binary), "--mode", mode, "--config", str(config_path.resolve()),
               "--input", str(input_path.resolve()), "--output", str(output_path.resolve()),
               "--summary", str(summary_path.resolve()), "--from-ms", str(from_ms),
               "--to-ms", str(to_ms)]
    record = {"command": command, "started_at_utc": iso(dt.datetime.now(UTC)),
              "binary_sha256": digest(binary), "exit_code": None,
              "log_ref": "command-1.log"}
    stdout = stderr = ""
    try:
        with tempfile.TemporaryDirectory(prefix="btc-arb-research-") as cwd:
            record["cwd"] = cwd
            completed = subprocess.run(
                command, env={"LANG": "C.UTF-8", "TZ": "UTC"}, cwd=cwd,
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=max(1.0, budget.remaining()), close_fds=True, check=False)
        stdout, stderr = completed.stdout, completed.stderr
        record["exit_code"] = completed.returncode
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        record["error"] = "rust.timeout"
        raise ResearchError(EXIT_BUDGET, "rust.timeout") from error
    except OSError as error:
        stderr = str(error)
        record["error"] = "rust.ioFailure"
        raise ResearchError(EXIT_CONTRACT, "rust.ioFailure", str(error)) from error
    finally:
        record["ended_at_utc"] = iso(dt.datetime.now(UTC))
        if records is not None:
            records.append(record)
        pending_error = sys.exc_info()[0] is not None
        try:
            write_text(output_path.parent / "command-1.log", stdout + "\nSTDERR:\n" + stderr)
        except OSError as error:
            print(f"rust.logFailure: {error}", file=sys.stderr)
            if not pending_error:
                raise
    summary = {}
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {"command": command, "exit_code": completed.returncode,
            "stdout": stdout, "stderr": stderr, "summary": summary}


# -------------------------------------------------------------- pairing ---

def pair_samples(bars: list[dict], output_rows: list[dict],
                 args: argparse.Namespace) -> list[dict]:
    """Pair each model value with the direction proxy label.

    The label is the next boundary's close against this boundary's close. It
    is a proxy, not an official settlement: it says nothing about the share
    book or the settlement rules.
    """
    start = parse_utc(args.start_utc, "start")
    split = parse_utc(args.split_utc, "split")
    end = parse_utc(args.end_utc, "end")
    frequency = args.frequency_seconds

    closes = {bar["time"]: bar["close"] for bar in bars}
    values = {}
    for row in output_rows:
        if row.get("event_type") != "value":
            continue
        at_ms = row["available_at_ms"]
        closes_at = dt.datetime.fromtimestamp(at_ms / 1000, tz=UTC)
        bar_time = int((closes_at - dt.timedelta(seconds=frequency)).timestamp())
        values[at_ms] = {
            "row": row,
            "label_at_ms": int((closes_at + dt.timedelta(seconds=frequency)).timestamp() * 1000),
            "strike": closes.get(bar_time),
            "future_close": closes.get(bar_time + frequency),
        }

    samples = []
    first_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    for at_ms in range(first_ms, end_ms, frequency * 1000):
        moment = dt.datetime.fromtimestamp(at_ms / 1000, tz=UTC)
        label_at = moment + dt.timedelta(seconds=frequency)
        bar_time = int(moment.timestamp()) - frequency
        row = values.get(at_ms, {}).get("row", {})
        strike = closes.get(bar_time)
        future_close = closes.get(bar_time + frequency)
        reasons = []
        label = None
        if strike is None:
            reasons.append("bar_missing")
        elif not row:
            raise ResearchError(EXIT_CONTRACT, "rust.valueMissing", str(at_ms))
        elif row.get("p_up") is None:
            reasons.append("warmup")
        if future_close is None or label_at >= end:
            reasons.append("label_missing")
        elif strike is not None:
            label = 1.0 if future_close > strike else 0.0 if future_close < strike else 0.5
        if moment < split < label_at:
            reasons.append("cross_split")
        partition = "excluded"
        if not reasons:
            if moment < split and label_at <= split:
                partition = "IS"
            elif moment >= split and label_at < end:
                partition = "OOS"
        brier = None
        baseline = None
        if label is not None and row.get("p_up") is not None and partition != "excluded":
            brier = (row["p_up"] - label) ** 2
            baseline = (0.5 - label) ** 2
        samples.append({
            "evidence_type": "real-proxy",
            "t_utc": iso(moment),
            "label_at_utc": iso(label_at),
            "partition": partition,
            "source": SOURCE_NAME,
            "venue": VENUE,
            "product": PRODUCT,
            "spot": strike,
            "proxy_strike": strike,
            "sigma": row.get("sigma"),
            "p_up": row.get("p_up"),
            "proxy_label": label,
            "label_type": LABEL_TYPE,
            "brier": brier,
            "baseline_brier": baseline,
            "status": "ok" if brier is not None else "insufficient-evidence",
            "reason": ";".join(reasons) if reasons else "none",
        })
    return samples


# ------------------------------------------------------------ comparison ---

def build_comparison(samples: list[dict], args: argparse.Namespace) -> list[dict]:
    """Build the comparison carrier's rows, one per evidence column."""
    rows = []
    for evidence in EVIDENCE_COLUMNS:
        for partition in PARTITIONS:
            for metric in COMPARISON_METRICS:
                rows.append({
                    "evidence_type": evidence,
                    "partition": partition,
                    "n": 0,
                    "metric": metric,
                    "value": NA,
                    "unit": COMPARISON_UNITS[COMPARISON_METRICS.index(metric)],
                    "caliber": "not_applicable",
                    "reason": "not_applicable",
                    "research_verdict": "insufficient-evidence",
                })
    if not samples:
        return rows
    for partition in PARTITIONS:
        subset = [sample for sample in samples if sample["partition"] == partition]
        values = {
            "sample_count": len(subset),
            "tie_count": sum(1 for sample in subset
                             if sample["proxy_label"] == 0.5),
        }
        p_ups = [sample["p_up"] for sample in subset if sample["p_up"] is not None]
        sigmas = [sample["sigma"] for sample in subset if sample["sigma"] is not None]
        briers = [sample["brier"] for sample in subset if sample["brier"] is not None]
        baselines = [sample["baseline_brier"] for sample in subset
                     if sample["baseline_brier"] is not None]
        if p_ups:
            values["p_up_mean"] = sum(p_ups) / len(p_ups)
            values["p_up_min"] = min(p_ups)
            values["p_up_max"] = max(p_ups)
        if sigmas:
            values["sigma_min"] = min(sigmas)
            values["sigma_max"] = max(sigmas)
        if briers:
            values["brier"] = sum(briers) / len(briers)
        if baselines:
            values["baseline_brier"] = sum(baselines) / len(baselines)
        for row in rows:
            if row["evidence_type"] != "real-proxy" or row["partition"] != partition:
                continue
            metric = row["metric"]
            if metric in values:
                row["value"] = values[metric]
                row["n"] = values["sample_count"]
                row["caliber"] = CALIBERS[metric]
                row["reason"] = "none" if metric in (
                    "sample_count", "tie_count") else "proxy_only"
            elif metric in ("net_pnl", "interval_return_pct", "annualized_return_pct",
                           "sharpe", "max_drawdown_pct", "calmar", "turnover_pct",
                           "information_ratio"):
                row["reason"] = "no_real_account_equity"
            else:
                row["reason"] = "proxy_only"
    return rows


# The caliber of each metric, written into the carrier.
CALIBERS = {
    "sample_count": "paired proxy samples in this partition",
    "tie_count": "proxy labels that tied",
    "p_up_mean": "mean of the model probability over the samples",
    "p_up_min": "smallest model probability over the samples",
    "p_up_max": "largest model probability over the samples",
    "sigma_min": "smallest per-root-second volatility over the samples",
    "sigma_max": "largest per-root-second volatility over the samples",
    "brier": "mean((p_up - proxy_label)^2) over the samples",
    "baseline_brier": "mean((0.5 - proxy_label)^2) over the same samples",
    "candidate_count": "candidates the shared core offered",
    "trade_count": "confirmed positive fills",
    "net_pnl": "USDT net profit of the account",
    "interval_return_pct": "percent return over the declared window",
    "annualized_return_pct": "percent return annualized",
    "sharpe": "mean/pstdev of adjacent equity returns x sqrt(periods per year)",
    "max_drawdown_pct": "peak-to-trough drawdown of the account equity",
    "calmar": "annualized return over the maximum drawdown",
    "turnover_pct": "percent of capital traded over the window",
    "information_ratio": "active return over the tracking error",
}


# --------------------------------------------------------------- carriers ---

def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    """Write the carrier, with the frozen column order."""
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_cell(row.get(column)) for column in columns})


def format_cell(value: Any) -> str:
    """Render one cell: numbers keep their precision, missing values are N/A."""
    if value is None:
        return NA
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return NA
        return format(value, ".17g")
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_text(path: Path, content: str) -> None:
    """Create one output exclusively, including in a precheck race."""
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -------------------------------------------------------------- document ---

def check_documents(budget: Budget) -> list[dict]:
    """Read the known official documentation, at most once each."""
    results = []
    for url in DOCUMENT_URLS:
        if budget.remaining() <= 0:
            results.append({"url": url, "status": "not_run",
                            "detail": "the wall-clock budget was spent"})
            continue
        budget.take("document")
        request = urllib.request.Request(
            url, method="GET", headers={"User-Agent": "yquant-strategy-lab/1"})
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=budget.timeout()) as response:
                results.append({"url": url, "status": str(response.status),
                                "detail": "read only; a document is not historical data"})
        except urllib.error.HTTPError as exc:
            results.append({"url": url, "status": str(exc.code),
                            "detail": "read only; no history is implied"})
        except (urllib.error.URLError, OSError, ValueError) as exc:
            results.append({"url": url, "status": "not_run",
                            "detail": type(exc).__name__})
    return results


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow a redirect: a 3xx is recorded, not followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# ----------------------------------------------------------------- main ---

def main(argv: list[str] | None = None) -> int:
    """Validate and reserve destinations before reading business inputs."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parse_args(argv)
        evidence_dir = Path(args.evidence_dir)
        if PROJECT_ROOT != Path("/home/pascal/workspace/yquant-investment") or not (
                PROJECT_ROOT / "AGENTS.md").is_file():
            raise ResearchError(EXIT_USAGE, "workspace.invalid")
        for name in ("rust_bin", "ohlc_file", "raw_pages_file", "availability_file"):
            value = getattr(args, name)
            if value and (not Path(value).is_file() or not os.access(value, os.R_OK)):
                raise ResearchError(EXIT_USAGE, "input.unreadable", value)
        if evidence_dir.exists() or evidence_dir.is_symlink():
            raise ResearchError(EXIT_USAGE, "evidenceDir.exists")
        if not args.no_publish:
            targets = [INSTANCE_ROOT / "reports" / name for name in
                       ("report.md", "events.csv", "proxy-samples.csv", "comparison.csv", "coverage.json")]
            targets.append(PROJECT_ROOT / "data/reports/2026-11-10-predict-btc5m-m2/report.md")
            if any(path.exists() or path.is_symlink() for path in targets):
                raise ResearchError(EXIT_USAGE, "publish.exists")
        evidence_dir.mkdir(parents=True, exist_ok=False)
    except (ResearchError, OSError) as error:
        print(str(error), file=sys.stderr)
        return error.exit_code if isinstance(error, ResearchError) else EXIT_USAGE

    budget = Budget(max_requests=args.max_data_requests, wall_seconds=args.wall_seconds)
    commands: list[dict] = []
    result = EXIT_CONTRACT
    try:
        write_json(evidence_dir / "parameters.json", {
            "schema_version": SCHEMA_VERSION, "parameters": vars(args),
            "entrance": "ohlc-file" if args.ohlc_file else "quantdinger-agent",
            "strategy_config": str(INSTANCE_ROOT / "config.json"),
            "strategy_parameters": {"min_edge": 0.03, "order_usd": 5.0, "min_secs_left": 30,
                                    "vol_floor": 0.00005, "half_life_secs": 300.0, "min_vol_samples": 20},
        })
        result = research(args, evidence_dir, budget, commands)
    except ResearchError as error:
        print(str(error), file=sys.stderr)
        result = error.exit_code
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"research.failed: {error}", file=sys.stderr)
        result = EXIT_CONTRACT
    finally:
        try:
            write_json(evidence_dir / "commands.json", {
                "schema_version": SCHEMA_VERSION, "commands": commands,
                "request_count": budget.requests, "qd_request_count": budget.qd_requests,
                "document_request_count": budget.document_requests,
                "elapsed_seconds": round(time.monotonic() - budget.started, 3),
                "research_exit_code": result,
            })
        except OSError as error:
            print(f"commands.failed: {error}", file=sys.stderr)
            if result == EXIT_EVIDENCE:
                result = EXIT_CONTRACT
    return result


def review_availability(args: argparse.Namespace) -> dict:
    """Preserve archived claims and record only local, file-backed observations."""
    if args.availability_file:
        availability = json.loads(Path(args.availability_file).read_text(encoding="utf-8"))
    else:
        availability = {"schema_version": SCHEMA_VERSION, "rows": [], "sources": [],
                        "historical_evidence": "NOT_CAPTURED"}
    checked = []
    paths = [
        "data/reports/2026-11-10-predict-btc5m-gaps/report.md",
        "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-readonly-probe.json",
        "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-btc5m-bars.json",
        "data/reports/2026-11-09-predict-btc5m-intake/evidence/sources.json",
        "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/src/service/predict_fun.rs",
    ]
    for name in paths:
        path = PROJECT_ROOT / name
        content = path.read_text(encoding="utf-8") if path.is_file() else None
        available_range: Any = "not_verified"
        observation = "NOT_CAPTURED"
        if content is not None:
            if name.endswith("quantdinger-readonly-probe.json"):
                probe = json.loads(content)
                available_range = [probe.get("first_utc"), probe.get("last_utc")]
                observation = {"kind": "archived_ohlc_probe", "row_count": probe.get("row_count"),
                               "observed_at": probe.get("observed_at"),
                               "venue_provenance": probe.get("actual_venue_provenance")}
            elif name.endswith("quantdinger-btc5m-bars.json"):
                archived = json.loads(content)
                times = [entry["time"] for entry in archived["bars"]]
                available_range = [iso(dt.datetime.fromtimestamp(min(times), UTC)),
                                   iso(dt.datetime.fromtimestamp(max(times), UTC))] if times else []
                observation = {"kind": "archived_ohlc_not_share_book", "bar_count": len(times)}
            elif name.endswith("sources.json"):
                sources = json.loads(content)
                observation = {"kind": "archived_document_claims", "official": sources.get("official", []),
                               "public_api_probe": sources.get("public_api_probe")}
            elif name.endswith("predict_fun.rs"):
                observation = {"kind": "public_route_source", "current_orderbook_route_present":
                               '/markets/{market_id}/orderbook' in content,
                               "history_coverage": "not_proven_by_current_book_route"}
            else:
                observation = {"kind": "archived_gap_assessment", "scope": "report sections 2 and 3",
                               "historical_share_book_and_official_labels": "not_verified"}
        checked.append({
            "path": name, "sha256": digest(path) if content is not None else None,
            "available_range": available_range, "observation": observation,
            "gap": "no_verified_history_for_declared_window",
        })
    availability.update(reviewed_at_utc=iso(dt.datetime.now(UTC)),
                        review_mode="offline_archive_review", checked_files=checked,
                        historical_command_logs="NOT_CAPTURED")
    availability["local_rows"] = [{
        "kind": kind, "query_range": [args.start_utc, args.end_utc],
        "checked_files": paths, "observed": "not_verified",
        "gap": "no_verified_history_for_declared_window",
    } for kind in ("historical_share_book", "market_identity_and_start_price",
                   "official_settlement_labels")]
    return availability


def research(args: argparse.Namespace, evidence_dir: Path, budget: Budget,
             commands: list[dict]) -> int:
    """Perform the single thin-I/O research run after parameters are frozen."""
    bars, meta = fetch_bars(args, budget)
    documents = [] if args.ohlc_file else check_documents(budget)
    coverage = build_coverage(bars, args, meta, budget)
    availability = review_availability(args)
    write_json(evidence_dir / "availability.json", availability)

    # The raw bars, without any secret.
    raw_payload = {
        "schema_version": SCHEMA_VERSION,
        "source": meta.get("source", SOURCE_NAME),
        "market": meta.get("market", MARKET),
        "symbol": meta.get("symbol", SYMBOL),
        "timeframe": meta.get("timeframe", TIMEFRAME),
        "venue": VENUE,
        "product": PRODUCT,
        "bars": bars,
    }
    if args.ohlc_file:
        with (evidence_dir / "ohlc.json").open("xb") as handle:
            handle.write(Path(args.ohlc_file).read_bytes())
    else:
        write_json(evidence_dir / "ohlc.json", raw_payload)
    if args.raw_pages_file:
        with (evidence_dir / "raw-pages.json").open("xb") as handle:
            handle.write(Path(args.raw_pages_file).read_bytes())
    elif meta.get("raw_pages"):
        write_json(evidence_dir / "raw-pages.json", {
            "schema_version": SCHEMA_VERSION, "pages": meta["raw_pages"],
        })
    coverage["source_hashes"] = {name: digest(Path(getattr(args, name)))
        for name in ("ohlc_file", "raw_pages_file", "availability_file") if getattr(args, name)}
    coverage["source_hashes"]["research.py"] = digest(Path(__file__))
    coverage["source_hashes"]["rust_bin"] = digest(Path(args.rust_bin))

    # The proxy event stream, and the Rust run over it.
    proxy_rows = build_proxy_input(bars, args)
    proxy_input = evidence_dir / "proxy-input.jsonl"
    write_text(proxy_input,
               "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in proxy_rows))
    config_path = INSTANCE_ROOT / "config.json"
    proxy_output = evidence_dir / "proxy-output.jsonl"
    proxy_summary = evidence_dir / "proxy-summary.json"
    start_ms = int(parse_utc(args.start_utc, "start").timestamp() * 1000)
    end_ms = int(parse_utc(args.end_utc, "end").timestamp() * 1000)
    rust = run_rust(Path(args.rust_bin), "proxy", config_path, proxy_input,
                    proxy_output, proxy_summary,
                    start_ms - (args.warmup_prices + 1) * args.frequency_seconds * 1000,
                    end_ms, budget, commands)
    if rust["exit_code"] not in (0, 3):
        code = EXIT_USAGE if rust["exit_code"] == 64 else EXIT_CONTRACT
        reason = "rust.ioFailure" if rust["exit_code"] == 5 else "rust.failed"
        raise ResearchError(code, reason, str(rust["exit_code"]))
    if rust["summary"].get("schema_version") != REPLAY_SCHEMA_VERSION:
        raise ResearchError(EXIT_CONTRACT, "rust.summaryInvalid")
    if proxy_rows and (not proxy_output.is_file() or not proxy_output.stat().st_size):
        raise ResearchError(EXIT_CONTRACT, "rust.outputMissing")

    output_rows = []
    if proxy_output.is_file():
        for line in proxy_output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                output_rows.append(json.loads(line))

    samples = pair_samples(bars, output_rows, args)
    is_count = sum(1 for sample in samples if sample["partition"] == "IS")
    oos_count = sum(1 for sample in samples if sample["partition"] == "OOS")
    tie_count = sum(1 for sample in samples
                    if sample["partition"] in PARTITIONS and sample["proxy_label"] == 0.5)
    cross_split = sum(1 for sample in samples if "cross_split" in sample["reason"])
    coverage["is_count"] = is_count
    coverage["oos_count"] = oos_count
    coverage["tie_count"] = tie_count
    coverage["cross_split_count"] = cross_split
    coverage["research_completed"] = bool(is_count and oos_count)
    coverage["research_verdict"] = "insufficient-evidence"
    coverage["reasons"] = [
        "no_historical_share_book",
        "no_official_settlement_labels",
        "venue_and_product_unproven",
        "coarse_ohlc_sampling_only",
        "cost_and_latency_not_measured",
    ]
    write_json(evidence_dir / "coverage.json", coverage)

    comparison = build_comparison(samples, args)
    write_csv(evidence_dir / "proxy-samples.csv", samples, [
        "evidence_type", "t_utc", "label_at_utc", "partition", "source", "venue",
        "product", "spot", "proxy_strike", "sigma", "p_up", "proxy_label",
        "label_type", "brier", "baseline_brier", "status", "reason"])
    write_csv(evidence_dir / "comparison.csv", comparison, [
        "evidence_type", "partition", "n", "metric", "value", "unit", "caliber",
        "reason", "research_verdict"])
    write_csv(evidence_dir / "events.csv", output_rows, [
        "schema_version", "event_id", "event_at_ms", "available_at_ms", "seq",
        "evidence_type", "source", "event_type", "market_id", "yes_token",
        "no_token", "symbol", "samples", "sigma", "p_up", "candidate", "token",
        "price", "fair", "edge", "result_status", "filled_shares",
        "entered_before", "entered_after", "reason"])

    report = render_report(
        args, coverage, samples, comparison, meta, documents,
        parameters=json.loads((evidence_dir / "parameters.json").read_text(encoding="utf-8")),
        availability=availability,
        execution={"request_count": budget.requests, "qd_request_count": budget.qd_requests,
                   "document_request_count": budget.document_requests,
                   "elapsed_seconds": round(time.monotonic() - budget.started, 3),
                   "research_exit_code": "NOT_FINAL", "timing_scope": "render_point"})
    write_text(evidence_dir / "report-preview.md", report)
    report_path = INSTANCE_ROOT / "reports" / "report.md"
    publish = not args.no_publish and coverage["research_completed"]
    if publish:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_text(report_path, report)
        for name in ("proxy-samples.csv", "comparison.csv", "events.csv", "coverage.json"):
            with (report_path.parent / name).open("xb") as handle:
                handle.write((evidence_dir / name).read_bytes())
        index = PROJECT_ROOT / "data/reports/2026-11-10-predict-btc5m-m2/report.md"
        write_text(index, render_index(index, report_path, digest(report_path),
                                       evidence_dir, iso(dt.datetime.now(UTC))))

    print(json.dumps({
        "verdict": "insufficient-evidence",
        "is_count": is_count,
        "oos_count": oos_count,
        "tie_count": tie_count,
        "coverage_complete": coverage["coverage_complete"],
        "request_count": budget.requests,
        "published": publish,
    }, ensure_ascii=False))
    return EXIT_EVIDENCE


def render_index(index_path: Path, report_path: Path, report_sha256: str,
                 evidence_dir: Path, generated_at_utc: str) -> str:
    """Render a portable index without duplicating the research body."""
    report_link = Path(os.path.relpath(report_path, index_path.parent)).as_posix()
    evidence_link = Path(os.path.relpath(evidence_dir, index_path.parent)).as_posix()
    return (
        "# M2 研究索引\n\n"
        f"唯一正文：[研究报告]({report_link})\n\n"
        f"SHA256：{report_sha256}\n\ngenerated_at_utc: {generated_at_utc}\n\n"
        f"原 Developer 研究证据：[既有结果]({evidence_link})\n\n"
        "原结果：真实 OHLC 代理研究，insufficient-evidence，exit3；实盘未就绪。\n"
        "历史 run3555 及其他旧目录未验收，只读保留；历史失败与流程偏差不改判。\n"
        "当前报告候选待独立 Verify/Review；生成索引不代表新研究或独立验收通过。\n"
    )


def render_report(args: argparse.Namespace, coverage: dict, samples: list[dict],
                  comparison: list[dict], meta: dict,
                  documents: list[dict], *, parameters: dict | None = None,
                  availability: dict | None = None, execution: dict | None = None) -> str:
    """Render the report body from carrier rows and explicit report context."""
    real_rows = [row for row in comparison
                 if row["evidence_type"] == "real-proxy"]
    lines = []
    lines.append("# predict-btc5m-btc-arb 研究报告")
    lines.append("")
    lines.append("> 首份真实数据研究（M2）。本文由 `research.py` 从同一组内存行渲染，"
                 "与 `proxy-samples.csv`、`comparison.csv` 同源。")
    lines.append("")
    lines.append("## 结论摘要")
    lines.append("")
    lines.append("- 结论：这是一份**降级的代理研究**。共享 Rust 决策核心在真实闭合 OHLC "
                 "边界上给出了模型概率，并与方向代理标签配对；没有历史份额盘口、没有官方结算标签，"
                 "因此没有可执行收益结论。")
    lines.append("- 判定分类：证据不足（insufficient-evidence）。")
    lines.append("- 影响范围：只支持“原版冻结参数下的粗频 EWMA 概率在该窗口的校准描述”，"
                 "不支持任何交易、实盘或策略盈利结论。")
    lines.append("")
    lines.append("## 数据与口径声明")
    lines.append("")
    lines.append(f"- 数据来源：{coverage['source']}（{meta.get('entrance')}），"
                 f"market={MARKET}，symbol={SYMBOL}，timeframe={TIMEFRAME}。")
    lines.append("- 市场身份：venue=UNKNOWN，product=UNKNOWN。供应方未返回可验证的"
                 "交易所与产品证明，不得写成 Binance 现货或任何具体场所。")
    lines.append(f"- 时间范围：{coverage['parameters']['start_utc']} 至 "
                 f"{coverage['parameters']['end_utc']}（UTC，半开区间）；"
                 f"预热自 {coverage['fetch_start_utc']} 起，"
                 f"as_of={coverage['parameters']['as_of_utc']}。")
    lines.append(f"- 频率：{coverage['parameters']['frequency_seconds']} 秒；"
                 f"实际闭合 bar {coverage['closed_count']} 根，"
                 f"评估边界 {coverage['evaluation_boundary_count']} 个。")
    lines.append("- 成本假设：UNKNOWN。费用、净份额、价差与延迟均未建模。")
    lines.append("- 指标口径：Brier = mean((p_up - 标签)^2)；基准为同标签的恒定 0.5 概率；"
                 "平价标签单列；样本内为 t<split 且标签可得时刻≤split，样本外为 t≥split "
                 "且标签可得时刻<end，跨界样本排除并计数。")
    lines.append("- 杠杆与保证金口径：UNKNOWN。本轮无账户权益，不生成权益曲线。")
    lines.append("")
    lines.append("## 证据身份、可用性与执行预算")
    lines.append("")
    lines.append("- fixture：纯软件行为证据，不是真实市场证据，不替代本轮 real-proxy 数值。")
    lines.append("- real-proxy：真实闭合 OHLC 与方向代理标签；非真实份额盘口或官方结算标签。")
    lines.append("- real-market：未执行；无已验证历史份额盘口和官方结算标签，不能声明真实交易收益。")
    lines.append("- 本文从既有结果渲染时仅修订报告表达，非本次重跑研究；"
                 "报告渲染不代表独立验收通过。")
    if availability is not None:
        lines.append(f"- 历史声明 checked_at_utc={availability.get('checked_at_utc')}；"
                     "下列 URL 状态仅为当时声明，未重新联网核验，not_verified 不升级。")
        for row in availability.get("sources", []):
            lines.append("- 历史来源：" + json.dumps(row, ensure_ascii=False, sort_keys=True))
        lines.append(f"- 仅本地核查 reviewed_at_utc={availability.get('reviewed_at_utc')}；"
                     f"historical_command_logs={availability.get('historical_command_logs')}。")
        for row in availability.get("local_rows", []):
            lines.append("- 本地可用性/缺口：" + json.dumps(row, ensure_ascii=False, sort_keys=True))
        for row in availability.get("checked_files", []):
            lines.append("- 核查文件/范围/hash：" + json.dumps(row, ensure_ascii=False, sort_keys=True))
    else:
        lines.append("- availability 报告上下文未提供，不推断来源可用性。")
    lines.append("")
    lines.append("### 原策略冻结参数")
    lines.append("")
    lines.append("| 参数 | 值 |")
    lines.append("|---|---|")
    if parameters is not None:
        for key, value in parameters["strategy_parameters"].items():
            unit = " USDT" if key == "order_usd" else ""
            lines.append(f"| {key} | {value}{unit} |")
    else:
        lines.append("参数上下文未提供；不在 renderer 中另造策略参数。")
    lines.append("")
    lines.append(f"- 预算上限（非实测）：max_pages={args.max_pages}，"
                 f"max_data_requests={args.max_data_requests}，wall_seconds={args.wall_seconds}。")
    if execution is not None:
        timing = ("截至渲染点采样，非完整终态墙钟"
                  if execution.get("timing_scope") == "render_point"
                  else "完整研究墙钟（commands.json）")
        lines.append(f"- {timing}：" + "，".join(
            f"{key}={execution[key]}" for key in (
                "request_count", "qd_request_count", "document_request_count",
                "elapsed_seconds", "research_exit_code")) + "。")
    else:
        lines.append("- 实测执行上下文未提供，不以预算代替请求数或墙钟。")
    lines.append(f"- coverage.elapsed_seconds={coverage['elapsed_seconds']} 为早期采样，"
                 "不是完整墙钟；报告重渲染耗时另记，不覆盖原研究耗时。")
    lines.append("- 成交/费用/流动性/极端冲击压力测试：本轮不适用，未执行；"
                 "无真实份额盘口、成交和账户权益。不新增压力模型、场景或数据。")
    lines.append("")
    lines.append("## 假设与未建模项")
    lines.append("")
    lines.append("- 假设：闭合 bar 的 close 是该边界唯一可得的价格；"
                 "该假设是“闭合立即可得”的代理时钟，不是真实接收时刻。")
    lines.append("- 未建模项：轮内价格路径、份额盘口与深度、官方结算规则、"
                 "费用与净份额、资金费、冲击成本、延迟。")
    lines.append("")
    lines.append("## 限制与不适用范围")
    lines.append("")
    lines.append("- 限制：粗频采样（5m）无法重建 5 分钟轮内波动与入场边际；"
                 "样本长度短；方向代理标签不是官方结算标签。")
    lines.append("- 不适用范围：不可推广到任何其他标的、周期、时期或账户；"
                 "不可用于实盘就绪判断。")
    lines.append("")
    lines.append("## 结果明细")
    lines.append("")
    lines.append("| 指标 | 数值 | 口径说明 | 原因 |")
    lines.append("|---|---|---|---|")
    for partition in PARTITIONS:
        for row in real_rows:
            if row["partition"] != partition:
                continue
            lines.append(f"| {row['metric']} ({partition}) | {format_cell(row['value'])} | "
                         f"{row['caliber']} | {row['reason']} |")
    lines.append("")
    lines.append("## 复现命令")
    lines.append("")
    lines.append("```text")
    lines.append("# 从项目根执行")
    lines.append("PYTHONDONTWRITEBYTECODE=1 .venv/bin/python "
                 "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/research.py "
                 f"--ohlc-file {args.ohlc_file} --raw-pages-file {args.raw_pages_file} "
                 f"--availability-file {args.availability_file} --rust-bin {args.rust_bin} "
                 f"--start-utc {args.start_utc} --split-utc {args.split_utc} "
                 f"--end-utc {args.end_utc} --as-of-utc {args.as_of_utc} "
                 "--frequency-seconds 300 --warmup-prices 21 --initial-capital 200 "
                 "--max-pages 2 --max-data-requests 50 --wall-seconds 1800 "
                 "--evidence-dir data/reports/2026-11-10-predict-btc5m-m2/evidence/"
                 "recovery-01/independent-verify/research --no-publish")
    lines.append("```")
    lines.append("")
    lines.append("## 证据分级")
    lines.append("")
    lines.append("| 结论项 | 分级 | 依据 |")
    lines.append("|---|---|---|")
    lines.append(f"| 粗频模型概率在窗口内的校准描述 | 可用 | "
                 f"{coverage['is_count']} 个样本内与 {coverage['oos_count']} 个样本外配对，"
                 f"逐样本见 proxy-samples.csv |")
    lines.append("| 历史份额盘口与真实入场 | 证据不足 | 无本地历史，官方文档不证明历史可得性 |")
    lines.append("| 官方结算标签与真实 PnL | 证据不足 | 无已验证的官方结算标签 |")
    lines.append("| 交易所与产品身份 | 证据不足 | 供应方未返回 venue/product 证明 |")
    lines.append("| 费用、净份额、延迟 | 不适用 | 本轮无成交，无从测量 |")
    lines.append("| 杠杆、保证金回执、网格表 A/B、四折、G/E、35% 阈值 | 不适用 | "
                 "本实例不提交 QD 回测，无真实账户权益 |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
