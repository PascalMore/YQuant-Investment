"""BTC5m 历史的日状态 / stream 水位 / 恢复 — 03-018 §6.5 / §7。

``IngestionStore`` 读写 ``03_data_ud_history_ingestion``（日分片 + stream
检查点；无 TTL）。

``plan_days`` —— 每源日预算（保留最近完整日 1 名额；其余最早未完成
优先；gap / pending 到期日去重合并；窗口内尚无记录的日期按缺日纳入）。

``scan_rounds`` —— Predict 新到旧分页枚举（页 / HTTP / 墙钟有界）：检查
页内与跨页 ``startsAt`` 非递增、游标推进、跨页同 ``startsAt`` 重叠报告。

``recheck_pending`` —— 到期 pending 按 ``next_check_at`` 稳定排序回查。

``commit_day`` —— 日 complete（内容 hash 必填），并推进连续水位。

``advance_contiguous`` —— 从 ``ingestion_start`` 逐日推进连续水位，
**不跳 gap**。

``HistoryRunner`` —— 把既有 ``DataPipeline``（extractor / transformer /
validator / loader）接到日级流程：raw → 每批 exact 读回 → 整日完整复核 →
day complete → 连续 stream 水位 / 失败回退。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from .common import (
    DATASET_KLINES,
    DATASET_ROUNDS,
    ERR_CONFLICT,
    ERR_NOT_INITIALIZED,
    INGESTION_COLLECTION,
    SOURCE_KLINES,
    SOURCE_ROUNDS,
    Budget,
    HistoryBudgetError,
    HistoryHTTPError,
    RawArchive,
    day_bounds_us,
    utc_now,
    utc_today,
)

from .extractors import normalize_round_envelope

#: 日状态。
DAY_STATES = ("pending", "running", "complete", "gap", "failed", "conflict")

#: 单日名义 round 槽（300 秒）。
NOMINAL_ROUND_SLOTS = 288

#: 单日秒槽。
SECONDS_PER_DAY = 86400

#: pending / unavailable / conflict 的回查退避（天）。
_RECHECK_BACKOFF_DAYS = (1, 2, 4, 7)


@dataclass
class DayPlan:
    """一个数据源的日计划项。"""

    dataset: str
    utc_date: str
    reason: str
    stored_due: datetime | None = None
    effective_due: datetime | None = None
    retry_policy: str = "missing_day"


_TRANSIENT_ERRORS = {"HTTP_NETWORK_ERROR", "HTTP_SERVER_ERROR", "HTTP_RATE_LIMITED"}
_CONTINUATIONS = {"BUDGET_EXHAUSTED", "SCAN_NOT_CLOSED"}
_WAIT_ERRORS = {"ARCHIVE_NOT_PUBLISHED_OR_MISSING", "SETTLEMENT_PENDING",
                "ROUND_COVERAGE_GAP", "MISSING_SECONDS", "DAY_MANIFEST_MISSING"}


def day_retry_policy(entry: Mapping[str, Any]) -> tuple[datetime | None, str]:
    """Interpret legacy due timestamps without modifying the stored checkpoint."""
    code = entry.get("error_code")
    stored = entry.get("next_retry_at")
    if entry.get("state") == "complete":
        return None, "complete"
    if entry.get("state") == "conflict":
        return stored, "manual_review"
    if code in _TRANSIENT_ERRORS:
        attempted = entry.get("last_attempt_at")
        due = attempted + timedelta(minutes=15) if attempted else stored
        due = min(stored, due) if stored and due else due
        service_due = entry.get("service_retry_at")
        if service_due:
            due = max(due, service_due) if due else service_due
        return due, "transient_15m"
    if code in _CONTINUATIONS:
        return None, "bounded_continuation"
    if code in _WAIT_ERRORS or (not code and entry.get("state") not in ("failed", "conflict")):
        return stored, "wait_24h"
    return stored, "manual_review"


def _failure_due(code: str | None, moment: datetime, service_due: datetime | None = None) -> datetime | None:
    if code in _TRANSIENT_ERRORS:
        due = moment + timedelta(minutes=15)
        return max(due, service_due) if service_due else due
    if code in _WAIT_ERRORS:
        return moment + timedelta(days=1)
    return None


@dataclass
class DayResult:
    """一个数据源的一日处理结果。"""

    dataset: str
    utc_date: str
    state: str
    counts: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    content_sha256: str | None = None
    raw_manifest_ref: str | None = None
    gap_manifest_ref: str | None = None


@dataclass
class RoundScanResult:
    """Predict 分页枚举结果。"""

    records: list[dict[str, Any]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    next_after: str | None = None
    closed: bool = False
    error_code: str | None = None
    overlap_count: int = 0
    raw_manifest_ref: str | None = None


class IngestionStore:
    """摄入检查点存储（``03_data_ud_history_ingestion``）。"""

    def __init__(self, mongo_db: Any) -> None:
        self._db = mongo_db
        self._collection = mongo_db[INGESTION_COLLECTION]

    @property
    def db(self) -> Any:
        """底层数据库句柄（供 runner 写历史集合）。"""
        return self._db

    # -- 键 --------------------------------------------------------------
    @staticmethod
    def day_id(dataset: str, utc_date: str) -> str:
        """返回日分片 ``_id``。"""
        return f"day/{dataset}/{utc_date}"

    @staticmethod
    def stream_id(dataset: str) -> str:
        """返回 stream ``_id``。"""
        return f"stream/{dataset}"

    # -- 读 --------------------------------------------------------------
    def get_day(self, dataset: str, utc_date: str) -> dict[str, Any] | None:
        """读取日分片。"""
        return self._collection.find_one({"_id": self.day_id(dataset, utc_date)})

    def get_stream(self, dataset: str) -> dict[str, Any] | None:
        """读取 stream 检查点。"""
        return self._collection.find_one({"_id": self.stream_id(dataset)})

    def list_days(self, dataset: str) -> list[dict[str, Any]]:
        """列出该 dataset 的全部日分片（按日期排序）。"""
        return list(
            self._collection.find(
                {"kind": "day", "dataset": dataset}
            ).sort("utc_date", 1)
        )

    # -- 写 --------------------------------------------------------------
    def write_day(
        self,
        dataset: str,
        utc_date: str,
        *,
        state: str,
        counts: Mapping[str, Any] | None = None,
        content_sha256: str | None = None,
        raw_manifest_ref: str | None = None,
        gap_manifest_ref: str | None = None,
        error_code: str | None = None,
        last_attempt_at: datetime | None = None,
        next_retry_at: datetime | None = None,
        service_retry_at: datetime | None = None,
    ) -> None:
        """写入日分片状态（``complete`` 时 content hash 必填）。"""
        if state not in DAY_STATES:
            raise ValueError(f"unknown day state {state!r}")
        if state == "complete" and not content_sha256:
            raise ValueError("complete day requires content_sha256")
        start_us, end_us = day_bounds_us(utc_date)
        now = last_attempt_at or utc_now()
        document = {
            "_id": self.day_id(dataset, utc_date),
            "kind": "day",
            "dataset": dataset,
            "utc_date": utc_date,
            "schema_version": 1,
            "window_start_us": start_us,
            "window_end_us": end_us,
            "state": state,
            "counts": dict(counts or {}),
            "gap_manifest_ref": gap_manifest_ref,
            "raw_manifest_ref": raw_manifest_ref,
            "content_sha256": content_sha256,
            "last_attempt_at": now,
            "next_retry_at": next_retry_at,
            "service_retry_at": service_retry_at,
            "error_code": error_code,
            "updated_at": now,
        }
        self._collection.replace_one({"_id": document["_id"]}, document, upsert=True)

    def init_stream(
        self,
        dataset: str,
        *,
        ingestion_start_us: int,
        enumerated_through_us: int | None = None,
        complete_through_us: int | None = None,
    ) -> None:
        """初始化 stream 检查点（显式锚点，不从数据库最大时间推导）。"""
        existing = self.get_stream(dataset)
        if existing is not None:
            current = existing.get("ingestion_start_us")
            if current != ingestion_start_us:
                raise HistoryBudgetError(
                    ERR_CONFLICT,
                    "stream anchor conflicts with the existing initialisation",
                )
            return
        now = utc_now()
        document = {
            "_id": self.stream_id(dataset),
            "kind": "stream",
            "dataset": dataset,
            "utc_date": "",
            "schema_version": 1,
            "ingestion_start_us": ingestion_start_us,
            "enumerated_through_us": enumerated_through_us,
            "complete_through_us": complete_through_us,
            "scan_cursor": None,
            "scan_upper_us": None,
            "scan_lower_us": None,
            "updated_at": now,
        }
        self._collection.replace_one({"_id": document["_id"]}, document, upsert=True)

    def write_stream(self, dataset: str, fields: Mapping[str, Any]) -> None:
        """更新 stream 检查点（只更新给定字段 + ``updated_at``）。"""
        update = dict(fields)
        update["updated_at"] = utc_now()
        self._collection.update_one(
            {"_id": self.stream_id(dataset)}, {"$set": update}, upsert=True
        )


# ---------------------------------------------------------------------------
# 计划
# ---------------------------------------------------------------------------


def ensure_history_indexes(db: Any) -> None:
    """Initialize/verify fixed history indexes, only from explicit apply; never drop."""
    from pymongo import timeout
    from .common import KLINES_COLLECTION, ROUNDS_COLLECTION

    if db.name != "yquant-data":
        raise HistoryHTTPError("HISTORY_INDEX_NAMESPACE")
    required = {
        ROUNDS_COLLECTION: [
            ("uniq_predict_round", [("source", 1), ("series_slug", 1), ("round_id", 1)], True),
            ("predict_round_range", [("source", 1), ("series_slug", 1), ("starts_at_us", 1), ("round_id", 1)], False),
            ("predict_round_pending", [("source", 1), ("series_slug", 1), ("settlement_state", 1),
                                       ("next_check_at", 1), ("starts_at_us", 1), ("round_id", 1)], False),
        ],
        KLINES_COLLECTION: [
            ("uniq_spot_kline_1s", [("source", 1), ("market_type", 1), ("symbol", 1),
                                    ("interval", 1), ("open_time_us", 1)], True),
        ],
        INGESTION_COLLECTION: [
            ("uniq_history_progress", [("kind", 1), ("dataset", 1), ("utc_date", 1)], True),
        ],
    }

    def missing_indexes():
        missing = []
        for collection, specs in required.items():
            indexes = db[collection].index_information()
            if any("expireAfterSeconds" in spec for spec in indexes.values()):
                raise HistoryHTTPError("HISTORY_INDEX_INCOMPATIBLE")
            for name, keys, unique in specs:
                matches = [spec for index_name, spec in indexes.items()
                           if index_name == name or list(spec["key"]) == keys]
                for spec in matches:
                    if (list(spec["key"]) != keys or bool(spec.get("unique")) != unique
                            or any(spec.get(option) for option in
                                   ("sparse", "partialFilterExpression", "collation", "hidden"))):
                        raise HistoryHTTPError("HISTORY_INDEX_INCOMPATIBLE")
                if not matches:
                    missing.append((collection, name, keys, unique))
        return missing

    try:
        with timeout(10):
            missing = missing_indexes()  # Reject incompatible namespaces before any DDL.
            for collection, name, keys, unique in missing:
                db[collection].create_index(keys, name=name, unique=unique)
            if missing_indexes():
                raise HistoryHTTPError("HISTORY_INDEX_READBACK_MISMATCH")
    except HistoryHTTPError:
        raise
    except Exception:
        raise HistoryHTTPError("HISTORY_INDEX_INITIALIZATION_FAILED") from None


def plan_days(
    store: IngestionStore,
    dataset: str,
    *,
    cutoff_utc_date: str,
    max_days: int,
    start_utc_date: str | None = None,
    end_utc_date: str | None = None,
    retry_dates: Sequence[str] = (),
) -> list[DayPlan]:
    """规划本轮要处理的日（有界、公平、gap 优先）。

    规则（Design §7.2）：

    * 先保留最近完整日 1 个名额。
    * 其余名额按**最早未完成日期**到 cutoff，并合并 gap / pending 到期日。
    * 只有 1 日预算且同时有旧 backlog 时，本次处理最近日并保留旧 backlog。
    * ``start_utc_date`` / ``end_utc_date`` 给出目标窗口时，窗口内**尚无
      记录**的日期也按缺日进入计划（不回填不推进水位）。

    Args:
        store: :class:`IngestionStore`。
        dataset: 数据集标识。
        cutoff_utc_date: 本次 cutoff UTC 日（不含）。
        max_days: 日名额。
        start_utc_date: 目标窗口下界（含）。
        end_utc_date: 目标窗口上界（不含）。

    Returns:
        :class:`DayPlan` 列表（长度 ≤ ``max_days``）。
    """
    days = store.list_days(dataset)
    state_by_date = {
        str(entry.get("utc_date")): entry
        for entry in days
        if entry.get("utc_date")
    }
    moment = utc_now()

    def due(entry):
        retry, policy = day_retry_policy(entry)
        return policy not in ("complete", "manual_review") and (retry is None or retry <= moment)

    target_end = min(cutoff_utc_date, end_utc_date or cutoff_utc_date)
    explicit = sorted(set(retry_dates))
    for day in explicit:
        if (day >= target_end or (start_utc_date and day < start_utc_date)
                or (state_by_date.get(day) or {}).get("state") == "complete"):
            raise ValueError("RETRY_DAY_OUTSIDE_WINDOW_OR_COMPLETE")
    if len(explicit) > max_days:
        raise ValueError("RETRY_DAYS_EXCEED_DAY_BUDGET")
    incomplete = [utc_date for utc_date, entry in state_by_date.items()
                  if utc_date < target_end and due(entry)]
    if start_utc_date:
        incomplete = [d for d in incomplete if d >= start_utc_date]
    if end_utc_date:
        incomplete = [d for d in incomplete if d < end_utc_date]

    def item(day, reason):
        entry = state_by_date.get(day) or {}
        effective, policy = day_retry_policy(entry)
        return DayPlan(dataset, day, reason, entry.get("next_retry_at"), effective, policy)

    plans = [item(day, "operator_retry") for day in explicit]
    seen: set[str] = set(explicit)

    # 显式窗口不得把实际 cutoff 后的日子带入本次目标。
    target_end = min(cutoff_utc_date, end_utc_date or cutoff_utc_date)
    # 最近完整日保留 1 名额（已完成则释放给最老未完成）。
    recent = _previous_day(target_end)
    recent_entry = state_by_date.get(recent)
    # A recently attempted recent day must not monopolize a one-day budget.
    if ((recent_entry is None or due(recent_entry))
            and (not start_utc_date or recent >= start_utc_date)
            and (max_days > 1 or not (recent_entry or {}).get("last_attempt_at"))):
        if len(plans) < max_days and recent not in seen:
            plans.append(item(recent, "recent_complete_day"))
            seen.add(recent)

    unseen = [day for day in _window_dates(start_utc_date, target_end)
              if day not in state_by_date]
    # Never-attempted days precede retries; attempted days rotate by actual last attempt.
    candidates = sorted(set(incomplete + unseen), key=lambda day: (
        (state_by_date.get(day) or {}).get("last_attempt_at") or datetime.min, day,
    ))
    for utc_date in candidates:
        if len(plans) >= max_days:
            break
        if utc_date in seen:
            continue
        entry = state_by_date.get(utc_date) or {}
        reason = {
            "gap": "known_gap",
            "failed": "failed_retry",
            "conflict": "conflict_review",
            "running": "interrupted_retry",
            "pending": "pending_day",
        }.get(str(entry.get("state")), "missing_day")
        plans.append(item(utc_date, reason))
        seen.add(utc_date)

    return plans[:max_days]


def _window_dates(
    start_utc_date: str | None, end_utc_date: str | None
) -> list[str]:
    """返回窗口内的 UTC 日序列（升序）。"""
    if not start_utc_date or not end_utc_date:
        return []
    start = datetime.strptime(start_utc_date, "%Y-%m-%d")
    end = datetime.strptime(end_utc_date, "%Y-%m-%d")
    out: list[str] = []
    cursor = start
    while cursor < end:
        out.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return out


def _previous_day(utc_date: str) -> str:
    day = datetime.strptime(utc_date, "%Y-%m-%d")
    return (day - timedelta(days=1)).strftime("%Y-%m-%d")


def advance_contiguous(
    store: IngestionStore, dataset: str, *, ingestion_start_us: int
) -> int | None:
    """从 ``ingestion_start`` 逐日推进连续 complete 水位（不跳 gap）。

    Returns:
        ``complete_through_us``（exclusive 边界）；无任何 complete 日时
        返回 ``None``。
    """
    days = store.list_days(dataset)
    by_date = {entry.get("utc_date"): entry for entry in days}
    boundary: int | None = None
    cursor_us = ingestion_start_us
    while True:
        utc_date = _date_from_us(cursor_us)
        entry = by_date.get(utc_date)
        if entry is None or entry.get("state") != "complete":
            break
        boundary = day_bounds_us(utc_date)[1]
        cursor_us = boundary
    return boundary


def _date_from_us(value: int) -> str:
    return datetime.utcfromtimestamp(value / 1_000_000).strftime("%Y-%m-%d")


def combined_complete_through(
    stores: Mapping[str, IngestionStore],
    *,
    ingestion_start_us: int,
) -> int | None:
    """返回两源联合完整水位（取最小；任一为 None 则仍为 None）。"""
    values = [
        advance_contiguous(store, dataset, ingestion_start_us=ingestion_start_us)
        for dataset, store in stores.items()
    ]
    if any(value is None for value in values):
        return None
    return min(values)  # type: ignore[type-var]


# ---------------------------------------------------------------------------
# Predict 分页枚举
# ---------------------------------------------------------------------------


def read_round_page(archive: RawArchive, page: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Replay official page/status bytes with exact hashes, never HTTP or synthesized raw."""
    import json
    from decimal import Decimal
    from pathlib import Path

    def read(reference):
        raw = archive.read_bytes(reference["raw_ref"])
        digest = hashlib.sha256(raw).hexdigest()
        if digest != reference["raw_sha256"] or Path(reference["raw_ref"]).stem != digest:
            raise HistoryHTTPError("RAW_REFERENCE_MISMATCH")
        return json.loads(raw.decode(), parse_float=Decimal)

    document = read(page)
    if (document.get("success") is not True or not isinstance(document.get("data"), list)
            or document.get("cursor") != page.get("cursor")
            or len(document["data"]) != page["count"]):
        raise HistoryHTTPError("PAGE_MANIFEST_MISMATCH")
    logs = {}
    references = page.get("status_refs", [])
    for reference in references:
        status = read(reference)
        if status.get("success") is not True or not isinstance(status.get("data"), list):
            raise HistoryHTTPError("STATUS_MANIFEST_MISMATCH")
        for entry in status["data"]:
            market_id = str(entry.get("marketId"))
            if market_id in logs:
                raise HistoryHTTPError("STATUS_MANIFEST_MISMATCH")
            logs[market_id] = entry.get("logs", [])
    return [dict(normalize_round_envelope(record), _status_logs=logs, _status_raw_refs=references,
                 _raw_ref=page["raw_ref"], _raw_sha256=page["raw_sha256"])
            for record in document["data"]]


def reconcile_round_raw(envelope: Mapping[str, Any], current: Mapping[str, Any] | None,
                        archive: RawArchive) -> dict[str, Any]:
    """Replay an exact predecessor only after proving the latest legal official fill.

    This does not grant the loader downgrade/overwrite permission. A different
    enumeration or terminal fact still reaches conflict, never a blind skip.
    """
    import json
    from decimal import Decimal
    from pathlib import Path
    from .loader import HistoryBatchLoader, _record_hash
    from .transforms import PredictRoundTransformer

    transformer = PredictRoundTransformer()
    original = transformer.transform_one(envelope)
    digest = _record_hash(original, DATASET_ROUNDS)
    if current is None or digest == _record_hash(current, DATASET_ROUNDS):
        return dict(envelope)
    reference = {"raw_ref": envelope.get("_raw_ref"),
                 "raw_sha256": envelope.get("_raw_sha256"), "record_sha256": digest}
    if reference not in current.get("raw_history", []):
        return dict(envelope)  # A genuinely new non-equal candidate must conflict.
    if (current.get("record_sha256") != _record_hash(current, DATASET_ROUNDS)
            or not HistoryBatchLoader._may_update(original, current, DATASET_ROUNDS)):
        raise HistoryHTTPError("RAW_FILL_CONFLICT")

    def read(ref):
        body = archive.read_bytes(ref["raw_ref"])
        if (hashlib.sha256(body).hexdigest() != ref["raw_sha256"]
                or Path(ref["raw_ref"]).stem != ref["raw_sha256"]):
            raise HistoryHTTPError("RAW_REFERENCE_MISMATCH")
        document = json.loads(body, parse_float=Decimal)
        if document.get("success") is not True:
            raise HistoryHTTPError("RAW_FILL_CONFLICT")
        return document["data"]

    # The accepted latest raw may be an identity response or a later enumeration.
    data = read(current)
    if isinstance(data, list):
        records = [normalize_round_envelope(row) for row in data]
        matches = [row for row in records if str(row["category"].get("id")) == original["round_id"]]
        if len(matches) != 1:
            raise HistoryHTTPError("RAW_FILL_CONFLICT")
        latest = dict(matches[0])
    elif isinstance(data, dict):
        latest = normalize_round_envelope(data)
    else:
        raise HistoryHTTPError("RAW_FILL_CONFLICT")
    evidence = current.get("resolution_evidence") or {}
    # Nonterminal category/price fills need no final-transition evidence. Replay
    # their actual category raw and require the same exact business hash below;
    # only a resolved fact (or existing evidence) requires the final status raw.
    if current.get("settlement_state") == "resolved" or evidence:
        logs = read(evidence) if evidence.get("raw_ref") else []
        market_id = original["market_id"]
        matches = [entry for entry in logs if str(entry.get("marketId")) == market_id] if isinstance(logs, list) else []
        if len(matches) != 1:
            raise HistoryHTTPError("RAW_FILL_CONFLICT")
        latest.update(_status_logs={market_id: matches[0].get("logs", [])},
                      _status_raw_refs=[{"raw_ref": evidence["raw_ref"], "raw_sha256": evidence["raw_sha256"]}])
    latest_record = transformer.transform_one(latest)
    if (_record_hash(latest_record, DATASET_ROUNDS) != current["record_sha256"]
            or any(latest_record.get(key) != original.get(key) for key in
                   ("source", "series_slug", "round_id", "market_id", "condition_id",
                    "starts_at_us", "ends_at_us"))):
        raise HistoryHTTPError("RAW_FILL_CONFLICT")
    return latest


async def scan_rounds(
    extractor: Any,
    *,
    budget: Budget,
    lower_us: int,
    upper_us: int,
    after: str | None = None,
    api_key: str | None = None,
    max_pages: int = 200,
    resume_state: Mapping[str, Any] | None = None,
    on_page: Any = None,
    collect_records: bool = True,
) -> RoundScanResult:
    """按新到旧分页枚举 Predict rounds（有界）。

    停止条件：游标推进且页内最后一条 ``startsAt`` 已越过下界 ``lower_us``
    （闭合枚举）；200 空页、重复游标或排序反向都不闭合。

    Args:
        extractor: :class:`~btc5m_history.extractors.PredictRoundExtractor`。
        budget: 请求 / 墙钟预算。
        lower_us: 目标下界（inclusive，UTC 微秒）。
        upper_us: 目标上界（exclusive，UTC 微秒）。
        after: 起始不透明游标。
        api_key: 可选 API key。
        max_pages: 单轮最多页数。

    Returns:
        :class:`RoundScanResult`。
    """
    from .transforms import datetime_to_us, parse_utc_datetime

    seed = dict(resume_state or {})
    if seed and (seed.get("lower_us") != lower_us or seed.get("upper_us") != upper_us
                 or seed.get("next_after") != after):
        raise HistoryHTTPError("SCAN_RESUME_MISMATCH")
    result = RoundScanResult(next_after=after, pages=list(seed.get("pages", [])))
    cursor = after
    seen_cursors: set[str] = set(seed.get("seen_cursors", []))
    if cursor is not None:
        seen_cursors.add(cursor)
    last_starts_us = seed.get("last_starts_us")
    covered_upper = seed.get("covered_upper", False)
    seen_records: dict[str, str] = dict(seed.get("seen_records", {}))

    for _ in range(max_pages):
        if budget.exhausted():
            result.error_code = "BUDGET_EXHAUSTED"
            break
        page = await extractor.extract_page(
            _predict_source(after=cursor), budget=budget, api_key=api_key
        )
        records = list(page.records)
        next_after = page.next_after
        starts_list = [
            datetime_to_us(parse_utc_datetime((record.get("category") or {}).get("startsAt")))
            for record in records
        ]
        starts_list = [value for value in starts_list if value is not None]
        if len(starts_list) != len(records) or any(
            later > earlier for earlier, later in zip(starts_list, starts_list[1:])
        ):
            result.error_code = "ORDER_REVERSAL"
            break
        if starts_list and max(starts_list) >= upper_us:
            covered_upper = True
        from skills.data.unified_data.history_types import canonical_json

        for record in records:
            key = str((record.get("category") or {}).get("id"))
            payload = hashlib.sha256(canonical_json(record).encode()).hexdigest()
            if key in seen_records and seen_records[key] != payload:
                result.error_code = "DUPLICATE_CONFLICT"
                break
            seen_records[key] = payload
        if result.error_code:
            break

        if last_starts_us is not None and starts_list:
            if max(starts_list) > last_starts_us:
                result.error_code = "ORDER_REVERSAL"
                break
        if last_starts_us is not None and starts_list:
            overlap = sum(1 for value in starts_list if value >= last_starts_us)
            if overlap:
                result.overlap_count += overlap

        if collect_records:
            result.records.extend(
                dict(record, _raw_ref=page.raw_ref, _raw_sha256=page.raw_sha256)
                for record in records
            )
        result.pages.append(
            {
                "after": cursor,
                "cursor": next_after,
                "count": len(records),
                "first_starts_at_us": starts_list[0] if starts_list else None,
                "last_starts_at_us": starts_list[-1] if starts_list else None,
                "raw_ref": page.raw_ref,
                "raw_sha256": page.raw_sha256,
                "status_refs": records[0].get("_status_raw_refs", []) if records else [],
            }
        )

        if not records:
            # 空页不能证明区间完整（不是闭合证据）。
            result.error_code = result.error_code or "EMPTY_PAGE_NOT_CLOSED"
            break
        if starts_list:
            last_starts_us = min(last_starts_us, min(starts_list)) if last_starts_us is not None else min(starts_list)
        if next_after and next_after in seen_cursors:
            result.error_code = "REPEATED_CURSOR"
            break
        if next_after:
            seen_cursors.add(next_after)
        closed = covered_upper and (not next_after or (
            last_starts_us is not None and last_starts_us < lower_us
        ))
        if on_page is not None:
            await on_page(records, result.pages[-1], {
                "lower_us": lower_us, "upper_us": upper_us, "next_after": next_after,
                "last_starts_us": last_starts_us, "covered_upper": covered_upper,
                "seen_cursors": sorted(seen_cursors), "seen_records": dict(seen_records),
                "pages": list(result.pages), "closed": closed,
            })
        if not next_after:
            # 自然终点：枚举闭合。
            result.closed = covered_upper
            result.error_code = None if covered_upper else "UPPER_BOUND_NOT_COVERED"
            result.next_after = None
            break
        result.next_after = next_after
        cursor = next_after
        if last_starts_us is not None and last_starts_us < lower_us:
            result.closed = covered_upper
            result.error_code = None if covered_upper else "UPPER_BOUND_NOT_COVERED"
            break
    return result


def _predict_source(after: str | None) -> Any:
    from .extractors import PredictPageSource

    return PredictPageSource(after=after)


# ---------------------------------------------------------------------------
# pending 回查
# ---------------------------------------------------------------------------


async def recheck_pending(
    db: Any, *, budget: Budget, archive: RawArchive, api_key: str | None = None,
    limit: int = 100, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Fair global due queue; real identity HTTP/ETVL precedes advancing attempted items."""
    from pymongo import timeout
    from .common import ROUNDS_COLLECTION
    from .extractors import (PredictRoundExtractor, BufferedRoundExtractor, BufferedRoundSource)
    from .loader import HistoryBatchLoader
    from .transforms import PredictRoundTransformer
    from .validators import HistoryValidator
    from ..pipeline import DataPipeline

    if limit <= 0:
        return []
    moment = now or utc_now()
    collection = db[ROUNDS_COLLECTION]
    with timeout(10):
        rows = list(collection.find({
            "source": SOURCE_ROUNDS, "series_slug": "btc-updown-5m",
            "settlement_state": {"$in": ["pending", "unavailable", "conflict"]},
            "next_check_at": {"$lte": moment},
        }).sort([("next_check_at", 1), ("starts_at_us", 1), ("round_id", 1)])
            .limit(min(100, max(0, limit))).max_time_ms(10000))
    attempted = []
    extractor = PredictRoundExtractor(archive)
    loader = HistoryBatchLoader(db, DATASET_ROUNDS)
    pipeline = DataPipeline(BufferedRoundExtractor(), PredictRoundTransformer(),
                            HistoryValidator(DATASET_ROUNDS), loader)
    for row in rows:
        if budget.exhausted():
            break
        before = budget.requests_used
        try:
            page = await extractor.extract_pending(row, budget=budget, api_key=api_key)
            # Queue selection/backoff time cannot establish visibility of later
            # category + status responses. Sample each completed pair separately.
            loader.set_context(raw_ref=page.raw_ref, raw_sha256=page.raw_sha256, fetched_at=utc_now())
            result = await pipeline.run(BufferedRoundSource(
                records=page.records, raw_ref=page.raw_ref, raw_sha256=page.raw_sha256,
            ), budget=budget)
            if result.errors:
                raise HistoryHTTPError("PENDING_ETVL_FAILED")
            attempted.append({"round_id": row["round_id"], "starts_at_us": row["starts_at_us"]})
        finally:
            if budget.requests_used > before:
                with timeout(10):
                    collection.update_one({"source": row["source"],
                                           "series_slug": row["series_slug"],
                                           "round_id": row["round_id"]},
                                          {"$inc": {"recheck_attempts": 1},
                                           "$set": {"next_check_at": _next_check_at(
                                               int(row.get("recheck_attempts", 0)) + 1, moment)}})
    for utc_date in sorted({_date_from_us(row["starts_at_us"]) for row in attempted}):
        store = IngestionStore(db)
        day = store.get_day(DATASET_ROUNDS, utc_date)
        if day and day.get("raw_manifest_ref"):
            import json
            from pathlib import Path

            reference = day["raw_manifest_ref"]
            body = archive.read_bytes(reference)
            if hashlib.sha256(body).hexdigest() != Path(reference).stem:
                raise HistoryHTTPError("SCAN_MANIFEST_CHANGED")
            manifest = json.loads(body)
            begin, stop = day_bounds_us(utc_date)
            if (manifest.get("kind") == "predict-scan" and manifest.get("closed")
                    and manifest["lower_us"] <= begin < stop <= manifest["upper_us"]):
                history = HistoryRunner(store, db, budget=budget, archive=archive)
                review = history._review_round_day(utc_date, begin, stop)
                history._finish_round_day(
                    utc_date, counts=dict(day.get("counts", {}), **review), review=review,
                    scan=RoundScanResult(closed=True, raw_manifest_ref=reference), errors=[],
                )
    return attempted


def _next_check_at(attempts: int, moment: datetime) -> datetime:
    """Wait 1/2/4/7 days after the persisted number of actual ID rechecks."""
    return moment + timedelta(days=_RECHECK_BACKOFF_DAYS[min(max(attempts, 1), 4) - 1])


# ---------------------------------------------------------------------------
# 日提交
# ---------------------------------------------------------------------------


def commit_day(
    store: IngestionStore,
    dataset: str,
    utc_date: str,
    *,
    counts: Mapping[str, Any],
    content_sha256: str,
    raw_manifest_ref: str | None = None,
    gap_manifest_ref: str | None = None,
) -> DayResult:
    """提交一日 complete（内容 hash 必填）并推进连续水位。"""
    store.write_day(
        dataset,
        utc_date,
        state="complete",
        counts=counts,
        content_sha256=content_sha256,
        raw_manifest_ref=raw_manifest_ref,
        gap_manifest_ref=gap_manifest_ref,
    )
    return DayResult(
        dataset=dataset,
        utc_date=utc_date,
        state="complete",
        counts=dict(counts),
        content_sha256=content_sha256,
        raw_manifest_ref=raw_manifest_ref,
        gap_manifest_ref=gap_manifest_ref,
    )


# ---------------------------------------------------------------------------
# HistoryRunner
# ---------------------------------------------------------------------------


class HistoryRunner:
    """日级摄入编排（真实走既有 ``DataPipeline``）。

    Args:
        store: :class:`IngestionStore`。
        mongo_db: UD 目标库句柄。
        budget: 请求 / 墙钟预算。
        archive: raw 归档。
        api_key: 可选 Predict API key。
    """

    def __init__(
        self,
        store: IngestionStore,
        mongo_db: Any,
        *,
        budget: Budget,
        archive: RawArchive | None = None,
        api_key: str | None = None,
    ) -> None:
        self._store = store
        self._db = mongo_db
        self._budget = budget
        self._archive = archive or RawArchive()
        self._api_key = api_key

    # -- 入口 ------------------------------------------------------------
    async def run_day(self, dataset: str, utc_date: str) -> DayResult:
        """执行一个数据源的一天。

        Returns:
            :class:`DayResult`。
        """
        if dataset == DATASET_KLINES:
            return await self.run_kline_day(utc_date)
        if dataset == DATASET_ROUNDS:
            return await self.run_round_day(utc_date)
        raise ValueError(f"unknown dataset {dataset!r}")

    # -- Binance ---------------------------------------------------------
    async def run_kline_day(self, utc_date: str) -> DayResult:
        """Binance 日归档 → chunk 流 → 管道 → 整日复核 → commit。"""
        from .extractors import BinanceDaySource, BinanceKlineExtractor
        from .loader import HistoryBatchLoader
        from .transforms import BinanceKlineTransformer
        from .validators import HistoryValidator
        from ..pipeline import DataPipeline

        start_us, end_us = day_bounds_us(utc_date)
        extractor = BinanceKlineExtractor(self._archive)
        loader = HistoryBatchLoader(self._db, DATASET_KLINES)
        pipeline = DataPipeline(
            extractor=extractor,
            transformer=BinanceKlineTransformer(),
            validator=HistoryValidator(DATASET_KLINES),
            loader=loader,
        )

        try:
            prepared = await extractor.prepare_day(
                BinanceDaySource(utc_date=utc_date), budget=self._budget
            )
        except HistoryHTTPError as exc:
            return self._fail_day(DATASET_KLINES, utc_date, exc.code,
                                  service_retry_at=exc.retry_at)
        except HistoryBudgetError as exc:
            return self._fail_day(DATASET_KLINES, utc_date, str(exc))

        raw_ref = prepared["raw_ref"]
        manifest_ref = prepared["manifest_ref"]
        raw_sha = prepared["raw_sha256"]
        total_rows = int(prepared["row_count"])
        chunk_size = max(1, min(self._budget.chunk_size, 5000))
        offset = 0
        inserted = updated = skipped = 0
        errors: list[str] = []

        while offset < total_rows:
            if self._budget.exhausted():
                errors.append("BUDGET_EXHAUSTED")
                break
            loader.set_context(
                raw_ref=raw_ref, raw_sha256=raw_sha, fetched_at=utc_now()
            )
            try:
                outcome = await pipeline.run(
                    _zip_chunk_source(raw_ref, offset, chunk_size),
                    budget=self._budget,
                )
            except Exception as exc:  # noqa: BLE001 — 批级失败 → 日不 complete
                errors.append(type(exc).__name__)
                break
            inserted += outcome.inserted
            updated += outcome.updated
            skipped += outcome.skipped
            errors.extend(str(item.get("reason")) for item in outcome.errors)
            if not (outcome.inserted or outcome.updated or outcome.skipped):
                # 空批 / 无进展 → 有界退出，不假装推进。
                break
            offset += chunk_size

        review = self._review_kline_day(utc_date, start_us, end_us)
        counts = {
            "csv_rows": total_rows,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "valid_unique_seconds": review["valid_unique_seconds"],
            "expected_seconds": SECONDS_PER_DAY,
            "missing_seconds": review["missing_seconds"],
            "coverage_ratio": review["coverage_ratio"],
            "zip_bytes": prepared.get("zip_bytes"),
            "checksum": prepared.get("checksum"),
            "batches": (offset + chunk_size - 1) // chunk_size,
        }
        if errors:
            counts["errors"] = errors[:5]
            return self._fail_day(DATASET_KLINES, utc_date, errors[0], counts=counts)
        if review["missing_seconds"] > 0:
            store = self._store
            store.write_day(
                DATASET_KLINES,
                utc_date,
                state="gap",
                counts=counts,
                gap_manifest_ref=review["gap_manifest_ref"],
                raw_manifest_ref=manifest_ref,
                error_code="MISSING_SECONDS",
                next_retry_at=utc_now() + timedelta(days=1),
            )
            return DayResult(
                dataset=DATASET_KLINES,
                utc_date=utc_date,
                state="gap",
                counts=counts,
                error_code="MISSING_SECONDS",
                raw_manifest_ref=manifest_ref,
                gap_manifest_ref=review["gap_manifest_ref"],
            )

        content_sha = review["content_sha256"]
        commit_day(
            self._store,
            DATASET_KLINES,
            utc_date,
            counts=counts,
            content_sha256=content_sha,
            raw_manifest_ref=manifest_ref,
            gap_manifest_ref=review["gap_manifest_ref"],
        )
        self._advance_stream(DATASET_KLINES)
        return DayResult(
            dataset=DATASET_KLINES,
            utc_date=utc_date,
            state="complete",
            counts=counts,
            content_sha256=content_sha,
            raw_manifest_ref=manifest_ref,
            gap_manifest_ref=review["gap_manifest_ref"],
        )

    def _review_kline_day(
        self, utc_date: str, start_us: int, end_us: int
    ) -> dict[str, Any]:
        """整日重读完整 key 集合并复核覆盖 / 内容 digest。"""
        from .common import KLINES_COLLECTION

        collection = self._db[KLINES_COLLECTION]
        docs = list(
            collection.find(
                {
                    "source": SOURCE_KLINES,
                    "market_type": "spot",
                    "symbol": "BTCUSDT",
                    "interval": "1s",
                    "open_time_us": {"$gte": start_us, "$lt": end_us},
                },
                {"_id": 0},
            )
        )
        opens = sorted({int(doc.get("open_time_us") or 0) for doc in docs})
        if len(opens) != len(docs) or any(
            value < start_us or value >= end_us or (value - start_us) % 1_000_000
            for value in opens
        ):
            raise HistoryHTTPError("READBACK_MISMATCH")
        valid = len(opens)
        missing = SECONDS_PER_DAY - valid
        digest = _digest_of(opens, docs)
        gap_ref = None
        if missing > 0:
            gap_ref = _write_gap_manifest(
                self._archive, utc_date, "binance-vision", opens, start_us, end_us
            )
        # Day counts enter the reader's exact canonical manifest too. Keep the
        # existing six-decimal statistic in BSON Decimal128, never binary float.
        from decimal import Decimal, ROUND_HALF_EVEN, localcontext
        from bson import Decimal128

        with localcontext() as context:
            context.prec = 34
            ratio = (Decimal(valid) / Decimal(SECONDS_PER_DAY)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_EVEN,
            )
        return {
            "valid_unique_seconds": valid,
            "missing_seconds": missing,
            "coverage_ratio": Decimal128(ratio),
            "content_sha256": digest,
            "gap_manifest_ref": gap_ref,
            "batches": 1,
        }

    # -- Predict ---------------------------------------------------------
    async def run_round_days(
        self, utc_dates: Sequence[str], *, restart_scan: bool = False,
    ) -> list[DayResult]:
        """一次抓取覆盖多日，逐日切片 → 管道 → 日复核 → commit。

        新到旧 API 不能服务端按日跳页，因此同一轮抓取一次，按 UTC 日切片
        后逐日入库；只有**闭合**枚举才允许提交对应日。续扫优先返回冻结
        窗口的实际处理日（占用本次日预算），而不是将新计划日算作已扫描。
        """
        from .extractors import (
            BufferedRoundExtractor,
            BufferedRoundSource,
            PredictRoundExtractor,
        )
        from .loader import HistoryBatchLoader
        from .transforms import PredictRoundTransformer
        from .validators import HistoryValidator
        from ..pipeline import DataPipeline

        import json
        from pathlib import Path

        if not utc_dates:
            if not restart_scan:
                return []
            active_stream = self._store.get_stream(DATASET_ROUNDS) or {}
            if active_stream.get("scan_lower_us") is None:
                raise HistoryHTTPError("NO_ACTIVE_SCAN")
            utc_dates = [_date_from_us(active_stream["scan_lower_us"])]
        day_limit = min(len(set(utc_dates)), self._budget.max_days_per_source)
        requested = sorted(set(utc_dates))[:day_limit]
        requested_lower = day_bounds_us(requested[0])[0]
        requested_upper = day_bounds_us(requested[-1])[1]
        stream = self._store.get_stream(DATASET_ROUNDS) or {}
        cursor = stream.get("scan_cursor")
        manifest_ref = stream.get("scan_manifest_ref")
        active = bool(cursor or manifest_ref)
        lower_us = int(stream["scan_lower_us"]) if active else requested_lower
        upper_us = int(stream["scan_upper_us"]) if active else requested_upper
        seed = None
        days = self._store.list_days(DATASET_ROUNDS) if active else []
        # A direct reference is authoritative: damage must not fall back to an
        # older day manifest. Legacy streams may still recover from day refs.
        references = [manifest_ref] if manifest_ref else [
            day.get("raw_manifest_ref") for day in days if day.get("raw_manifest_ref")
        ]
        for reference in dict.fromkeys(references):
            if not isinstance(reference, str):
                raise HistoryHTTPError("SCAN_RESUME_MISMATCH")
            raw = self._archive.read_bytes(reference)
            if hashlib.sha256(raw).hexdigest() != Path(reference).stem:
                raise HistoryHTTPError("SCAN_MANIFEST_CHANGED")
            candidate = json.loads(raw)
            if (candidate.get("kind") == "predict-scan"
                    and candidate.get("lower_us") == lower_us
                    and candidate.get("upper_us") == upper_us
                    and candidate.get("next_after") == cursor):
                seed, manifest_ref = candidate, reference
                break
            if stream.get("scan_manifest_ref"):
                raise HistoryHTTPError("SCAN_RESUME_MISMATCH")
        if active and seed is None:
            raise HistoryHTTPError("SCAN_STATE_MISSING")

        ordered = requested
        scan_dates = requested
        if seed:
            from itertools import islice

            if (lower_us >= upper_us or lower_us != day_bounds_us(
                    datetime.fromtimestamp(lower_us / 1_000_000, timezone.utc).date().isoformat())[0]
                    or (upper_us - lower_us) % 86400_000_000):
                raise HistoryHTTPError("SCAN_RESUME_MISMATCH")
            scan_dates = seed.get("utc_dates")
            if scan_dates is not None and (
                    not scan_dates or scan_dates != sorted(set(scan_dates))
                    or any(not lower_us <= day_bounds_us(day)[0] < day_bounds_us(day)[1] <= upper_us
                           for day in scan_dates)):
                raise HistoryHTTPError("SCAN_RESUME_MISMATCH")
            # Old manifests lack the original plan: review their frozen UTC
            # days in bounded batches, never charge a new plan day to an old scan.
            frozen_dates = scan_dates if scan_dates is not None else (
                datetime.fromtimestamp(value / 1_000_000, timezone.utc).date().isoformat()
                for value in range(lower_us, upper_us, 86400_000_000)
            )
            reviewed = {day["utc_date"] for day in days
                        if not restart_scan and seed.get("closed") and day.get("raw_manifest_ref") == manifest_ref
                        and day.get("counts", {}).get("closed") is True}
            ordered = list(islice((day for day in frozen_dates if day not in reviewed), day_limit))
            if not ordered and any(lower_us <= day_bounds_us(day)[0] < upper_us for day in requested):
                # Replaying the same frozen day is idempotent; retirement only
                # moves to a genuinely different plan, not back onto its own window.
                ordered = [day for day in requested if lower_us <= day_bounds_us(day)[0] < upper_us]
            if not ordered:
                # Only a validated, closed, fully reviewed scan may be retired.
                seed, manifest_ref, cursor = None, None, None
                lower_us, upper_us = requested_lower, requested_upper
                ordered = scan_dates = requested
        if restart_scan:
            if seed is None:
                raise HistoryHTTPError("NO_ACTIVE_SCAN")
            # Validate every retained byte before resetting only the scan pointer.
            # A damaged raw is never repaired by discarding its reference.
            for page in seed["pages"]:
                read_round_page(self._archive, page)
            history = list(stream.get("scan_restart_history", []))
            if manifest_ref not in history:
                history.append(manifest_ref)
            fresh = {"kind": "predict-scan", "lower_us": lower_us, "upper_us": upper_us,
                     "utc_dates": scan_dates, "next_after": None, "pages": [], "closed": False}
            manifest_ref, _ = self._archive.store_json(utc_today(), fresh)
            self._store.write_stream(DATASET_ROUNDS, {"scan_restart_history": history,
                "scan_cursor": None, "scan_manifest_ref": manifest_ref,
                "scan_lower_us": lower_us, "scan_upper_us": upper_us})
            seed, cursor = None, None
        loader = HistoryBatchLoader(self._db, DATASET_ROUNDS)
        pipeline = DataPipeline(BufferedRoundExtractor(), PredictRoundTransformer(),
                                HistoryValidator(DATASET_ROUNDS), loader)
        counts_by_day = {day: {"inserted": 0, "updated": 0, "skipped": 0,
                               "day_records": 0} for day in ordered}

        async def ingest(records, page):
            for day in ordered:
                rows = _select_day_records(records, *day_bounds_us(day))
                if not rows:
                    continue
                from pymongo import timeout
                from .common import ROUNDS_COLLECTION

                with timeout(10):
                    current = {row["round_id"]: row for row in self._db[ROUNDS_COLLECTION].find({
                        "source": SOURCE_ROUNDS, "series_slug": "btc-updown-5m",
                        "round_id": {"$in": [str(row["category"]["id"]) for row in rows]},
                    }).max_time_ms(10000)}
                rows = [reconcile_round_raw(
                    dict(row, _raw_ref=page["raw_ref"], _raw_sha256=page["raw_sha256"]),
                    current.get(str(row["category"]["id"])), self._archive,
                ) for row in rows]
                loader.set_context(raw_ref=page["raw_ref"], raw_sha256=page["raw_sha256"],
                                   fetched_at=utc_now())
                outcome = await pipeline.run(BufferedRoundSource(
                    records=rows, raw_ref=page["raw_ref"], raw_sha256=page["raw_sha256"],
                ), budget=self._budget)
                if outcome.errors:
                    raise HistoryHTTPError("PAGE_ETVL_FAILED")
                for key in ("inserted", "updated", "skipped"):
                    counts_by_day[day][key] += getattr(outcome, key)
                counts_by_day[day]["day_records"] += len(rows)

        async def checkpoint(records, page, state: dict[str, Any]):
            nonlocal manifest_ref
            await ingest(records, page)
            state = dict(state, kind="predict-scan")
            if scan_dates is not None:
                state["utc_dates"] = scan_dates
            manifest_ref, _ = self._archive.store_json(utc_today(), state)
            # Publish the resumable scan independently of per-day result writes.
            self._store.write_stream(DATASET_ROUNDS, {"scan_cursor": state["next_after"],
                                                       "scan_lower_us": lower_us,
                                                       "scan_upper_us": upper_us,
                                                       "scan_manifest_ref": manifest_ref})
            for day in ordered:
                self._store.write_day(DATASET_ROUNDS, day, state="pending",
                                      counts=counts_by_day[day], raw_manifest_ref=manifest_ref,
                                      error_code="SCAN_NOT_CLOSED")

        replay_complete = True
        if seed:
            for page in seed["pages"]:
                if self._budget.remaining() <= 0:
                    replay_complete = False
                    break
                await ingest(read_round_page(self._archive, page), page)
            self._store.write_stream(DATASET_ROUNDS, {"scan_cursor": cursor,
                                                       "scan_lower_us": lower_us,
                                                       "scan_upper_us": upper_us,
                                                       "scan_manifest_ref": manifest_ref})
        if seed and not replay_complete:
            scan = RoundScanResult(pages=seed["pages"], error_code="BUDGET_EXHAUSTED")
        elif seed and seed.get("closed"):
            scan = RoundScanResult(pages=seed["pages"], closed=True)
        else:
            try:
                scan = await scan_rounds(
                    PredictRoundExtractor(self._archive), budget=self._budget,
                    lower_us=lower_us, upper_us=upper_us, after=cursor, api_key=self._api_key,
                    resume_state=seed, on_page=checkpoint, collect_records=False,
                )
            except (HistoryHTTPError, HistoryBudgetError) as exc:
                code = exc.code if isinstance(exc, HistoryHTTPError) else "BUDGET_EXHAUSTED"
                return [self._fail_day(DATASET_ROUNDS, day, code,
                            counts=counts_by_day[day], raw_manifest_ref=manifest_ref,
                            service_retry_at=getattr(exc, "retry_at", None)) for day in ordered]
        scan.raw_manifest_ref = manifest_ref
        results = []
        for day in ordered:
            review = self._review_round_day(day, *day_bounds_us(day))
            counts = dict(counts_by_day[day], pages=len(scan.pages), closed=scan.closed,
                          **{key: value for key, value in review.items()
                             if key != "content_sha256"})
            counts["stored_rounds"] = review["stored"]
            errors = [] if scan.error_code in (None, "BUDGET_EXHAUSTED", "EMPTY_PAGE_NOT_CLOSED") else [scan.error_code]
            day_scan = scan
            if not lower_us <= day_bounds_us(day)[0] < day_bounds_us(day)[1] <= upper_us:
                day_scan = RoundScanResult(error_code="DAY_OUTSIDE_FIXED_SCAN")
            results.append(self._finish_round_day(day, counts=counts, review=review,
                                                   scan=day_scan, errors=errors))
        return results

    def _finish_round_day(
        self,
        utc_date: str,
        *,
        counts: dict[str, Any],
        review: dict[str, Any],
        scan: RoundScanResult,
        errors: Sequence[str],
    ) -> DayResult:
        """Publish completion only after enumerated page-chain and exact day review."""
        if (errors or review["conflict"] or review["duplicate_natural_keys"]
                or review["invalid_identity"] or review["overlaps"] or review["off_grid"]
                or review["invalid_settlement"]):
            state, code = "conflict", errors[0] if errors else "ROUND_CONFLICT"
        elif not scan.closed:
            state, code = "pending", scan.error_code or "SCAN_NOT_CLOSED"
        elif not review["coverage_ok"]:
            state, code = "gap", "ROUND_COVERAGE_GAP"
        elif review["pending"] or review["unavailable"]:
            state, code = "pending", "SETTLEMENT_PENDING"
        elif not scan.raw_manifest_ref:
            state, code = "pending", "DAY_MANIFEST_MISSING"
        else:
            state, code = "complete", None
        counts = dict(counts, closed=bool(scan.closed and scan.raw_manifest_ref))
        digest = review["content_sha256"] if state == "complete" else None
        moment = utc_now()
        self._store.write_day(
            DATASET_ROUNDS, utc_date, state=state, counts=counts,
            error_code=code, content_sha256=digest, raw_manifest_ref=scan.raw_manifest_ref,
            last_attempt_at=moment, next_retry_at=_failure_due(code, moment),
        )
        self._advance_stream(DATASET_ROUNDS)
        return DayResult(DATASET_ROUNDS, utc_date, state, counts=counts,
                         error_code=code, content_sha256=digest,
                         raw_manifest_ref=scan.raw_manifest_ref)

    async def run_round_day(self, utc_date: str) -> DayResult:
        """执行一个 Predict 日（单日切片）。"""
        results = await self.run_round_days([utc_date])
        return results[0]

    def _review_round_day(
        self, utc_date: str, start_us: int, end_us: int,
        *, docs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """核对日身份、名义槽与结算；verify 可复用已读取的同一批内容。"""
        from decimal import Decimal
        from bson import Decimal128
        from .common import ROUNDS_COLLECTION

        if docs is None:
            docs = list(self._db[ROUNDS_COLLECTION].find(
                {"source": SOURCE_ROUNDS, "series_slug": "btc-updown-5m",
                 "starts_at_us": {"$gte": start_us, "$lt": end_us}}, {"_id": 0},
            ))
        step = 300_000_000
        states = {state: 0 for state in ("resolved", "pending", "unavailable", "conflict")}
        identities = set()
        starts = []
        invalid_identity = duplicates = off_grid = invalid_settlement = missing_start_prices = 0
        for doc in docs:
            identity = (doc.get("source"), doc.get("series_slug"), doc.get("round_id"))
            duplicates += identity in identities
            identities.add(identity)
            round_id, market_id = doc.get("round_id"), doc.get("market_id")
            begin, stop = doc.get("starts_at_us"), doc.get("ends_at_us")
            valid_time = (isinstance(begin, int) and not isinstance(begin, bool)
                          and isinstance(stop, int) and not isinstance(stop, bool)
                          and start_us <= begin < end_us and stop - begin == step)
            valid_identity = (
                doc.get("source") == SOURCE_ROUNDS and doc.get("series_slug") == "btc-updown-5m"
                and isinstance(round_id, str) and round_id.isascii() and round_id.isdecimal()
                and isinstance(market_id, str) and market_id.isascii() and market_id.isdecimal()
                and bool(doc.get("round_slug")) and bool(doc.get("condition_id"))
                and doc.get("price_feed_symbol") == "BTCUSDT" and valid_time
            )
            invalid_identity += not valid_identity
            if valid_time:
                starts.append(begin)
                off_grid += (begin - start_us) % step != 0
            prices = []
            for field_name in ("start_price", "end_price"):
                price = doc.get(field_name)
                price = price.to_decimal() if isinstance(price, Decimal128) else price
                prices.append(isinstance(price, Decimal) and price.is_finite() and price > 0)
            missing_start_prices += not prices[0]
            state = doc.get("settlement_state") or "pending"
            if state not in states:
                state = "conflict"
            states[state] += 1
            if state == "resolved":
                invalid_settlement += not (
                    all(prices) and doc.get("official_outcome") in ("UP", "DOWN", "DRAW")
                    and isinstance(doc.get("resolved_at_us"), int)
                    and bool(doc.get("resolution_evidence"))
                )
        distinct = set(starts)
        missing = sorted(set(range(start_us, end_us, step)) - distinct)
        intervals = []
        for begin in missing:
            if intervals and intervals[-1][1] == begin:
                intervals[-1][1] = begin + step
            else:
                intervals.append([begin, begin + step])
        ordered = sorted(starts)
        overlaps = sum(right < left + step for left, right in zip(ordered, ordered[1:]))
        coverage_ok = not (missing or duplicates or invalid_identity or overlaps or off_grid
                           or missing_start_prices or invalid_settlement)
        return {
            "stored": len(docs), **states,
            "valid_identity": len(docs) - invalid_identity,
            "invalid_identity": invalid_identity, "duplicate_natural_keys": duplicates,
            "distinct_start_slots": len(distinct), "nominal_slots": NOMINAL_ROUND_SLOTS,
            "missing_nominal_slots": len(missing), "missing_nominal_intervals": intervals,
            "overlaps": overlaps, "off_grid": off_grid,
            "missing_start_prices": missing_start_prices,
            "invalid_settlement": invalid_settlement, "coverage_ok": coverage_ok,
            "content_sha256": _digest_of([], docs),
        }

    # -- 公共 ------------------------------------------------------------
    def _fail_day(
        self,
        dataset: str,
        utc_date: str,
        error_code: str,
        *,
        counts: Mapping[str, Any] | None = None,
        raw_manifest_ref: str | None = None,
        service_retry_at: datetime | None = None,
    ) -> DayResult:
        state = "pending" if error_code == "BUDGET_EXHAUSTED" else "failed"
        moment = utc_now()
        previous = self._store.get_day(dataset, utc_date) or {}
        reference = raw_manifest_ref or previous.get("raw_manifest_ref")
        self._store.write_day(
            dataset,
            utc_date,
            state=state,
            counts=counts or {},
            error_code=error_code,
            raw_manifest_ref=reference,
            last_attempt_at=moment,
            next_retry_at=_failure_due(error_code, moment, service_retry_at),
            service_retry_at=service_retry_at,
        )
        self._advance_stream(dataset)
        return DayResult(
            dataset=dataset,
            utc_date=utc_date,
            state=state,
            counts=dict(counts or {}),
            error_code=error_code,
            raw_manifest_ref=reference,
        )

    def _advance_stream(self, dataset: str) -> None:
        """按连续 complete 日推进 stream 水位（不跳 gap）。"""
        stream = self._store.get_stream(dataset)
        if not stream:
            return
        anchor = stream.get("ingestion_start_us")
        if anchor is None:
            return
        boundary = advance_contiguous(
            self._store, dataset, ingestion_start_us=int(anchor)
        )
        enumerated = self._enumerated_boundary(dataset, int(anchor))
        fields = {"complete_through_us": boundary, "enumerated_through_us": enumerated}
        if any(stream.get(key) != value for key, value in fields.items()):
            self._store.write_stream(dataset, fields)

    def _enumerated_boundary(self, dataset: str, anchor: int) -> int | None:
        """Advance only across contiguous verified daily enumeration/archival evidence."""
        import json
        from pathlib import Path

        days = {day["utc_date"]: day for day in self._store.list_days(dataset)}
        cursor, boundary = anchor, None
        manifests = {}
        while True:
            date = _date_from_us(cursor)
            day = days.get(date) or {}
            counts = day.get("counts") or {}
            ref = day.get("raw_manifest_ref")
            if not ref:
                break
            try:
                if ref not in manifests:
                    raw = self._archive.read_bytes(ref)
                    if hashlib.sha256(raw).hexdigest() != Path(ref).stem:
                        break
                    manifests[ref] = json.loads(raw)
                manifest = manifests[ref]
                begin, end = day_bounds_us(date)
                if dataset == DATASET_ROUNDS:
                    if (not counts.get("closed") or not manifest.get("closed")
                            or manifest.get("kind") != "predict-scan" or not manifest.get("pages")
                            or not manifest["lower_us"] <= begin < end <= manifest["upper_us"]
                            or counts.get("missing_nominal_slots") != 0
                            or counts.get("distinct_start_slots") != NOMINAL_ROUND_SLOTS
                            or any(counts.get(key, 0) for key in (
                                "invalid_identity", "duplicate_natural_keys", "overlaps", "off_grid"))):
                        break
                elif (day.get("state") != "complete" or manifest.get("utc_date") != date
                      or counts.get("valid_unique_seconds") != SECONDS_PER_DAY
                      or counts.get("missing_seconds") != 0):
                    break
            except (OSError, ValueError, KeyError, TypeError, HistoryHTTPError):
                break
            boundary = cursor = end
        return boundary


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _zip_chunk_source(raw_ref: str, offset: int, limit: int) -> Any:
    from .extractors import ZipChunkSource

    return ZipChunkSource(raw_ref=raw_ref, offset=offset, limit=limit)


def _select_day_records(
    records: Iterable[Mapping[str, Any]], start_us: int, end_us: int
) -> list[dict[str, Any]]:
    """只保留落在目标日窗口内的 round envelope。"""
    from .transforms import datetime_to_us, parse_utc_datetime

    out: list[dict[str, Any]] = []
    for record in records:
        category = record.get("category") or {}
        starts = datetime_to_us(parse_utc_datetime(category.get("startsAt")))
        if starts is None:
            continue
        if start_us <= starts < end_us:
            out.append(dict(record))
    return out


def _digest_of(keys: Sequence[Any], docs: Sequence[Mapping[str, Any]]) -> str:
    """按稳定顺序对业务 digest 做整体 hash。"""
    from skills.data.unified_data.history_types import canonical_json, sha256_hex

    from .loader import _record_hash

    pairs = []
    for doc in docs:
        dataset = DATASET_KLINES if "open_time_us" in doc else DATASET_ROUNDS
        digest = _record_hash(doc, dataset)
        if doc.get("schema_version") != 1 or digest != doc.get("record_sha256"):
            raise HistoryHTTPError("READBACK_MISMATCH")
        key = (int(doc["open_time_us"]) if dataset == DATASET_KLINES else
               (int(doc["starts_at_us"]), str(doc["round_id"])))
        pairs.append([key, digest])
    pairs.sort(key=lambda pair: pair[0])
    return sha256_hex(canonical_json(pairs))


def _write_gap_manifest(
    archive: RawArchive,
    utc_date: str,
    source: str,
    opens: Sequence[int],
    start_us: int,
    end_us: int,
) -> str:
    """写缺口 manifest（不把百万槽数组塞进单文档）。"""
    import json

    missing = _missing_intervals(opens, start_us, end_us)
    payload = {
        "utc_date": utc_date,
        "source": source,
        "expected_seconds": SECONDS_PER_DAY,
        "valid_unique_seconds": len(opens),
        "missing_seconds": sum(
            (stop - begin) for begin, stop in missing
        ),
        "missing_intervals": [[begin, stop] for begin, stop in missing[:2000]],
        "missing_intervals_truncated": len(missing) > 2000,
    }
    raw_ref, _ = archive.store_bytes(
        utc_date, json.dumps(payload, sort_keys=True).encode("utf-8"), kind="predict"
    )
    return raw_ref


def _missing_intervals(
    opens: Sequence[int], start_us: int, end_us: int
) -> list[tuple[int, int]]:
    """返回缺失秒区间（微秒边界，右开）。"""
    out: list[tuple[int, int]] = []
    present = set(opens)
    cursor = start_us
    step = 1_000_000
    while cursor < end_us:
        if cursor in present:
            cursor += step
            continue
        begin = cursor
        while cursor < end_us and cursor not in present:
            cursor += step
        out.append((begin, cursor))
    return out


__all__ = [
    "DAY_STATES",
    "NOMINAL_ROUND_SLOTS",
    "SECONDS_PER_DAY",
    "DayPlan",
    "DayResult",
    "HistoryRunner",
    "IngestionStore",
    "RoundScanResult",
    "advance_contiguous",
    "combined_complete_through",
    "commit_day",
    "plan_days",
    "recheck_pending",
    "scan_rounds",
]
