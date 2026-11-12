"""BTC5m 历史的公共常量、预算、raw 归档与受限 HTTP — 03-018 §6 / §7。

本模块**不** import Mongo、**不**解析行情。它只提供：

* 固定来源 URL / 集合名 / 索引名常量；
* :class:`Budget` — 日 / 墙钟 / 请求 / 批大小预算；
* :class:`RawArchive` — raw 落盘（临时文件 → fsync → 原子替换）；
* :func:`http_get` — 仅白名单公开 GET 的受限 HTTP（含重试 / 退避）；
* 脱敏报告辅助。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import hashlib
from http.client import IncompleteRead
import json
import os
import time
import urllib.error
import urllib.request
import re
from urllib.parse import parse_qs, urlsplit, quote as url_escape
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

#: 固定采集根。
RAW_ROOT = Path("data/source/predict-btc5m-history")

#: Predict API 基础 URL。
PREDICT_BASE = "https://api.predict.fun"

#: 固定 series slug。
SERIES_SLUG = "btc-updown-5m"

#: 固定 Binance 日归档模板。
BINANCE_ZIP_URL = (
    "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
    "BTCUSDT-1s-{date}.zip"
)
BINANCE_CHECKSUM_URL = BINANCE_ZIP_URL + ".CHECKSUM"

#: 目标集合。
ROUNDS_COLLECTION = "03_data_ud_predict_btc5m_rounds"
KLINES_COLLECTION = "03_data_ud_binance_spot_klines_1s"
INGESTION_COLLECTION = "03_data_ud_history_ingestion"

#: 固定数据集标识。
DATASET_ROUNDS = "predict_btc5m_rounds"
DATASET_KLINES = "binance_spot_btcusdt_1s"

#: 固定来源标识。
SOURCE_ROUNDS = "predict.fun"
SOURCE_KLINES = "binance-vision"

#: 唯一允许的公开 GET 路径前缀（白名单）。
ALLOWED_HTTP_PREFIXES: tuple[str, ...] = (
    "https://api.predict.fun/v1/series/",
    "https://api.predict.fun/v1/markets/",
    "https://api.predict.fun/v1/categories/",
    "https://data.binance.vision/data/spot/daily/klines/",
)

#: 退出码（本题专属）。
EXIT_OK = 0
EXIT_PARTIAL = 10
EXIT_FAIL = 20
EXIT_BUSY = 30
EXIT_TIMEOUT = 40

#: HTTP 单次超时（秒）与最多尝试次数。
HTTP_TIMEOUT_SECONDS = 30
HTTP_MAX_ATTEMPTS = 3

#: ZIP 大小上限（压缩 / 解压）。
MAX_ZIP_COMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 512 * 1024 * 1024

#: 稳定错误码。
ERR_CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
ERR_ARCHIVE_NOT_PUBLISHED = "ARCHIVE_NOT_PUBLISHED_OR_MISSING"
ERR_BAD_CSV = "BAD_CSV"
ERR_MISSING_SECONDS = "MISSING_SECONDS"
ERR_DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"
ERR_HTTP_UNAUTHORIZED = "HTTP_UNAUTHORIZED"
ERR_HTTP_FORBIDDEN = "HTTP_FORBIDDEN"
ERR_HTTP_RATE_LIMITED = "HTTP_RATE_LIMITED"
ERR_HTTP_SERVER_ERROR = "HTTP_SERVER_ERROR"
ERR_BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
ERR_NOT_INITIALIZED = "NOT_INITIALIZED"
ERR_CONFLICT = "CONFLICT"
ERR_READBACK_MISMATCH = "READBACK_MISMATCH"
ERR_BUSY = "BUSY"


class HistoryBudgetError(RuntimeError):
    """预算耗尽（有界退出）。"""


class HistoryHTTPError(RuntimeError):
    """HTTP 失败（带稳定错误码，不含 header / body）。"""

    def __init__(self, code: str, message: str = "", *, retry_at: datetime | None = None) -> None:
        self.code = code
        self.retry_at = retry_at
        super().__init__(f"{code}: {message}" if message else code)


@dataclass
class Budget:
    """有界预算（日 / 墙钟 / 请求 / chunk）。

    Attributes:
        max_days_per_source: 每源每日最多处理日预算。
        wall_seconds: 总墙钟预算。
        max_requests: 本轮最多 HTTP 请求数。
        chunk_size: 价格 chunk 行数上限（≤5000）。
    """

    max_days_per_source: int = 7
    wall_seconds: float = 1800
    max_requests: int = 1000
    chunk_size: int = 5000
    requests_used: int = 0
    _started_at: float = field(default_factory=time.monotonic, repr=False)
    _parent: Budget | None = field(default=None, repr=False)

    def fork(self, *, requests: int, seconds: float) -> Budget:
        """Reserve a bounded lane while charging every request to the global budget."""
        return Budget(
            max_days_per_source=self.max_days_per_source,
            wall_seconds=min(self.remaining(), max(0.0, seconds)) + 20,
            max_requests=min(max(0, requests), self.max_requests - self.requests_used),
            chunk_size=self.chunk_size, _parent=self,
        )

    def validate(self) -> None:
        """校验预算范围。

        Raises:
            HistoryBudgetError: 参数越界。
        """
        if not 1 <= self.max_days_per_source <= 92:
            raise HistoryBudgetError("max_days_per_source must be within 1..92")
        if not 30 <= self.wall_seconds <= 3600:
            raise HistoryBudgetError("wall_seconds must be within 30..3600")
        if not 1 <= self.max_requests <= 5000:
            raise HistoryBudgetError("max_requests must be within 1..5000")
        if not 1 <= self.chunk_size <= 5000:
            raise HistoryBudgetError("chunk_size must be within 1..5000")

    def elapsed(self) -> float:
        """返回已用墙钟秒数（monotonic）。"""
        return time.monotonic() - self._started_at

    def remaining(self) -> float:
        """返回剩余墙钟秒数（保留最后 20 秒写总结）。"""
        remaining = self.wall_seconds - self.elapsed() - 20.0
        return min(remaining, self._parent.remaining()) if self._parent else remaining

    def take_request(self) -> None:
        """占用一个 HTTP 请求名额。

        Raises:
            HistoryBudgetError: 请求预算耗尽或墙钟不足。
        """
        if self.requests_used >= self.max_requests:
            raise HistoryBudgetError(ERR_BUDGET_EXHAUSTED)
        if self.remaining() <= 0:
            raise HistoryBudgetError(ERR_BUDGET_EXHAUSTED)
        if self._parent:
            self._parent.take_request()
        self.requests_used += 1

    def exhausted(self) -> bool:
        """返回是否已耗尽（请求或墙钟）。"""
        return (self.requests_used >= self.max_requests or self.remaining() <= 0
                or bool(self._parent and self._parent.exhausted()))


class RawArchive:
    """raw 归档（原子落盘 + 精确字节 hash）。

    路径规则（SPEC §5.1）：

    * Predict：``<root>/predict.fun/<UTC 日>/<sha256>.json``
    * Binance：``<root>/binance-vision/<UTC 日>/<官方 ZIP 名>/<sha256>.zip``
    """

    def __init__(self, root: Path | str = RAW_ROOT) -> None:
        self._root = Path(root)

    def _predict_dir(self, utc_date: str) -> Path:
        return self._root / "predict.fun" / utc_date

    def _binance_dir(self, utc_date: str, zip_name: str) -> Path:
        return self._root / "binance-vision" / utc_date / zip_name

    def store_bytes(
        self, utc_date: str, payload: bytes, *, kind: str = "predict"
    ) -> tuple[str, str]:
        """原子落盘原始字节并返回 ``(raw_ref, sha256)``。

        Args:
            utc_date: 实际抓取 UTC 日（``YYYY-MM-DD``）。
            payload: 原始精确字节。
            kind: ``predict`` 或 ``binance``。

        Returns:
            ``(raw_ref, raw_sha256)``；``raw_ref`` 是项目相对路径。
        """
        day_bounds_us(utc_date)
        if kind not in {"predict", "binance", "binance-checksum", "binance-manifest"}:
            raise HistoryHTTPError("RAW_KIND_NOT_ALLOWED")
        digest = hashlib.sha256(payload).hexdigest()
        if kind in ("binance", "binance-checksum", "binance-manifest"):
            target_dir = self._binance_dir(utc_date, _binance_zip_name(utc_date))
        else:
            target_dir = self._predict_dir(utc_date)
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = {"binance": ".zip", "binance-checksum": ".CHECKSUM"}.get(kind, ".json")
        target = target_dir / f"{digest}{suffix}"
        if not target.exists():
            tmp = target.with_suffix(target.suffix + ".part")
            with open(tmp, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        return str(target), digest

    def store_json(self, utc_date: str, payload: Any) -> tuple[str, str]:
        """把 JSON 响应的**原始文本**落盘并返回 ``(raw_ref, sha256)``。"""
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return self.store_bytes(utc_date, text.encode("utf-8"), kind="predict")

    def read_bytes(self, raw_ref: str) -> bytes:
        """按 raw_ref 读取原始字节。"""
        return self.resolve(raw_ref).read_bytes()

    def resolve(self, raw_ref: str) -> Path:
        """Resolve an exact archive reference; reject escape and symlink traversal."""
        path = Path(raw_ref).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise HistoryHTTPError("RAW_PATH_NOT_ALLOWED")
        parts = path.relative_to(self._root.resolve()).parts
        if (len(parts) < 3 or not re.fullmatch(r"[0-9a-f]{64}", path.stem)
                or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", parts[1])):
            raise HistoryHTTPError("RAW_PATH_NOT_ALLOWED")
        if not ((parts[0] == "predict.fun" and len(parts) == 3 and path.suffix == ".json")
                or (parts[0] == "binance-vision" and len(parts) == 4
                    and parts[2] == _binance_zip_name(parts[1])
                    and path.suffix in {".zip", ".CHECKSUM", ".json"})):
            raise HistoryHTTPError("RAW_PATH_NOT_ALLOWED")
        return path


def _binance_zip_name(utc_date: str) -> str:
    return f"BTCUSDT-1s-{utc_date}.zip"


# ---------------------------------------------------------------------------
# 受限 HTTP
# ---------------------------------------------------------------------------


def _is_allowed_url(url: str) -> bool:
    """Match exact public origins, paths and query shapes, not arbitrary prefixes."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(values) != 1 for values in query.values()):
        return False
    if parsed.netloc == "api.predict.fun":
        if parsed.path == f"/v1/series/{SERIES_SLUG}/rounds":
            return (set(query) <= {"status", "first", "after"}
                    and query.get("status", ["ENDED"]) == ["ENDED"]
                    and query.get("first", ["100"])[0].isdigit()
                    and 1 <= int(query.get("first", ["100"])[0]) <= 100)
        if parsed.path == "/v1/markets/status-logs":
            ids = query.get("ids", [""])[0].split(",")
            return set(query) == {"ids"} and 1 <= len(ids) <= 100 and all(
                re.fullmatch(r"[0-9]+", market_id) for market_id in ids
            )
        return not query and bool(re.fullmatch(
            r"/v1/(markets/[0-9]+|categories/[A-Za-z0-9_-]+)", parsed.path
        ))
    return (parsed.netloc == "data.binance.vision" and not query and bool(re.fullmatch(
        r"/data/spot/daily/klines/BTCUSDT/1s/BTCUSDT-1s-[0-9]{4}-[0-9]{2}-[0-9]{2}[.]zip(?:[.]CHECKSUM)?",
        parsed.path,
    )))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HistoryHTTPError("HTTP_REDIRECT_NOT_ALLOWED")


def _open_http(request: Any, *, timeout: float) -> Any:
    """Open without redirects; API credentials cannot leave the original request."""
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def http_get(
    url: str,
    *,
    budget: Budget,
    api_key: str | None = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    max_attempts: int = HTTP_MAX_ATTEMPTS,
) -> bytes:
    """执行一次白名单公开 GET（有限重试 / 退避）。

    Args:
        url: 完整 URL（必须命中 :data:`ALLOWED_HTTP_PREFIXES`）。
        budget: 预算（占用请求名额）。
        api_key: 可选 API key（只作为 ``X-API-Key`` 头，不落盘、不打印）。
        timeout: 单次超时秒数。
        max_attempts: 最多尝试次数。

    Returns:
        响应原始字节。

    Raises:
        HistoryHTTPError: 非白名单 URL / 401 / 403 / 429 / 5xx / 网络错误。
    """
    if not _is_allowed_url(url):
        raise HistoryHTTPError("HTTP_URL_NOT_ALLOWED")

    last_code = ""
    retry_at = None
    for attempt in range(1, max_attempts + 1):
        budget.take_request()
        request = urllib.request.Request(url, method="GET")
        if urlsplit(url).netloc == "api.predict.fun":
            request.add_header("User-Agent", "YQuant-DataHistory/1.0")
        if api_key:
            request.add_header("X-API-Key", api_key)
        try:
            with _open_http(request, timeout=min(timeout, budget.remaining())) as response:
                limit = MAX_ZIP_COMPRESSED_BYTES if url.endswith(".zip") else 8 * 1024 * 1024
                payload = response.read(limit + 1)
                if len(payload) > limit:
                    raise HistoryHTTPError("HTTP_RESPONSE_TOO_LARGE")
                if api_key and api_key.encode() in payload:
                    raise HistoryHTTPError("HTTP_SECRET_IN_RESPONSE")
                return payload
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            last_code = str(status)
            if status in (401, 403):
                raise HistoryHTTPError(
                    ERR_HTTP_UNAUTHORIZED if status == 401 else ERR_HTTP_FORBIDDEN,
                    f"status={status}",
                ) from None
            if status == 429 or 500 <= status < 600:
                service_due = _retry_after_at(exc.headers.get("Retry-After") if exc.headers else None)
                if service_due is not None:
                    retry_at = max(retry_at, service_due) if retry_at else service_due
            if status == 429:
                if attempt >= max_attempts or (retry_at and
                        (retry_at - utc_now()).total_seconds() >= budget.remaining()):
                    raise HistoryHTTPError(ERR_HTTP_RATE_LIMITED, "status=429", retry_at=retry_at) from None
                _sleep_backoff(attempt, budget, not_before=retry_at)
                continue
            if 500 <= status < 600:
                if attempt >= max_attempts or (retry_at and
                        (retry_at - utc_now()).total_seconds() >= budget.remaining()):
                    raise HistoryHTTPError(ERR_HTTP_SERVER_ERROR, f"status={status}", retry_at=retry_at) from None
                _sleep_backoff(attempt, budget, not_before=retry_at)
                continue
            raise HistoryHTTPError("HTTP_ERROR", f"status={status}") from None
        except (urllib.error.URLError, IncompleteRead):
            if attempt >= max_attempts:
                raise HistoryHTTPError("HTTP_NETWORK_ERROR", "urlopen failed") from None
            _sleep_backoff(attempt, budget)
    raise HistoryHTTPError("HTTP_ERROR", last_code or "exhausted")


def _retry_after_at(value: str | None) -> datetime | None:
    """Retain only a valid server due timestamp, never the header text."""
    from datetime import timedelta
    from email.utils import parsedate_to_datetime

    if not value:
        return None
    try:
        if value.strip().isdecimal():
            return utc_now() + timedelta(seconds=int(value))
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return date.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        return None


def _sleep_backoff(attempt: int, budget: Budget, *, not_before: datetime | None = None) -> None:
    """有限指数退避（受剩余墙钟约束），不提前于官方 Retry-After。"""
    delay = min(2 ** (attempt - 1), 8)
    if not_before:
        delay = max(delay, (not_before - utc_now()).total_seconds())
    remaining = budget.remaining()
    if remaining <= 0:
        raise HistoryBudgetError(ERR_BUDGET_EXHAUSTED)
    time.sleep(min(delay, max(0.0, remaining)))


# ---------------------------------------------------------------------------
# 时间 / 脱敏
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """返回保留实际微秒的 naive-UTC 时钟，存储层再向上取毫秒。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_today() -> str:
    """返回当前 UTC 日（``YYYY-MM-DD``）。"""
    return utc_now().strftime("%Y-%m-%d")


def day_bounds_us(utc_date: str) -> tuple[int, int]:
    """返回某 UTC 日的 ``[start_us, end_us)`` 半开边界。"""
    from datetime import datetime as _dt

    day = _dt.strptime(utc_date, "%Y-%m-%d")
    epoch = _dt(1970, 1, 1)
    start_us = int((day - epoch).total_seconds()) * 1_000_000
    return start_us, start_us + 86_400_000_000


def redact(text: str, secrets: Mapping[str, str] | None = None) -> str:
    """把已知 secret 值替换为 ``[REDACTED]``。"""
    if not secrets:
        return text
    out = text
    for value in secrets.values():
        if value:
            out = out.replace(value, "[REDACTED]")
    return out


__all__ = [
    "ALLOWED_HTTP_PREFIXES",
    "BINANCE_CHECKSUM_URL",
    "BINANCE_ZIP_URL",
    "DATASET_KLINES",
    "DATASET_ROUNDS",
    "ERR_ARCHIVE_NOT_PUBLISHED",
    "ERR_BAD_CSV",
    "ERR_BUDGET_EXHAUSTED",
    "ERR_BUSY",
    "ERR_CHECKSUM_MISMATCH",
    "ERR_CONFLICT",
    "ERR_DUPLICATE_CONFLICT",
    "ERR_HTTP_FORBIDDEN",
    "ERR_HTTP_RATE_LIMITED",
    "ERR_HTTP_SERVER_ERROR",
    "ERR_HTTP_UNAUTHORIZED",
    "ERR_MISSING_SECONDS",
    "ERR_NOT_INITIALIZED",
    "ERR_READBACK_MISMATCH",
    "EXIT_BUSY",
    "EXIT_FAIL",
    "EXIT_OK",
    "EXIT_PARTIAL",
    "EXIT_TIMEOUT",
    "HTTP_MAX_ATTEMPTS",
    "HTTP_TIMEOUT_SECONDS",
    "INGESTION_COLLECTION",
    "KLINES_COLLECTION",
    "MAX_ZIP_COMPRESSED_BYTES",
    "MAX_ZIP_UNCOMPRESSED_BYTES",
    "PREDICT_BASE",
    "RAW_ROOT",
    "ROUNDS_COLLECTION",
    "SERIES_SLUG",
    "SOURCE_KLINES",
    "SOURCE_ROUNDS",
    "Budget",
    "HistoryBudgetError",
    "HistoryHTTPError",
    "RawArchive",
    "day_bounds_us",
    "http_get",
    "redact",
    "utc_now",
    "utc_today",
]
