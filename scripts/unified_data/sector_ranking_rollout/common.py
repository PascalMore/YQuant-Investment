"""03-016 rollout shared components — 4 Gate CLIs 共用（DESIGN-03-016 V0.4 §3.3）。

本模块提供：

* 退出码常量（SPEC G0-C-004：0/1/2/3/4）。
* :class:`ConnLoader` — 唯一受控连接源（CL-1 ~ CL-6）：仅 ``MONGODB_HOST`` /
  ``MONGODB_PORT`` / ``MONGODB_USERNAME`` / ``MONGODB_PASSWORD`` /
  ``MONGODB_DATABASE`` 五键组件式构造；**不允许 URI / prefix / alias /
  fallback**；缺失任一必需键 → fail-fast EXIT_CONN(3)，仅报告键名；
  fingerprint 只含结构字段，不含任何连接值。
* :class:`BudgetReader` — Gate-1/3 查询强制层（G1-B-001 ~ G1-B-007）：
  查询类型白名单（count/distinct/find/aggregate）、过滤强制（白名单字段
  ``full_symbol``（SW L1 行业指数，值集由 ``stock_sector_info`` L1 universe
  派生）/ ``trade_date`` / ``classify_system``（``stock_sector_info`` 查询用）
  至少一个）、单次 find limit 上限、maxTimeMS/serverSelectionTimeoutMS 超时、
  预算统计。**不再使用** ``sector_code``（801* 前缀）或 ``index_basic_info``
  ``market=\"CN\"`` 作为 L1 主路径过滤（L1 契约校正，SPEC G1-B-002）。
* :func:`redact` / :func:`scan_secrets` — secrets 脱敏与泄露扫描
  （G0-C-005；泄露类别 ``uri_with_credentials`` / ``password_value`` /
  ``token_value`` / ``secret_value``）。
* ReportWriter 家族 — :func:`resolve_report_dir` / :func:`write_report` /
  :func:`log_jsonl`（G0-C-007/008/010）。
* 交易日状态检查（SPEC G4-P-001 ~ G4-P-010，F2 闭合）：:class:`SessionStatus`
  枚举、:class:`TradeCalendar` 抽象 + :class:`FakeTradeCalendar` 测试注入、
  :class:`CompletedSessionPolicy`（Asia/Shanghai 15:00 cutoff；FUTURE /
  TODAY_UNCLOSED 抛 ``ValueError``；calendar=None → fail-closed）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
import os
import re
import time as time_mod
from abc import ABC, abstractmethod
from datetime import date, datetime, time as dt_time, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from skills.data.unified_data.models.domain.sector_ranking import (
    is_valid_trade_date,
)

# ---------------------------------------------------------------------------
# 退出码常量（SPEC G0-C-004）
# ---------------------------------------------------------------------------

EXIT_OK = 0        # 成功（dry-run / apply / verify 全过）
EXIT_PARAM = 1     # 参数/前置校验失败
EXIT_STOP = 2      # 停止条件命中（G1-S / G2-S / G3-S / G4-S / SC-016-G0-1）
EXIT_CONN = 3      # 连接/凭据失败（fail-fast，不降级）
EXIT_VERIFY = 4    # verify 失败

# ---------------------------------------------------------------------------
# 连接契约常量（CL-1 ~ CL-6）
# ---------------------------------------------------------------------------

REQUIRED_CONN_KEYS: tuple[str, ...] = (
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_USERNAME",
    "MONGODB_PASSWORD",
    "MONGODB_DATABASE",
)
CONN_SOURCE = "MONGODB_*"

_CLIENT_TIMEOUT_MS = 10_000  # serverSelectionTimeoutMS / connectTimeoutMS（G0-C-006 ≤10s）


class ConnLoader:
    """唯一受控连接源加载器（组件式构造，无 URI / prefix / alias / fallback）。

    Args:
        env: 环境映射（测试显式注入；``None`` 时读 ``os.environ``）。
        client_factory: ``pymongo.MongoClient`` 或等价构造（测试注入
            ``mongomock.MongoClient``，CL-5）。
    """

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._env: Mapping[str, str] = env if env is not None else os.environ
        self._client_factory: Callable[..., Any] = (
            client_factory if client_factory is not None else self._default_client
        )

    @staticmethod
    def _default_client(**kwargs: Any) -> Any:
        # 延迟 import：仅在生产 apply 路径构造真实 pymongo。
        from pymongo import MongoClient

        return MongoClient(**kwargs)

    # ------------------------------------------------------------------
    # 结构探测（不含值）
    # ------------------------------------------------------------------

    def describe_missing(self) -> list[str]:
        """返回缺失的必需键名列表（不含值，CL-3）。"""
        return [key for key in REQUIRED_CONN_KEYS if not self._env.get(key)]

    def fingerprint(self) -> dict[str, Any]:
        """连接结构指纹（CL-6）：只含 source 标签 + keys_present + auth_configured。"""
        return {
            "source": CONN_SOURCE,
            "keys_present": [key for key in REQUIRED_CONN_KEYS if self._env.get(key)],
            "auth_configured": bool(
                self._env.get("MONGODB_USERNAME") and self._env.get("MONGODB_PASSWORD")
            ),
        }

    def secret_entries(self) -> list[tuple[str, str]]:
        """(泄露类别, 值) 对，供 redact / scan_secrets 使用；绝不打印。"""
        entries: list[tuple[str, str]] = []
        for key, kind in (
            ("MONGODB_HOST", "secret_value"),
            ("MONGODB_PORT", "secret_value"),
            ("MONGODB_USERNAME", "secret_value"),
            ("MONGODB_DATABASE", "secret_value"),
        ):
            value = self._env.get(key)
            if value:
                entries.append((kind, value))
        password = self._env.get("MONGODB_PASSWORD")
        if password:
            entries.append(("password_value", password))
        return entries

    # ------------------------------------------------------------------
    # 连接构造（组件式；缺失键 → fail-fast）
    # ------------------------------------------------------------------

    def load_client(self) -> Any:
        missing = self.describe_missing()
        if missing:
            raise MissingConnectionKeyError(missing)
        return self._client_factory(
            host=self._env["MONGODB_HOST"],
            port=int(self._env["MONGODB_PORT"]),
            username=self._env["MONGODB_USERNAME"],
            password=self._env["MONGODB_PASSWORD"],
            authSource=self._env["MONGODB_DATABASE"],
            serverSelectionTimeoutMS=_CLIENT_TIMEOUT_MS,
            connectTimeoutMS=_CLIENT_TIMEOUT_MS,
        )

    def load_db(self) -> Any:
        client = self.load_client()
        return client.get_database(self._env["MONGODB_DATABASE"])


class MissingConnectionKeyError(Exception):
    """缺失必需连接键（CL-3 → EXIT_CONN(3)）。"""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__(
            "missing required MONGODB_* connection key(s): "
            + ", ".join(self.missing)
        )


# ---------------------------------------------------------------------------
# BudgetReader（G1-B-001 ~ G1-B-007）
# ---------------------------------------------------------------------------

# 过滤白名单（G1-B-002，F3 闭合 + L1 契约校正：find 与 aggregate 首 stage
# 同一规则；不再使用 sector_code / market 作为 L1 主路径过滤）
ALLOWED_FILTER_FIELDS: frozenset[str] = frozenset(
    {"full_symbol", "trade_date", "classify_system"}
)

# realtime/intraday 标记（G1-C-005 / G3-B-009 / RT-4）
REALTIME_MARKERS: frozenset[str] = frozenset({"realtime", "intraday", "rt"})


class BudgetViolation(Exception):
    """查询预算违规（G1-S-007 → 退出码 2）。"""


def _validate_filter(filter: Mapping[str, Any] | None) -> dict[str, Any]:
    """find filter 与 aggregate 首 stage 共用的过滤强制校验。"""
    if not filter:
        raise BudgetViolation("empty filter is forbidden (G1-B-005)")
    if not any(key in ALLOWED_FILTER_FIELDS for key in filter):
        raise BudgetViolation(
            "filter must contain at least one allow-listed field "
            f"{sorted(ALLOWED_FILTER_FIELDS)}, got {sorted(filter)}"
        )
    return dict(filter)


def _validate_pipeline(pipeline: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not pipeline:
        raise BudgetViolation("empty pipeline is forbidden (G1-B-005)")
    first = dict(pipeline[0])
    if set(first.keys()) != {"$match"}:
        raise BudgetViolation("aggregate first stage must be $match (G1-B-002)")
    _validate_filter(first["$match"])
    return [dict(s) for s in pipeline]


class BudgetReader:
    """Gate-1/3 查询强制层：白名单方法 + 过滤校验 + 条数/超时上限 + 统计。

    Args:
        db: pymongo / mongomock Database。
        max_find: 单次 find limit 上限（G1-B-003，默认 1000）。
        max_time_ms: 每次查询 maxTimeMS（G1-B-004，默认 30000）。
        server_selection_timeout_ms: serverSelectionTimeoutMS（默认 10000）。
        cumulative_rows_limit: 累计命中行数上限（G1-B-006，**Gate-1 scope**；
            默认 100000）。``None`` 禁用全局累计阻断（G3-B-019，Gate-3
            专用——job 层无全局阈值）。
        day_rows_limit: 日级命中行数上限（G3-B-018，**Gate-3 专用**；默认
            ``None`` 不启用）。Gate-3 ``main`` 显式传 ``4 * len(expected)``
            （31 → 124）；每次查询后检查 ``cumulative_rows > day_rows_limit``
            → :class:`BudgetViolation` → G3-S-013。
        max_rows: 兼容别名（等价于 ``cumulative_rows_limit``；保留供既有
            调用方/测试使用，任一给定即覆盖默认）。
    """

    def __init__(
        self,
        db: Any,
        *,
        max_find: int = 1000,
        max_time_ms: int = 30_000,
        server_selection_timeout_ms: int = 10_000,
        cumulative_rows_limit: int | None = 100_000,
        day_rows_limit: int | None = None,
        max_rows: int | None = None,
    ) -> None:
        self._db = db
        self._max_find = max_find
        self._max_time_ms = max_time_ms
        self._server_selection_timeout_ms = server_selection_timeout_ms
        if max_rows is not None:
            cumulative_rows_limit = max_rows
        self._cumulative_rows_limit = cumulative_rows_limit
        self._day_rows_limit = day_rows_limit
        self._total_rows = 0
        self._stats: list[dict[str, Any]] = []

    @property
    def cumulative_rows(self) -> int:
        """当前累计命中行数（Gate-1 判 G1-B-006；Gate-3 单日 informational）。"""
        return self._total_rows

    def reset_stats(self) -> None:
        """清零累计计数器（``cumulative_rows``）**与** stats 列表（G3-B-017）。

        二者必须同时清零，否则 ``days[].query_budget`` 跨日累加（违
        G3-A-003）。Gate-3 每 ``process_day`` 开头调用；job 级聚合
        （``summary.total_query_rows`` / 顶层 ``query_budget``）必须在 reset
        外基于保留的逐日记录计算（reset-safe，DESIGN §3.6.6）。
        """
        self._total_rows = 0
        self._stats = []

    def _record(self, kind: str, rows: int, ms: float) -> None:
        # 先记录本次查询（审计证据），再判上限——违规查询也进入 stats，
        # 使 failed_days[].query_budget 反映停止前实际执行的查询。
        self._total_rows += rows
        self._stats.append({"kind": kind, "count": 1, "rows": rows, "ms": round(ms, 3)})
        # G1-B-006（Gate-1 scope）：累计命中 > 上限 → BudgetViolation
        if (
            self._cumulative_rows_limit is not None
            and self._total_rows > self._cumulative_rows_limit
        ):
            raise BudgetViolation(
                f"cumulative rows {self._total_rows} exceed budget "
                f"{self._cumulative_rows_limit} (G1-B-006); narrow the query range"
            )
        # G3-B-018（Gate-3 专用）：单日累计命中 > 日级上限 → BudgetViolation
        if self._day_rows_limit is not None and self._total_rows > self._day_rows_limit:
            raise BudgetViolation(
                f"per-day rows {self._total_rows} exceed day limit "
                f"{self._day_rows_limit} (G3-B-018)"
            )

    def count(self, collection: str, filter: Mapping[str, Any]) -> int:
        f = _validate_filter(filter)
        start = time_mod.monotonic()
        result = self._db[collection].count_documents(
            f,
            maxTimeMS=self._max_time_ms,
        )
        self._record("count", int(result), time_mod.monotonic() - start)
        return int(result)

    def distinct(self, collection: str, key: str, filter: Mapping[str, Any]) -> list:
        f = _validate_filter(filter)
        start = time_mod.monotonic()
        result = list(self._db[collection].distinct(key, f))
        self._record("distinct", len(result), time_mod.monotonic() - start)
        return result

    def find(
        self,
        collection: str,
        filter: Mapping[str, Any],
        *,
        limit: int = 1000,
        projection: Mapping[str, Any] | None = None,
    ) -> list[dict]:
        if limit > self._max_find:
            raise BudgetViolation(
                f"find limit {limit} exceeds budget {self._max_find} (G1-B-003)"
            )
        f = _validate_filter(filter)
        start = time_mod.monotonic()
        cursor = self._db[collection].find(
            f,
            projection=dict(projection) if projection else None,
            limit=limit,
            max_time_ms=self._max_time_ms,
        )
        rows = [dict(doc) for doc in cursor]
        self._record("find", len(rows), time_mod.monotonic() - start)
        return rows

    def aggregate(
        self, collection: str, pipeline: list[Mapping[str, Any]]
    ) -> list[dict]:
        pipe = _validate_pipeline(pipeline)
        start = time_mod.monotonic()
        rows = [dict(doc) for doc in self._db[collection].aggregate(pipe)]
        self._record("aggregate", len(rows), time_mod.monotonic() - start)
        return rows

    def stats(self) -> list[dict[str, Any]]:
        """预算审计统计（G1-B-007）：按 kind 聚合 count/rows/ms。"""
        merged: dict[str, dict[str, Any]] = {}
        for rec in self._stats:
            item = merged.setdefault(
                rec["kind"],
                {"kind": rec["kind"], "count": 0, "rows": 0, "ms": 0.0},
            )
            item["count"] += rec["count"]
            item["rows"] += rec["rows"]
            item["ms"] = round(item["ms"] + rec["ms"], 3)
        return list(merged.values())


# ---------------------------------------------------------------------------
# ReportWriter + 日志 + 脱敏（G0-C-005 / G0-C-007 / G0-C-008 / G0-C-010）
# ---------------------------------------------------------------------------

REPORT_DIR_DEFAULT = "data/rollout/sector-ranking"

_URI_WITH_CREDENTIALS_RE = re.compile(
    r"mongodb(\+srv)?://[^/\s:@]+:[^@\s]+@", re.IGNORECASE
)


def _now_iso() -> str:
    """UTC ISO-8601 时间戳（report/log 统一格式，G0-C-010）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_report_dir(report_dir: str | None) -> str:
    """规范化 report 目录并 ``mkdir -p``（G0-C-007）。"""
    path = Path(report_dir) if report_dir else Path(REPORT_DIR_DEFAULT)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _json_safe(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def write_report(report_dir: str, gate: str, payload: dict[str, Any]) -> None:
    """写 ``gate{N}-report.json``（最新证据）+ 时间戳归档副本 + ``.md`` 摘要。

    Args:
        report_dir: 产物目录（已由 :func:`resolve_report_dir` 创建）。
        gate: Gate 前缀，如 ``"gate1"``。
        payload: report 字典（含 tool/version/timestamp/checks 等字段）。
    """
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)

    canonical = directory / f"{gate}-report.json"
    canonical.write_text(_json_safe(payload), encoding="utf-8")

    stamp = _now_iso().replace(":", "").replace("-", "").replace("Z", "")
    archive = directory / f"{gate}-report-{stamp}.json"
    archive.write_text(_json_safe(payload), encoding="utf-8")

    md_path = directory / f"{gate}-report.md"
    md_path.write_text(_report_markdown(gate, payload), encoding="utf-8")


def _report_markdown(gate: str, payload: Mapping[str, Any]) -> str:
    tool = payload.get("tool", gate)
    checks = payload.get("checks", {})
    stops = payload.get("stop_conditions_hit", [])
    lines = [
        f"# {tool} report",
        "",
        f"- gate: {gate}",
        f"- timestamp: {payload.get('timestamp', 'n/a')}",
        f"- conclusion: {'STOP' if stops else 'PASS'}",
    ]
    if isinstance(checks, Mapping) and checks:
        lines.append("- checks:")
        for key, value in checks.items():
            lines.append(f"  - {key}: {value}")
    if stops:
        lines.append(f"- stop_conditions_hit: {list(stops)}")
    lines.append("")
    return "\n".join(lines)


def log_jsonl(
    report_dir: str,
    gate: str,
    record: Mapping[str, Any],
    *,
    secret_entries: Iterable[tuple[str, str]] = (),
) -> None:
    """追加结构化 JSONL 日志（G0-C-008）；写前对 record 全文脱敏。"""
    log_dir = Path(report_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{gate}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
    line = dict(record)
    line.setdefault("timestamp", _now_iso())
    text = json.dumps(line, ensure_ascii=False, sort_keys=True)
    with (log_dir / filename).open("a", encoding="utf-8") as handle:
        handle.write(redact(text, secret_entries=secret_entries) + "\n")


def redact(
    text: str,
    *,
    secret_entries: Iterable[tuple[str, str]] = (),
) -> str:
    """掩码已知敏感值（连接值 / token / secret；G0-C-005）。"""
    result = text
    for kind, value in secret_entries:
        if isinstance(value, str) and value:
            result = result.replace(value, f"[REDACTED:{kind}]")
    return result


def scan_secrets(
    text: str,
    *,
    secret_entries: Iterable[tuple[str, str]] = (),
) -> list[str]:
    """返回命中的泄露类别列表；非空 → SC-016-G0-1 → 退出码 2。

    类别：``uri_with_credentials``（URI 含凭据段，兜底扫描，非允许连接形态）、
    ``password_value`` / ``token_value`` / ``secret_value``（已知值出现）。
    """
    hits: list[str] = []
    if _URI_WITH_CREDENTIALS_RE.search(text):
        hits.append("uri_with_credentials")
    for kind, value in secret_entries:
        if (
            isinstance(value, str)
            and len(value) >= 4
            and value in text
            and kind not in hits
        ):
            hits.append(kind)
    return sorted(hits)


# ---------------------------------------------------------------------------
# 交易日状态检查（SPEC G4-P-001 ~ G4-P-010 / DESIGN §3.3.5，F2 闭合）
# ---------------------------------------------------------------------------


class SessionStatus(Enum):
    FUTURE = "future"
    TODAY_UNCLOSED = "today_unclosed"
    TODAY_CLOSED = "today_closed"
    PAST_TRADING_DAY = "past_trading_day"
    PAST_NON_TRADING_DAY = "past_non_trading_day"


class TradeCalendar(ABC):
    @abstractmethod
    def is_trading_day(self, day: date) -> bool: ...


class FakeTradeCalendar(TradeCalendar):
    """测试注入：显式交易日集合；零真实 I/O（CL-5 同纪律）。"""

    def __init__(self, trading_days: Iterable[str]) -> None:
        self._days: set[str] = {str(d) for d in trading_days}

    def is_trading_day(self, day: date) -> bool:
        return day.isoformat() in self._days


class PolicyUnavailableError(Exception):
    """受控交易日历证据缺失 → fail-closed（G4-P-008/009）。"""


class CompletedSessionPolicy:
    """交易日状态判定（唯一输入 ``(trade_date, now)``，唯一输出 SessionStatus）。

    ``FUTURE`` / ``TODAY_UNCLOSED`` 抛 ``ValueError``（错误类别
    ``ERR_FUTURE_DATE`` / ``ERR_TODAY_UNCLOSED``，G4-P-004/005）；
    当日已收盘 / 历史交易日 / 非交易日不抛错（G4-P-006/007）。
    ``calendar=None`` → fail-closed：构造即抛 :class:`PolicyUnavailableError`。
    """

    CLOSE_CUTOFF = dt_time(15, 0)  # Asia/Shanghai 15:00 CST（15:00 整视为已收盘）
    TZ = ZoneInfo("Asia/Shanghai")

    def __init__(
        self,
        calendar: TradeCalendar | None,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        if calendar is None:
            raise PolicyUnavailableError(
                "trade-calendar evidence unavailable; fail-closed (G4-P-008/009)"
            )
        self._calendar = calendar
        self._now_fn: Callable[[], datetime] = now_fn or (
            lambda: datetime.now(timezone.utc)
        )

    def classify(self, trade_date: str, now: datetime | None = None) -> SessionStatus:
        if not is_valid_trade_date(trade_date):
            raise ValueError(
                f"trade_date must be a valid YYYY-MM-DD string, got {trade_date!r}"
            )
        now_utc = now if now is not None else self._now_fn()
        now_cst = now_utc.astimezone(self.TZ)
        today = now_cst.date()
        target = date.fromisoformat(trade_date)

        if target > today:
            raise ValueError(
                f"ERR_FUTURE_DATE trade_date {trade_date} is in the future"
            )
        if target == today:
            if (
                self._calendar.is_trading_day(target)
                and now_cst.time() < self.CLOSE_CUTOFF
            ):
                raise ValueError(
                    f"ERR_TODAY_UNCLOSED trade_date {trade_date} is today and "
                    "the market has not closed yet"
                )
            return SessionStatus.TODAY_CLOSED
        if self._calendar.is_trading_day(target):
            return SessionStatus.PAST_TRADING_DAY
        return SessionStatus.PAST_NON_TRADING_DAY


__all__ = [
    "ALLOWED_FILTER_FIELDS",
    "CONN_SOURCE",
    "CompletedSessionPolicy",
    "ConnLoader",
    "EXIT_CONN",
    "EXIT_OK",
    "EXIT_PARAM",
    "EXIT_STOP",
    "EXIT_VERIFY",
    "FakeTradeCalendar",
    "MissingConnectionKeyError",
    "PolicyUnavailableError",
    "REALTIME_MARKERS",
    "REPORT_DIR_DEFAULT",
    "REQUIRED_CONN_KEYS",
    "BudgetReader",
    "BudgetViolation",
    "SessionStatus",
    "TradeCalendar",
    "log_jsonl",
    "redact",
    "resolve_report_dir",
    "scan_secrets",
    "write_report",
]
