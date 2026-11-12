"""BTC5m 窄历史读取的类型与纯辅助函数 — 03-018 §8.1 / §8.2。

本模块**只**提供纯数据契约：请求 / 窗口 / 三个分离流 / 内容 manifest /
业务 hash 辅助。它不做 I/O、不联网、不建索引、不 import pymongo 之外的
运行时对象。

时间口径：

* 业务时间统一 int64 UTC Unix 微秒（``*_us``）。
* 本地观察时间来自可信抓取 manifest 的 BSON datetime（毫秒精度），
  向上取毫秒 → 微秒，禁止向下截断引入亚毫秒前视。
* ``available_at_us`` 分 ``observed``（默认）与 ``event-time-proxy``
  （必须显式选择）两种模式，规则见 :data:`AVAILABILITY_RULES`。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator, Mapping

#: 历史记录 schema 版本（固定 1；未知版本 fail）。
SCHEMA_VERSION = 1

#: 内容 manifest 版本。
CONTENT_MANIFEST_VERSION = 1

#: 受支持的 availability 模式。
AVAILABILITY_MODES: tuple[str, ...] = ("observed", "event-time-proxy")

#: 两个数据集的固定标识。
DATASET_ROUNDS = "predict_btc5m_rounds"
DATASET_KLINES = "binance_spot_btcusdt_1s"

#: 固定来源标识。
SOURCE_ROUNDS = "predict.fun"
SOURCE_KLINES = "binance-vision"

#: 固定业务口径（本题不接受任意币种 / 库名 / network）。
SERIES_SLUG = "btc-updown-5m"
MARKET_TYPE = "spot"
SYMBOL = "BTCUSDT"
INTERVAL = "1s"

#: 每行内容 / 类别 → available_at 规则（Design §8.2）。
AVAILABILITY_RULES: Mapping[str, str] = {
    "candle_ohlcv_observed": "max(close_exclusive_us, first_observed_at_us_ceil_ms)",
    "candle_ohlcv_proxy": "close_exclusive_us",
    "start_price_observed": "max(starts_at_us, start_price_observed_at_us)",
    "start_price_proxy": "starts_at_us",
    "identity_observed": "first_observed_at_us",
    "identity_proxy": "published_at_us (fallback first_observed_at_us)",
    "label_observed": "max(ends_at_us, resolved_at_us, label_observed_at_us)",
    "label_proxy": "max(ends_at_us, resolved_at_us)",
}


class HistoryError(Exception):
    """窄历史读取的显式错误。

    Attributes:
        code: 稳定错误码（如 ``INVALID_ARGUMENT`` / ``DATASET_CHANGED`` /
            ``HISTORY_NOT_CONFIGURED`` / ``UNKNOWN_SCHEMA_VERSION``）。
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


# ---------------------------------------------------------------------------
# 时间辅助
# ---------------------------------------------------------------------------


def ceil_ms_to_us(dt: datetime | None) -> int | None:
    """把 BSON datetime（毫秒精度）向上取整到整毫秒再转微秒。

    向上取整而非截断，避免亚毫秒精度向下取整引入前视。

    Args:
        dt: naive-UTC 或 tz-aware datetime；``None`` 返回 ``None``。

    Returns:
        UTC Unix 微秒（int）或 ``None``。
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    epoch = datetime(1970, 1, 1)
    delta = dt - epoch
    total_us = delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
    remainder = total_us % 1000
    if remainder:
        # 向上取整到下一个整毫秒（不向下截断，避免亚毫秒前视）。
        total_us += 1000 - remainder
    return total_us


def parse_utc(value: Any) -> datetime:
    """解析显式 UTC 时间为 naive-UTC datetime。

    Args:
        value: ``datetime`` 或带 ``Z`` / 零 offset 的 ISO 字符串。

    Raises:
        HistoryError: ``INVALID_ARGUMENT`` — naive / 非 UTC 输入。
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise HistoryError("INVALID_ARGUMENT", f"cannot parse {value!r}") from exc
    else:
        raise HistoryError("INVALID_ARGUMENT", f"cannot parse {value!r}")

    if parsed.tzinfo is None:
        raise HistoryError("INVALID_ARGUMENT", "naive datetime is not accepted")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise HistoryError("INVALID_ARGUMENT", "non-UTC offset is not accepted")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def to_us(dt: datetime) -> int:
    """把 naive-UTC datetime 转成 UTC Unix 微秒（整数运算，不用 float）。"""
    epoch = datetime(1970, 1, 1)
    delta = dt - epoch
    return delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds


def from_us(value: int) -> datetime:
    """把 UTC Unix 微秒转回 naive-UTC datetime。"""
    epoch = datetime(1970, 1, 1)
    return epoch + _timedelta_us(value)


def _timedelta_us(value: int):
    from datetime import timedelta

    return timedelta(microseconds=value)


# ---------------------------------------------------------------------------
# 规范化与 hash
# ---------------------------------------------------------------------------


def decimal_text(value: Decimal | None) -> str | None:
    """把 Decimal 规范成去尾零、无负零的十进制字符串。

    不经过 float，因此不损失精度；``None`` 原样返回。
    """
    if value is None:
        return None
    if value.is_nan() or value.is_infinite():
        raise HistoryError("INVALID_ARGUMENT", "non-finite Decimal is not storable")
    # Formatting is exact; normalize() would round using the caller's context.
    if value.is_zero():
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def canonical_json(payload: Any) -> str:
    """返回确定性 JSON 文本（键排序、Decimal 走规范字符串、int 不转 float）。"""
    return json.dumps(
        _canonicalize(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"$dec": decimal_text(value)}
    to_decimal = getattr(value, "to_decimal", None)
    if callable(to_decimal):
        # bson.Decimal128：与 Decimal 走同一规范十进制表示。
        return {"$dec": decimal_text(Decimal(str(to_decimal())))}
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        raise HistoryError("INVALID_ARGUMENT", "float is not allowed in canonical payload")
    if isinstance(value, Mapping):
        return {str(k): _canonicalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, datetime):
        return {"$dt": ceil_ms_to_us(value)}
    raise HistoryError("INVALID_ARGUMENT", f"unsupported type {type(value).__name__}")


def sha256_hex(text: str) -> str:
    """返回 UTF-8 文本的 SHA-256 小写 hex。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_sha256(fields: Mapping[str, Any]) -> str:
    """返回 v1 业务字段 hash（不含 fetched_at / raw_ref 等易变字段）。

    字段投影由调用方负责（只传业务字段）；本函数只做规范化 + SHA-256。
    """
    return sha256_hex(canonical_json(fields))


# ---------------------------------------------------------------------------
# 请求 / 窗口 / 行 DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryRequest:
    """窄历史读取请求。

    Attributes:
        start_utc: 主窗口下界（含），显式 UTC。
        end_utc: 主窗口上界（不含），显式 UTC。
        warmup_seconds: 主窗口之前的预热秒数（非负，默认 0）。
        as_of_utc: 可得时间上界（必填，显式 UTC）。
        availability_mode: ``observed``（默认）或 ``event-time-proxy``。
        expected_manifest: 上一份业务 content manifest（或其 sha256）。
    """

    start_utc: datetime
    end_utc: datetime
    as_of_utc: datetime
    warmup_seconds: int = 0
    availability_mode: str = "observed"
    expected_manifest: Any | None = None

    def validate(self) -> None:
        """校验参数合法性。

        Raises:
            HistoryError: ``INVALID_ARGUMENT``。
        """
        if (isinstance(self.warmup_seconds, bool) or not isinstance(self.warmup_seconds, int)
                or self.warmup_seconds < 0):
            raise HistoryError("INVALID_ARGUMENT", "warmup_seconds must be a nonnegative integer")
        if self.start_utc >= self.end_utc:
            raise HistoryError("INVALID_ARGUMENT", "start_utc must be < end_utc")
        if self.availability_mode not in AVAILABILITY_MODES:
            raise HistoryError(
                "INVALID_ARGUMENT",
                f"unknown availability_mode {self.availability_mode!r}",
            )
        if self.expected_manifest is not None and not isinstance(
            self.expected_manifest, (str, Mapping)
        ):
            raise HistoryError(
                "INVALID_ARGUMENT", "expected_manifest must be a mapping or sha256"
            )

    @property
    def read_start_us(self) -> int:
        """读取下界（含预热）。"""
        return to_us(self.start_utc) - self.warmup_seconds * 1_000_000

    @property
    def read_end_us(self) -> int:
        """读取上界（不含）。"""
        return to_us(self.end_utc)

    @property
    def main_start_us(self) -> int:
        """主窗口下界（不含预热）。"""
        return to_us(self.start_utc)

    @property
    def main_end_us(self) -> int:
        """主窗口上界（不含）。"""
        return to_us(self.end_utc)


@dataclass(frozen=True)
class FeatureRow:
    """特征行：仅 OHLCV 与合法 startPrice。

    不含 ``end_price`` / ``outcome`` / ``resolved_at`` / ``settlement_state``。
    """

    kind: str
    source: str
    source_event_time_us: int
    available_at_us: int
    is_warmup: bool
    open_time_us: int | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: Decimal | None = None
    close_exclusive_us: int | None = None
    round_id: str | None = None
    start_price: Decimal | None = None


@dataclass(frozen=True)
class RoundMetadataRow:
    """round 身份元数据行（白名单投影）。

    结算状态 / 结算价只出现在 label 流或 coverage，不在此泄露。
    """

    kind: str
    source: str
    source_event_time_us: int
    available_at_us: int
    is_warmup: bool
    round_id: str
    series_slug: str
    market_id: str
    condition_id: str
    starts_at_us: int
    ends_at_us: int
    published_at_us: int | None = None


@dataclass(frozen=True)
class LabelRow:
    """官方标签行（只有合格最终结果才有资格）。"""

    kind: str
    source: str
    source_event_time_us: int
    available_at_us: int
    is_warmup: bool
    round_id: str
    official_outcome: str
    end_price: Decimal | None = None
    starts_at_us: int = 0
    ends_at_us: int = 0
    resolved_at_us: int | None = None


@dataclass
class Coverage:
    """覆盖统计（stored 与 as_of eligible 分别报告）。"""

    stored_rows: int = 0
    eligible_rows: int = 0
    main_window_rows: int = 0
    warmup_rows: int = 0
    per_day: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class HistoryWindow:
    """窄历史读取窗口：三个分离流 + 覆盖 + manifest。

    ``iter_features`` / ``iter_round_metadata`` / ``iter_labels`` 是三个
    **互不混合**的流。消费方在完整消费后必须调用 :meth:`verify_consumed`。
    """

    request: HistoryRequest
    status: str
    sources: tuple[str, ...]
    kinds: tuple[str, ...]
    units: Mapping[str, str]
    schema_version: int
    coverage: Coverage
    missing: list[dict[str, Any]] = field(default_factory=list)
    pending: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    availability_assumptions: list[str] = field(default_factory=list)
    content_manifest: dict[str, Any] = field(default_factory=dict)
    provenance_manifest: dict[str, Any] = field(default_factory=dict)
    content_sha256: str | None = None
    _features: list[FeatureRow] = field(default_factory=list, repr=False)
    _metadata: list[RoundMetadataRow] = field(default_factory=list, repr=False)
    _labels: list[LabelRow] = field(default_factory=list, repr=False)
    _consumed: bool = field(default=False, repr=False)
    _stream_factories: dict[str, Any] = field(default_factory=dict, repr=False)
    _stream_digests: dict[str, str] = field(default_factory=dict, repr=False)
    _verify_snapshot: Any = field(default=None, repr=False)

    def _iterate(self, name: str, fallback: Any) -> Iterator[Any]:
        self._stream_digests.pop(name, None)
        self._consumed = False
        digest = hashlib.sha256()
        rows = self._stream_factories[name]() if name in self._stream_factories else fallback
        for row in rows:
            digest.update((canonical_json(asdict(row)) + "\n").encode("utf-8"))
            yield row
        self._stream_digests[name] = digest.hexdigest()
        self._consumed = len(self._stream_digests) == 3

    def iter_features(self) -> Iterator[FeatureRow]:
        """迭代有界特征流，不混入标签。"""
        yield from self._iterate("features", self._features)

    def iter_round_metadata(self) -> Iterator[RoundMetadataRow]:
        """迭代有界身份元数据流。"""
        yield from self._iterate("metadata", self._metadata)

    def iter_labels(self) -> Iterator[LabelRow]:
        """迭代有界官方标签流。"""
        yield from self._iterate("labels", self._labels)

    def output_digest(self) -> str:
        """返回确定性输出摘要；未消费时返回读取阶段的预期摘要。"""
        if not self._consumed and self._stream_factories:
            return self.content_manifest["output_sha256"]
        if self._stream_digests:
            return sha256_hex(canonical_json(self._stream_digests))
        payload = {}
        for name, rows in (("features", self._features), ("metadata", self._metadata),
                           ("labels", self._labels)):
            digest = hashlib.sha256()
            for row in rows:
                digest.update((canonical_json(asdict(row)) + "\n").encode("utf-8"))
            payload[name] = digest.hexdigest()
        return sha256_hex(canonical_json(payload))

    def verify_consumed(self) -> str:
        """确认完整消费并返回内容 hash。

        Raises:
            HistoryError: ``INCOMPLETE_CONSUMPTION`` — 未完整消费。
        """
        if not self._consumed:
            raise HistoryError(
                "INCOMPLETE_CONSUMPTION",
                "all three streams must be consumed before verification",
            )
        if self._verify_snapshot is not None:
            self._verify_snapshot()
        digest = self.output_digest()
        expected = self.content_manifest.get("output_sha256")
        if expected and expected != digest:
            raise HistoryError(
                "DATASET_CHANGED", "consumed output digest differs from manifest"
            )
        return digest

    def mark_consumed(self) -> None:
        """标记三个流已被完整消费（由 reader 在产出全部行后调用）。"""
        if len(self._stream_digests) != 3:
            raise HistoryError("INCOMPLETE_CONSUMPTION", "consume all streams first")
        self._consumed = True


def _feature_payload(row: FeatureRow) -> dict[str, Any]:
    return {
        "kind": row.kind,
        "source": row.source,
        "source_event_time_us": row.source_event_time_us,
        "available_at_us": row.available_at_us,
        "is_warmup": row.is_warmup,
        "open_time_us": row.open_time_us,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "volume": row.volume,
        "close_exclusive_us": row.close_exclusive_us,
        "round_id": row.round_id,
        "start_price": row.start_price,
    }


def _metadata_payload(row: RoundMetadataRow) -> dict[str, Any]:
    return {
        "kind": row.kind,
        "source": row.source,
        "source_event_time_us": row.source_event_time_us,
        "available_at_us": row.available_at_us,
        "is_warmup": row.is_warmup,
        "round_id": row.round_id,
        "series_slug": row.series_slug,
        "market_id": row.market_id,
        "condition_id": row.condition_id,
        "starts_at_us": row.starts_at_us,
        "ends_at_us": row.ends_at_us,
        "published_at_us": row.published_at_us,
    }


def _label_payload(row: LabelRow) -> dict[str, Any]:
    return {
        "kind": row.kind,
        "source": row.source,
        "source_event_time_us": row.source_event_time_us,
        "available_at_us": row.available_at_us,
        "is_warmup": row.is_warmup,
        "round_id": row.round_id,
        "official_outcome": row.official_outcome,
        "end_price": row.end_price,
        "starts_at_us": row.starts_at_us,
        "ends_at_us": row.ends_at_us,
        "resolved_at_us": row.resolved_at_us,
    }


__all__ = [
    "AVAILABILITY_MODES",
    "AVAILABILITY_RULES",
    "CONTENT_MANIFEST_VERSION",
    "DATASET_KLINES",
    "DATASET_ROUNDS",
    "INTERVAL",
    "MARKET_TYPE",
    "SCHEMA_VERSION",
    "SERIES_SLUG",
    "SOURCE_KLINES",
    "SOURCE_ROUNDS",
    "SYMBOL",
    "Coverage",
    "FeatureRow",
    "HistoryError",
    "HistoryRequest",
    "HistoryWindow",
    "LabelRow",
    "RoundMetadataRow",
    "canonical_json",
    "ceil_ms_to_us",
    "decimal_text",
    "from_us",
    "parse_utc",
    "record_sha256",
    "sha256_hex",
    "to_us",
]
