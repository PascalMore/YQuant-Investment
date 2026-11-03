"""Grid training parameter freeze coordination (DESIGN-06-002 V1.4 §11.5/§11.6).

Thin main-repo adapter over the frozen offline calculations in grid_research.py
and the existing quantdinger Agent client. Nothing here performs network,
credential, database or strategy-execution work at import time; the only
network-capable path is ``collect_training`` driven through explicitly
injected callables, and the ``--collect`` CLI mode is a separately authorized
operation, never a default.

Public signatures are fixed by Design §11.5:
- validate_training_response(data, cell) -> dict
- prepare_training_cell(cell, data) -> dict
- freeze_training(cells, responses, *, output_dir) -> dict
- verify_training_freeze(manifest_path) -> dict
- collect_training(*, base_url, output_dir, agent_call, resolve_agent_token,
  now_utc, monotonic) -> dict
- main(argv=None) -> int   (--describe | --verify-freeze PATH | --collect)

grid_research.py and quantdinger.py are loaded by adjacent absolute file path
via spec_from_file_location (works from any cwd, no sys.path changes, no
reverse imports). Canonical JSON reuses grid_research.canonical_json unchanged.
quantdinger.py is not extended.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time
from typing import Any, Callable
import urllib.parse

__all__ = [
    "TrainingVerificationError",
    "validate_training_response",
    "prepare_training_cell",
    "freeze_training",
    "verify_training_freeze",
    "collect_training",
    "main",
]

_LAB = Path(__file__).resolve().parents[1]
_HERE = Path(__file__).resolve().parent

# Frozen native template identity (must equal the instance generator's lock).
TEMPLATE_SHA256 = "25320a59133818ecbb2d363cc418b0bae717bdcf669fc9f46f67be294056ac85"
TEMPLATE_RELATIVE_PATH = "strategies/neutral-grid-pumpusdt/strategy.py"
GENERATOR_RELATIVE_PATH = "strategies/neutral-grid-four-window-v1/research.py"
CALCULATIONS_RELATIVE_PATH = "scripts/grid_research.py"

TRAINING_SCHEMA_VERSION = "grid_training_ohlc_v1"
PARAMETERS_SCHEMA_VERSION = "grid_training_parameters_v1"
FREEZE_SCHEMA_VERSION = "grid_training_freeze_v1"
MANIFEST_NAME = "g02-training-freeze.json"
EVIDENCE_SUBDIR = Path("evidence") / "g02-training"
BUDGET_REF = "evidence/g02-training/budget.json"

DAY_SECONDS = 86400
TRAINING_LIMIT = 365
SOURCE_HOST = "https://api.gateio.ws"
METADATA_PATH = "/api/v4/futures/usdt/contracts"
CANDLE_PATH = "/api/v4/futures/usdt/candlesticks"
CANONICAL_SUFFIX = "/USDT:USDT"

WALL_CLOCK_LIMIT_SECONDS = 1800
PROVIDER_REQUEST_LIMIT = 50
PROVIDER_REQUESTS_PER_CELL = 2
AGENT_CALL_TIMEOUT_SECONDS = 30.0

MANIFEST_STATUS_COMPLETE = "complete"
MANIFEST_STATUS_INCOMPLETE = "incomplete"
NOT_READ_REASON = "not_read_due_to_stop"
CODE_KIND_LOCKED_CANDIDATE = "locked_candidate"

ITEM_STATUSES = (
    "ready", "no-feasible-geometry", "history_insufficient", "insufficient_evidence",
)

COSTS = {
    "initialCapital": 1000,
    "leverageEnabled": True,
    "leverage": 10,
    "commission": 0.0005,
    "slippage": 0.0005,
    "funding": "not_modeled",
    "dynamic_anchor": False,
}

LIMITATIONS = [
    "training prices only; provider volume stays unverified (volume_status=not_provided)",
    "historical identity validity and listing boundary remain UNKNOWN",
    "strategy code is locked_candidate: EVIDENCE_READY stays False and "
    "code_execution_eligible=false; parameters-ready is not backtest-ready",
    "offline freeze verification covers evidence integrity, not live provider access",
]

DATA_KEYS = frozenset({
    "schema_version", "data_mode", "status", "reason", "market", "symbol", "timeframe",
    "count", "identity", "identity_evidence", "source", "klines", "normalized_sha256",
    "coverage", "synthetic", "volume_status", "backtest_eligible",
    "historical_volume_validity",
})
COVERAGE_KEYS = frozenset({
    "requested_start_utc", "cutoff_utc", "requested_limit", "raw_count", "actual_count",
    "unique_count", "first_open_utc", "last_open_utc", "last_close_utc",
    "duplicate_count", "conflicting_count", "missing_count", "misaligned_count",
    "excluded_unclosed_count", "excluded_out_of_range_count",
    "short_training_history", "listing_boundary",
})
SOURCE_KEYS = frozenset({
    "provider", "host", "path", "query", "retrieved_at_utc", "raw_rows",
    "raw_rows_sha256", "provider_request_count", "request_policy", "metadata",
})
METADATA_KEYS = frozenset({
    "raw", "sha256", "retrieved_at_utc", "source", "settlement_basis", "quote_basis",
    "metadata_scope", "historical_identity_validity",
})
IDENTITY_KEYS = frozenset({
    "exchange_id", "market_type", "settle", "contract_type", "canonical_symbol",
    "native_contract",
})
KLINE_KEYS = frozenset({
    "open_time_utc", "close_time_utc", "available_at_utc", "availability_basis",
    "observed_at_utc", "open", "high", "low", "close", "identity",
})
METADATA_RAW_ALLOWED = frozenset({"name", "type", "base", "quote", "settle"})
ITEM_KEYS = frozenset({
    "cell_id", "window", "start_utc", "end_utc", "cutoff_utc", "identity",
    "instrument", "status", "reason", "evidence_ref", "evidence_sha256",
    "raw_rows_sha256", "metadata_sha256", "normalized_sha256", "training_range",
    "count", "last_available", "observed_at", "short", "listing", "geometry",
    "parameters_ref", "params_sha256", "code_ref", "code_sha256", "code_kind",
    "code_execution_eligible", "generator_sources", "job_id", "run_id",
})


class TrainingVerificationError(ValueError):
    """Independent verification failed; the response/freeze cannot be trusted."""


# --------------------------------------------------------------------------
# Neighbor module loading (adjacent absolute paths, lazy, no import-time I/O)
# --------------------------------------------------------------------------

_GRID_RESEARCH: Any = None
_QUANTDINGER: Any = None


def _load_neighbor(module_name: str, file_name: str) -> Any:
    path = _HERE / file_name
    if not path.is_file():
        raise TrainingVerificationError(f"required neighbor module missing: {file_name}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise TrainingVerificationError(f"neighbor module loader missing: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def grid_research() -> Any:
    """Load the frozen offline calculations module once by absolute path."""
    global _GRID_RESEARCH
    if _GRID_RESEARCH is None:
        _GRID_RESEARCH = _load_neighbor(
            "grid_training_dep_grid_research", "grid_research.py")
    return _GRID_RESEARCH


def quantdinger() -> Any:
    """Load the existing Agent client module once by absolute path."""
    global _QUANTDINGER
    if _QUANTDINGER is None:
        _QUANTDINGER = _load_neighbor(
            "grid_training_dep_quantdinger", "quantdinger.py")
    return _QUANTDINGER


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------

def _iso_utc(moment: dt.datetime) -> str:
    """Match the backend timestamp format exactly (isoformat with Z suffix)."""
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise TrainingVerificationError(f"{label} is not an ISO-8601 UTC string")
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TrainingVerificationError(f"{label} is not an ISO-8601 UTC string") from None
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise TrainingVerificationError(f"{label} must carry a UTC offset")
    if _iso_utc(moment) != value:
        raise TrainingVerificationError(f"{label} is not in canonical UTC-Z form")
    return moment


def _as_aware_datetime(value: Any, label: str) -> dt.datetime:
    if isinstance(value, dt.datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise TrainingVerificationError(f"{label} is not an ISO-8601 datetime") from None
    else:
        raise TrainingVerificationError(f"{label} must be a datetime or ISO string")
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise TrainingVerificationError(f"{label} must be timezone-aware")
    return moment


def _strictly(actual: Any, expected: Any) -> bool:
    """Type-sensitive equality: booleans/null never equal 0/1/other values."""
    if expected is True or expected is False or expected is None:
        return actual is expected
    return actual == expected


def _sha256_object(value: Any) -> str:
    """Digest an object with the reused canonical JSON (never modified here)."""
    try:
        text = grid_research().canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise TrainingVerificationError(
            f"object cannot be safely evidenced: {type(exc).__name__}") from None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_verified(path: Path, payload: bytes) -> str:
    """Write bytes exclusively, read them back and verify the digest."""
    if path.exists():
        raise TrainingVerificationError(f"refusing to overwrite existing file: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    readback = path.read_bytes()
    if readback != payload:
        raise TrainingVerificationError(f"read-back mismatch for {path.name}")
    return _sha256_bytes(readback)


def _read_json_object(path: Path, label: str) -> dict:
    if not path.is_file():
        raise TrainingVerificationError(f"{label} is missing: {path}")
    try:
        loaded = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrainingVerificationError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(loaded, dict):
        raise TrainingVerificationError(f"{label} is not a JSON object: {path}")
    return loaded


# --------------------------------------------------------------------------
# Cell context and identity helpers
# --------------------------------------------------------------------------

def _cell_context(cell: Any) -> dict:
    """Validate one frozen matrix cell and derive its request constants."""
    if not isinstance(cell, dict):
        raise TrainingVerificationError("cell must be a dict")
    cell_id = cell.get("cell_id")
    contract = cell.get("contract")
    window = cell.get("window")
    if not isinstance(cell_id, str) or not cell_id:
        raise TrainingVerificationError("cell_id must be a non-empty string")
    if not isinstance(window, str) or not window:
        raise TrainingVerificationError("cell window label missing")
    if (not isinstance(contract, str) or len(contract) <= 4
            or not contract.endswith("USDT")):
        raise TrainingVerificationError(f"cell contract is not a USDT pair: {cell_id}")
    base = contract[:-4]
    if not base.isascii() or not base.isalnum() or not base.isupper():
        raise TrainingVerificationError(f"cell contract base is not canonical: {cell_id}")
    start = _as_aware_datetime(cell.get("start_utc"), "cell start_utc")
    if start.utcoffset() != dt.timedelta(0):
        raise TrainingVerificationError("cell start_utc must be UTC")
    if (start.hour, start.minute, start.second, start.microsecond) != (0, 0, 0, 0):
        raise TrainingVerificationError("cell start_utc must be a UTC midnight")
    end = _as_aware_datetime(cell.get("end_utc"), "cell end_utc")
    return {
        "cell_id": cell_id, "contract": contract, "base": base, "window": window,
        "native_contract": f"{base}_USDT", "start": start, "end": end,
        "cutoff": int(start.timestamp()),
    }


def instrument_for_identity(identity: dict) -> str:
    """Build the parse_instrument-shaped identity string and round-trip it.

    The backend ``parse_instrument`` itself is never imported here (main repo
    does not import backend services); the local construction must round-trip
    back to the exact native contract name, which the subrepo alignment tests
    cover against the real backend parser.
    """
    if not isinstance(identity, dict):
        raise TrainingVerificationError("identity must be a dict")
    canonical = identity.get("canonical_symbol")
    native = identity.get("native_contract")
    if not isinstance(canonical, str) or not canonical.endswith(CANONICAL_SUFFIX):
        raise TrainingVerificationError("canonical_symbol is not BASE/USDT:USDT")
    base = canonical[: -len(CANONICAL_SUFFIX)]
    if not base or not base.isascii() or not base.isalnum() or not base.isupper():
        raise TrainingVerificationError("canonical_symbol base is not canonical")
    if native != f"{base}_USDT":
        raise TrainingVerificationError("canonical_symbol/native_contract mismatch")
    instrument = f"Crypto:{base}/USDT@gate:swap"
    market_part, separator, venue_part = instrument.partition("@")
    if not separator or not market_part.startswith("Crypto:"):
        raise TrainingVerificationError("instrument round-trip failed")
    pair = market_part.split(":", 1)[1]
    if "/" not in pair:
        raise TrainingVerificationError("instrument round-trip failed")
    pair_base, pair_quote = pair.split("/", 1)
    venue, _, market_type = venue_part.partition(":")
    if (venue, market_type, pair_quote) != ("gate", "swap", "USDT"):
        raise TrainingVerificationError("instrument round-trip failed")
    if f"{pair_base}_USDT" != native:
        raise TrainingVerificationError("instrument round-trip failed")
    return instrument


def _generator_sources() -> list:
    """Byte identities of every read-only source that produced the code."""
    sources = []
    for label, relative in (
        ("instance_generator", GENERATOR_RELATIVE_PATH),
        ("native_template", TEMPLATE_RELATIVE_PATH),
        ("offline_calculations", CALCULATIONS_RELATIVE_PATH),
    ):
        path = _LAB / relative
        if not path.is_file():
            raise TrainingVerificationError(f"generator source missing: {relative}")
        sources.append({
            "kind": label, "path": relative,
            "sha256": _sha256_bytes(path.read_bytes()),
        })
    return sources


# --------------------------------------------------------------------------
# Independent mirror of the backend normalization (no backend import)
# --------------------------------------------------------------------------

def _mirror_price(raw: Any, field: str):
    """Mirror backend _price: illegal prices yield None (raw stays preserved)."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, str):
        if raw.strip().lower() in ("nan", "inf", "-inf", "+inf"):
            return None
        try:
            number = float(raw)
        except ValueError:
            return None
    elif isinstance(raw, (int, float)):
        number = float(raw)
    else:
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _derive_from_raw(raw_rows: Any, *, cutoff: int, limit: int) -> dict:
    """Re-derive the exact backend normalization from the preserved raw rows."""
    if not isinstance(raw_rows, list):
        raise TrainingVerificationError("source.raw_rows is not a list")
    window_start = cutoff - limit * DAY_SECONDS
    window_opens = {cutoff - DAY_SECONDS * (index + 1) for index in range(limit)}
    derived: list = []
    excluded_out_of_range = 0
    invalid_price_count = 0
    for row in raw_rows:
        if not isinstance(row, dict):
            raise TrainingVerificationError("raw row is not an object")
        opened = row.get("t")
        if isinstance(opened, bool) or not isinstance(opened, int):
            raise TrainingVerificationError("bar t must be integer unix seconds")
        if opened < window_start or opened >= cutoff:
            excluded_out_of_range += 1
            continue
        prices = {}
        usable = True
        for field in ("o", "h", "l", "c"):
            value = _mirror_price(row.get(field), field)
            if value is None:
                usable = False
                break
            prices[field] = value
        if not usable:
            invalid_price_count += 1
            continue
        if prices["l"] > min(prices["o"], prices["c"]) or \
                prices["h"] < max(prices["o"], prices["c"]):
            invalid_price_count += 1
            continue
        derived.append({"t": opened, **{f: prices[f] for f in ("o", "h", "l", "c")}})
    derived.sort(key=lambda bar: bar["t"])
    seen: dict = {}
    duplicate_count = conflicting_count = 0
    unique: list = []
    for bar in derived:
        prior = seen.get(bar["t"])
        if prior is not None:
            duplicate_count += 1
            if any(bar[f] != prior[f] for f in ("o", "h", "l", "c")):
                conflicting_count += 1
            continue
        seen[bar["t"]] = bar
        unique.append(bar)
    missing = len(window_opens - seen.keys())
    misaligned = sum(1 for left, right in zip(unique, unique[1:])
                     if right["t"] - left["t"] != DAY_SECONDS)
    unclosed = sum(1 for bar in derived if bar["t"] + DAY_SECONDS > cutoff)
    count = len(unique)
    last_close = unique[-1]["t"] + DAY_SECONDS if unique else None
    return {
        "unique": unique, "count": count, "cutoff": cutoff, "limit": limit,
        "duplicate_count": duplicate_count, "conflicting_count": conflicting_count,
        "missing_count": missing, "misaligned_count": misaligned,
        "excluded_out_of_range_count": excluded_out_of_range,
        "invalid_price_count": invalid_price_count, "window_size": limit,
        "unclosed_count": unclosed, "last_close": last_close,
    }


def _verified_listing_start(listing: Any, identity: dict, mirror: dict,
                            observed_at: dt.datetime) -> int | None:
    """Validate the internal synthetic listing receipt, not provider metadata.

    Production Native only emits UNKNOWN. The pure acceptance seam records
    source/raw values/retrieval/digest and binds the listing to this product.
    Its first full day is independently derived from listed_at_utc; a partial
    listing day is never admitted. This is not a new production data source.
    """
    if listing == {"status": "UNKNOWN", "reason": "listing_boundary_unverified"}:
        return None
    if not isinstance(listing, dict):
        raise TrainingVerificationError("listing boundary is not an object")
    _require_key_set(listing, frozenset({
        "status", "first_full_open_utc", "source", "raw", "sha256", "retrieved_at_utc",
    }), "internal listing boundary")
    if listing["status"] != "VERIFIED" or listing["source"] != "internal_synthetic":
        raise TrainingVerificationError("listing source is not the internal synthetic seam")
    raw = listing["raw"]
    if not isinstance(raw, dict) or set(raw) != {"identity", "listed_at_utc"}:
        raise TrainingVerificationError("listing raw fields mismatch")
    if raw["identity"] != identity or _sha256_object(raw) != listing["sha256"]:
        raise TrainingVerificationError("listing identity/digest mismatch")
    listed = _parse_iso_utc(raw["listed_at_utc"], "listing listed_at_utc")
    retrieved = _parse_iso_utc(listing["retrieved_at_utc"], "listing retrieved_at_utc")
    if not listed <= retrieved <= observed_at:
        raise TrainingVerificationError("listing retrieval chronology mismatch")
    first_full = listed.replace(hour=0, minute=0, second=0, microsecond=0)
    if first_full < listed:
        first_full += dt.timedelta(days=1)
    if listing["first_full_open_utc"] != _iso_utc(first_full):
        raise TrainingVerificationError("listing first complete day mismatch")
    start = int(first_full.timestamp())
    if not mirror["cutoff"] - mirror["limit"] * DAY_SECONDS < start <= mirror["cutoff"]:
        raise TrainingVerificationError("listing does not explain the requested prefix")
    return start


def _mirror_classification(mirror: dict, *, listing_start: int | None = None) -> tuple:
    """Mirror production UNKNOWN verdicts or verify the internal listing seam."""
    count = mirror["count"]
    invalid = mirror["invalid_price_count"]
    missing = mirror["missing_count"]
    misaligned = mirror["misaligned_count"]
    duplicate = mirror["duplicate_count"]
    conflicting = mirror["conflicting_count"]
    if listing_start is not None:
        expected_opens = list(range(listing_start, mirror["cutoff"], DAY_SECONDS))
        if ([row["t"] for row in mirror["unique"]] != expected_opens
                or any((invalid, misaligned, duplicate, conflicting, mirror["unclosed_count"]))
                or missing != mirror["limit"] - count):
            raise TrainingVerificationError("listing proof contradicts the complete daily history")
        if count < 2:
            return "history_insufficient", f"training.historyInsufficient:count={count}", True
        return "ok", None, True
    if count < 2:
        return ("insufficient_evidence",
                f"training.unusableSample:count={count},invalid={invalid}", None)
    if mirror["last_close"] != mirror["cutoff"]:
        return ("insufficient_evidence",
                "training.trailingGap:last_close_before_cutoff", None)
    if (count == mirror["limit"] and missing == 0 and misaligned == 0
            and duplicate == 0 and conflicting == 0 and invalid == 0):
        return "ok", None, False
    if missing == mirror["window_size"] or missing > 0:
        return ("insufficient_evidence",
                f"training.unprovenReturn:count={count},missing={missing}", None)
    return ("insufficient_evidence",
            f"training.discontinuity:missing={missing},misaligned={misaligned},"
            f"duplicate={duplicate},conflicting={conflicting},invalid={invalid}",
            None)


def _expected_identity(metadata_raw: Any, native_contract: str) -> dict:
    """Cross-check the whitelisted raw contract metadata independently."""
    if not isinstance(metadata_raw, dict):
        raise TrainingVerificationError("metadata raw is not an object")
    if not set(metadata_raw).issubset(METADATA_RAW_ALLOWED):
        raise TrainingVerificationError("metadata raw carries non-whitelisted fields")
    name = metadata_raw.get("name")
    contract_type = metadata_raw.get("type")
    if not isinstance(name, str) or not isinstance(contract_type, str):
        raise TrainingVerificationError("contract name/type missing")
    if name != native_contract:
        raise TrainingVerificationError("contract name mismatch")
    if contract_type.lower() != "direct":
        raise TrainingVerificationError("contract is not a direct linear contract")
    base = metadata_raw.get("base")
    quote = metadata_raw.get("quote")
    settle = metadata_raw.get("settle")
    if settle is not None and str(settle).upper() != "USDT":
        raise TrainingVerificationError("settlement is not USDT")
    if quote is not None and str(quote).upper() != "USDT":
        raise TrainingVerificationError("quote is not USDT")
    if base is not None and str(base).upper() != native_contract.rsplit("_USDT", 1)[0]:
        raise TrainingVerificationError("base mismatch")
    canonical_symbol = f"{native_contract.rsplit('_USDT', 1)[0]}{CANONICAL_SUFFIX}"
    return {
        "exchange_id": "gate", "market_type": "swap", "settle": "USDT",
        "contract_type": "direct", "canonical_symbol": canonical_symbol,
        "native_contract": native_contract,
    }


def _require_key_set(container: dict, expected: frozenset, label: str) -> None:
    actual = set(container)
    if actual != set(expected):
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise TrainingVerificationError(
            f"{label} key set mismatch (missing={missing}, unexpected={extra})")


# --------------------------------------------------------------------------
# validate_training_response
# --------------------------------------------------------------------------

def validate_training_response(data: dict, cell: dict) -> dict:
    """No-I/O independent verification of one training response (§11.5).

    Recomputes the raw/metadata/normalized digests, re-derives OHLC/UTC/
    identity from the preserved raw rows and compares every frozen envelope
    field, the source route/query/range, coverage and capability flags against
    that derivation. Never trusts ``data.status`` or server booleans alone.
    Raises TrainingVerificationError (a ValueError) on any integrity mismatch.
    """
    gr = grid_research()
    ctx = _cell_context(cell)
    if not isinstance(data, dict):
        raise TrainingVerificationError("training response is not a dict")
    _require_key_set(data, DATA_KEYS, "response")
    if data.get("schema_version") != TRAINING_SCHEMA_VERSION:
        raise TrainingVerificationError("schema_version mismatch")
    if data.get("data_mode") != "training_ohlc":
        raise TrainingVerificationError("data_mode mismatch")
    if data.get("market") != "Crypto":
        raise TrainingVerificationError("market mismatch")
    if data.get("symbol") != ctx["contract"]:
        raise TrainingVerificationError("symbol does not match the authorized request")
    if data.get("timeframe") != "1D":
        raise TrainingVerificationError("timeframe mismatch")

    source = data.get("source")
    if not isinstance(source, dict):
        raise TrainingVerificationError("source is not an object")
    _require_key_set(source, SOURCE_KEYS, "source")
    if source.get("provider") != "native_gate":
        raise TrainingVerificationError("source provider mismatch")
    if source.get("host") != SOURCE_HOST or source.get("path") != CANDLE_PATH:
        raise TrainingVerificationError("source host/path mismatch")
    request_policy = source.get("request_policy")
    if request_policy != {"automatic_retries": 0, "pagination": 0, "redirects": 0}:
        raise TrainingVerificationError("source request_policy mismatch")
    try:
        provider_request_count = int(source.get("provider_request_count"))
    except (TypeError, ValueError):
        raise TrainingVerificationError("provider_request_count is not an integer") from None
    if not 0 < provider_request_count <= PROVIDER_REQUESTS_PER_CELL:
        raise TrainingVerificationError("provider_request_count outside the frozen budget")
    retrieved = _parse_iso_utc(source.get("retrieved_at_utc"), "source.retrieved_at_utc")

    query = source.get("query")
    if not isinstance(query, dict):
        raise TrainingVerificationError("source.query is not an object")
    cutoff = ctx["cutoff"]
    expected_query = {
        "contract": ctx["native_contract"], "interval": "1d",
        "from": cutoff - TRAINING_LIMIT * DAY_SECONDS, "to": cutoff - 1,
    }
    if query != expected_query:
        raise TrainingVerificationError("source query/range mismatch")

    raw_rows = source.get("raw_rows")
    raw_rows_sha = _sha256_object(raw_rows)
    if raw_rows_sha != source.get("raw_rows_sha256"):
        raise TrainingVerificationError("raw_rows digest mismatch")

    metadata = source.get("metadata")
    if not isinstance(metadata, dict):
        raise TrainingVerificationError("source.metadata is not an object")
    _require_key_set(metadata, METADATA_KEYS, "source.metadata")
    identity = _expected_identity(metadata.get("raw"), ctx["native_contract"])
    metadata_sha = _sha256_object(metadata.get("raw"))
    if metadata_sha != metadata.get("sha256"):
        raise TrainingVerificationError("metadata digest mismatch")
    _parse_iso_utc(metadata.get("retrieved_at_utc"), "metadata.retrieved_at_utc")
    if metadata.get("source") != {"host": SOURCE_HOST, "path": METADATA_PATH}:
        raise TrainingVerificationError("metadata source route mismatch")
    if (metadata.get("settlement_basis") != "endpoint_path"
            or metadata.get("quote_basis") != "contract_name"
            or metadata.get("metadata_scope") != "current_snapshot"
            or metadata.get("historical_identity_validity") != "UNKNOWN"):
        raise TrainingVerificationError("metadata evidence labels mismatch")
    if data.get("identity_evidence") != metadata:
        raise TrainingVerificationError("identity_evidence differs from source.metadata")
    if data.get("identity") != identity:
        raise TrainingVerificationError("identity mismatch")

    mirror = _derive_from_raw(raw_rows, cutoff=cutoff, limit=TRAINING_LIMIT)
    coverage = data.get("coverage")
    if not isinstance(coverage, dict):
        raise TrainingVerificationError("coverage is not an object")
    listing = coverage.get("listing_boundary")
    listing_start = _verified_listing_start(listing, identity, mirror, retrieved)
    status, reason, short = _mirror_classification(mirror, listing_start=listing_start)
    if data.get("status") != status:
        raise TrainingVerificationError(
            f"status mismatch: response={data.get('status')!r} derived={status!r}")
    if data.get("reason") != reason:
        raise TrainingVerificationError(
            f"reason mismatch: response={data.get('reason')!r} derived={reason!r}")

    klines = data.get("klines")
    if not isinstance(klines, list) or len(klines) != mirror["count"]:
        raise TrainingVerificationError("klines count mismatch")
    normalized_sha = _sha256_object(klines)
    if normalized_sha != data.get("normalized_sha256"):
        raise TrainingVerificationError("normalized digest mismatch")
    bars = []
    for server_bar, row in zip(klines, mirror["unique"]):
        if not isinstance(server_bar, dict):
            raise TrainingVerificationError("kline is not an object")
        _require_key_set(server_bar, KLINE_KEYS, "kline")
        open_moment = dt.datetime.fromtimestamp(row["t"], tz=dt.timezone.utc)
        close_moment = dt.datetime.fromtimestamp(row["t"] + DAY_SECONDS, tz=dt.timezone.utc)
        expected_bar = {
            "open_time_utc": _iso_utc(open_moment),
            "close_time_utc": _iso_utc(close_moment),
            "available_at_utc": _iso_utc(close_moment),
            "availability_basis": "bar_close_boundary",
            "observed_at_utc": source.get("retrieved_at_utc"),
            "open": row["o"], "high": row["h"], "low": row["l"], "close": row["c"],
            "identity": identity,
        }
        for field, expected_value in expected_bar.items():
            if server_bar.get(field) != expected_value:
                raise TrainingVerificationError(f"kline {field} mismatch")
        bars.append({
            "open_time_utc": expected_bar["open_time_utc"],
            "close_time_utc": expected_bar["close_time_utc"],
            "available_at_utc": expected_bar["available_at_utc"],
            "availability_basis": "bar_close_boundary",
            "observed_at_utc": expected_bar["observed_at_utc"],
            "open": row["o"], "high": row["h"], "low": row["l"], "close": row["c"],
            "identity": dict(identity),
        })

    _require_key_set(coverage, COVERAGE_KEYS, "coverage")
    unique = mirror["unique"]
    expected_coverage = {
        "requested_start_utc": _iso_utc(
            dt.datetime.fromtimestamp(cutoff - TRAINING_LIMIT * DAY_SECONDS,
                                      tz=dt.timezone.utc)),
        "cutoff_utc": _iso_utc(dt.datetime.fromtimestamp(cutoff, tz=dt.timezone.utc)),
        "requested_limit": TRAINING_LIMIT,
        "raw_count": len(raw_rows) if isinstance(raw_rows, list) else 0,
        "actual_count": mirror["count"],
        "unique_count": mirror["count"],
        "first_open_utc": _iso_utc(
            dt.datetime.fromtimestamp(unique[0]["t"], tz=dt.timezone.utc)) if unique else None,
        "last_open_utc": _iso_utc(
            dt.datetime.fromtimestamp(unique[-1]["t"], tz=dt.timezone.utc)) if unique else None,
        "last_close_utc": _iso_utc(
            dt.datetime.fromtimestamp(mirror["last_close"], tz=dt.timezone.utc))
        if mirror["last_close"] is not None else None,
        "duplicate_count": mirror["duplicate_count"],
        "conflicting_count": mirror["conflicting_count"],
        "missing_count": mirror["missing_count"],
        "misaligned_count": mirror["misaligned_count"],
        "excluded_unclosed_count": mirror["unclosed_count"],
        "excluded_out_of_range_count": mirror["excluded_out_of_range_count"],
        "short_training_history": short,
        "listing_boundary": listing,
    }
    for field, expected_value in expected_coverage.items():
        if not _strictly(coverage.get(field), expected_value):
            raise TrainingVerificationError(f"coverage {field} mismatch")
    if coverage.get("actual_count") != data.get("count") or \
            data.get("count") != mirror["count"]:
        raise TrainingVerificationError("count fields disagree")
    if not _strictly(data.get("synthetic"), False) \
            or not _strictly(data.get("backtest_eligible"), False):
        raise TrainingVerificationError("capability flags mismatch")
    if data.get("volume_status") != "not_provided" \
            or data.get("historical_volume_validity") != "UNKNOWN":
        raise TrainingVerificationError("volume/history disclosure mismatch")

    if status != "ok":
        return {
            "cell_id": ctx["cell_id"], "status": status, "reason": reason,
            "count": mirror["count"], "bars": [],
            "identity": identity, "coverage": dict(coverage),
            "training_range": None,
            "short_training_history": short,
            "listing_boundary": dict(coverage["listing_boundary"]),
            "last_available": None,
            "observed_at_utc": source.get("retrieved_at_utc"),
            "evidence": {
                "raw_rows_sha256": raw_rows_sha, "metadata_sha256": metadata_sha,
                "normalized_sha256": normalized_sha,
                "provider_request_count": provider_request_count,
                "retrieved_at_utc": source.get("retrieved_at_utc"),
            },
            "derived_at_utc": _iso_utc(retrieved),
        }

    training_range = {
        "L": min(bar["low"] for bar in bars), "U": max(bar["high"] for bar in bars),
    }
    return {
        "cell_id": ctx["cell_id"], "status": status, "reason": None,
        "count": mirror["count"], "bars": bars,
        "identity": identity, "coverage": dict(coverage),
        "training_range": training_range,
        "short_training_history": short,
        "listing_boundary": dict(coverage["listing_boundary"]),
        "last_available": bars[-1]["available_at_utc"],
        "observed_at_utc": source.get("retrieved_at_utc"),
        "evidence": {
            "raw_rows_sha256": raw_rows_sha, "metadata_sha256": metadata_sha,
            "normalized_sha256": normalized_sha,
            "provider_request_count": provider_request_count,
            "retrieved_at_utc": source.get("retrieved_at_utc"),
        },
        "derived_at_utc": _iso_utc(retrieved),
    }


# --------------------------------------------------------------------------
# prepare_training_cell
# --------------------------------------------------------------------------

def _build_parameters(ctx: dict, validated: dict, geometry: dict) -> dict:
    """Full frozen parameter object (§11.6); nothing required may be omitted."""
    gr = grid_research()
    return {
        "schema_version": PARAMETERS_SCHEMA_VERSION,
        "cell_id": ctx["cell_id"], "contract": ctx["contract"],
        "window": ctx["window"],
        "start_utc": _iso_utc(ctx["start"]), "end_utc": _iso_utc(ctx["end"]),
        "cutoff_utc": _iso_utc(ctx["start"]), "before_time": ctx["cutoff"],
        "instrument": instrument_for_identity(validated["identity"]),
        "identity": dict(validated["identity"]),
        "market": dict(gr.MARKET),
        "training": {
            "count": validated["count"],
            "training_range": dict(validated["training_range"]),
            "training_start_utc": geometry["training_start_utc"],
            "training_end_utc": geometry["training_end_utc"],
            "available_at_utc": geometry["training_available_at_utc"],
            "observed_at_utc": validated["observed_at_utc"],
            "availability_basis": "bar_close_boundary",
            "short": validated["short_training_history"],
            "listing": dict(validated["listing_boundary"]),
            "raw_rows_sha256": validated["evidence"]["raw_rows_sha256"],
            "metadata_sha256": validated["evidence"]["metadata_sha256"],
            "normalized_sha256": validated["evidence"]["normalized_sha256"],
        },
        "geometry": dict(geometry),
        "costs": dict(COSTS),
        "generator_sources": _generator_sources(),
    }


def prepare_training_cell(cell: dict, data: dict) -> dict:
    """Validate one response and re-derive coverage/geometry via grid_research.

    Full 365-bar rows cover the requested window; internally proven short
    listings cover their independently verified first full day to the cutoff.
    Both reuse check_coverage(frequency_seconds=86400) and derive_geometry.
    Only after independent validation is internal ``provenance_ok`` attached;
    an external flag can never skip validation. No I/O.
    """
    gr = grid_research()
    validated = validate_training_response(data, cell)
    ctx = _cell_context(cell)
    result = {
        "cell_id": ctx["cell_id"], "validate": validated,
        "coverage": None, "geometry": None, "parameters": None,
        "status": None, "reason": validated["reason"],
    }
    if validated["status"] != "ok":
        result["status"] = validated["status"]
        return result
    start = ctx["start"]
    coverage_start = (
        _parse_iso_utc(validated["listing_boundary"]["first_full_open_utc"], "listing first full day")
        if validated["short_training_history"] is True
        else start - dt.timedelta(days=TRAINING_LIMIT)
    )
    bars = [dict(bar, provenance_ok=True) for bar in validated["bars"]]
    coverage = gr.check_coverage(bars, validated["identity"], coverage_start, start,
                                 DAY_SECONDS)
    if coverage.get("status") != "ok":
        raise TrainingVerificationError(
            f"coverage verification failed: {coverage.get('reason')}")
    geometry = gr.derive_geometry(bars, start)
    result["coverage"] = dict(coverage)
    result["geometry"] = dict(geometry)
    if geometry.get("status") != "ok":
        result["status"] = "no-feasible-geometry"
        result["reason"] = geometry.get("reason")
        return result
    result["status"] = "ready"
    result["reason"] = None
    result["parameters"] = _build_parameters(ctx, validated, geometry)
    return result


# --------------------------------------------------------------------------
# freeze_training (pure coordination plus explicit local persistence)
# --------------------------------------------------------------------------

def _freeze_item(cell: dict, response: Any, output_dir: Path) -> tuple:
    gr = grid_research()
    ctx = _cell_context(cell)
    cid = ctx["cell_id"]
    item = {
        "cell_id": cid, "window": ctx["window"],
        "start_utc": _iso_utc(ctx["start"]), "end_utc": _iso_utc(ctx["end"]),
        "cutoff_utc": _iso_utc(ctx["start"]),
        "identity": None, "instrument": None,
        "status": None, "reason": None,
        "evidence_ref": None, "evidence_sha256": None,
        "raw_rows_sha256": None, "metadata_sha256": None, "normalized_sha256": None,
        "training_range": None, "count": None, "last_available": None,
        "observed_at": None, "short": None, "listing": None,
        "geometry": None,
        "parameters_ref": None, "params_sha256": None,
        "code_ref": None, "code_sha256": None,
        "code_kind": None, "code_execution_eligible": None,
        "generator_sources": None,
        "job_id": None, "run_id": None,
    }
    if response is None:
        item["status"] = "insufficient_evidence"
        item["reason"] = NOT_READ_REASON
        return item, {"status": item["status"]}
    if isinstance(response, dict) and response.get("not_read") is True:
        reason = response.get("reason")
        if not isinstance(reason, str) or not reason:
            raise TrainingVerificationError(
                f"not-read row {cid} requires an explicit reason")
        item["status"] = "insufficient_evidence"
        item["reason"] = reason
        return item, {"status": item["status"]}
    if not isinstance(response, dict):
        raise TrainingVerificationError(
            f"response for {cid} must be a data dict or an explicit not-read marker")

    prepared = prepare_training_cell(cell, response)
    validated = prepared["validate"]
    evidence_rel = EVIDENCE_SUBDIR / f"{cid}.training.json"
    evidence_sha = _write_verified(
        output_dir / evidence_rel,
        gr.canonical_json(response).encode("utf-8"))
    item.update({
        "identity": dict(validated["identity"]),
        "instrument": instrument_for_identity(validated["identity"]),
        "evidence_ref": evidence_rel.as_posix(), "evidence_sha256": evidence_sha,
        "raw_rows_sha256": validated["evidence"]["raw_rows_sha256"],
        "metadata_sha256": validated["evidence"]["metadata_sha256"],
        "normalized_sha256": validated["evidence"]["normalized_sha256"],
        "training_range": (None if validated["training_range"] is None
                           else dict(validated["training_range"])),
        "count": validated["count"],
        "last_available": validated["last_available"],
        "observed_at": validated["observed_at_utc"],
        "short": validated["short_training_history"],
        "listing": dict(validated["listing_boundary"]),
        "geometry": None if prepared["geometry"] is None else dict(prepared["geometry"]),
        "status": prepared["status"], "reason": prepared["reason"],
    })
    if prepared["status"] == "ready":
        geometry = prepared["geometry"]
        parameters_rel = EVIDENCE_SUBDIR / f"{cid}.parameters.json"
        params_sha = _write_verified(
            output_dir / parameters_rel,
            gr.canonical_json(prepared["parameters"]).encode("utf-8"))
        generator_cell = dict(cell, native_instrument=item["instrument"])
        code = gr.generate_strategy_source(
            cell=generator_cell, template_sha256=TEMPLATE_SHA256, geometry=geometry)
        code_rel = EVIDENCE_SUBDIR / f"{cid}.strategy.py"
        code_sha = _write_verified(output_dir / code_rel, code.encode("utf-8"))
        item.update({
            "parameters_ref": parameters_rel.as_posix(), "params_sha256": params_sha,
            "code_ref": code_rel.as_posix(), "code_sha256": code_sha,
            "code_kind": CODE_KIND_LOCKED_CANDIDATE,
            "code_execution_eligible": False,
            "generator_sources": _generator_sources(),
        })
    return item, {"status": prepared["status"]}


# Instance template lock is checked lazily against the frozen constant so the
# module import itself performs no file reads.
_TEMPLATE_IDENTITY: dict = {"checked": False}


def _check_template_identity() -> None:
    if _TEMPLATE_IDENTITY.get("checked"):
        return
    research_path = _LAB / GENERATOR_RELATIVE_PATH
    if not research_path.is_file():
        raise TrainingVerificationError("instance generator missing")
    text = research_path.read_text(encoding="utf-8")
    marker = f'TEMPLATE_SHA256 = "{TEMPLATE_SHA256}"'
    if marker not in text:
        raise TrainingVerificationError("instance template lock drifted from the frozen constant")
    template_path = _LAB / TEMPLATE_RELATIVE_PATH
    if not template_path.is_file():
        raise TrainingVerificationError("native template missing")
    if _sha256_bytes(template_path.read_bytes()) != TEMPLATE_SHA256:
        raise TrainingVerificationError("native template bytes drifted from the frozen constant")
    _TEMPLATE_IDENTITY["checked"] = True


def freeze_training(cells: list, responses: dict, *, output_dir: Path) -> dict:
    """Freeze the default 16-target matrix with explicit local writes (§11.6).

    Unknown or stopped rows keep their reason; nothing is padded with default
    code or parameters. Evidence/parameter/code files are written and read
    back first, then the manifest and its body digest. No network, no strategy
    execution, no compile.
    """
    gr = grid_research()
    _check_template_identity()
    output_dir = Path(output_dir)
    cells = list(cells)
    if len(cells) != 16:
        raise TrainingVerificationError(
            f"freeze requires exactly the 16 default targets, got {len(cells)}")
    # D5-3/R-05: the anchor travels with the batch cells; a default anchor must
    # never define the frozen matrix (that was B-1).
    anchors = {cell.get("anchor_utc") for cell in cells}
    if len(anchors) != 1 or anchors == {None}:
        raise TrainingVerificationError(
            "cells must carry exactly one explicit anchor_utc (D5-3)")
    batch_anchor = next(iter(anchors))
    batch_frequency = cells[0].get("frequency_seconds") or 3600
    expected_cells = gr.build_cells(anchor_utc=batch_anchor,
                                    frequency_seconds=batch_frequency)
    expected_ids = [item["cell_id"] for item in expected_cells]
    ids = []
    for cell in cells:
        context = _cell_context(cell)
        ids.append(context["cell_id"])
    if sorted(ids) != sorted(expected_ids) or len(set(ids)) != len(ids):
        raise TrainingVerificationError("cells are not exactly the default matrix")
    if not isinstance(responses, dict):
        raise TrainingVerificationError("responses must be a dict keyed by cell_id")
    unknown = set(responses) - set(ids)
    if unknown:
        raise TrainingVerificationError(f"responses carry unknown cells: {sorted(unknown)}")
    manifest_path = output_dir / MANIFEST_NAME
    if manifest_path.exists():
        raise TrainingVerificationError(
            "freeze manifest already exists: refusing overwrite (STOP, no resume)")

    items: list = []
    summaries: dict = {}
    for cell in cells:
        item, summary = _freeze_item(cell, responses.get(cell["cell_id"]), output_dir)
        items.append(item)
        summaries[item["cell_id"]] = summary["status"]
    has_not_read = any(item["reason"] == NOT_READ_REASON for item in items)
    contracts = list(dict.fromkeys(
        _cell_context(cell)["contract"] for cell in cells))
    windows = list(dict.fromkeys(_cell_context(cell)["window"] for cell in cells))
    anchor = expected_cells[0]["anchor_utc"]
    task_date = anchor.date().isoformat()
    body = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "matrix": {
            "contracts": contracts, "windows": windows,
            "anchor_utc": _iso_utc(anchor),
            "task_date": task_date,
            "frequency_seconds": batch_frequency,
        },
        "items": items,
        "budget_ref": BUDGET_REF,
        "limits": {
            "whoami": 1, "klines_per_cell": 1, "klines_total": len(cells),
            "provider_requests": PROVIDER_REQUEST_LIMIT,
            "wall_clock_seconds": WALL_CLOCK_LIMIT_SECONDS,
        },
        "limitations": list(LIMITATIONS),
        "status": MANIFEST_STATUS_INCOMPLETE if has_not_read else MANIFEST_STATUS_COMPLETE,
    }
    manifest = {**body, "body_sha256": _sha256_object(body)}
    manifest_sha = _write_verified(
        manifest_path, gr.canonical_json(manifest).encode("utf-8"))
    stored = _read_json_object(manifest_path, "freeze manifest")
    if stored.get("body_sha256") != manifest.get("body_sha256"):
        raise TrainingVerificationError("manifest body digest changed after write")
    return {
        "manifest_ref": manifest_path.as_posix(),
        "manifest_status": manifest["status"],
        "manifest_sha256": manifest_sha,
        "items": len(items),
        "cells": summaries,
    }


# --------------------------------------------------------------------------
# verify_training_freeze (read-only re-verification, never repairs)
# --------------------------------------------------------------------------

def verify_training_freeze(manifest_path: Path) -> dict:
    """Recompute every digest and re-derive geometry/code from local files.

    Read-only: nothing is repaired or refetched. Any content change, path
    identity mismatch or derivation disagreement rejects the freeze.
    """
    gr = grid_research()
    _check_template_identity()
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise TrainingVerificationError(f"freeze manifest is missing: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise TrainingVerificationError("manifest is not a JSON object")
    if manifest.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise TrainingVerificationError("manifest schema_version mismatch")
    body = dict(manifest)
    declared_digest = body.pop("body_sha256", None)
    if not isinstance(declared_digest, str) or not declared_digest:
        raise TrainingVerificationError("manifest body_sha256 missing")
    if _sha256_object(body) != declared_digest:
        raise TrainingVerificationError("manifest body_sha256 mismatch")
    if body.get("budget_ref") != BUDGET_REF:
        raise TrainingVerificationError("manifest budget_ref mismatch")
    items = body.get("items")
    if not isinstance(items, list) or len(items) != 16:
        raise TrainingVerificationError("manifest must carry exactly 16 items")
    matrix = body.get("matrix") if isinstance(body.get("matrix"), dict) else {}
    manifest_anchor = matrix.get("anchor_utc")
    if not manifest_anchor:
        raise TrainingVerificationError("manifest matrix anchor_utc missing (D5-3)")
    default_cells = gr.build_cells(
        anchor_utc=manifest_anchor,
        frequency_seconds=matrix.get("frequency_seconds") or 3600)
    default_index = {cell["cell_id"]: cell for cell in default_cells}
    if [item.get("cell_id") for item in items] != \
            [cell["cell_id"] for cell in default_cells]:
        raise TrainingVerificationError(
            "manifest rows are not the default matrix in canonical order")
    base_dir = manifest_path.parent
    cells_report = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != set(ITEM_KEYS):
            raise TrainingVerificationError(
                f"manifest item key set mismatch for {item.get('cell_id')!r}")
        cid = item["cell_id"]
        if item.get("status") not in ITEM_STATUSES:
            raise TrainingVerificationError(f"item {cid} carries an unknown status")
        if not _strictly(item.get("job_id"), None) or not _strictly(item.get("run_id"), None):
            raise TrainingVerificationError(f"item {cid} carries job/run identifiers")

        def _require_null(*fields: str) -> None:
            for field in fields:
                if not _strictly(item.get(field), None):
                    raise TrainingVerificationError(
                        f"item {cid} field {field} must be null for status "
                        f"{item.get('status')}")

        cell = default_index[cid]
        context = _cell_context(cell)
        for field, expected_value in (
            ("window", context["window"]), ("start_utc", _iso_utc(context["start"])),
            ("end_utc", _iso_utc(context["end"])), ("cutoff_utc", _iso_utc(context["start"])),
        ):
            if item.get(field) != expected_value:
                raise TrainingVerificationError(f"item {cid} field {field} mismatch")
        if item.get("reason") == NOT_READ_REASON:
            if item["status"] != "insufficient_evidence":
                raise TrainingVerificationError(f"item {cid} not-read status mismatch")
            _require_null("evidence_ref", "evidence_sha256", "parameters_ref",
                          "params_sha256", "code_ref", "code_sha256", "identity",
                          "instrument", "geometry", "raw_rows_sha256", "metadata_sha256",
                          "normalized_sha256", "training_range", "count", "last_available",
                          "observed_at", "short", "listing", "code_kind",
                          "code_execution_eligible", "generator_sources")
            cells_report[cid] = item["status"]
            continue
        cell = default_index[cid]
        evidence_ref = item.get("evidence_ref")
        expected_ref = (EVIDENCE_SUBDIR / f"{cid}.training.json").as_posix()
        if evidence_ref != expected_ref:
            raise TrainingVerificationError(f"item {cid} evidence_ref mismatch")
        evidence_path = base_dir / evidence_ref
        evidence_bytes = evidence_path.read_bytes()
        if _sha256_bytes(evidence_bytes) != item.get("evidence_sha256"):
            raise TrainingVerificationError(f"item {cid} evidence bytes mismatch")
        training = json.loads(evidence_bytes.decode("utf-8"))
        validated = validate_training_response(training, cell)
        for field, expected_value in (
            ("raw_rows_sha256", validated["evidence"]["raw_rows_sha256"]),
            ("metadata_sha256", validated["evidence"]["metadata_sha256"]),
            ("normalized_sha256", validated["evidence"]["normalized_sha256"]),
            ("count", validated["count"]),
            ("last_available", validated["last_available"]),
            ("observed_at", validated["observed_at_utc"]),
            ("short", validated["short_training_history"]),
        ):
            if not _strictly(item.get(field), expected_value):
                raise TrainingVerificationError(f"item {cid} field {field} mismatch")
        if item.get("identity") != validated["identity"]:
            raise TrainingVerificationError(f"item {cid} identity mismatch")
        if item.get("instrument") != instrument_for_identity(validated["identity"]):
            raise TrainingVerificationError(f"item {cid} instrument mismatch")
        if item.get("listing") != validated["listing_boundary"]:
            raise TrainingVerificationError(f"item {cid} listing mismatch")
        item_range = item.get("training_range")
        if item_range != validated["training_range"]:
            raise TrainingVerificationError(f"item {cid} training_range mismatch")
        prepared = prepare_training_cell(cell, training)
        if item.get("status") != prepared["status"] \
                or item.get("reason") != prepared["reason"]:
            raise TrainingVerificationError(
                f"item {cid} status/reason disagree with re-derivation")
        item_geometry = item.get("geometry")
        if item_geometry != prepared["geometry"]:
            raise TrainingVerificationError(f"item {cid} geometry mismatch")
        if prepared["status"] == "ready":
            parameters_ref = item.get("parameters_ref")
            expected_params_ref = (EVIDENCE_SUBDIR / f"{cid}.parameters.json").as_posix()
            if parameters_ref != expected_params_ref:
                raise TrainingVerificationError(f"item {cid} parameters_ref mismatch")
            params_bytes = (base_dir / parameters_ref).read_bytes()
            if _sha256_bytes(params_bytes) != item.get("params_sha256"):
                raise TrainingVerificationError(f"item {cid} params bytes mismatch")
            parameters = json.loads(params_bytes.decode("utf-8"))
            if parameters != prepared["parameters"]:
                raise TrainingVerificationError(f"item {cid} parameters object mismatch")
            code_ref = item.get("code_ref")
            expected_code_ref = (EVIDENCE_SUBDIR / f"{cid}.strategy.py").as_posix()
            if code_ref != expected_code_ref:
                raise TrainingVerificationError(f"item {cid} code_ref mismatch")
            code_bytes = (base_dir / code_ref).read_bytes()
            if _sha256_bytes(code_bytes) != item.get("code_sha256"):
                raise TrainingVerificationError(f"item {cid} code bytes mismatch")
            regenerated = gr.generate_strategy_source(
                cell=dict(cell, native_instrument=item["instrument"]),
                template_sha256=TEMPLATE_SHA256, geometry=prepared["geometry"])
            if regenerated.encode("utf-8") != code_bytes:
                raise TrainingVerificationError(f"item {cid} code no longer regenerates")
            if item.get("code_kind") != CODE_KIND_LOCKED_CANDIDATE \
                    or not _strictly(item.get("code_execution_eligible"), False):
                raise TrainingVerificationError(f"item {cid} code lock fields mismatch")
            sources = item.get("generator_sources")
            if not isinstance(sources, list) or sources != _generator_sources():
                raise TrainingVerificationError(f"item {cid} generator_sources mismatch")
            for entry in sources:
                if not isinstance(entry, dict) or "path" not in entry or "sha256" not in entry:
                    raise TrainingVerificationError(
                        f"item {cid} generator source entry malformed")
                source_path = _LAB / entry["path"]
                if not source_path.is_file():
                    raise TrainingVerificationError(
                        f"item {cid} generator source missing: {entry['path']}")
                if _sha256_bytes(source_path.read_bytes()) != entry["sha256"]:
                    raise TrainingVerificationError(
                        f"item {cid} generator source bytes drifted: {entry['path']}")
        else:
            _require_null("parameters_ref", "params_sha256", "code_ref", "code_sha256")
        cells_report[cid] = item["status"]
    has_not_read = any(
        item.get("reason") == NOT_READ_REASON for item in items)
    expected_manifest_status = (
        MANIFEST_STATUS_INCOMPLETE if has_not_read else MANIFEST_STATUS_COMPLETE)
    if body.get("status") != expected_manifest_status:
        raise TrainingVerificationError(
            f"manifest status {body.get('status')!r} disagrees with item reasons")
    return {
        "status": "ok",
        "manifest": manifest_path.as_posix(),
        "manifest_status": body.get("status"),
        "items": len(items),
        "cells": cells_report,
        "verified": [
            "body_sha256", "item digests", "identity/instrument round-trip",
            "geometry re-derivation", "parameters objects",
            "strategy code regeneration", "generator source bytes",
            "status/reason consistency",
        ],
        "not_verified": [
            "budget.json runtime content (collector scope, not freeze scope)",
        ],
    }

# --------------------------------------------------------------------------
# collect_training (explicit dependency injection, separate authorization)
# --------------------------------------------------------------------------

def _origin(base_url: str) -> str:
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise TrainingVerificationError("base_url is not an http(s) origin")
    return f"{parts.scheme}://{parts.netloc}"


def _whoami_authorization(data: Any) -> dict:
    """Keep only market/scope authorization facts; never the raw response."""
    scope_present = False
    gate_swap_crypto_declared = False
    if isinstance(data, dict):
        for field, expected in (("exchange", "gate"), ("exchange_id", "gate"),
                                ("product", "swap"), ("market_type", "swap")):
            if field in data and data[field] != expected:
                raise TrainingVerificationError("whoami identity contradicts training target")
        scopes = data.get("scopes")
        if not isinstance(scopes, (list, tuple, set, dict)):
            scopes = data.get("scope")
        scope_present = bool(scopes)
        try:
            text = grid_research().canonical_json(data)
        except (TypeError, ValueError):
            text = ""
        gate_swap_crypto_declared = (
            '"gate"' in text and '"swap"' in text and '"Crypto"' in text)
    return {
        "whoami": "ok", "scope_present": scope_present,
        "gate_swap_crypto_declared": gate_swap_crypto_declared,
    }


def _stop_reason(exc: BaseException) -> str:
    """Sanitized STOP cause; never raw payloads, headers or credentials."""
    if hasattr(exc, "exit_code") and hasattr(exc, "summary"):
        try:
            return f"agent:{exc.summary()}"  # summary() scrubs secrets upstream
        except Exception:
            return f"agent:{type(exc).__name__}"
    if isinstance(exc, (TrainingVerificationError, ValueError)):
        return f"integrity:{exc}"
    return f"unexpected:{type(exc).__name__}"


def collect_training(*, base_url: str, output_dir: Path,
                     agent_call: Callable,
                     resolve_agent_token: Callable,
                     now_utc: Callable,
                     monotonic: Callable,
                     anchor_utc: dt.datetime | None = None,
                     frequency_seconds: int = 3600) -> dict:
    """Collect training responses cell by cell and freeze them locally.

    All dependencies are explicit: the Agent caller, the token resolver (its
    value is consumed only inside the calls and never enters argv, manifests
    or logs), the clock and the monotonic source. Budget: whoami<=1,
    klines<=1/cell and <=16 total, provider requests<=50 with two reserved per
    cell, wall clock<=1800s. Any STOP preserves already-read evidence and
    records the remaining rows as not_read_due_to_stop. Running this against
    a live Agent requires a separate, explicit authorization; offline tests
    inject fakes at these boundaries only.
    """
    gr = grid_research()
    for name, callable_value in (
        ("agent_call", agent_call), ("resolve_agent_token", resolve_agent_token),
        ("now_utc", now_utc), ("monotonic", monotonic),
    ):
        if not callable(callable_value):
            raise TrainingVerificationError(f"{name} must be callable")
    if not isinstance(base_url, str) or not base_url.strip():
        raise TrainingVerificationError("base_url is required")
    output_dir = Path(output_dir)
    cells = gr.build_cells()
    anchor = cells[0]["anchor_utc"]
    moment = now_utc()
    if not isinstance(moment, dt.datetime) or moment.tzinfo is None:
        raise TrainingVerificationError("now_utc must return a timezone-aware datetime")
    moment = _as_aware_datetime(moment, "now_utc result")
    gr.validate_run_anchor(anchor, moment)
    evidence_dir = output_dir / EVIDENCE_SUBDIR
    if evidence_dir.exists():
        raise TrainingVerificationError(
            "training evidence directory already exists: STOP, no resume/restart")
    token = resolve_agent_token()
    if not isinstance(token, str) or not token.strip():
        raise TrainingVerificationError("agent token missing: auth.missing")

    started = monotonic()
    budget = {
        "whoami_attempts": 0, "whoami_limit": 1,
        "klines_attempts": 0, "klines_limit": len(cells),
        "provider_requests_reserved": 0, "provider_limit": PROVIDER_REQUEST_LIMIT,
        "provider_receipts": 0,
        "started_at_utc": _iso_utc(moment),
        "wall_clock_limit_seconds": WALL_CLOCK_LIMIT_SECONDS,
        "stop_reason": None,
    }
    responses: dict = {}
    billing_records: dict = {}
    stop_reason: str | None = None
    whoami: dict | None = None

    try:
        budget["whoami_attempts"] += 1
        whoami_data, _discarded_headers = agent_call(
            "agent_whoami", base_url=base_url, token=token,
            timeout=AGENT_CALL_TIMEOUT_SECONDS)
        if (isinstance(whoami_data, dict)
                and quantdinger().billing_contradiction(whoami_data.get("billing"))):
            raise TrainingVerificationError("billing.charged")
        whoami = _whoami_authorization(whoami_data)
    except Exception as exc:  # any whoami failure stops before the first kline
        stop_reason = _stop_reason(exc)

    if stop_reason is None:
        evidence_dir.mkdir(parents=True, exist_ok=False)
        access = {
            "target_origin": _origin(base_url),
            "operations_allowlist": [
                "GET /api/agent/v1/whoami", "GET /api/agent/v1/klines"],
            "authorization_reference": (
                "DESIGN-06-002 V1.4 §11.8; kanban card t_88957939 (non-secret)"),
            "whoami": whoami,
            "budget_limits": {
                "whoami": 1, "klines_per_cell": 1, "klines_total": len(cells),
                "provider_requests": PROVIDER_REQUEST_LIMIT,
                "wall_clock_seconds": WALL_CLOCK_LIMIT_SECONDS,
            },
            "created_at_utc": _iso_utc(moment),
        }
        _write_verified(
            evidence_dir / "access-check.json",
            gr.canonical_json(access).encode("utf-8"))
        for cell in cells:
            cid = cell["cell_id"]
            elapsed = monotonic() - started
            if elapsed >= WALL_CLOCK_LIMIT_SECONDS:
                stop_reason = "wall_clock_exhausted"
                break
            if (budget["provider_requests_reserved"] + PROVIDER_REQUESTS_PER_CELL
                    > PROVIDER_REQUEST_LIMIT):
                stop_reason = "provider_budget_exhausted"
                break
            if budget["klines_attempts"] + 1 > budget["klines_limit"]:
                stop_reason = "klines_budget_exhausted"
                break
            budget["klines_attempts"] += 1
            budget["provider_requests_reserved"] += PROVIDER_REQUESTS_PER_CELL
            params = {
                "data_mode": "training_ohlc", "market": "Crypto",
                "symbol": cell["contract"], "timeframe": "1D",
                "exchange_id": "gate", "market_type": "swap",
                "before_time": _cell_context(cell)["cutoff"],
                "limit": TRAINING_LIMIT,
            }
            try:
                data, _discarded_headers = agent_call(
                    "agent_klines", base_url=base_url, token=token, params=params,
                    timeout=AGENT_CALL_TIMEOUT_SECONDS)
            except Exception as exc:
                stop_reason = _stop_reason(exc)
                break
            billing = data.get("billing") if isinstance(data, dict) else None
            if quantdinger().billing_contradiction(billing):
                stop_reason = "billing.charged"
                break
            billing_records[cid] = (
                "absent" if not isinstance(billing, dict)
                else str(billing.get("status") or "absent"))
            try:
                prepared = prepare_training_cell(cell, data)
            except ValueError as exc:
                stop_reason = _stop_reason(exc)
                break
            if isinstance(data, dict) and isinstance(data.get("source"), dict):
                try:
                    budget["provider_receipts"] += int(
                        data["source"].get("provider_request_count") or 0)
                except (TypeError, ValueError):
                    pass
            responses[cid] = data
            if prepared["status"] == "insufficient_evidence":
                stop_reason = f"training:{prepared['reason']}"
                break
            if monotonic() - started >= WALL_CLOCK_LIMIT_SECONDS:
                stop_reason = "wall_clock_exhausted"
                break

    if not evidence_dir.exists():
        # The whoami failed before any evidence existed; still freeze the
        # honest all-not-read manifest plus the budget record.
        evidence_dir.mkdir(parents=True, exist_ok=False)
    budget["elapsed_seconds"] = monotonic() - started
    budget["stop_reason"] = stop_reason
    budget["cells"] = {
        cell["cell_id"]: ("read" if cell["cell_id"] in responses else "not_read")
        for cell in cells
    }
    budget["billing"] = dict(billing_records)
    _write_verified(
        evidence_dir / "budget.json", gr.canonical_json(budget).encode("utf-8"))
    frozen = freeze_training(cells, responses, output_dir=output_dir)
    return {
        "manifest_ref": frozen["manifest_ref"],
        "manifest_status": frozen["manifest_status"],
        "stop_reason": stop_reason,
        "budget": {key: value for key, value in budget.items()},
        "cells": frozen["cells"],
    }


# --------------------------------------------------------------------------
# CLI (describe / verify-freeze / collect; no default collect, no token flags)
# --------------------------------------------------------------------------

def _describe_plan() -> dict:
    gr = grid_research()
    cells = gr.build_cells()
    return {
        "script": "grid_training.py",
        "mode": "describe",
        "schema_version": FREEZE_SCHEMA_VERSION,
        "network": "none in describe mode",
        "cells": [
            {
                "cell_id": cell["cell_id"], "contract": cell["contract"],
                "window": cell["window"], "start_utc": _iso_utc(cell["start_utc"]),
                "end_utc": _iso_utc(cell["end_utc"]),
                "before_time": _cell_context(cell)["cutoff"],
                "symbol": cell["contract"], "limit": TRAINING_LIMIT,
            }
            for cell in cells
        ],
        "commands": {
            "describe": "--describe (offline plan only)",
            "verify_freeze": "--verify-freeze PATH (local verification only)",
            "collect": ("--collect --base-url URL --output-dir PATH "
                        "(requires separate explicit authorization)"),
        },
        "limits": {
            "whoami": 1, "klines_per_cell": 1, "klines_total": 16,
            "provider_requests": PROVIDER_REQUEST_LIMIT,
            "wall_clock_seconds": WALL_CLOCK_LIMIT_SECONDS,
        },
    }


def _default_agent_call(operation: str, **kwargs: Any):
    return quantdinger().agent_call(operation, **kwargs)


def _default_resolve_agent_token(**kwargs: Any):
    return quantdinger().resolve_agent_token(**kwargs)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: describe prints the in-memory plan; verify-freeze only reads
    local files; collect only performs the explicitly authorized Agent reads.
    Mutually exclusive modes, no default collect, no token on the command
    line, no compile/backtest/execute/direct-fetch options exist.
    """
    parser = argparse.ArgumentParser(
        prog="grid_training.py",
        description="Grid training freeze coordination (DESIGN-06-002 V1.4 §11.5/§11.6)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--describe", action="store_true",
                      help="print the in-memory collection plan; no token, no network")
    mode.add_argument("--verify-freeze", metavar="PATH",
                      help="verify an existing freeze manifest locally")
    mode.add_argument("--collect", action="store_true",
                      help="collect via the Agent API (requires separate authorization)")
    parser.add_argument("--base-url", metavar="URL",
                        help="Agent API base URL (collect mode only)")
    parser.add_argument("--output-dir", metavar="PATH",
                        help="freeze output directory (collect mode only)")
    args = parser.parse_args(argv)

    if args.describe:
        print(grid_research().canonical_json(_describe_plan()))
        return 0

    if args.verify_freeze is not None:
        try:
            result = verify_training_freeze(Path(args.verify_freeze))
        except (TrainingVerificationError, ValueError) as exc:
            print(grid_research().canonical_json(
                {"status": "rejected", "reason": str(exc)}))
            return 3
        print(grid_research().canonical_json(result))
        return 0

    if not args.base_url or not args.output_dir:
        parser.error("--collect requires --base-url and --output-dir")
    try:
        result = collect_training(
            base_url=args.base_url, output_dir=Path(args.output_dir),
            agent_call=_default_agent_call,
            resolve_agent_token=_default_resolve_agent_token,
            now_utc=lambda: dt.datetime.now(dt.timezone.utc),
            monotonic=time.monotonic)
    except (TrainingVerificationError, ValueError) as exc:
        print(grid_research().canonical_json(
            {"status": "rejected", "reason": str(exc)}))
        return 3
    print(grid_research().canonical_json(result))
    if result.get("manifest_status") != MANIFEST_STATUS_COMPLETE \
            or result.get("stop_reason"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
