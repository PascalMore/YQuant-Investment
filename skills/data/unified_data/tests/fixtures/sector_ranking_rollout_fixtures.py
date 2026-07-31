"""03-016 rollout Gate tool fixtures（新增 fixture，不与 03-015 fixture 混用）。

DESIGN-03-016 V0.4 §5.2 / §3.1.1。全部 fixture 为纯数据 / mongomock 构造，
零真实 I/O（CL-5 同纪律）。SW L1 universe 只用 3 个代码的小集合证明逻辑
正确性，不代表生产 universe（H-049u；Gate-1 权威校验）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import mongomock

# 测试 dataset / 交易日常量（fixture 内显式，非生产常量）。
DATASET = "sw2021_ta_cn"

# 3 个申万风格 code/name（仅测试用）。
EXPECTED_UNIVERSE: dict[str, str] = {
    "801010": "农林牧渔",
    "801080": "电子",
    "801780": "银行",
}

# 源数据 trade_date 形态（TA-CN 风格 YYYYMMDD）。
SOURCE_DATE_FORMAT = "YYYYMMDD"

# 连续可用交易日（外部格式 YYYY-MM-DD ↔ 内部格式 YYYYMMDD）。
AVAILABLE_DATES = ["2026-07-10", "2026-07-13", "2026-07-14"]
AVAILABLE_DATES_INTERNAL = ["20260710", "20260713", "20260714"]

RECOMMENDED_CANARY = "2026-07-14"

# 每 code 每日的 close（3 日 × 3 code，覆盖前一日推导）。
_CLOSES: dict[str, dict[str, float]] = {
    "801010": {"20260710": 1000.0, "20260713": 1010.0, "20260714": 1020.0},
    "801080": {"20260710": 2000.0, "20260713": 1980.0, "20260714": 2010.0},
    "801780": {"20260710": 3000.0, "20260713": 3050.0, "20260714": 3030.0},
}

REFERENCE_CSV_HEADER = "sector_code,sector_name,note"


def make_sw_index_docs(
    *,
    codes: Iterable[str] | None = None,
    source: str = "sw",
    dates: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """构造 ``index_daily_quotes`` 文档（3 code × 3 交易日，TA-CN YYYYMMDD）。"""
    code_list = list(codes) if codes is not None else list(EXPECTED_UNIVERSE)
    date_list = list(dates) if dates is not None else AVAILABLE_DATES_INTERNAL
    docs: list[dict[str, Any]] = []
    for trade_date in date_list:
        for code in code_list:
            docs.append(
                {
                    "sector_code": code,
                    "trade_date": trade_date,
                    "close": _CLOSES[code][trade_date],
                    "source": source,
                }
            )
    return docs


def make_index_basic_docs(
    *,
    universe: dict[str, str] | None = None,
    use_code_fallback: bool = False,
    classify: str = "行业",
) -> list[dict[str, Any]]:
    """构造 ``index_basic_info`` 文档（market=CN + SW L1 前缀 + name）。

    ``use_code_fallback=True`` 时省略 ``sector_code`` 字段，验证候选 code
    提取顺序回退到 ``code``（G1-C-001 提取顺序：sector_code → code → symbol）。
    """
    uni = universe if universe is not None else EXPECTED_UNIVERSE
    docs: list[dict[str, Any]] = []
    for code, name in uni.items():
        doc: dict[str, Any] = {
            "market": "CN",
            "name": name,
            "type": classify,
        }
        if use_code_fallback:
            doc["code"] = code
            doc["symbol"] = code
        else:
            doc["sector_code"] = code
        docs.append(doc)
    return docs


def make_sw_index_docs_missing_close(codes: Iterable[str]) -> list[dict[str, Any]]:
    """指定 code 在 2026-07-13 缺失 close 的文档集（G1-C-004 负例）。"""
    docs = make_sw_index_docs()
    missing = set(codes)
    result: list[dict[str, Any]] = []
    for doc in docs:
        if doc["trade_date"] == "20260713" and doc["sector_code"] in missing:
            bad = dict(doc)
            bad["close"] = None
            result.append(bad)
        else:
            result.append(doc)
    return result


def make_sw_index_docs_rt_marker(
    rt_source: str = "realtime", dates: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """部分文档带 realtime/intraday 标记（G1-C-005 / G1-S-006 负例）。"""
    docs = make_sw_index_docs(dates=dates)
    docs[0]["source"] = rt_source
    return docs


def make_mongomock_db(
    *,
    index_daily: Iterable[dict[str, Any]] | None = None,
    index_basic: Iterable[dict[str, Any]] | None = None,
) -> Any:
    """构造 fresh mongomock db，可选预置 index_daily_quotes / index_basic_info。"""
    db = mongomock.MongoClient().get_database("rollout_test")
    if index_daily:
        db["index_daily_quotes"].insert_many(list(index_daily))
    if index_basic:
        db["index_basic_info"].insert_many(list(index_basic))
    return db


def make_expected_universe() -> dict[str, str]:
    """显式 expected universe（3 code → name）。"""
    return dict(EXPECTED_UNIVERSE)


def make_reference_csv(tmp_path: Path, *, universe: dict[str, str] | None = None) -> Path:
    """写 ``reference/sw_l1_reference.csv`` 到 tmp_path 并返回路径。"""
    uni = universe if universe is not None else EXPECTED_UNIVERSE
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    path = ref_dir / "sw_l1_reference.csv"
    lines = [
        "# REFERENCE-ONLY — test reference (3-code mini universe)",
        REFERENCE_CSV_HEADER,
    ]
    for code, name in uni.items():
        lines.append(f"{code},{name},test")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_mismatch_reference_csv(tmp_path: Path) -> Path:
    """含差异的 reference（name 不一致 + 多一个 code / 少一个 code）。"""
    uni = dict(EXPECTED_UNIVERSE)
    uni["801010"] = "农林牧渔改名"  # name mismatch
    uni.pop("801080")  # db 有 reference 无
    uni["801999"] = "测试多余"  # reference 有 db 无
    return make_reference_csv(tmp_path, universe=uni)


def make_gate1_report(
    tmp_path: Path,
    *,
    universe: dict[str, str] | None = None,
    available_dates: Iterable[str] | None = None,
    canary_candidates: Iterable[str] | None = None,
) -> Path:
    """写一份 gate1-report.json（Gate-3/4 的 --expected-file 输入）。"""
    uni = universe if universe is not None else EXPECTED_UNIVERSE
    dates = list(available_dates) if available_dates is not None else AVAILABLE_DATES
    candidates = (
        list(canary_candidates)
        if canary_candidates is not None
        else [RECOMMENDED_CANARY]
    )
    report = {
        "tool": "gate1_smoke",
        "version": "0.1.0",
        "timestamp": "2026-07-31T23:00:00Z",
        "conn_source": "MONGODB_*",
        "conn_fingerprint": {
            "source": "MONGODB_*",
            "keys_present": [
                "MONGODB_HOST",
                "MONGODB_PORT",
                "MONGODB_USERNAME",
                "MONGODB_PASSWORD",
                "MONGODB_DATABASE",
            ],
            "auth_configured": True,
        },
        "query_budget": [],
        "trade_date_format": SOURCE_DATE_FORMAT,
        "expected_sector_codes": sorted(uni),
        "expected_sector_names": uni,
        "trade_date_range": {"min": dates[0], "max": dates[-1]},
        "coverage_by_date": {
            d: {"expected": len(uni), "observed": len(uni), "ratio": 1.0}
            for d in dates
        },
        "close_missing_by_date": {d: [] for d in dates},
        "source_distribution": {"sw": len(uni) * len(dates)},
        "realtime_markers": [],
        "discrepancies": [],
        "canary_candidates": candidates,
        "recommended_canary": candidates[0] if candidates else None,
        "checks": {"G1-C-001": "PASS"},
        "stop_conditions_hit": [],
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "gate1-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def make_binding(tmp_path: Path, *, enabled: bool = False) -> Path:
    """写 ``binding_state.json`` 到 tmp_path 并返回路径。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "binding_state.json"
    path.write_text(
        json.dumps(
            {
                "capability": "sector.ranking_history",
                "enabled": enabled,
                "gate": 4,
                "updated_at": "2026-07-31T23:00:00Z",
                "previous": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


__all__ = [
    "AVAILABLE_DATES",
    "AVAILABLE_DATES_INTERNAL",
    "DATASET",
    "EXPECTED_UNIVERSE",
    "RECOMMENDED_CANARY",
    "REFERENCE_CSV_HEADER",
    "SOURCE_DATE_FORMAT",
    "make_binding",
    "make_expected_universe",
    "make_gate1_report",
    "make_index_basic_docs",
    "make_mismatch_reference_csv",
    "make_mongomock_db",
    "make_reference_csv",
    "make_sw_index_docs",
    "make_sw_index_docs_missing_close",
    "make_sw_index_docs_rt_marker",
]
