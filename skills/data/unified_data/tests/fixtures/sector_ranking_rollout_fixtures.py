"""03-016 rollout Gate tool fixtures（新增 fixture，不与 03-015 fixture 混用）。

DESIGN-03-016 V0.6 §5.2 / §3.1.1（L1 契约校正：universe 来源
``stock_sector_info``，行情 join field ``full_symbol``）。全部 fixture 为
纯数据 / mongomock 构造，零真实 I/O（CL-5 同纪律）。

L1 universe 契约（SPEC G1-C-001）：
* 唯一主来源 ``stock_sector_info``，filter ``{classify_system: \"SW\"}``，
  distinct ``(l1_code, l1_name)`` 恰好 31。
* canonical code / 行情 join key = 带 ``.SI`` 后缀的 ``l1_code``，匹配
  ``index_daily_quotes.full_symbol``。
* ``EXPECTED_UNIVERSE_31`` 为 31 个真实申万一级行业（仅测试 fixture，用于
  断言恰好 31 条）；``EXPECTED_UNIVERSE``（3 code 小集合）保留用于
  gate4 冻结测试兼容与局部逻辑证明（不代表生产 universe，H-049u）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import mongomock

# 测试 dataset / 交易日常量（fixture 内显式，非生产常量）。
DATASET = "sw2021_ta_cn"

# 3 个申万风格 code/name（仅测试用；保留无后缀形态供 gate4 冻结测试兼容，
# 生产契约 code 为 .SI 后缀——见 EXPECTED_UNIVERSE_SI）。
EXPECTED_UNIVERSE: dict[str, str] = {
    "801010": "农林牧渔",
    "801080": "电子",
    "801780": "银行",
}

# 3 个 .SI 后缀 code/name（L1 契约 canonical 形态，行情 join key = full_symbol）。
EXPECTED_UNIVERSE_SI: dict[str, str] = {
    "801010.SI": "农林牧渔",
    "801080.SI": "电子",
    "801780.SI": "银行",
}

# 31 个真实申万一级行业（SW 2021，.SI 后缀 canonical 形态）。恰好 31 条，
# 用于断言 G1-C-001 / G1-S-002 的 31 约束。
EXPECTED_UNIVERSE_31: dict[str, str] = {
    "801010.SI": "农林牧渔",
    "801030.SI": "基础化工",
    "801040.SI": "钢铁",
    "801050.SI": "有色金属",
    "801080.SI": "电子",
    "801110.SI": "家用电器",
    "801120.SI": "食品饮料",
    "801130.SI": "纺织服饰",
    "801140.SI": "轻工制造",
    "801150.SI": "医药生物",
    "801160.SI": "公用事业",
    "801170.SI": "交通运输",
    "801180.SI": "房地产",
    "801200.SI": "商贸零售",
    "801210.SI": "社会服务",
    "801230.SI": "综合",
    "801710.SI": "建筑材料",
    "801720.SI": "建筑装饰",
    "801730.SI": "电力设备",
    "801740.SI": "国防军工",
    "801750.SI": "计算机",
    "801760.SI": "传媒",
    "801770.SI": "通信",
    "801780.SI": "银行",
    "801790.SI": "非银金融",
    "801880.SI": "汽车",
    "801890.SI": "机械设备",
    "801950.SI": "煤炭",
    "801960.SI": "石油石化",
    "801970.SI": "环保",
    "801980.SI": "美容护理",
}

# 源数据 trade_date 形态（TA-CN 风格 YYYYMMDD）。
SOURCE_DATE_FORMAT = "YYYYMMDD"

# 连续可用交易日（外部格式 YYYY-MM-DD ↔ 内部格式 YYYYMMDD）。
AVAILABLE_DATES = ["2026-07-10", "2026-07-13", "2026-07-14"]
AVAILABLE_DATES_INTERNAL = ["20260710", "20260713", "20260714"]

RECOMMENDED_CANARY = "2026-07-14"

# 每 code 每日的 close（3 日 × 3 code，覆盖前一日推导）。key 为无后缀
# code（make_sw_index_docs 内部剥离 .SI 后查表；未在表中的 code 用
# _default_close 确定性生成，保证 31 L1 fixture 可用）。
_CLOSES: dict[str, dict[str, float]] = {
    "801010": {"20260710": 1000.0, "20260713": 1010.0, "20260714": 1020.0},
    "801080": {"20260710": 2000.0, "20260713": 1980.0, "20260714": 2010.0},
    "801780": {"20260710": 3000.0, "20260713": 3050.0, "20260714": 3030.0},
}

REFERENCE_CSV_HEADER = "sector_code,sector_name,note"


def _strip_si(code: str) -> str:
    return code[:-3] if code.endswith(".SI") else code


def _default_close(code: str, trade_date: str) -> float:
    """未在 _CLOSES 表中的 code 的确定性 close（有限数值，供 31 L1 fixture）。"""
    base = 1000.0 + (int(_strip_si(code)) % 1000)
    day_index = AVAILABLE_DATES_INTERNAL.index(trade_date) if trade_date in AVAILABLE_DATES_INTERNAL else 0
    return base + day_index * 5.0


def make_sw_index_docs(
    *,
    codes: Iterable[str] | None = None,
    source: str = "sw",
    dates: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """构造 ``index_daily_quotes`` 文档（code × 交易日，TA-CN YYYYMMDD）。

    每个文档带 ``full_symbol``（行情 join key，L1 契约）与 ``sector_code``
    （兼容 gate4 冻结测试 / 旧断言）；值均为传入 code。
    """
    code_list = list(codes) if codes is not None else list(EXPECTED_UNIVERSE)
    date_list = list(dates) if dates is not None else AVAILABLE_DATES_INTERNAL
    docs: list[dict[str, Any]] = []
    for trade_date in date_list:
        for code in code_list:
            close = _CLOSES.get(_strip_si(code), {}).get(trade_date)
            if close is None:
                close = _default_close(code, trade_date)
            docs.append(
                {
                    "full_symbol": code,
                    "sector_code": code,
                    "trade_date": trade_date,
                    "close": close,
                    "source": source,
                }
            )
    return docs


def make_stock_sector_info_docs(
    *,
    universe: dict[str, str] | None = None,
    classify_system: str = "SW",
) -> list[dict[str, Any]]:
    """构造 ``stock_sector_info`` 文档（L1 universe 唯一主来源，G1-C-001）。

    每个文档含 ``l1_code`` / ``l1_name`` / ``classify_system``（真实结构）。
    """
    uni = universe if universe is not None else EXPECTED_UNIVERSE_31
    return [
        {
            "l1_code": code,
            "l1_name": name,
            "classify_system": classify_system,
        }
        for code, name in uni.items()
    ]


def make_index_basic_docs(
    *,
    universe: dict[str, str] | None = None,
    use_code_fallback: bool = False,
    classify: str = "行业",
) -> list[dict[str, Any]]:
    """构造 ``index_basic_info`` 文档（仅 gate4 冻结测试兼容，非生产主来源）。

    保留仅供冻结的 ``test_sector_ranking_rollout_gate4.py`` 引用；gate1/gate3
    生产路径不得使用（L1 契约校正：universe 主来源 = ``stock_sector_info``）。
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


def make_sw_index_docs_missing_close(
    codes: Iterable[str], *, universe: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """指定 full_symbol 在 2026-07-13 缺失 close 的文档集（G1-C-004 负例）。

    ``codes`` 为缺失 close 的 full_symbol 值集；``universe`` 为生成行情文档
    的 code 全集（默认 = ``codes`` 所在全集推断）。
    """
    universe_list = list(universe) if universe is not None else None
    docs = make_sw_index_docs(codes=universe_list)
    missing = set(codes)
    result: list[dict[str, Any]] = []
    for doc in docs:
        if doc["trade_date"] == "20260713" and doc["full_symbol"] in missing:
            bad = dict(doc)
            bad["close"] = None
            result.append(bad)
        else:
            result.append(doc)
    return result


def make_sw_index_docs_rt_marker(
    rt_source: str = "realtime",
    dates: Iterable[str] | None = None,
    *,
    universe: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """部分文档带 realtime/intraday 标记（G1-C-005 / G1-S-006 负例）。"""
    docs = make_sw_index_docs(dates=dates, codes=list(universe) if universe is not None else None)
    docs[0]["source"] = rt_source
    return docs


def make_mongomock_db(
    *,
    index_daily: Iterable[dict[str, Any]] | None = None,
    index_basic: Iterable[dict[str, Any]] | None = None,
    stock_sector_info: Iterable[dict[str, Any]] | None = None,
) -> Any:
    """构造 fresh mongomock db，可选预置 index_daily_quotes / index_basic_info /
    stock_sector_info。

    ``index_basic`` 参数保留供 gate4 冻结测试；生产路径 fixture 使用
    ``stock_sector_info``。
    """
    db = mongomock.MongoClient().get_database("rollout_test")
    if index_daily:
        db["index_daily_quotes"].insert_many(list(index_daily))
    if index_basic:
        db["index_basic_info"].insert_many(list(index_basic))
    if stock_sector_info:
        db["stock_sector_info"].insert_many(list(stock_sector_info))
    return db


def make_expected_universe() -> dict[str, str]:
    """显式 expected universe（3 code，无后缀，gate4 兼容形态）。"""
    return dict(EXPECTED_UNIVERSE)


def make_expected_universe_si() -> dict[str, str]:
    """显式 expected universe（3 code，.SI 后缀 canonical 形态）。"""
    return dict(EXPECTED_UNIVERSE_SI)


def make_reference_csv(tmp_path: Path, *, universe: dict[str, str] | None = None) -> Path:
    """写 ``reference/sw_l1_reference.csv`` 到 tmp_path 并返回路径。"""
    uni = universe if universe is not None else EXPECTED_UNIVERSE_SI
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    path = ref_dir / "sw_l1_reference.csv"
    lines = [
        "# REFERENCE-ONLY — test reference (mini universe)",
        REFERENCE_CSV_HEADER,
    ]
    for code, name in uni.items():
        lines.append(f"{code},{name},test")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_mismatch_reference_csv(tmp_path: Path) -> Path:
    """含差异的 reference（name 不一致 + 多一个 code / 少一个 code）。"""
    uni = dict(EXPECTED_UNIVERSE_SI)
    uni["801010.SI"] = "农林牧渔改名"  # name mismatch
    uni.pop("801080.SI")  # db 有 reference 无
    uni["801999.SI"] = "测试多余"  # reference 有 db 无
    return make_reference_csv(tmp_path, universe=uni)


def make_gate1_report(
    tmp_path: Path,
    *,
    universe: dict[str, str] | None = None,
    available_dates: Iterable[str] | None = None,
    canary_candidates: Iterable[str] | None = None,
    universe_source: str = "stock_sector_info",
) -> Path:
    """写一份 gate1-report.json（Gate-3/4 的 --expected-file 输入）。

    L1 契约（SPEC G1-R-004/005）：含 ``expected_sector_codes`` /
    ``expected_sector_names`` / ``expected_full_symbols``（``.SI`` 后缀 L1
    join 值集）与 ``universe_source``。默认 universe 为无后缀 3 code 形态
    （兼容 gate4 冻结测试）；Gate-3 测试应显式传 ``universe=EXPECTED_UNIVERSE_SI``
    以覆盖 ``.SI`` 校验。
    """
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
        "expected_full_symbols": sorted(uni),
        "universe_source": universe_source,
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
    "EXPECTED_UNIVERSE_31",
    "EXPECTED_UNIVERSE_SI",
    "RECOMMENDED_CANARY",
    "REFERENCE_CSV_HEADER",
    "SOURCE_DATE_FORMAT",
    "make_binding",
    "make_expected_universe",
    "make_expected_universe_si",
    "make_gate1_report",
    "make_index_basic_docs",
    "make_mismatch_reference_csv",
    "make_mongomock_db",
    "make_reference_csv",
    "make_stock_sector_info_docs",
    "make_sw_index_docs",
    "make_sw_index_docs_missing_close",
    "make_sw_index_docs_rt_marker",
]
