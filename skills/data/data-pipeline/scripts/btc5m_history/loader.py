"""BTC5m 历史的批加载与精确读回 — 03-018 §6.5。

``HistoryBatchLoader``：

* 固定 dataset → 集合 allowlist；**只写两个历史集合**。
* 先按自然键一次批量 find 现有记录，比较业务 hash 与不可变字段。
* 新记录 ``UpdateOne(filter=自然键, $setOnInsert=全记录, upsert=True)``；
  **不 insert_many**，避免重复键与并发插入冲突。
* 同事实 → skip，**不刷新** fetched / 观察时间。
* pending → resolved 是同自然键的 **CAS** 更新（filter 含旧
  ``record_sha256``，``upsert=False``）；CAS 未命中 → 冲突错误。
* 已 resolved 的价格 / outcome / 结算时间，或已验收秒线的非等值变化 →
  **零覆盖**，只记冲突（不写库）。
* bulk_write ≤5000、``ordered=False``、acknowledged、有限 timeout。
* 有界批量精确读回（按自然键批量 find，比较全部规范化业务字段）。

它**不**提交日状态、**不**推进 stream 水位（那属于 runner）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from ..loaders.base import BaseLoader, LoadResult

from .common import (
    DATASET_KLINES,
    DATASET_ROUNDS,
    ERR_CONFLICT,
    ERR_READBACK_MISMATCH,
    KLINES_COLLECTION,
    ROUNDS_COLLECTION,
)

#: 单次 bulk_write 上限。
MAX_BULK = 5000

#: dataset → 允许写入的集合。
DATASET_COLLECTIONS: dict[str, str] = {
    DATASET_ROUNDS: ROUNDS_COLLECTION,
    DATASET_KLINES: KLINES_COLLECTION,
}

#: 自然键字段。
ROUND_KEY = ("source", "series_slug", "round_id")
KLINE_KEY = ("source", "market_type", "symbol", "interval", "open_time_us")

#: 本地易变字段（不进业务 hash，读回只要求存在）。
LOCAL_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "_id",
        "fetched_at",
        "raw_ref",
        "raw_sha256",
        "first_observed_at",
        "start_price_observed_at",
        "label_observed_at",
        "next_check_at",
        "updated_at",
        "record_sha256",
        "previous_record_sha256",
        "raw_history",
    }
)

#: rounds 业务字段投影（SPEC §5.2）。
ROUND_BUSINESS_FIELDS: tuple[str, ...] = (
    "schema_version",
    "source",
    "series_slug",
    "round_id",
    "round_slug",
    "market_id",
    "condition_id",
    "published_at_us",
    "starts_at_us",
    "ends_at_us",
    "start_price",
    "end_price",
    "price_feed_provider",
    "price_feed_symbol",
    "category_status",
    "market_status",
    "trading_status",
    "settlement_state",
    "official_outcome",
    "resolution_evidence",
    "resolved_at_us",
)

#: klines 业务字段投影（SPEC §5.3）。
KLINE_BUSINESS_FIELDS: tuple[str, ...] = (
    "schema_version",
    "source",
    "market_type",
    "symbol",
    "interval",
    "open_time_us",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time_us",
    "close_exclusive_us",
    "quote_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
    "source_timestamp_unit",
    "source_row",
)

#: rounds 中允许“空 → 有值”补齐的业务事实。
ROUND_FILLABLE_FIELDS: frozenset[str] = frozenset(
    {
        "start_price",
        "end_price",
        "official_outcome",
        "resolved_at_us",
        "resolution_evidence",
        "settlement_state",
        "category_status",
        "market_status",
        "trading_status",
    }
)

#: 已 resolved 后不可被覆盖的业务事实。
ROUND_RESOLVED_FACTS: frozenset[str] = frozenset(
    {"start_price", "end_price", "official_outcome", "resolved_at_us"}
)


class HistoryBatchLoader(BaseLoader):
    """BTC5m 历史的批量 upsert + 精确读回 loader。

    Args:
        mongo_db: UD 目标库句柄。
        dataset: ``predict_btc5m_rounds`` 或 ``binance_spot_btcusdt_1s``。
    """

    def __init__(self, mongo_db: Any, dataset: str) -> None:
        if dataset not in DATASET_COLLECTIONS:
            raise ValueError(f"unknown dataset {dataset!r}")
        name = getattr(mongo_db, "name", None)
        if isinstance(name, str) and name != "yquant-data":
            raise ValueError("history namespace must be yquant-data")
        self._db = mongo_db
        self._dataset = dataset
        self._raw_ref: str | None = None
        self._raw_sha256: str | None = None
        self._fetched_at: datetime | None = None

    @property
    def target_type(self) -> str:
        """目标存储类型。"""
        return "mongodb"

    @property
    def collection(self) -> str:
        """本 dataset 对应的目标集合。"""
        return DATASET_COLLECTIONS[self._dataset]

    # ------------------------------------------------------------------
    # 批次上下文（raw 证据 + 抓取时间）
    # ------------------------------------------------------------------

    def set_context(
        self,
        *,
        raw_ref: str | None = None,
        raw_sha256: str | None = None,
        fetched_at: datetime | None = None,
    ) -> None:
        """设置本批的 raw 引用与抓取时间（由 runner / extractor 提供）。"""
        self._raw_ref = raw_ref
        self._raw_sha256 = raw_sha256
        self._fetched_at = fetched_at

    # ------------------------------------------------------------------
    # 自然键
    # ------------------------------------------------------------------

    def natural_key(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """返回记录的自然键 filter。

        Raises:
            ValueError: 自然键字段缺失。
        """
        fields = ROUND_KEY if self._dataset == DATASET_ROUNDS else KLINE_KEY
        missing = [field for field in fields if record.get(field) is None]
        if missing:
            raise ValueError(f"missing natural key field(s): {missing}")
        return {field: record[field] for field in fields}

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    async def load(self, records: list[dict[str, Any]]) -> LoadResult:
        """写入一批记录并做精确读回。

        Args:
            records: 已 transform + validate 的记录。

        Returns:
            :class:`LoadResult`（表达**当前批**写结果）。
        """
        result = LoadResult()
        if not records:
            return result

        from pymongo import UpdateOne, timeout

        try:
            prepared = self._prepare(records)
        except ValueError:
            result.errors.append({"reason": ERR_CONFLICT, "key": {}})
            return result
        collection = self._db[self.collection]
        for offset in range(0, len(prepared), MAX_BULK):
            chunk = prepared[offset : offset + MAX_BULK]
            try:
                with timeout(10):
                    existing_docs = list(collection.find(
                        {"$or": [self.natural_key(row) for row in chunk]}
                    ))
                    existing = {_key_tuple(doc, self._dataset): doc for doc in existing_docs}
                    if len(existing) != len(existing_docs):
                        result.errors.append({"reason": ERR_CONFLICT, "key": {}})
                        continue
                    operations, expected = [], []
                    inserted = updated = skipped = 0
                    for row in chunk:
                        key = self.natural_key(row)
                        current = existing.get(_key_tuple(row, self._dataset))
                        if current is None:
                            expected.append(row)
                            operations.append(UpdateOne(key, {"$setOnInsert": row}, upsert=True))
                            inserted += 1
                            continue
                        if not current.get("record_sha256"):
                            result.errors.append({"reason": ERR_READBACK_MISMATCH, "key": key})
                            continue
                        if current["record_sha256"] != _record_hash(current, self._dataset):
                            result.errors.append({"reason": ERR_READBACK_MISMATCH, "key": key})
                            continue
                        if _business_fields_equal(current, row, self._dataset):
                            expected.append(current)
                            skipped += 1
                            continue
                        if not _immutable_fields_equal(current, row) or not self._may_update(current, row, self._dataset):
                            result.errors.append({"reason": ERR_CONFLICT, "key": _redact_key(key)})
                            continue
                        payload = dict(row)
                        # Existing fact times and original provenance never move on replay/fill.
                        for field in ("first_observed_at", "fetched_at", "start_price_observed_at",
                                      "label_observed_at"):
                            if current.get(field) is not None:
                                payload[field] = current[field]
                        if current.get("settlement_state") == "conflict":
                            # A newly accepted Flat label was not known at the
                            # quarantined record's first observation time.
                            payload["label_observed_at"] = row["fetched_at"]
                        payload["previous_record_sha256"] = current["record_sha256"]
                        payload["raw_history"] = list(current.get("raw_history", [])) + [{
                            "raw_ref": current.get("raw_ref"),
                            "raw_sha256": current.get("raw_sha256"),
                            "record_sha256": current["record_sha256"],
                        }]
                        payload["updated_at"] = row["fetched_at"]
                        expected.append(payload)
                        operations.append(UpdateOne(
                            dict(key, record_sha256=current["record_sha256"]),
                            {"$set": payload}, upsert=False,
                        ))
                        updated += 1
                    # A conflicting candidate must not cause any write in this batch.
                    if result.errors:
                        continue
                    upserted = 0
                    if operations:
                        outcome = collection.bulk_write(operations, ordered=False)
                        if getattr(outcome, "acknowledged", None) is not True:
                            raise RuntimeError("UNKNOWN_ACK")
                        if outcome.matched_count + outcome.upserted_count != len(operations):
                            raise RuntimeError("CAS_MISMATCH")
                        upserted = outcome.upserted_count
                    if not all(self.readback(expected).values()):
                        result.errors.append({"reason": ERR_READBACK_MISMATCH, "key": {}})
                        continue
                    result.inserted += upserted
                    result.updated += updated
                    result.skipped += skipped + inserted - upserted
            except Exception:  # noqa: BLE001 — never persist driver exception/credentials
                result.errors.append({"reason": "BULK_OR_READ_FAILED", "key": {}})
        return result

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _prepare(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """补齐公共字段并按自然键去重（保留首次出现）。"""
        seen: dict[tuple[Any, ...], dict[str, Any]] = {}
        prepared: list[dict[str, Any]] = []
        for record in records:
            item = dict(record)
            key_tuple = _key_tuple(self.natural_key(item), self._dataset)
            if key_tuple in seen:
                if not _business_fields_equal(seen[key_tuple], item, self._dataset):
                    raise ValueError("duplicate natural key conflict")
                continue
            seen[key_tuple] = item
            fetched_at = item.get("fetched_at") or self._fetched_at
            if fetched_at is None:
                fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if self._dataset == DATASET_ROUNDS:
                valid_namespace = (item.get("source") == "predict.fun"
                                   and item.get("series_slug") == "btc-updown-5m")
            else:
                valid_namespace = all(item.get(key) == value for key, value in (
                    ("source", "binance-vision"), ("market_type", "spot"),
                    ("symbol", "BTCUSDT"), ("interval", "1s"),
                ))
            if not valid_namespace or item.get("schema_version") != 1:
                raise ValueError("invalid history namespace/schema")
            item["fetched_at"] = fetched_at
            item.setdefault("first_observed_at", fetched_at)
            if self._dataset == DATASET_ROUNDS:
                if item.get("start_price") is not None and item.get("start_price_observed_at") is None:
                    item["start_price_observed_at"] = fetched_at
                if item.get("settlement_state") == "resolved" and item.get("label_observed_at") is None:
                    item["label_observed_at"] = fetched_at
            from skills.data.unified_data.history_types import ceil_ms_to_us, from_us

            for field in ("fetched_at", "first_observed_at", "start_price_observed_at", "label_observed_at"):
                if item.get(field) is not None:
                    item[field] = from_us(ceil_ms_to_us(item[field]))
            if (self._dataset == DATASET_ROUNDS
                    and item.get("settlement_state") in ("pending", "unavailable", "conflict")
                    and item.get("next_check_at") is None):
                item["next_check_at"] = item["first_observed_at"]
            if self._raw_ref is not None:
                item.setdefault("raw_ref", self._raw_ref)
            if self._raw_sha256 is not None:
                item.setdefault("raw_sha256", self._raw_sha256)
            item["record_sha256"] = _record_hash(item, self._dataset)
            prepared.append(_bson_values(item))
        return prepared

    @staticmethod
    def _may_update(
        current: Mapping[str, Any], record: Mapping[str, Any], dataset: str,
    ) -> bool:
        """判断是否允许在现有记录上更新业务事实。

        * rounds：只允许“空 → 有值”的补齐；已 resolved 的关键事实不可覆盖。
        * klines：已验收秒线不可非等值覆盖。
        """
        if dataset == DATASET_KLINES:
            return False
        changed = _changed_business_fields(current, record, dataset)
        if not changed:
            return False
        if not changed <= ROUND_FILLABLE_FIELDS:
            return False
        if current.get("settlement_state") not in ("pending", "unavailable"):
            if not _is_flat_correction(current, record):
                return False
        for field in ("category_status", "market_status", "trading_status"):
            terminal_statuses = ("RESOLVED", "CLOSED") if field == "trading_status" else ("RESOLVED",)
            if field in changed and not (
                record.get("settlement_state") == "resolved"
                and record.get(field) in terminal_statuses
            ):
                return False
        for field in ROUND_RESOLVED_FACTS | {"resolution_evidence"}:
            if field in changed and current.get(field) not in (None, ""):
                return False
        return True

    # ------------------------------------------------------------------
    # 读回
    # ------------------------------------------------------------------

    def readback(self, records: list[dict[str, Any]]) -> dict[str, bool]:
        """有界批量精确读回并比较规范化业务字段。

        Returns:
            ``{key_tuple: is_exact_match}``。
        """
        from pymongo import timeout

        collection = self._db[self.collection]
        out: dict[str, bool] = {}
        prepared = [dict(record) for record in records]
        for start in range(0, len(prepared), MAX_BULK):
            chunk = prepared[start : start + MAX_BULK]
            keys = [self.natural_key(record) for record in chunk]
            with timeout(10):
                docs = list(collection.find({"$or": keys}))
            by_key = {
                _key_tuple(doc, self._dataset): doc
                for doc in docs
            }
            for record in chunk:
                key = self.natural_key(record)
                key_tuple = tuple(key[field] for field in sorted(key))
                doc = by_key.get(key_tuple)
                out[str(key_tuple)] = (
                    len(docs) == len(by_key) and bool(doc)
                    and _readback_equal(doc, record, self._dataset)
                )
        return out


# -----------------------------------------------------------------------
# 辅助
# -----------------------------------------------------------------------


def _is_flat_correction(current: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    """Allow only an unlabeled conflict to acquire complete official Flat proof."""
    from bson import Decimal128
    from .transforms import TransformError, _flat_evidence, datetime_to_us, parse_utc_datetime

    evidence = record.get("resolution_evidence")
    if (current.get("settlement_state") != "conflict"
            or current.get("official_outcome") not in (None, "")
            or current.get("resolution_evidence") not in (None, "")
            or record.get("settlement_state") != "resolved" or record.get("official_outcome") != "DRAW"
            or record.get("market_status") != "RESOLVED" or record.get("category_status") != "RESOLVED"
            or record.get("trading_status") not in ("RESOLVED", "CLOSED")
            or not isinstance(evidence, Mapping)):
        return False
    prices = [record.get(field) for field in ("start_price", "end_price")]
    prices = [value.to_decimal() if isinstance(value, Decimal128) else value for value in prices]
    expected = _flat_evidence({
        "id": record.get("market_id"), "description": evidence.get("rule_text"),
        "outcomes": evidence.get("outcomes"), "resolution": evidence.get("original_resolution"),
    }, *prices)
    if expected is None or any(_normalize(evidence.get(key)) != _normalize(value)
                               for key, value in expected.items()):
        return False
    transition = evidence.get("final_transition")
    if not isinstance(transition, Mapping) or transition.get("status") != "RESOLVED":
        return False
    try:
        resolved = datetime_to_us(parse_utc_datetime(transition.get("timestamp")))
    except TransformError:
        return False
    return (isinstance(record.get("ends_at_us"), int) and resolved is not None
            and resolved >= record["ends_at_us"] and resolved == record.get("resolved_at_us"))


def _bson_values(value: Any, field: str = "") -> Any:
    """Encode ETVL Decimal/int64 values without float conversion."""
    from bson import Decimal128, Int64

    if isinstance(value, Decimal):
        return Decimal128(value)
    if isinstance(value, Mapping):
        return {key: _bson_values(item, key) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_bson_values(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool) and (
        field.endswith("_us") or field in ("number_of_trades", "source_row")
    ):
        return Int64(value)
    return value


def _key_tuple(doc: Mapping[str, Any], dataset: str) -> tuple[Any, ...]:
    fields = ROUND_KEY if dataset == DATASET_ROUNDS else KLINE_KEY
    return tuple(doc.get(field) for field in sorted(fields))


def _redact_key(key: Mapping[str, Any]) -> dict[str, str]:
    """错误报告里的自然键（只保留字符串形态，不含原始异常）。"""
    return {k: str(v) for k, v in key.items()}


def _business_fields(
    record: Mapping[str, Any], dataset: str
) -> dict[str, Any]:
    """返回业务字段投影（去掉 raw 引用等本地易变字段）。"""
    fields = ROUND_BUSINESS_FIELDS if dataset == DATASET_ROUNDS else KLINE_BUSINESS_FIELDS
    payload = {field: record.get(field) for field in fields}
    evidence = payload.get("resolution_evidence")
    if isinstance(evidence, Mapping):
        payload["resolution_evidence"] = _strip_raw_refs(evidence)
    return payload


def _strip_raw_refs(value: Any) -> Any:
    """从证据对象里剥离 raw 引用（raw 路径属 provenance，不进业务 hash）。"""
    if isinstance(value, Mapping):
        return {
            key: _strip_raw_refs(item)
            for key, item in value.items()
            if key not in ("raw_ref", "raw_sha256")
        }
    if isinstance(value, (list, tuple)):
        return [_strip_raw_refs(item) for item in value]
    return value


def _record_hash(record: Mapping[str, Any], dataset: str) -> str:
    """返回 v1 业务字段 hash（不含本地易变字段）。"""
    from skills.data.unified_data.history_types import record_sha256

    return record_sha256(_business_fields(record, dataset))


def _business_fields_equal(
    current: Mapping[str, Any], record: Mapping[str, Any], dataset: str
) -> bool:
    """比较业务事实（不含 fetched_at / raw_ref / 观察时间等易变字段）。"""
    left = _business_fields(current, dataset)
    right = _business_fields(record, dataset)
    for key in set(left) | set(right):
        if _normalize(left.get(key)) != _normalize(right.get(key)):
            return False
    return True


def _changed_business_fields(
    current: Mapping[str, Any], record: Mapping[str, Any], dataset: str
) -> set[str]:
    """返回业务字段中取值不同的字段集合。"""
    left = _business_fields(current, dataset)
    right = _business_fields(record, dataset)
    return {
        key
        for key in set(left) | set(right)
        if _normalize(left.get(key)) != _normalize(right.get(key))
    }


def _immutable_fields_equal(
    current: Mapping[str, Any], record: Mapping[str, Any]
) -> bool:
    """比较不可变字段（身份 / 时间）。"""
    immutable = ("source", "series_slug", "round_id", "starts_at_us", "ends_at_us",
                 "market_type", "symbol", "interval", "open_time_us")
    for key in immutable:
        if key not in record:
            continue
        if _normalize(current.get(key)) != _normalize(record.get(key)):
            return False
    return True


def _normalize(value: Any) -> Any:
    """规范化比较值（Decimal / datetime / 数字）。"""
    from skills.data.unified_data.history_types import decimal_text

    if isinstance(value, Decimal):
        return ("dec", decimal_text(value))
    to_decimal = getattr(value, "to_decimal", None)
    if callable(to_decimal):
        return ("dec", decimal_text(to_decimal()))
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return ("dt", value.isoformat())
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", repr(value))
    if isinstance(value, (list, tuple)):
        return ("list", tuple(_normalize(item) for item in value))
    if isinstance(value, Mapping):
        return (
            "map",
            tuple(sorted((k, _normalize(v)) for k, v in value.items())),
        )
    return value


def _readback_equal(
    doc: Mapping[str, Any], record: Mapping[str, Any], dataset: str
) -> bool:
    """比较读回文档与应写记录。

    业务字段必须完全一致；本地易变字段要求**存在**（观察时间由写入路径
    保留，不要求与本批新值相同）。
    """
    if not _business_fields_equal(doc, record, dataset):
        return False
    for field in ("fetched_at", "first_observed_at", "record_sha256"):
        if doc.get(field) is None:
            return False
    for field in LOCAL_ONLY_FIELDS - {"_id"}:
        if field in record and _normalize(doc.get(field)) != _normalize(record[field]):
            return False
    return doc["record_sha256"] == _record_hash(doc, dataset)


__all__ = [
    "DATASET_COLLECTIONS",
    "KLINE_BUSINESS_FIELDS",
    "KLINE_KEY",
    "LOCAL_ONLY_FIELDS",
    "MAX_BULK",
    "ROUND_BUSINESS_FIELDS",
    "ROUND_KEY",
    "ROUND_RESOLVED_FACTS",
    "HistoryBatchLoader",
]
