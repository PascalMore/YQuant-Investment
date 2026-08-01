"""03-017 quote metadata governance runner fixtures（DESIGN-03-017 V0.1 §5.1/§5.2）。

新增 fixture，不与 03-016/03-015 fixture 混用。全部 fixture 为纯数据 /
mongomock 构造，**零真实 I/O**（CL-5 同纪律）。

覆盖 §5.2 显式零写 dry-run 测试矩阵 D1~D12 所需场景：

* :func:`make_sw_universe` — ``stock_sector_info`` SW L1 universe（带/不带
  ``.SI`` 后缀混合，验证 C17-102 归一化）。
* :func:`make_quote_doc` — 单条 ``index_daily_quotes`` 候选形态文档（含全部
  受保护字段；``version`` / ``name`` 用 ``ABSENT`` 哨兵表示缺失）。
* :func:`make_sw_quote_docs` — 候选文档集（确定性字符串 ``_id``，按
  ``_id`` 升序）。
* :func:`make_mixed_quote_docs` — D5 混合分类数据集（gates 全过；
  already/missing/nonconforming/name_present/both_needed 全覆盖）。
* :func:`make_gate_fail_docs` 系列 — gate 反例（market≠CN / full_symbol∉U /
  period≠daily / data_source≠akshare / 后缀异常）。
* :func:`make_db` — fresh mongomock db（可预置 quote docs + universe）。
* :func:`make_checkpoint` — 写 checkpoint JSONL 文件（模拟中断现场）。

``MIXED_CLASSIFICATION`` 为 :func:`make_mixed_quote_docs` 的预期分类计数
（V17-001/002 恒等式与 R17-003 字段对齐）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import mongomock

# 3 个申万 L1 行业 code/name（测试 fixture；与 03-016 EXPECTED_UNIVERSE_SI 对齐）。
UNIVERSE_SI: dict[str, str] = {
    "801010.SI": "农林牧渔",
    "801080.SI": "电子",
    "801780.SI": "银行",
}

# 默认交易日（TA-CN 风格 YYYYMMDD）。
DATES: tuple[str, ...] = ("20260710", "20260713")


class _Absent:
    """字段缺失哨兵（version/name 缺省用）。"""

    def __repr__(self) -> str:  # pragma: no cover — 仅调试
        return "<ABSENT>"


ABSENT = _Absent()


# ---------------------------------------------------------------------------
# universe / 文档构造
# ---------------------------------------------------------------------------


def make_sw_universe(*, with_suffix: bool = True) -> list[dict[str, Any]]:
    """构造 ``stock_sector_info`` 文档（``classify_system == "SW"``）。

    ``with_suffix=True`` 时 ``l1_code`` 带 ``.SI`` 后缀；``False`` 时为无后缀
    6 位数字形态（两者归一化后应得到同一 universe，C17-102）。
    """
    docs: list[dict[str, Any]] = []
    for code, name in UNIVERSE_SI.items():
        docs.append(
            {
                "l1_code": code if with_suffix else code.split(".")[0],
                "l1_name": name,
                "classify_system": "SW",
            }
        )
    return docs


def make_quote_doc(
    *,
    full_symbol: str = "801010.SI",
    trade_date: str = "20260710",
    data_source: str = "akshare",
    market: str = "CN",
    period: str = "daily",
    version: Any = ABSENT,
    name: Any = ABSENT,
    _id: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    """构造一条 ``index_daily_quotes`` 候选形态文档（含全部受保护字段）。

    ``version`` / ``name`` 传 ``ABSENT`` 表示字段缺失；其余受保护字段
    （OHLCV/provenance 等）全部给出，用于验证 mutation 不触碰它们。
    """
    code = full_symbol.split(".")[0]
    doc: dict[str, Any] = {
        "full_symbol": full_symbol,
        "code": code,
        "symbol": full_symbol,
        "market": market,
        "trade_date": trade_date,
        "period": period,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "pre_close": 100.0,
        "volume": 1000,
        "amount": 100500.0,
        "pct_chg": 0.5,
        "change": 0.5,
        "data_source": data_source,
        "created_at": "2026-07-10T00:00:00Z",
        "updated_at": "2026-07-10T00:00:00Z",
    }
    if version is not ABSENT:
        doc["version"] = version
    if name is not ABSENT:
        doc["name"] = name
    doc.update(extra)
    if _id is not None:
        doc["_id"] = _id
    return doc


def make_sw_quote_docs(
    *,
    codes: Iterable[str] | None = None,
    dates: Iterable[str] | None = None,
    version: Any = 1,
    name: Any = ABSENT,
    data_source: str = "akshare",
    market: str = "CN",
    period: str = "daily",
    id_start: int = 1,
) -> list[dict[str, Any]]:
    """候选文档集（code × 交易日；确定性字符串 ``_id`` 从 ``id_start`` 递增）。"""
    code_list = list(codes) if codes is not None else list(UNIVERSE_SI)
    date_list = list(dates) if dates is not None else list(DATES)
    docs: list[dict[str, Any]] = []
    index = id_start
    for trade_date in date_list:
        for code in code_list:
            docs.append(
                make_quote_doc(
                    full_symbol=code,
                    trade_date=trade_date,
                    data_source=data_source,
                    market=market,
                    period=period,
                    version=version,
                    name=name,
                    _id=f"id{index:06d}",
                )
            )
            index += 1
    return docs


def make_mixed_quote_docs(*, id_start: int = 1) -> list[dict[str, Any]]:
    """D5 混合分类数据集（gates 全过；**不含** version==1 且 name 存在的候选，
    保证 V17-001 版本分区恒等式成立——见 :data:`MIXED_CLASSIFICATION`）。"""
    docs = [
        # already_compliant（version==1，无 name）
        make_quote_doc(
            full_symbol="801010.SI", trade_date="20260710", version=1,
            name=ABSENT, _id=f"id{id_start:06d}",
        ),
        # missing_version + name_present → both_needed
        make_quote_doc(
            full_symbol="801010.SI", trade_date="20260713", version=ABSENT,
            name="食品饮料", _id=f"id{id_start + 1:06d}",
        ),
        # nonconforming_version（int!=1，无 name）
        make_quote_doc(
            full_symbol="801080.SI", trade_date="20260710", version=2,
            name=ABSENT, _id=f"id{id_start + 2:06d}",
        ),
        # nonconforming_version（float）+ name_present → both_needed
        make_quote_doc(
            full_symbol="801080.SI", trade_date="20260713", version=1.5,
            name="电子", _id=f"id{id_start + 3:06d}",
        ),
        # nonconforming_version（str）+ name_present → both_needed
        make_quote_doc(
            full_symbol="801780.SI", trade_date="20260710", version="1",
            name="银行", _id=f"id{id_start + 4:06d}",
        ),
        # missing_version，无 name
        make_quote_doc(
            full_symbol="801780.SI", trade_date="20260713", version=ABSENT,
            name=ABSENT, _id=f"id{id_start + 5:06d}",
        ),
    ]
    return docs


# make_mixed_quote_docs 的预期分类计数（V17-001/002/003 对齐）
MIXED_CLASSIFICATION: dict[str, int] = {
    "already_compliant": 1,
    "missing_version": 2,
    "nonconforming_version": 3,
    "version_fix_needed": 5,
    "name_present": 3,
    "name_absent": 3,
    "both_needed": 3,
    "version_ok": 1,
    "version_ok_name_present": 0,
}


# ---------------------------------------------------------------------------
# gate 反例 fixture（D2 / D3 / C17-201/202/204/205）
# ---------------------------------------------------------------------------


def make_market_fail_docs(*, id_start: int = 1) -> list[dict[str, Any]]:
    """C17-204 反例：一条候选 market="HK"。"""
    docs = make_mixed_quote_docs(id_start=id_start)
    bad = dict(docs[0])
    bad["market"] = "HK"
    docs[0] = bad
    return docs


def make_code_family_fail_docs(*, id_start: int = 1) -> list[dict[str, Any]]:
    """C17-203 反例：一条候选 full_symbol ∉ U（999999.SI）。"""
    docs = make_mixed_quote_docs(id_start=id_start)
    bad = dict(docs[0])
    bad["full_symbol"] = "999999.SI"
    bad["code"] = "999999"
    bad["symbol"] = "999999.SI"
    docs[0] = bad
    return docs


def make_period_fail_docs(*, id_start: int = 1) -> list[dict[str, Any]]:
    """C17-205 反例：一条候选 period="weekly"。"""
    docs = make_mixed_quote_docs(id_start=id_start)
    bad = dict(docs[0])
    bad["period"] = "weekly"
    docs[0] = bad
    return docs


def make_data_source_fail_docs(*, id_start: int = 1) -> list[dict[str, Any]]:
    """C17-202 反例：一条候选 data_source="tushare"（仍是 .SI，非候选但观察）。"""
    docs = make_mixed_quote_docs(id_start=id_start)
    bad = dict(docs[0])
    bad["data_source"] = "tushare"
    docs[0] = bad
    return docs


def make_suffix_fail_docs(*, id_start: int = 1) -> list[dict[str, Any]]:
    """C17-201 反例：一条候选 full_symbol 无 .SI 后缀（.SH）。"""
    docs = make_mixed_quote_docs(id_start=id_start)
    bad = dict(docs[0])
    bad["full_symbol"] = "801010.SH"
    bad["code"] = "801010"
    bad["symbol"] = "801010.SH"
    docs[0] = bad
    return docs


def make_observation_docs(*, id_start: int = 1) -> list[dict[str, Any]]:
    """C17-206 观察项：非候选记录（.SI 但非 akshare；akshare 但非 .SI），
    仅计入 census 观察，不 mutate。"""
    return [
        make_quote_doc(
            full_symbol="801010.SI", trade_date="20260710", data_source="tushare",
            version=ABSENT, name="农林牧渔", _id=f"obs{id_start:06d}",
        ),
        make_quote_doc(
            full_symbol="600519.SH", trade_date="20260710", data_source="akshare",
            version=ABSENT, name="贵州茅台", _id=f"obs{id_start + 1:06d}",
        ),
    ]


# ---------------------------------------------------------------------------
# mongomock db / checkpoint helper
# ---------------------------------------------------------------------------


def make_db(
    *,
    quote_docs: Iterable[dict[str, Any]] = (),
    universe_docs: Iterable[dict[str, Any]] | None = None,
    db_name: str = "tradingagents",
) -> Any:
    """构造 fresh mongomock db，可选预置 ``index_daily_quotes`` /
    ``stock_sector_info``。"""
    db = mongomock.MongoClient().get_database(db_name)
    docs = list(quote_docs)
    if docs:
        db["index_daily_quotes"].insert_many(docs)
    uni = list(universe_docs) if universe_docs is not None else make_sw_universe()
    if uni:
        db["stock_sector_info"].insert_many(uni)
    return db


def make_checkpoint(tmp_path: Path, run_id: str, records: Iterable[dict[str, Any]]) -> Path:
    """写入 checkpoint JSONL 文件（模拟中断现场），返回文件路径。"""
    path = Path(tmp_path) / f"quote-governance-checkpoint-{run_id}.jsonl"
    lines = [json.dumps(rec, ensure_ascii=False, sort_keys=True) for rec in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
