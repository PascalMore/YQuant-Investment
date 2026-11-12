"""BTC5m 历史的采集节点 — 03-018 §6.3 / §6.4。

两个 extractor 都实现既有 ``BaseExtractor`` 协议（``source_type`` /
``validate_source`` / ``extract``）：

* :class:`PredictRoundExtractor` —— 一次只取一页（``first=100``）。
* :class:`BinanceKlineExtractor` —— 先 ``prepare_day`` 下载并校验 ZIP +
  CHECKSUM，再按 chunk 顺序读 CSV。

两者都**不**装 OCR、不调用 LLM、不访问其他 profile 配置。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ..extractors.base import BaseExtractor

from .common import (
    BINANCE_CHECKSUM_URL,
    BINANCE_ZIP_URL,
    ERR_ARCHIVE_NOT_PUBLISHED,
    ERR_BAD_CSV,
    ERR_CHECKSUM_MISMATCH,
    ERR_HTTP_FORBIDDEN,
    ERR_HTTP_UNAUTHORIZED,
    MAX_ZIP_COMPRESSED_BYTES,
    MAX_ZIP_UNCOMPRESSED_BYTES,
    PREDICT_BASE,
    SERIES_SLUG,
    Budget,
    HistoryHTTPError,
    RawArchive,
    day_bounds_us,
    http_get,
    utc_today,
)


@dataclass
class PredictPageSource:
    """Predict 一页请求的描述。

    Attributes:
        after: 不透明游标（``None`` 表示首页）。
        first: 页大小（最多 100）。
        status: 官方过滤状态（固定 ``ENDED``）。
    """

    after: str | None = None
    first: int = 100
    status: str = "ENDED"


@dataclass
class BinanceDaySource:
    """Binance 日归档描述。"""

    utc_date: str


@dataclass
class ZipChunkSource:
    """已校验 ZIP 内的一个 CSV chunk。"""

    raw_ref: str
    offset: int
    limit: int = 5000


@dataclass
class BufferedRoundSource:
    """已在本地抓取并筛选好的 round envelope（管道仍走真实 extractor 协议）。

    用于「同一轮抓取结果 → 逐日切片 → 管道入库」，避免对同一批数据再
    发一次网络请求。
    """

    records: list[dict[str, Any]] = field(default_factory=list)
    raw_ref: str | None = None
    raw_sha256: str | None = None


@dataclass
class ExtractResult:
    """一次 extract 的结果（记录 + 页 / chunk 证据）。"""

    records: list[dict[str, Any]] = field(default_factory=list)
    cursor: str | None = None
    next_after: str | None = None
    raw_ref: str | None = None
    raw_sha256: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def normalize_round_envelope(record: Any) -> dict[str, Any]:
    """Wrap an official flat category once; retain canonical internal envelopes.

    Ambiguous dual structures are rejected rather than choosing one identity or
    silently losing fields. Business identity/price/status validation stays in
    the existing transformer and validator.
    """
    if not isinstance(record, dict):
        raise HistoryHTTPError("PREDICT_API_ERROR", "round is not an object")
    markets = record.get("markets")
    if not isinstance(markets, list) or any(not isinstance(market, dict) for market in markets):
        raise HistoryHTTPError("PREDICT_API_ERROR", "markets is not an object list")
    if "category" in record:
        category = record["category"]
        if (not isinstance(category, dict) or "markets" in category
                or any(key not in {"category", "markets"} and not key.startswith("_")
                       for key in record)):
            raise HistoryHTTPError("PREDICT_API_ERROR", "ambiguous round envelope")
        return dict(record)
    return {"category": {key: value for key, value in record.items() if key != "markets"},
            "markets": markets}


class PredictRoundExtractor(BaseExtractor):
    """Predict BTC5m rounds 页采集器。"""

    @property
    def source_type(self) -> str:
        """来源标识。"""
        return "predict.fun"

    def __init__(self, archive: RawArchive | None = None) -> None:
        self._archive = archive or RawArchive()

    async def validate_source(self, source: Any) -> bool:
        """校验 source 是 :class:`PredictPageSource`。"""
        return isinstance(source, PredictPageSource)

    async def extract(self, source: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """抓取一页并返回原始 round envelope 列表。

        Args:
            source: :class:`PredictPageSource`。
            **kwargs: ``budget``（必需）、``api_key``（可选）。

        Returns:
            原始 round 字典列表（未映射字段）。

        Raises:
            HistoryHTTPError: HTTP 失败。
        """
        result = await self.extract_page(source, **kwargs)
        return result.records

    async def extract_page(
        self,
        source: PredictPageSource,
        *,
        budget: Budget,
        api_key: str | None = None,
    ) -> ExtractResult:
        """抓取一页并返回带游标 / raw 证据的结果。"""
        url = (
            f"{PREDICT_BASE}/v1/series/{SERIES_SLUG}/rounds"
            f"?status={source.status}&first={source.first}"
        )
        if source.after:
            from .common import url_escape

            url = f"{url}&after={url_escape(source.after, safe='')}"
        payload = http_get(url, budget=budget, api_key=api_key)
        from decimal import Decimal

        document = json.loads(payload.decode("utf-8"), parse_float=Decimal, parse_int=int)
        if document.get("success") is not True or not isinstance(document.get("data"), list):
            raise HistoryHTTPError("PREDICT_API_ERROR", "invalid response envelope")
        records = [normalize_round_envelope(record) for record in document["data"]]
        cursor = document.get("cursor")
        next_after = cursor if isinstance(cursor, str) and cursor else None
        raw_ref, raw_sha = self._archive.store_bytes(utc_today(), payload)
        ids = sorted({
            str(market["id"]) for record in records
            for market in record.get("markets", [])
            if market.get("id") is not None and market.get("seriesSlug") == SERIES_SLUG
        })
        status_refs = []
        logs_by_id = {}
        for offset in range(0, len(ids), 100):
            logs_payload = http_get(
                f"{PREDICT_BASE}/v1/markets/status-logs?ids={','.join(ids[offset:offset + 100])}",
                budget=budget, api_key=api_key,
            )
            logs_doc = json.loads(logs_payload.decode("utf-8"), parse_float=Decimal)
            if logs_doc.get("success") is not True or not isinstance(logs_doc.get("data"), list):
                raise HistoryHTTPError("PREDICT_API_ERROR", "invalid status logs")
            logs_ref, logs_sha = self._archive.store_bytes(utc_today(), logs_payload)
            status_refs.append({"raw_ref": logs_ref, "raw_sha256": logs_sha})
            for entry in logs_doc["data"]:
                market_id = str(entry.get("marketId"))
                if market_id not in ids or market_id in logs_by_id:
                    raise HistoryHTTPError("CONFLICT", "status log market identity")
                logs_by_id[market_id] = entry.get("logs", [])
        records = [dict(record, _status_logs=logs_by_id,
                        _status_raw_refs=status_refs) for record in records]
        return ExtractResult(
            records=records,
            cursor=cursor if isinstance(cursor, str) else None,
            next_after=next_after,
            raw_ref=raw_ref,
            raw_sha256=raw_sha,
            evidence={
                "after": source.after,
                "cursor": next_after,
                "count": len(records),
                "first_starts_at": (
                    records[0]["category"].get("startsAt") if records else None
                ),
            },
        )


    async def extract_pending(
        self, row: dict[str, Any], *, budget: Budget, api_key: str | None = None,
    ) -> ExtractResult:
        """Requery an explicit category/market identity, never search latest pages."""
        from .common import url_escape

        slug = row.get("round_slug")
        market_id = str(row.get("market_id", ""))
        if not slug or not market_id.isdecimal():
            raise HistoryHTTPError("PENDING_IDENTITY_MISSING")
        body = http_get(f"{PREDICT_BASE}/v1/categories/{url_escape(slug, safe='')}",
                        budget=budget, api_key=api_key)
        document = json.loads(body.decode(), parse_float=Decimal)
        category = document.get("data")
        if document.get("success") is not True or not isinstance(category, dict):
            raise HistoryHTTPError("PREDICT_API_ERROR")
        record = normalize_round_envelope(category)
        category = record["category"]
        markets = record["markets"]
        if (str(category.get("id")) != row.get("round_id") or category.get("slug") != slug
                or category.get("seriesSlug") != SERIES_SLUG
                or len([market for market in markets if str(market.get("id")) == market_id]) != 1):
            raise HistoryHTTPError("PENDING_IDENTITY_CONFLICT")
        raw_ref, raw_sha = self._archive.store_bytes(utc_today(), body)
        logs_body = http_get(f"{PREDICT_BASE}/v1/markets/status-logs?ids={market_id}",
                             budget=budget, api_key=api_key)
        logs = json.loads(logs_body.decode(), parse_float=Decimal)
        if (logs.get("success") is not True or not isinstance(logs.get("data"), list)
                or len(logs["data"]) != 1 or str(logs["data"][0].get("marketId")) != market_id):
            raise HistoryHTTPError("PENDING_IDENTITY_CONFLICT")
        logs_ref, logs_sha = self._archive.store_bytes(utc_today(), logs_body)
        record.update(_status_logs={market_id: logs["data"][0].get("logs", [])},
                      _status_raw_refs=[{"raw_ref": logs_ref, "raw_sha256": logs_sha}])
        return ExtractResult(records=[record], raw_ref=raw_ref, raw_sha256=raw_sha)


class BufferedRoundExtractor(BaseExtractor):
    """回放已抓取的 round envelope（不联网）。"""

    @property
    def source_type(self) -> str:
        """来源标识。"""
        return "predict.fun"

    async def validate_source(self, source: Any) -> bool:
        """校验 source 是 :class:`BufferedRoundSource`。"""
        return isinstance(source, BufferedRoundSource)

    async def extract(self, source: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """返回已缓冲的 round envelope 列表。"""
        if not isinstance(source, BufferedRoundSource):
            raise TypeError(f"unsupported source type {type(source).__name__}")
        return list(source.records)


class BinanceKlineExtractor(BaseExtractor):
    """Binance spot BTCUSDT 1s 日归档采集器。"""

    @property
    def source_type(self) -> str:
        """来源标识。"""
        return "binance-vision"

    def __init__(self, archive: RawArchive | None = None) -> None:
        self._archive = archive or RawArchive()

    async def validate_source(self, source: Any) -> bool:
        """校验 source 是 :class:`BinanceDaySource` 或 :class:`ZipChunkSource`。"""
        return isinstance(source, (BinanceDaySource, ZipChunkSource))

    async def extract(self, source: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """按 source 类型执行日准备或 chunk 读取。"""
        if isinstance(source, BinanceDaySource):
            prepared = await self.prepare_day(source, **kwargs)
            return prepared["rows"]
        if isinstance(source, ZipChunkSource):
            return await self.extract_chunk(source, **kwargs)
        raise TypeError(f"unsupported source type {type(source).__name__}")

    async def prepare_day(
        self,
        source: BinanceDaySource,
        *,
        budget: Budget,
    ) -> dict[str, Any]:
        """下载并校验当日 ZIP + CHECKSUM，返回 CSV 行与 raw 证据。

        Raises:
            HistoryHTTPError: 404（未发布 / 缺失）、checksum 不符、坏 ZIP。
        """
        zip_url = BINANCE_ZIP_URL.format(date=source.utc_date)
        checksum_url = BINANCE_CHECKSUM_URL.format(date=source.utc_date)
        try:
            checksum_bytes = http_get(checksum_url, budget=budget)
            zip_bytes = http_get(zip_url, budget=budget)
        except HistoryHTTPError as exc:
            if exc.code in (ERR_HTTP_UNAUTHORIZED, ERR_HTTP_FORBIDDEN):
                raise
            if "404" in str(exc):
                raise HistoryHTTPError(
                    ERR_ARCHIVE_NOT_PUBLISHED, source.utc_date
                ) from None
            raise

        if len(zip_bytes) > MAX_ZIP_COMPRESSED_BYTES:
            raise HistoryHTTPError("ZIP_TOO_LARGE", str(len(zip_bytes)))

        expected = _parse_checksum(checksum_bytes)
        checksum_fields = checksum_bytes.decode("utf-8").split()
        zip_name = f"BTCUSDT-1s-{source.utc_date}.zip"
        if len(checksum_fields) != 2 or checksum_fields[1].lstrip("*") != zip_name:
            raise HistoryHTTPError(ERR_CHECKSUM_MISMATCH, "archive filename mismatch")
        actual = hashlib.sha256(zip_bytes).hexdigest()
        if expected != actual:
            raise HistoryHTTPError(ERR_CHECKSUM_MISMATCH, source.utc_date)

        raw_ref, raw_sha = self._archive.store_bytes(
            source.utc_date, zip_bytes, kind="binance"
        )
        checksum_ref, checksum_sha = self._archive.store_bytes(
            source.utc_date, checksum_bytes, kind="binance-checksum"
        )
        manifest_ref, _ = self._archive.store_bytes(
            source.utc_date, json.dumps({
                "utc_date": source.utc_date, "zip_name": zip_name,
                "raw_ref": raw_ref, "raw_sha256": raw_sha,
                "checksum_ref": checksum_ref, "checksum_sha256": checksum_sha,
            }, sort_keys=True).encode("utf-8"), kind="binance-manifest",
        )
        rows = self._read_csv_rows(zip_bytes, utc_date=source.utc_date)
        return {
            "manifest_ref": manifest_ref,
            "checksum_ref": checksum_ref,
            "rows": rows,
            "raw_ref": raw_ref,
            "raw_sha256": raw_sha,
            "zip_bytes": len(zip_bytes),
            "checksum": expected,
            "row_count": len(rows),
        }

    async def extract_chunk(
        self,
        source: ZipChunkSource,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """从已归档 ZIP 读一个 CSV chunk（不重复下载）。"""
        path = self._archive.resolve(source.raw_ref)
        rows = self._read_csv_rows(path.read_bytes())
        return rows[source.offset : source.offset + source.limit]

    @staticmethod
    def _read_csv_rows(zip_bytes: bytes, *, utc_date: str | None = None) -> list[dict[str, Any]]:
        """解析 ZIP 内唯一 CSV 成员，返回原始字符串行（``{"cols", "row_number"}``）。

        Raises:
            HistoryHTTPError: CRC 失败 / 多成员 / 解压超限 / 路径穿越。
        """
        try:
            archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            raise HistoryHTTPError(ERR_BAD_CSV, "bad zip") from exc
        with archive:
            if archive.testzip() is not None:
                raise HistoryHTTPError(ERR_BAD_CSV, "crc failure")
            names = [
                info.filename
                for info in archive.infolist()
                if not info.is_dir()
            ]
            if len(names) != 1:
                raise HistoryHTTPError(ERR_BAD_CSV, f"members={len(names)}")
            info = archive.getinfo(names[0])
            if info.file_size > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise HistoryHTTPError("ZIP_UNCOMPRESSED_TOO_LARGE", str(info.file_size))
            if "/" in names[0] or names[0].startswith(".."):
                raise HistoryHTTPError(ERR_BAD_CSV, "unsafe member path")
            # The archive itself identifies the UTC day, including chunk replay.
            import re
            match = re.fullmatch(r"BTCUSDT-1s-(\d{4}-\d{2}-\d{2})\.csv", names[0])
            if not match or (utc_date is not None and match[1] != utc_date):
                raise HistoryHTTPError(ERR_BAD_CSV, "unexpected member name")
            from .common import day_bounds_us
            begin, stop = day_bounds_us(match[1])
            text = archive.read(names[0]).decode("utf-8")
        rows = [row for row in csv.reader(io.StringIO(text)) if row]
        previous = None
        for row in rows:
            if len(row) != 12 or not row[0].isascii() or not row[0].isdecimal():
                raise HistoryHTTPError(ERR_BAD_CSV, "invalid CSV schema/open time")
            opened = int(row[0])
            if (not begin <= opened < stop or opened % 1_000_000
                    or (previous is not None and opened <= previous)):
                raise HistoryHTTPError(ERR_BAD_CSV, "UTC day/order/duplicate violation")
            previous = opened
        return [
            {"cols": row, "row_number": index}
            for index, row in enumerate(rows, start=1)
        ]


def _parse_checksum(payload: bytes) -> str:
    """解析官方 ``.CHECKSUM`` 文件（``<sha256>  <zip name>``）。"""
    text = payload.decode("utf-8").strip()
    if not text:
        raise HistoryHTTPError(ERR_CHECKSUM_MISMATCH, "empty checksum")
    return text.split()[0].lower()


__all__ = [
    "BinanceDaySource",
    "BinanceKlineExtractor",
    "BufferedRoundExtractor",
    "BufferedRoundSource",
    "ExtractResult",
    "PredictPageSource",
    "PredictRoundExtractor",
    "ZipChunkSource",
]
