"""Canonical sector classification (Phase 1A) and snapshot (Phase 3 P3-A).

Two dataclasses live in this module:

* :class:`SectorClassification` — Phase 1A. Maps to the TA-CN
  ``stock_sector_info`` collection. The TA-CN document records a
  single 3-tier classification record per (``full_symbol``,
  ``classify_system``) pair.
* :class:`SectorSnapshot` — Phase 3 P3-A. Canonical shape of a
  single (sector_code, snapshot_date) sector / industry aggregate
  row (DESIGN-03-014 §3.1, SPEC-03-014 §3.1). 19 fields plus a
  relaxed :meth:`from_dict` factory. Strict business unique key is
  ``{market, sector_code, snapshot_date}`` (DESIGN §0.4 / SPEC
  §4.bis.1).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SectorClassification:
    """行业/板块分类 — ``stock_sector_info`` canonical。"""

    full_symbol: str
    classify_system: str
    l1_code: str
    l1_name: str
    l2_code: str | None = None
    l2_name: str | None = None
    l3_code: str | None = None
    l3_name: str | None = None
    datasource: str = "tushare"
    update_at: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "SectorClassification":
        """从 ``stock_sector_info`` 文档映射。"""
        if not isinstance(doc, dict):
            raise TypeError(
                f"SectorClassification.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        return cls(
            full_symbol=str(doc.get("full_symbol", "")),
            classify_system=str(doc.get("classify_system", "SW")),
            l1_code=str(doc.get("l1_code", "")),
            l1_name=str(doc.get("l1_name", "")),
            l2_code=doc.get("l2_code"),
            l2_name=doc.get("l2_name"),
            l3_code=doc.get("l3_code"),
            l3_name=doc.get("l3_name"),
            datasource=str(doc.get("datasource") or "tushare"),
            update_at=doc.get("update_at"),
        )


@dataclass
class SectorSnapshot:
    """板块/行业快照（Phase 3 P3-A）。

    每日各板块的聚合快照。每条记录表示一个板块在某交易日收盘后
    的快照数据。消费方可通过 ``sector.snapshot``（单板块）和
    ``sector.ranking``（当日排名）访问。

    本数据为辅助研究数据，不构成交易指令或投资建议。

    Field set is frozen at SPEC-03-014 §3.1 / DESIGN-03-014 §3.1.
    The 19 fields comprise four required business-identity fields
    (``sector_code``, ``sector_name``, ``sector_type``,
    ``snapshot_date``) plus ``market`` / ``provider`` defaults, three
    integer counts (advance / decline / total) and the remaining
    ranking / leading-stock / volume / membership / metadata fields
    defaulting to ``None``. The dataclass does NOT enforce the
    ``advance_count + decline_count <= total_count`` invariant — that
    is the provider's responsibility per SPEC §3.1 字段约束.
    """

    sector_code: str                           # (必填) 板块代码，如 "BK0489"
    sector_name: str                           # (必填) 板块名称，如 "白酒"
    sector_type: str                           # (必填) industry / concept / region / style
    snapshot_date: str                         # (必填) 快照日期，格式 "YYYY-MM-DD"
    market: str = "CN"                         # (必填) 市场
    provider: str = ""                         # (必填) 数据来源，如 "akshare"

    # 排名与涨跌
    rank: int | None = None                    # [可选] 当日涨幅排名（1=涨幅最高）
    pct_chg: float | None = None               # [可选] 板块涨跌幅 %（如 2.35）

    # 领涨信息
    leading_stock: str | None = None           # [可选] 领涨股代码（如 "600519"）
    leading_stock_name: str | None = None      # [可选] 领涨股名称
    leading_pct_chg: float | None = None       # [可选] 领涨股涨幅 %

    # 涨跌家数
    advance_count: int = 0                     # 上涨家数
    decline_count: int = 0                     # 下跌家数
    total_count: int = 0                       # 成分股总数

    # 资金流与量价
    turnover_rate: float | None = None         # [可选] 板块换手率 %
    main_net_inflow: float | None = None       # [可选] 主力净流入（元）

    # 元数据
    members: list[str] | None = None           # [可选] 成分股代码列表
    fetched_at: str | None = None              # [可选] 数据获取时间，ISO-8601
    raw_payload: dict | None = None            # [可选] 原始 AKShare 返回

    @classmethod
    def from_dict(cls, d: dict) -> "SectorSnapshot":
        """从字典构造，缺失字段填 None / 0。松弛映射，不抛 KeyError。

        Implements the SPEC-03-014 §3.1 ``from_dict`` contract:
        required text fields fall back to empty strings, optional
        numeric fields fall back to ``None`` (with the three count
        fields coerced to ``int`` and defaulting to ``0``), and the
        list field defaults to ``None`` if missing. Extra keys in
        ``d`` are silently ignored — see test_provider_phase3 contract
        note ⑧.
        """
        if not isinstance(d, dict):
            raise TypeError(
                f"SectorSnapshot.from_dict expects dict, got {type(d).__name__}"
            )
        return cls(
            sector_code=str(d.get("sector_code", "")),
            sector_name=str(d.get("sector_name", "")),
            sector_type=str(d.get("sector_type", "")),
            snapshot_date=str(d.get("snapshot_date", "")),
            market=str(d.get("market", "CN")),
            provider=str(d.get("provider", "")),
            rank=d.get("rank"),
            pct_chg=d.get("pct_chg"),
            leading_stock=d.get("leading_stock"),
            leading_stock_name=d.get("leading_stock_name"),
            leading_pct_chg=d.get("leading_pct_chg"),
            advance_count=d.get("advance_count", 0) or 0,
            decline_count=d.get("decline_count", 0) or 0,
            total_count=d.get("total_count", 0) or 0,
            turnover_rate=d.get("turnover_rate"),
            main_net_inflow=d.get("main_net_inflow"),
            members=d.get("members"),
            fetched_at=d.get("fetched_at"),
            raw_payload=d.get("raw_payload"),
        )


__all__ = ["SectorClassification", "SectorSnapshot"]
