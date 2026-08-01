"""03-017 quote metadata governance runner shared components (DESIGN-03-017 V0.1 §3.3).

本模块为 ``tradingagents.index_daily_quotes`` SW 历史 quote metadata 治理
runner（RFC-03-017 / SPEC-03-017）提供共享组件：

* 退出码常量（SPEC C17-002：``0/1/2/3/4``）。
* :class:`ConnLoader` — 唯一受控连接源（CL-1 ~ CL-6）：仅
  ``MONGODB_HOST`` / ``MONGODB_PORT`` / ``MONGODB_USERNAME`` /
  ``MONGODB_PASSWORD`` / ``MONGODB_DATABASE`` 五键组件式构造；**不允许
  URI / prefix / alias / fallback**；缺失任一必需键 → fail-fast
  EXIT_CONN(3)，仅报告键名；fingerprint 只含结构字段，不含任何连接值。
* ReportWriter 家族 — :func:`resolve_report_dir` / :func:`write_report` /
  :func:`log_jsonl`（C17-007/008/010，产物目录
  ``data/rollout/index-daily-quote-governance/``）。
* :func:`redact` / :func:`scan_secrets` / :func:`redact_payload` — secrets
  脱敏与泄露扫描（C17-005 / SC-017-G0-1；泄露类别
  ``uri_with_credentials`` / ``password_value`` / ``token_value`` /
  ``secret_value``）。
* :class:`CheckpointStore` — apply 每批 checkpoint JSONL（B17-004/006，
  resume key = ``_id``）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

# ---------------------------------------------------------------------------
# 退出码常量（SPEC C17-002）
# ---------------------------------------------------------------------------

EXIT_OK = 0        # 成功（census/dry-run/apply/verify 全过；含空候选 no-op）
EXIT_PARAM = 1     # 参数/前置校验失败（非法 --mode / --batch-size / 缺 --yes）
EXIT_STOP = 2      # 停止条件命中（C17-201~205 gate FAIL / SC-017-G0-1）
EXIT_CONN = 3      # 连接/凭据失败（fail-fast，不降级）
EXIT_VERIFY = 4    # verify 失败（V17-004~006）

# ---------------------------------------------------------------------------
# 连接契约常量（CL-1 ~ CL-6 / SPEC C17-012）
# ---------------------------------------------------------------------------

REQUIRED_CONN_KEYS: tuple[str, ...] = (
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_USERNAME",
    "MONGODB_PASSWORD",
    "MONGODB_DATABASE",
)
CONN_SOURCE = "MONGODB_*"

_CLIENT_TIMEOUT_MS = 10_000  # serverSelectionTimeoutMS / connectTimeoutMS（C17-006 ≤10s）


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
        # 延迟 import：仅在生产路径构造真实 pymongo。
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
        """(泄露类别, 值) 对，供 redact / scan_secrets 使用；绝不打印。

        注：**不含 ``MONGODB_DATABASE`` 的值**——数据库名是结构信息（R17-001
        要求 report 的 ``collection`` 字段固定输出 ``tradingagents.index_daily_quotes``，
        而 ``MONGODB_DATABASE`` 生产值即 ``tradingagents``），把它登记为
        secret 会在 scan_secrets 中产生必然的误报；host/port/username/password
        均为凭据类，照常登记。
        """
        entries: list[tuple[str, str]] = []
        for key, kind in (
            ("MONGODB_HOST", "secret_value"),
            ("MONGODB_PORT", "secret_value"),
            ("MONGODB_USERNAME", "secret_value"),
        ):
            value = self._env.get(key)
            if value:
                entries.append((kind, str(value)))
        password = self._env.get("MONGODB_PASSWORD")
        if password:
            entries.append(("password_value", str(password)))
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
            "missing required MONGODB_* connection key(s): " + ", ".join(self.missing)
        )


# ---------------------------------------------------------------------------
# ReportWriter + 日志 + 脱敏（C17-005 / C17-007 / C17-008 / C17-010）
# ---------------------------------------------------------------------------

REPORT_DIR_DEFAULT = "data/rollout/index-daily-quote-governance"

_URI_WITH_CREDENTIALS_RE = re.compile(
    r"mongodb(\+srv)?://[^/\s:@]+:[^@\s]+@", re.IGNORECASE
)


def utc_now_iso() -> str:
    """UTC ISO-8601 时间戳（report/log 统一格式，C17-010）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_report_dir(report_dir: str | None) -> str:
    """规范化 report 目录并 ``mkdir -p``（C17-007）。"""
    path = Path(report_dir) if report_dir else Path(REPORT_DIR_DEFAULT)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _json_safe(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def write_report(report_dir: str, payload: dict[str, Any]) -> None:
    """写 ``quote-governance-report.json``（最新证据）+ 时间戳归档副本 +
    ``.md`` 人读摘要（C17-007，归档副本不覆盖历史）。"""
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)

    canonical = directory / "quote-governance-report.json"
    canonical.write_text(_json_safe(payload), encoding="utf-8")

    stamp = utc_now_iso().replace(":", "").replace("-", "").replace("Z", "")
    archive = directory / f"quote-governance-report-{stamp}.json"
    archive.write_text(_json_safe(payload), encoding="utf-8")

    md_path = directory / "quote-governance-report.md"
    md_path.write_text(_report_markdown(payload), encoding="utf-8")


def _report_markdown(payload: Mapping[str, Any]) -> str:
    tool = payload.get("tool", "quote-metadata-governance")
    stops = payload.get("stop_conditions_hit", [])
    checks = payload.get("checks", {})
    stats = payload.get("stats", {})
    classification = payload.get("classification", {})
    plan = payload.get("plan", {})
    lines = [
        f"# {tool} report",
        "",
        f"- mode: {payload.get('mode', 'n/a')}",
        f"- timestamp: {payload.get('ts_utc', 'n/a')}",
        f"- run_id: {payload.get('run_id', 'n/a')}",
        f"- conclusion: {'STOP' if stops else 'PASS'}",
        f"- total_candidates: {stats.get('total_candidates', 'n/a')}",
        f"- total_docs_scanned: {stats.get('total_docs_scanned', 'n/a')}",
    ]
    if isinstance(classification, Mapping) and classification:
        lines.append("- classification:")
        for key, value in classification.items():
            lines.append(f"  - {key}: {value}")
    if isinstance(plan, Mapping) and plan:
        lines.append("- plan:")
        for key, value in plan.items():
            lines.append(f"  - {key}: {value}")
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
    record: Mapping[str, Any],
    *,
    secret_entries: Iterable[tuple[str, str]] = (),
) -> None:
    """追加结构化 JSONL 日志（C17-008）；写前对 record 全文脱敏。"""
    log_dir = Path(report_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    filename = f"quote-governance-{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
    line = dict(record)
    line.setdefault("timestamp", utc_now_iso())
    text = json.dumps(line, ensure_ascii=False, sort_keys=True)
    with (log_dir / filename).open("a", encoding="utf-8") as handle:
        handle.write(redact(text, secret_entries=secret_entries) + "\n")


def redact(
    text: str,
    *,
    secret_entries: Iterable[tuple[str, str]] = (),
) -> str:
    """掩码已知敏感值（连接值 / token / secret；C17-005）。"""
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
    """返回命中的泄露类别列表；非空 → SC-017-G0-1 → 退出码 2。

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


def redact_payload(
    value: Any,
    *,
    secret_entries: Iterable[tuple[str, str]] = (),
) -> Any:
    """递归脱敏 report/log payload 中的字符串值（防御性，C17-005）。"""
    entries = list(secret_entries)
    if isinstance(value, dict):
        return {key: redact_payload(item, secret_entries=entries) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item, secret_entries=entries) for item in value]
    if isinstance(value, str):
        return redact(value, secret_entries=entries)
    return value


# ---------------------------------------------------------------------------
# CheckpointStore（B17-004 / B17-006，resume key = `_id`）
# ---------------------------------------------------------------------------


class CheckpointStore:
    """apply 每批 checkpoint（JSONL，带 run_id 与日期，不覆盖历史）。

    Args:
        report_dir: 产物目录（C17-007）。
        run_id: 本次运行标识（决定 checkpoint 文件名）；重跑同一 run_id
            可从最后成功 checkpoint 恢复（B17-006）。
    """

    def __init__(self, report_dir: str, run_id: str) -> None:
        self.report_dir = str(report_dir)
        self.run_id = str(run_id)
        self.path = (
            Path(self.report_dir) / f"quote-governance-checkpoint-{self.run_id}.jsonl"
        )

    def load(self) -> dict[str, Any] | None:
        """读最后一行 checkpoint；无文件/无有效行 → ``None``。"""
        if not self.path.exists():
            return None
        last: dict[str, Any] | None = None
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        last = parsed
        except OSError:
            return None
        return last

    def save(self, record: Mapping[str, Any]) -> None:
        """追加一条 checkpoint（B17-004：``{batch_seq, batch_start_id,
        batch_end_id, matched, modified, ts_utc}``）。"""
        line = dict(record)
        line.setdefault("ts_utc", utc_now_iso())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")


__all__ = [
    "CONN_SOURCE",
    "CheckpointStore",
    "ConnLoader",
    "EXIT_CONN",
    "EXIT_OK",
    "EXIT_PARAM",
    "EXIT_STOP",
    "EXIT_VERIFY",
    "MissingConnectionKeyError",
    "REPORT_DIR_DEFAULT",
    "REQUIRED_CONN_KEYS",
    "log_jsonl",
    "redact",
    "redact_payload",
    "resolve_report_dir",
    "scan_secrets",
    "utc_now_iso",
    "write_report",
]
