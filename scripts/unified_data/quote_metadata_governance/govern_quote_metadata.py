"""03-017 quote metadata governance runner — single CLI, four modes (DESIGN-03-017 V0.1).

对 ``tradingagents.index_daily_quotes`` 中**申万（SW）行业指数历史日线记录的
quote 级 metadata** 执行安全、幂等、可审计的历史归一化（RFC-03-017 /
SPEC-03-017）：

* ``census``（默认，只读）— 候选谓词 ``P`` 查询 + 权威 universe ``U`` 推导 +
  fail-closed 三重证据门禁 C17-201~205 + 合规分类。
* ``dry-run``（只读）— 复跑 census，输出预期 mutation 计数 + 有界脱敏样本
  （R17-001~007），零写。
* ``apply``（显式副作用，必须 ``--yes``）— 按 census 固化的候选 ``_id`` 列表
  逐批 ``bulk_write(UpdateOne, ordered=False, upsert=False)``（M17/B17），
  每批 checkpoint JSONL，stop-on-error，幂等可恢复。
* ``verify``（只读）— 写后 re-census + 计数方程 V17-001~006。

核心组件（本模块）：

* ``build_predicate`` / ``derive_universe`` — SPEC C17-101/102。
* ``run_census`` — gates C17-201~207 + 分类 C17-301~304 + 候选 ``_id`` 固化。
* ``plan_mutation`` — dry-run 预期计数（V17-003 方程）。
* ``QuoteMetadataWriter`` — namespace 白名单 + 字段白名单真实 pymongo 写入器
  （仅 ``tradingagents.index_daily_quotes``，仅 ``$set version`` / ``$unset name``，
  无 upsert / replace / delete / insert / DDL）。
* ``apply_mutation`` — 批次 / checkpoint / resume / stop-on-error / 有界重试。
* ``verify`` — V17-004~006 写后只读验证。

全部逻辑可在 mongomock 上离线测试（测试注入 ``ConnLoader(env=..., 
client_factory=mongomock.MongoClient)`` 或直接传 mongomock db）；T3 阶段
**零真实 Mongo I/O**（任务绝对禁止）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from pymongo import UpdateOne
from pymongo.errors import AutoReconnect, ConnectionFailure

from .common import (
    CONN_SOURCE,
    EXIT_CONN,
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
    EXIT_VERIFY,
    CheckpointStore,
    ConnLoader,
    MissingConnectionKeyError,
    REPORT_DIR_DEFAULT,
    log_jsonl,
    redact_payload,
    resolve_report_dir,
    scan_secrets,
    utc_now_iso,
    write_report,
)

# ---------------------------------------------------------------------------
# 常量（SPEC C17-101 / C17-106 / M17-007 / R17-004）
# ---------------------------------------------------------------------------

COLLECTION = "index_daily_quotes"            # namespace: tradingagents.index_daily_quotes
UNIVERSE_COLLECTION = "stock_sector_info"
DATABASE = "tradingagents"                   # 仅报告用；实际库名来自 MONGODB_DATABASE

# R17-004 受保护字段（OHLCV/provenance 等；存在性计数，绝不触碰）
PROTECTED_FIELDS: tuple[str, ...] = (
    "full_symbol",
    "code",
    "symbol",
    "market",
    "trade_date",
    "period",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "pct_chg",
    "data_source",
    "created_at",
    "updated_at",
)

VERSION_BUCKETS: tuple[str, ...] = ("absent", "int==1", "int!=1", "float", "str", "other")
NAME_BUCKETS: tuple[str, ...] = ("absent", "str", "non-str")

SAMPLE_CATEGORIES: tuple[str, ...] = (
    "already_compliant",
    "missing_version",
    "nonconforming_version",
    "name_present",
    "both_needed",
)
SAMPLE_MAX_PER_CATEGORY = 5  # R17-005：每类至多 5 条

_ABSENT = object()


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class NamespaceViolation(Exception):
    """尝试操作目标集合外（M17-007 → 停止，退出码 2）。"""


class InvalidUpdate(Exception):
    """更新越界：upsert / 非 UpdateOne / 非 $set/$unset / 非白名单键（M17-001~004）。"""


# ---------------------------------------------------------------------------
# 候选谓词与权威 universe（C17-101 ~ C17-103）
# ---------------------------------------------------------------------------


def build_predicate() -> dict[str, Any]:
    """C17-101：``data_source == "akshare"`` ∧ ``full_symbol`` 以 ``.SI`` 结尾。

    精确字符串后缀匹配（``\\\\.SI$``）；禁止前缀/模糊猜测。
    """
    return {"data_source": "akshare", "full_symbol": {"$regex": "\\.SI$"}}


def candidate_matches(doc: Mapping[str, Any]) -> bool:
    """与 ``build_predicate`` 语义一致的内存判定（精确字符串后缀匹配）。"""
    return (
        doc.get("data_source") == "akshare"
        and isinstance(doc.get("full_symbol"), str)
        and doc["full_symbol"].endswith(".SI")
    )


def normalize_l1_code(code: Any) -> str:
    """l1_code 归一化（与 ``SwIndexDailyService._normalize_code`` 一致：
    去后缀、取 ``.`` 前部分、大写），再统一加 ``.SI`` 后缀（C17-102）。"""
    base = str(code or "").split(".", 1)[0].strip().upper()
    return f"{base}.SI"


def derive_universe(db: Any) -> set[str]:
    """C17-102：``stock_sector_info`` 中 ``classify_system == "SW"`` 的
    ``l1_code`` 归一化集合（权威 universe ``U``）。"""
    docs = db[UNIVERSE_COLLECTION].find({"classify_system": "SW"})
    universe: set[str] = set()
    for doc in docs:
        code = doc.get("l1_code")
        if code is None or str(code).strip() == "":
            continue
        universe.add(normalize_l1_code(code))
    universe.discard(".SI")  # 空 base 的归一化产物
    return universe


# ---------------------------------------------------------------------------
# 合规分类（C17-301 ~ C17-304）
# ---------------------------------------------------------------------------


def version_state(doc: Mapping[str, Any]) -> str:
    """``version`` 类型直方图键：absent / int==1 / int!=1 / float / str / other。

    注意 Python ``bool`` 是 ``int`` 子类，但 BSON bool ≠ int，故先判 bool
    （``version: true`` 归类 ``other``，非合规）。
    """
    if "version" not in doc:
        return "absent"
    value = doc["version"]
    if isinstance(value, bool):
        return "other"
    if isinstance(value, int):
        return "int==1" if value == 1 else "int!=1"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return "other"


def name_state(doc: Mapping[str, Any]) -> str:
    """``name`` 类型直方图键：absent / str / non-str。"""
    if "name" not in doc:
        return "absent"
    return "str" if isinstance(doc["name"], str) else "non-str"


def classify_candidate(doc: Mapping[str, Any]) -> dict[str, bool]:
    """按 C17-301~304 对单个候选分类。

    Returns:
        ``{"version_ok", "version_fix_needed", "name_present",
        "already_compliant", "both_needed"}``。``already_compliant`` =
        version 为 int==1 且 name 不存在（C17-301）。
    """
    version_ok = version_state(doc) == "int==1"
    name_present = "name" in doc
    version_fix = not version_ok
    return {
        "version_ok": version_ok,
        "version_fix_needed": version_fix,
        "name_present": name_present,
        "name_unset_needed": name_present,
        "already_compliant": version_ok and not name_present,
        "both_needed": version_fix and name_present,
    }


# ---------------------------------------------------------------------------
# Census（C17-201 ~ C17-207 / C17-301 ~ C17-304）
# ---------------------------------------------------------------------------


@dataclass
class CensusReport:
    """census 结果（含候选 ``_id`` 固化列表与逐 id mutation plan）。"""

    predicate: dict[str, Any]
    universe: list[str]
    total_docs_scanned: int
    total_candidates: int
    candidate_ids: list[Any] = field(default_factory=list)
    gates: dict[str, dict[str, Any]] = field(default_factory=dict)
    stop_conditions_hit: list[str] = field(default_factory=list)
    classification: dict[str, int] = field(default_factory=dict)
    version_histogram: dict[str, int] = field(default_factory=dict)
    name_histogram: dict[str, int] = field(default_factory=dict)
    protected_presence: dict[str, int] = field(default_factory=dict)
    observations: dict[str, int] = field(default_factory=dict)
    samples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    mutation_plan: dict[str, dict[str, bool]] = field(default_factory=dict)
    nothing_to_do: bool = False
    ts_utc: str = ""


def _empty_classification() -> dict[str, int]:
    return {
        "already_compliant": 0,
        "missing_version": 0,
        "nonconforming_version": 0,
        "version_fix_needed": 0,
        "version_ok": 0,
        "version_ok_name_present": 0,
        "name_present": 0,
        "name_absent": 0,
        "both_needed": 0,
    }


def _empty_histograms() -> tuple[dict[str, int], dict[str, int]]:
    return {key: 0 for key in VERSION_BUCKETS}, {key: 0 for key in NAME_BUCKETS}


def _gate_suffix(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """C17-201：100% 候选 ``full_symbol`` 以 ``.SI`` 结尾；distinct 后缀 == {".SI"}。"""
    counts: Counter[str] = Counter()
    for doc in candidates:
        fs = doc.get("full_symbol")
        if isinstance(fs, str) and fs.endswith(".SI"):
            counts[".SI"] += 1
        else:
            counts["<not .SI>"] += 1
    return {
        "pass": set(counts) == {".SI"},
        "evidence": {"distinct_suffixes": sorted(counts), "counts": dict(counts)},
    }


def _gate_data_source(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """C17-202：100% 候选 ``data_source == "akshare"``；distinct == {"akshare"}。"""
    counts: Counter[str] = Counter(doc.get("data_source") for doc in candidates)
    return {
        "pass": set(counts) == {"akshare"},
        "evidence": {"distinct_values": sorted(counts), "counts": dict(counts)},
    }


def _gate_code_family(
    candidates: Sequence[Mapping[str, Any]], universe: Iterable[str]
) -> dict[str, Any]:
    """C17-203：P 内 ``distinct(full_symbol)`` ⊆ U；反例计数 == 0。

    失败时报告反例清单（full_symbol + trade_date 计数）。
    """
    universe_set = set(universe)
    distinct_fs = {doc.get("full_symbol") for doc in candidates}
    counterexamples = sorted(
        (fs for fs in distinct_fs if fs not in universe_set), key=str
    )
    listing: list[dict[str, Any]] = []
    if counterexamples:
        by_symbol: dict[Any, list[Any]] = {}
        for doc in candidates:
            fs = doc.get("full_symbol")
            if fs in set(counterexamples):
                by_symbol.setdefault(fs, []).append(doc.get("trade_date"))
        listing = [
            {
                "full_symbol": fs,
                "trade_date_count": len(dates),
                "distinct_trade_dates": len(set(dates)),
            }
            for fs, dates in by_symbol.items()
        ]
    return {
        "pass": not counterexamples,
        "evidence": {
            "distinct_full_symbols": sorted(distinct_fs, key=str),
            "counterexample_count": len(counterexamples),
            "counterexamples": listing,
        },
    }


def _gate_market(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """C17-204：100% 候选 ``market == "CN"``（字段存在时）；缺失计数 == 0。"""
    counts: Counter[str] = Counter()
    missing = 0
    for doc in candidates:
        if "market" not in doc:
            missing += 1
        else:
            counts[doc["market"]] += 1
    return {
        "pass": missing == 0 and set(counts) == {"CN"},
        "evidence": {
            "distinct_values": sorted(counts),
            "counts": dict(counts),
            "missing": missing,
        },
    }


def _gate_period(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """C17-205：100% 候选 ``period == "daily"``（字段存在时）；缺失计数 == 0。"""
    counts: Counter[str] = Counter()
    missing = 0
    for doc in candidates:
        if "period" not in doc:
            missing += 1
        else:
            counts[doc["period"]] += 1
    return {
        "pass": missing == 0 and set(counts) == {"daily"},
        "evidence": {
            "distinct_values": sorted(counts),
            "counts": dict(counts),
            "missing": missing,
        },
    }


def _evaluate_gates(
    candidates: Sequence[Mapping[str, Any]], universe: Iterable[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """C17-207：C17-201 → 202 → 203 → 204 → 205 串行；任一 FAIL 即停止，
    后续 gate 不执行。"""
    gates: dict[str, dict[str, Any]] = {}
    stops: list[str] = []
    evaluators: tuple[tuple[str, Callable[[Sequence[Mapping[str, Any]]], dict[str, Any]]], ...] = (
        ("C17-201", _gate_suffix),
        ("C17-202", _gate_data_source),
        ("C17-203", lambda cands: _gate_code_family(cands, universe)),
        ("C17-204", _gate_market),
        ("C17-205", _gate_period),
    )
    for gate_id, fn in evaluators:
        result = fn(candidates)
        gates[gate_id] = result
        if not result["pass"]:
            stops.append(gate_id)
            break
    return gates, stops


def _add_sample(
    samples: dict[str, list[dict[str, Any]]],
    doc: Mapping[str, Any],
    vs: str,
) -> None:
    """R17-005：有界样本（每类 ≤5），每条仅 id_prefix/full_symbol/trade_date/
    name_presence/version_summary；不输出原始 name 值、完整 _id、凭据。"""
    cls = classify_candidate(doc)
    categories: list[str] = []
    if cls["already_compliant"]:
        categories.append("already_compliant")
    if vs == "absent":
        categories.append("missing_version")
    elif vs != "int==1":
        categories.append("nonconforming_version")
    if cls["name_present"]:
        categories.append("name_present")
    if cls["both_needed"]:
        categories.append("both_needed")
    entry = {
        "id_prefix": str(doc.get("_id", ""))[:6],
        "full_symbol": doc.get("full_symbol"),
        "trade_date": doc.get("trade_date"),
        "name_presence": "present" if cls["name_present"] else "absent",
        "version_summary": vs,
    }
    for category in categories:
        if len(samples[category]) < SAMPLE_MAX_PER_CATEGORY:
            samples[category].append(entry)


def run_census(
    db: Any,
    predicate: Mapping[str, Any] | None = None,
    universe: Iterable[str] | None = None,
) -> CensusReport:
    """执行只读 census：候选查询 + 权威 universe + 门禁 + 分类 + ``_id`` 固化。

    - ``predicate`` 缺省 = ``build_predicate()``（C17-101）。
    - ``universe`` 缺省 = ``derive_universe(db)``（C17-102）；U 为空 → 停止
      （C17-103）。
    - ``total_candidates == 0`` → ``nothing_to_do``（成功 no-op，C17-104）。
    - 返回含候选 ``_id`` 列表（按 ``_id`` 升序，B17-003）与逐 id mutation plan。
    """
    predicate_dict = dict(predicate) if predicate is not None else build_predicate()
    ts = utc_now_iso()
    coll = db[COLLECTION]

    all_docs = [dict(doc) for doc in coll.find({})]
    total_docs_scanned = len(all_docs)
    candidates = [doc for doc in all_docs if candidate_matches(doc)]

    observations = {
        "si_non_akshare": sum(
            1
            for doc in all_docs
            if isinstance(doc.get("full_symbol"), str)
            and doc["full_symbol"].endswith(".SI")
            and doc.get("data_source") != "akshare"
        ),
        "akshare_non_si": sum(
            1
            for doc in all_docs
            if doc.get("data_source") == "akshare"
            and not (
                isinstance(doc.get("full_symbol"), str)
                and doc["full_symbol"].endswith(".SI")
            )
        ),
    }

    if universe is None:
        universe = derive_universe(db)
    universe_list = sorted(universe)

    report = CensusReport(
        predicate=predicate_dict,
        universe=universe_list,
        total_docs_scanned=total_docs_scanned,
        total_candidates=len(candidates),
        observations=observations,
        nothing_to_do=len(candidates) == 0,
        ts_utc=ts,
    )

    # C17-103：U 为空 → fail-closed 停止
    if not universe_list:
        report.stop_conditions_hit.append("C17-103")
        return report

    # C17-104：空候选 → 成功 no-op（不执行 gates——空集下的 "100%" 无意义）
    if not candidates:
        report.classification = _empty_classification()
        report.version_histogram, report.name_histogram = _empty_histograms()
        report.protected_presence = {key: 0 for key in PROTECTED_FIELDS}
        report.samples = {cat: [] for cat in SAMPLE_CATEGORIES}
        report.checks = {
            "v17_001": True,
            "v17_002": True,
        }
        return report

    # C17-207：串行门禁（任一 FAIL 即停止后续 gate）
    report.gates, report.stop_conditions_hit = _evaluate_gates(candidates, universe_list)

    # 分类 / 分布 / 样本 / mutation plan / _id 固化（gate FAIL 时仍计算，
    # 供 report 记录证据分布；apply 在 main 中由 stop_conditions_hit 拦截）
    _classify(report, candidates)
    return report


def _classify(report: CensusReport, candidates: Sequence[Mapping[str, Any]]) -> None:
    classification = _empty_classification()
    version_hist, name_hist = _empty_histograms()
    protected = {key: 0 for key in PROTECTED_FIELDS}
    samples = {cat: [] for cat in SAMPLE_CATEGORIES}
    plan: dict[str, dict[str, bool]] = {}
    ids: list[Any] = []

    for doc in candidates:
        cid = doc.get("_id")
        ids.append(cid)
        vs = version_state(doc)
        cls = classify_candidate(doc)
        plan[str(cid)] = {
            "set_version": cls["version_fix_needed"],
            "unset_name": cls["name_present"],
        }
        version_hist[vs] += 1
        name_hist[name_state(doc)] += 1
        for key in PROTECTED_FIELDS:
            if key in doc:
                protected[key] += 1
        if vs == "absent":
            classification["missing_version"] += 1
        elif vs == "int==1":
            classification["version_ok"] += 1
            if cls["already_compliant"]:
                classification["already_compliant"] += 1
            else:
                classification["version_ok_name_present"] += 1
        else:
            classification["nonconforming_version"] += 1
        if cls["name_present"]:
            classification["name_present"] += 1
        else:
            classification["name_absent"] += 1
        if cls["both_needed"]:
            classification["both_needed"] += 1
        _add_sample(samples, doc, vs)

    classification["version_fix_needed"] = (
        classification["missing_version"] + classification["nonconforming_version"]
    )

    report.classification = classification
    report.version_histogram = version_hist
    report.name_histogram = name_hist
    report.protected_presence = protected
    report.samples = samples
    report.mutation_plan = plan
    # B17-003：候选按 _id 升序处理（_id 为稳定 resume key）
    report.candidate_ids = sorted(ids, key=lambda value: str(value))
    # V17-001 / V17-002：分类恒等式（C17-301 定义 already_compliant 含
    # "name 不存在"；因此生产 post-repair 不变式下版本分区恒成立——若出现
    # version==1 且 name 存在的候选，V17-001 会如实报 False）
    report.checks = {
        "v17_001": (
            len(ids)
            == classification["already_compliant"]
            + classification["missing_version"]
            + classification["nonconforming_version"]
            and len(ids)
            == classification["name_present"] + classification["name_absent"]
        ),
        "v17_002": (
            classification["version_fix_needed"]
            == classification["missing_version"]
            + classification["nonconforming_version"]
        ),
    }


# ---------------------------------------------------------------------------
# Dry-run 报告（R17-001 ~ R17-007 / V17-003）
# ---------------------------------------------------------------------------


def _expected_counts(classification: Mapping[str, int]) -> dict[str, int]:
    version_fix = int(classification.get("version_fix_needed", 0))
    name_present = int(classification.get("name_present", 0))
    both = int(classification.get("both_needed", 0))
    return {
        "expected_set_version_ops": version_fix,
        "expected_unset_name_ops": name_present,
        "expected_update_docs": version_fix + name_present - both,
    }


def census_to_report_dict(
    census: CensusReport,
    *,
    mode: str,
    run_id: str,
    conn_fingerprint: Mapping[str, Any],
) -> dict[str, Any]:
    """把 census 组装为 R17-001~007 report 字典（census/dry-run/apply 共用）。"""
    expected = _expected_counts(census.classification)
    checks = dict(census.checks)
    checks["v17_003"] = (
        expected["expected_set_version_ops"] == int(census.classification.get("version_fix_needed", 0))
        and expected["expected_unset_name_ops"] == int(census.classification.get("name_present", 0))
        and expected["expected_update_docs"]
        == int(census.classification.get("version_fix_needed", 0))
        + int(census.classification.get("name_present", 0))
        - int(census.classification.get("both_needed", 0))
    )
    return {
        "tool": "quote-metadata-governance",
        "run_id": run_id,
        "mode": mode,
        "ts_utc": census.ts_utc,
        "conn_source": CONN_SOURCE,
        "conn_fingerprint": dict(conn_fingerprint),
        "collection": f"{DATABASE}.{COLLECTION}",
        "predicate": census.predicate,
        "universe_count": len(census.universe),
        "stats": {
            "total_candidates": census.total_candidates,
            "total_docs_scanned": census.total_docs_scanned,
        },
        "classification": dict(census.classification),
        "distributions": {
            "version_histogram": dict(census.version_histogram),
            "name_histogram": dict(census.name_histogram),
            "protected_presence": dict(census.protected_presence),
        },
        "samples": census.samples,
        "plan": expected,
        "gates": census.gates,
        "observations": dict(census.observations),
        "stop_conditions_hit": list(census.stop_conditions_hit),
        "checks": checks,
        "nothing_to_do": census.nothing_to_do,
    }


def plan_mutation(census: CensusReport) -> dict[str, Any]:
    """dry-run 报告（R17-001~007；基于 census 结果，纯函数零写）。"""
    report = census_to_report_dict(
        census,
        mode="dry-run",
        run_id="",
        conn_fingerprint={},
    )
    report["plan"] = _expected_counts(census.classification)
    return report


# ---------------------------------------------------------------------------
# QuoteMetadataWriter（M17-001 ~ M17-007）
# ---------------------------------------------------------------------------


class _BulkWriteResult:
    """聚合结果替身（mongomock 降级路径用；与 pymongo BulkWriteResult 同形态）。"""

    def __init__(self, matched: int, modified: int, upserted: int = 0) -> None:
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_count = upserted


def _is_mongomock(coll: Any) -> bool:
    """判定集合是否为 mongomock（测试替身）。

    mongomock 4.3 的 ``BulkOperationBuilder.add_update`` 没有 ``sort`` 形参，
    无法消费 pymongo 4.17 ``UpdateOne._add_to_bulk`` 传出的 ``sort`` kwarg；
    对 mongomock 集合等价降级为逐条 ``update_one``（``ordered=False`` 语义：
    操作彼此独立），真实 pymongo 仍走 ``bulk_write(ordered=False)``（B17-002）。
    """
    return type(coll).__module__.split(".")[0] == "mongomock"


class QuoteMetadataWriter:
    """真实 pymongo 生产写入器（仅限 ``tradingagents.index_daily_quotes`` 候选记录）。

    与 03-015 ``HistoricalRankingWriter`` 平行但**允许真实 db**；每个操作先过
    ``_assert_namespace``（拒绝目标集合外的一切读写）。仅允许
    ``UpdateOne``、``ordered=False``、``upsert=False``、``$set {version:1}`` /
    ``$unset {name:""}``；**无 replace_one / delete_one / insert / upsert /
    DDL 接口**（M17-002/M17-006）。
    """

    COLLECTION = COLLECTION
    ALLOWED_SET_KEYS: frozenset[str] = frozenset({"version"})
    ALLOWED_UNSET_KEYS: frozenset[str] = frozenset({"name"})

    def __init__(self, db: Any) -> None:
        if db is None:
            raise TypeError("QuoteMetadataWriter requires a db (pymongo / mongomock)")
        self._db = db

    def _assert_namespace(self, collection: str | None) -> None:
        if collection is not None and collection != self.COLLECTION:
            raise NamespaceViolation(
                f"collection {collection!r} is outside the allowlist "
                f"(only {self.COLLECTION})"
            )

    def _validate_update(self, update: Mapping[str, Any]) -> None:
        if not isinstance(update, Mapping):
            raise InvalidUpdate("update must be a mapping of operators")
        for op in update:
            if op not in ("$set", "$unset"):
                raise InvalidUpdate(
                    f"only $set/$unset allowed in update, got {op!r} (M17-001/M17-004)"
                )
        for key in update.get("$set", {}):
            if key not in self.ALLOWED_SET_KEYS:
                raise InvalidUpdate(
                    f"$set key {key!r} outside whitelist "
                    f"{sorted(self.ALLOWED_SET_KEYS)} (M17-004)"
                )
        for key in update.get("$unset", {}):
            if key not in self.ALLOWED_UNSET_KEYS:
                raise InvalidUpdate(
                    f"$unset key {key!r} outside whitelist "
                    f"{sorted(self.ALLOWED_UNSET_KEYS)} (M17-004)"
                )
        set_value = update.get("$set", {}).get("version")
        if set_value is not None and set_value != 1:
            raise InvalidUpdate("version must be normalized to 1 (M17-001)")

    def _validate_operation(self, op: Any) -> None:
        if not isinstance(op, UpdateOne):
            raise InvalidUpdate("only UpdateOne operations are allowed (M17-002)")
        if op._upsert:  # noqa: SLF001 — pymongo private attr, stable across versions
            raise InvalidUpdate("upsert is forbidden (M17-002)")
        self._validate_update(op._doc)  # noqa: SLF001

    def update_one(
        self,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        *,
        upsert: bool = False,
    ) -> Any:
        """单条更新（仅 COLLECTION；upsert 恒为 False）。"""
        self._assert_namespace(self.COLLECTION)
        if upsert:
            raise InvalidUpdate("upsert is forbidden (M17-002)")
        self._validate_update(update)
        return self._db[self.COLLECTION].update_one(dict(filter), dict(update), upsert=False)

    def bulk_write(
        self,
        operations: Sequence[Any],
        *,
        ordered: bool = False,
    ) -> Any:
        """批量更新（仅 COLLECTION；``ordered=False``，B17-002）。"""
        self._assert_namespace(self.COLLECTION)
        op_list = list(operations)
        for op in op_list:
            self._validate_operation(op)
        coll = self._db[self.COLLECTION]
        if _is_mongomock(coll):
            # mongomock 4.3 无法消费 pymongo 4.17 UpdateOne 的 sort kwarg：
            # 等价降级为逐条 update_one（操作彼此独立，= ordered=False 语义）。
            # upsert 恒为 False（M17-002），upserted 恒为 0。
            matched = 0
            modified = 0
            for op in op_list:
                result = coll.update_one(op._filter, op._doc, upsert=False)
                matched += int(result.matched_count or 0)
                modified += int(result.modified_count or 0)
            return _BulkWriteResult(matched, modified, 0)
        return coll.bulk_write(op_list, ordered=ordered)


# ---------------------------------------------------------------------------
# Apply（M17 / B17）
# ---------------------------------------------------------------------------


def _is_transient(exc: BaseException) -> bool:
    """瞬态错误判定（B17-005：连接/超时类；有界重试 ≤2 次，重试耗尽即停止）。"""
    if isinstance(exc, (AutoReconnect, ConnectionFailure)):
        return True
    return False


def _bulk_write_with_retry(
    writer: QuoteMetadataWriter,
    ops: list[Any],
    *,
    transient_retries: int = 2,
) -> Any:
    """有界瞬态重试（≤``transient_retries`` 次）；耗尽或永久错误 → 抛最终异常。"""
    last_exc: BaseException | None = None
    for attempt in range(transient_retries + 1):
        try:
            return writer.bulk_write(ops, ordered=False)
        except Exception as exc:  # noqa: BLE001 — 有界重试后停止（B17-005）
            last_exc = exc
            if attempt >= transient_retries or not _is_transient(exc):
                break
    assert last_exc is not None
    raise last_exc


def apply_mutation(
    db: Any,
    ids: Sequence[Any],
    batch_size: int,
    ckpt: CheckpointStore,
    plan: Mapping[str, Mapping[str, bool]],
    *,
    writer: QuoteMetadataWriter | None = None,
    transient_retries: int = 2,
    secret_entries: Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    """按 census 固化的候选 ``_id`` 列表分批执行 ``$set``/``$unset``（B17）。

    - 候选按 ``_id`` 升序（B17-003）；每批至多 ``batch_size`` 条 update_one
      （B17-001）；批内 ``bulk_write(ordered=False)``（B17-002）。
    - 每批写完后持久化 checkpoint（B17-004）；checkpoint 成功才进入下一批。
    - stop-on-error（B17-005）：瞬态错误有界重试 ≤2 次，耗尽即停止；
      永久错误立即停止；不自动扩批/继续。
    - 恢复（B17-006）：从最后成功 checkpoint 的 ``batch_end_id`` 继续；
      已修复记录在分类阶段被识别为已合规并跳过（幂等收敛，M17-005）。
    - 已合规 id（``set_version=False`` 且 ``unset_name=False``）**不发写**
      （M17-005 已合规 id 不发写；幂等重跑为纯 no-op）。
    """
    writer = writer if writer is not None else QuoteMetadataWriter(db)
    store = ckpt

    loaded = store.load()
    start_from = loaded.get("batch_end_id") if loaded else None
    resumed = loaded is not None

    batches = [ids[index : index + batch_size] for index in range(0, len(ids), batch_size)]
    batch_records: list[dict[str, Any]] = []
    cumulative_matched = 0
    cumulative_modified = 0
    stop_conditions: list[str] = []

    for seq, batch in enumerate(batches, 1):
        if start_from is not None and str(batch[0]) <= str(start_from):
            continue  # 已 checkpoint 的批（B17-006）
        ops: list[Any] = []
        for cid in batch:
            flags = plan.get(str(cid), {"set_version": False, "unset_name": False})
            update: dict[str, Any] = {}
            if flags.get("set_version"):
                update["$set"] = {"version": 1}
            if flags.get("unset_name"):
                update["$unset"] = {"name": ""}
            if update:
                ops.append(UpdateOne({"_id": cid}, update, upsert=False))

        matched = 0
        modified = 0
        error: str | None = None
        if ops:
            try:
                result = _bulk_write_with_retry(
                    writer, ops, transient_retries=transient_retries
                )
                matched = int(result.matched_count or 0)
                modified = int(result.modified_count or 0)
            except Exception as exc:  # noqa: BLE001 — stop-on-error（B17-005）
                error = f"{type(exc).__name__}: {exc}"
                stop_conditions.append(f"apply_batch_{seq}: {error}")

        record = {
            "batch_seq": seq,
            "batch_start_id": str(batch[0]),
            "batch_end_id": str(batch[-1]),
            "matched": matched,
            "modified": modified,
            "ops": len(ops),
            "ts_utc": utc_now_iso(),
        }
        batch_records.append(record)
        log_jsonl(
            store.report_dir,
            {"action": "batch", "run_id": store.run_id, **record},
            secret_entries=secret_entries,
        )
        if stop_conditions:
            break
        try:
            store.save(record)  # B17-004：checkpoint 成功才进入下一批
        except Exception as exc:  # noqa: BLE001
            stop_conditions.append(f"checkpoint_{seq}: {type(exc).__name__}: {exc}")
            break
        cumulative_matched += matched
        cumulative_modified += modified

    return {
        "cumulative_matched": cumulative_matched,
        "cumulative_modified": cumulative_modified,
        "batches": batch_records,
        "resumed": resumed,
        "resumed_from": start_from,
        "total_batches": len(batches),
        "stop_conditions_hit": stop_conditions,
    }


# ---------------------------------------------------------------------------
# Verify（V17-001 ~ V17-006）
# ---------------------------------------------------------------------------


def _load_previous_report(report_dir: str) -> dict[str, Any] | None:
    """读取最近 census/dry-run/apply report（同 report-dir 下的
    ``quote-governance-report.json`` 最新证据，供 V17-004~006 对照）。"""
    path = Path(report_dir) / "quote-governance-report.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def verify(
    db: Any,
    predicate: Mapping[str, Any] | None,
    pre_stats: Mapping[str, Any],
    *,
    run_id: str = "",
    conn_fingerprint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """写后只读 re-census + V17-001~006 方程校验（SPEC §3.8 / DESIGN §3.7）。

    ``pre_stats`` 为最近 census/dry-run/apply report（apply 后应含
    ``plan.expected_update_docs`` 与 ``apply.cumulative_matched/modified``）。
    任一 check FAIL → 调用方返回 EXIT_VERIFY=4。
    """
    post = run_census(db, predicate)
    expected = _expected_counts(post.classification)
    checks = dict(post.checks)
    checks["v17_003"] = (
        expected["expected_set_version_ops"] == int(post.classification.get("version_fix_needed", 0))
        and expected["expected_unset_name_ops"] == int(post.classification.get("name_present", 0))
        and expected["expected_update_docs"]
        == int(post.classification.get("version_fix_needed", 0))
        + int(post.classification.get("name_present", 0))
        - int(post.classification.get("both_needed", 0))
    )

    pre_total = (pre_stats or {}).get("stats", {}).get("total_candidates")
    pre_protected = (pre_stats or {}).get("distributions", {}).get("protected_presence", {})
    pre_expected_docs = (pre_stats or {}).get("plan", {}).get("expected_update_docs")
    apply_evidence = (pre_stats or {}).get("apply", {})
    cumulative_modified = apply_evidence.get("cumulative_modified")
    cumulative_matched = apply_evidence.get("cumulative_matched")

    post_version_conforming = int(post.classification.get("version_ok", 0))
    post_name_absent = int(post.classification.get("name_absent", 0))

    checks["v17_004"] = pre_total is not None and post.total_candidates == int(pre_total)
    checks["v17_005"] = (
        post_version_conforming == post.total_candidates
        and post_name_absent == post.total_candidates
    )
    checks["v17_006"] = (
        cumulative_modified is not None
        and pre_expected_docs is not None
        and int(cumulative_modified) == int(pre_expected_docs)
        and cumulative_matched is not None
        and int(cumulative_matched) >= int(cumulative_modified)
        and dict(pre_protected) == post.protected_presence
    )

    differences = [key for key, value in checks.items() if not value]

    report = census_to_report_dict(
        post,
        mode="verify",
        run_id=run_id,
        conn_fingerprint=conn_fingerprint or {},
    )
    report["checks"] = checks
    report["verify"] = {
        "pre_total_candidates": pre_total,
        "post_total_candidates": post.total_candidates,
        "pre_protected_presence": dict(pre_protected),
        "post_protected_presence": dict(post.protected_presence),
        "expected_update_docs": pre_expected_docs,
        "cumulative_modified": cumulative_modified,
        "cumulative_matched": cumulative_matched,
        "differences": differences,
    }
    return report


# ---------------------------------------------------------------------------
# CLI（SPEC C17-001 ~ C17-012）
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="govern_quote_metadata",
        description=(
            "03-017 SW historical quote metadata governance runner "
            "(census/dry-run/apply/verify; apply 需 --yes 显式确认)"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["census", "dry-run", "apply", "verify"],
        default="census",
        help="运行模式（默认 census）",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="显式确认副作用模式（仅 --mode apply 有效；缺省视为 dry-run，C17-004）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="批次大小 1..1000（默认 500，C17-011）",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help=f"产物目录（默认 {REPORT_DIR_DEFAULT}，C17-007）",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="本次运行标识（决定 checkpoint 文件名；重跑同一 run-id 可恢复，B17-006）",
    )
    return parser


def _emit(
    report_dir: str,
    payload: dict[str, Any],
    secret_entries: Iterable[tuple[str, str]],
) -> list[str]:
    """写 report + 审计日志；返回 secret 泄露命中类别（非空 → SC-017-G0-1）。"""
    entries = list(secret_entries)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    hits = scan_secrets(text, secret_entries=entries)
    if hits:
        payload["stop_conditions_hit"] = list(payload.get("stop_conditions_hit") or []) + [
            "SC-017-G0-1"
        ]
        payload["secrets_hits"] = list(hits)
    safe = redact_payload(payload, secret_entries=entries)
    write_report(report_dir, safe)
    log_jsonl(
        report_dir,
        {
            "action": f"report:{payload.get('mode', '?')}",
            "run_id": payload.get("run_id"),
            "total_candidates": payload.get("stats", {}).get("total_candidates"),
            "stop_conditions_hit": payload.get("stop_conditions_hit", []),
        },
        secret_entries=entries,
    )
    return hits


def _run_census_mode(
    db: Any,
    loader: ConnLoader,
    report_dir: str,
    run_id: str,
    predicate: Mapping[str, Any],
    *,
    mode: str,
) -> int:
    census = run_census(db, predicate)
    payload = census_to_report_dict(
        census,
        mode=mode,
        run_id=run_id,
        conn_fingerprint=loader.fingerprint(),
    )
    hits = _emit(report_dir, payload, loader.secret_entries())
    if hits:
        print(f"error: secrets detected in output (SC-017-G0-1): {hits}", file=sys.stderr)
        return EXIT_STOP
    if census.stop_conditions_hit:
        print(f"census STOP: {census.stop_conditions_hit}", file=sys.stderr)
        return EXIT_STOP
    if not census.checks.get("v17_001", True) or not census.checks.get("v17_002", True):
        print("census FAIL: classification identity V17-001/V17-002 violated", file=sys.stderr)
        return EXIT_PARAM
    if mode == "dry-run" and not payload["checks"].get("v17_003", True):
        print("dry-run FAIL: expected-mutation equation V17-003 violated", file=sys.stderr)
        return EXIT_PARAM
    if census.nothing_to_do:
        print(f"{mode}: nothing to do")
    else:
        print(f"{mode}: ok (total_candidates={census.total_candidates})")
    return EXIT_OK


def _run_apply_mode(
    db: Any,
    loader: ConnLoader,
    report_dir: str,
    run_id: str,
    predicate: Mapping[str, Any],
    batch_size: int,
) -> int:
    census = run_census(db, predicate)
    payload = census_to_report_dict(
        census,
        mode="apply",
        run_id=run_id,
        conn_fingerprint=loader.fingerprint(),
    )
    if census.stop_conditions_hit:
        payload["apply"] = {"applied": False, "reason": "census_stop"}
        hits = _emit(report_dir, payload, loader.secret_entries())
        if hits:
            return EXIT_STOP
        print(f"apply STOP (census): {census.stop_conditions_hit}", file=sys.stderr)
        return EXIT_STOP
    if not census.checks.get("v17_001", True) or not census.checks.get("v17_002", True):
        payload["apply"] = {"applied": False, "reason": "classification_invalid"}
        _emit(report_dir, payload, loader.secret_entries())
        print("apply FAIL: classification identity V17-001/V17-002 violated", file=sys.stderr)
        return EXIT_PARAM
    if census.nothing_to_do:
        payload["apply"] = {"applied": False, "reason": "nothing_to_do"}
        hits = _emit(report_dir, payload, loader.secret_entries())
        if hits:
            return EXIT_STOP
        print("apply: nothing to do")
        return EXIT_OK

    ckpt = CheckpointStore(report_dir, run_id)
    result = apply_mutation(
        db,
        census.candidate_ids,
        batch_size,
        ckpt,
        census.mutation_plan,
        secret_entries=loader.secret_entries(),
    )
    payload["apply"] = {
        "applied": True,
        "cumulative_matched": result["cumulative_matched"],
        "cumulative_modified": result["cumulative_modified"],
        "resumed": result["resumed"],
        "resumed_from": result["resumed_from"],
        "total_batches": result["total_batches"],
        "batches": result["batches"],
    }
    hits = _emit(report_dir, payload, loader.secret_entries())
    if hits:
        return EXIT_STOP
    if result["stop_conditions_hit"]:
        print(f"apply STOP: {result['stop_conditions_hit']}", file=sys.stderr)
        return EXIT_STOP
    print(
        f"apply: ok (matched={result['cumulative_matched']}, "
        f"modified={result['cumulative_modified']})"
    )
    return EXIT_OK


def _run_verify_mode(
    db: Any,
    loader: ConnLoader,
    report_dir: str,
    run_id: str,
    predicate: Mapping[str, Any],
) -> int:
    pre = _load_previous_report(report_dir)
    if pre is None:
        print(
            "error: verify requires a previous census/dry-run/apply report in "
            "report-dir for V17-004~006 comparison",
            file=sys.stderr,
        )
        return EXIT_PARAM
    report = verify(
        db,
        predicate,
        pre,
        run_id=run_id,
        conn_fingerprint=loader.fingerprint(),
    )
    hits = _emit(report_dir, report, loader.secret_entries())
    if hits:
        return EXIT_STOP
    if report.get("stop_conditions_hit"):
        print(f"verify STOP: {report['stop_conditions_hit']}", file=sys.stderr)
        return EXIT_STOP
    failed = [key for key, value in report.get("checks", {}).items() if not value]
    if failed:
        print(f"verify FAIL: {failed}", file=sys.stderr)
        return EXIT_VERIFY
    print(f"verify: ok (total_candidates={report['stats']['total_candidates']})")
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, conn: ConnLoader | None = None) -> int:
    """CLI 入口（SPEC C17-001~012）。``conn`` 供测试注入 mongomock 连接。"""
    parser = _build_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: --help → 0；参数错误 → EXIT_PARAM(1)
        code = exc.code
        return int(code) if isinstance(code, int) and code == 0 else EXIT_PARAM

    if not (1 <= args.batch_size <= 1000):
        print(f"error: --batch-size must be in 1..1000, got {args.batch_size}", file=sys.stderr)
        return EXIT_PARAM

    mode = args.mode
    if mode == "apply" and not args.yes:
        print("warning: --mode apply requires --yes (C17-004); treating as dry-run", file=sys.stderr)
        mode = "dry-run"
    if mode != "apply" and args.yes:
        print(f"warning: --yes only meaningful for --mode apply; ignored for {mode}", file=sys.stderr)
    if mode == "verify" and (args.yes or args.batch_size != 500):
        print("warning: --yes/--batch-size ignored in --mode verify (read-only)", file=sys.stderr)

    loader = conn if conn is not None else ConnLoader()
    report_dir = resolve_report_dir(args.report_dir)
    run_id = args.run_id or f"qg-{uuid.uuid4().hex[:12]}"
    predicate = build_predicate()

    try:
        db = loader.load_db()
    except MissingConnectionKeyError as exc:
        print(
            f"error: missing required connection key(s): {exc.missing} (C17-012)",
            file=sys.stderr,
        )
        return EXIT_CONN

    if mode == "census":
        return _run_census_mode(db, loader, report_dir, run_id, predicate, mode="census")
    if mode == "dry-run":
        return _run_census_mode(db, loader, report_dir, run_id, predicate, mode="dry-run")
    if mode == "apply":
        return _run_apply_mode(db, loader, report_dir, run_id, predicate, args.batch_size)
    if mode == "verify":
        return _run_verify_mode(db, loader, report_dir, run_id, predicate)
    return EXIT_PARAM  # unreachable


if __name__ == "__main__":
    sys.exit(main())
