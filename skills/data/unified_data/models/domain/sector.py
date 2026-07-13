"""Canonical sector classification (Phase 1A).

:class:`SectorClassification` maps to ``stock_sector_info``. The TA-CN
document records a single 3-tier classification record per
(``full_symbol``, ``classify_system``) pair.
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


__all__ = ["SectorClassification"]
