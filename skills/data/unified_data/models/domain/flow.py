"""Capital-flow domain object (Phase 3 P3-B).

This module hosts the :class:`CapitalFlowRecord` dataclass — the
canonical representation of a single (symbol, trade_date) capital-flow
row. Used by:

* ``services/flow_service.py`` — query path (per-stock daily flow +
  northbound) and the explicit refresh path (offline scaffold only).
* ``adapters/p3_persistence_writer.py`` — P3-B persistence writer
  reads / upserts into ``03_data_ud_stock_capital_flow``.

The dataclass shape (17 fields) is frozen at SPEC-03-014 V0.2 §3.2 and
re-pinned at DESIGN-03-014 V0.5 §3.2. Field semantics:

* ``symbol`` / ``market`` / ``trade_date`` — business unique key
  (V0.5 §0.4 ``P3_UNIQUE_KEYS_BY_CAPABILITY``). 必填; ``from_dict`` falls
  back to empty string so a missing key never raises KeyError
  (``from_dict`` 松映射 contract).
* ``main_net_inflow`` + the four band fields — main/super-large/large/
  medium/small net flow. Sign convention: **positive = net inflow,
  negative = net outflow** (SPEC §3.2 表 footnote).
* ``main_net_inflow_ratio`` — main-flow-as-percentage. Optional.
* ``northbound_*`` — only populated for 沪/深港通标的. Non-港通标的 the
  three fields are ``None`` and the record still persists (V0.5 §2.3
  "部分字段不可用").
* ``margin_*`` — 融资融券 fields. ``None`` when the symbol is not a
  融资融券标的 (SPEC §3.2 表 [待验证]).
* ``fetched_at`` — ISO-8601 fetch timestamp.
* ``provider`` — non-empty (必填); defaults to empty string when the
  source dict omits it.

The dataclass does not carry ``raw_payload`` — capital-flow data is too
voluminous to embed (SPEC §3.2 禁止字段 note).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapitalFlowRecord:
    """个股资金流记录（Phase 3 P3-B）。

    每条记录表示个股在某交易日的资金流向数据。
    消费方可通过 ``flow.capital_flow_daily``（个股）和
    ``flow.northbound_daily``（北向资金-个股级）获取。

    本数据为辅助研究数据，不构成交易指令或投资建议。

    ``record_scope`` 说明：

    * ``flow.capital_flow_daily`` 查询填充全部资金流字段
      （主力/大单/中单/小单/北向/融资融券）。
    * ``flow.northbound_daily`` 查询仅填充 ``northbound_*`` 字段
      （``symbol``/``market``/``trade_date`` 必有，其余资金流字段为空）。

    两者共享同一集合 ``03_data_ud_stock_capital_flow`` 和同一 domain
    object，但查询时填充的字段子集不同。
    """

    symbol: str  # (必填) 标的代码，如 "600519"
    market: str  # (必填) 市场，如 "CN"
    trade_date: str  # (必填) 交易日，格式 "YYYY-MM-DD"

    # 资金流核心字段
    main_net_inflow: float | None = None  # 主力净流入（元）；正=净流入，负=净流出
    super_large_net_inflow: float | None = None  # 超大单净流入（元）
    large_net_inflow: float | None = None  # 大单净流入（元）
    medium_net_inflow: float | None = None  # 中单净流入（元）
    small_net_inflow: float | None = None  # 小单净流入（元）
    main_net_inflow_ratio: float | None = None  # 主力净流入占比 %

    # 北向资金（仅沪/深港通标的）
    northbound_net_inflow: float | None = None  # 北向净买入（元）
    northbound_hold_shares: float | None = None  # 北向持股数（股）
    northbound_hold_ratio: float | None = None  # 北向持股比例 %

    # 融资融券
    margin_buy: float | None = None  # 融资买入额（元）
    margin_sell: float | None = None  # 融券卖出额（元）
    margin_balance: float | None = None  # 融资余额（元）

    # 元数据
    fetched_at: str | None = None  # 数据获取时间，ISO-8601
    provider: str = ""  # (必填) 数据来源，如 "akshare"

    @classmethod
    def from_dict(cls, d: dict) -> "CapitalFlowRecord":
        """从字典构造，缺失字段填 None。松弛映射，不抛 KeyError。

        Per V0.5 §3.2 the dataclass is a strict passthrough — the sign
        convention (positive = 净流入, negative = 净流出) is preserved
        without transformation. ``provider`` falls back to ``""`` so a
        missing provider is representable (matching SPEC §3.2 必填 with
        empty-string default).
        """
        return cls(
            symbol=str(d.get("symbol", "")),
            market=str(d.get("market", "")),
            trade_date=str(d.get("trade_date", "")),
            main_net_inflow=d.get("main_net_inflow"),
            super_large_net_inflow=d.get("super_large_net_inflow"),
            large_net_inflow=d.get("large_net_inflow"),
            medium_net_inflow=d.get("medium_net_inflow"),
            small_net_inflow=d.get("small_net_inflow"),
            main_net_inflow_ratio=d.get("main_net_inflow_ratio"),
            northbound_net_inflow=d.get("northbound_net_inflow"),
            northbound_hold_shares=d.get("northbound_hold_shares"),
            northbound_hold_ratio=d.get("northbound_hold_ratio"),
            margin_buy=d.get("margin_buy"),
            margin_sell=d.get("margin_sell"),
            margin_balance=d.get("margin_balance"),
            fetched_at=d.get("fetched_at"),
            provider=str(d.get("provider", "")),
        )

    @classmethod
    def from_northbound_dict(cls, d: dict) -> "CapitalFlowRecord":
        """Construct a record with the northbound field projection.

        Implements the V0.5 §3.2 ``record_scope`` rule for the
        ``flow.northbound_daily`` capability: only the
        ``{symbol, market, trade_date}`` business-key plus the three
        ``northbound_*`` fields plus the ``fetched_at`` / ``provider``
        metadata fields are populated. The five flow bands
        (``main_net_inflow`` etc.) plus the three ``margin_*`` fields
        are **explicitly** set to ``None`` regardless of what the
        source dict carries, so downstream code can rely on the
        scope contract.

        This is the **canonical** projection factory for northbound
        payloads and is the public entry point the
        :meth:`FlowService.get_northbound_flow` facade uses when
        shaping Router output. The factory does NOT mutate the input
        dict — it reads from it and builds a new
        :class:`CapitalFlowRecord`.
        """
        return cls(
            symbol=str(d.get("symbol", "")),
            market=str(d.get("market", "")),
            trade_date=str(d.get("trade_date", "")),
            main_net_inflow=None,
            super_large_net_inflow=None,
            large_net_inflow=None,
            medium_net_inflow=None,
            small_net_inflow=None,
            main_net_inflow_ratio=None,
            northbound_net_inflow=d.get("northbound_net_inflow"),
            northbound_hold_shares=d.get("northbound_hold_shares"),
            northbound_hold_ratio=d.get("northbound_hold_ratio"),
            margin_buy=None,
            margin_sell=None,
            margin_balance=None,
            fetched_at=d.get("fetched_at"),
            provider=str(d.get("provider", "")),
        )

    def to_canonical(self) -> "CapitalFlowRecord":
        """Return a new record with the canonical field subset for the capability.

        The current dataclass already holds the **full** 17-field
        shape; the canonical-object promise is enforced at the
        service-facade layer rather than via a per-record flag. This
        helper is therefore a **passthrough** — it exists so call
        sites that want to project a record before returning it can
        chain ``.to_canonical()`` without having to know whether the
        record was built via :meth:`from_dict` or
        :meth:`from_northbound_dict`. The returned record is a fresh
        :class:`CapitalFlowRecord` (the source is dataclass-cloneable
        via :func:`dataclasses.replace`), so future versions can add
        scope-dependent filtering here without breaking the public
        dataclass shape.

        Service-layer callers should prefer :meth:`from_dict` /
        :meth:`from_northbound_dict` for input shaping rather than
        calling :meth:`to_canonical` for output filtering — the latter
        is reserved for cases where the projection is symmetric (e.g.
        log emission, audit context).
        """
        # dataclass-style passthrough — every field is preserved. The
        # signature / return shape is fixed so future scope rules can
        # be added without churn at the call site.
        from dataclasses import replace

        return replace(self)


__all__ = ["CapitalFlowRecord"]