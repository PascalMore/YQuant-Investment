"""QualitySummary — Phase 2 质量汇总聚合（DESIGN-03-011 §6）。

mongo_db=None → noop 模式。catch-and-log，写入失败不抛到调用方。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..models import DataResult

logger = logging.getLogger(__name__)


class QualitySummary:
    """按 (domain, security_id, date) 聚合的质量汇总。

    mongo_db=None → noop 模式（不写任何数据，不抛异常）。
    """

    def __init__(
        self,
        mongo_db: Any = None,
        collection_name: str = "03_data_ud_quality_summary",
    ) -> None:
        self._mongo_db = mongo_db
        self._collection_name = collection_name

    def update(
        self,
        result: DataResult,
        *,
        quality_score: float | None,
        quality_tier: str | None,
        now: datetime | None = None,
    ) -> None:
        """更新质量汇总。catch-and-log 模式。"""
        if self._mongo_db is None:
            return

        if now is None:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
        date_str = now.strftime("%Y-%m-%d")
        doc_id = f"{result.domain}:{result.security_id.canonical}:{date_str}"
        provider = result.provider

        try:
            self._mongo_db[self._collection_name].update_one(
                {"_id": doc_id},
                {
                    "$setOnInsert": {
                        "domain": result.domain,
                        "security_id": result.security_id.canonical,
                        "date": date_str,
                    },
                    "$inc": {
                        "query_count": 1,
                        f"provider_distribution.{provider}": 1,
                    },
                    "$set": {
                        "last_updated": now,
                    },
                    "$min": {
                        "min_quality_score": quality_score
                        if quality_score is not None
                        else 999
                    },
                    "$max": {
                        "max_quality_score": quality_score
                        if quality_score is not None
                        else -1
                    },
                },
                upsert=True,
            )

            # avg_quality_score 精确计算（DESIGN §6.3）：先读再写。
            current = self._mongo_db[self._collection_name].find_one(
                {"_id": doc_id}
            )
            if current and current.get("query_count", 0) > 0 and quality_score is not None:
                old_count = current["query_count"]
                old_avg = current.get("avg_quality_score", 0.0)
                new_avg = (old_avg * (old_count - 1) + quality_score) / old_count
                self._mongo_db[self._collection_name].update_one(
                    {"_id": doc_id},
                    {"$set": {"avg_quality_score": new_avg}},
                )
        except Exception as exc:
            logger.warning(
                "QualitySummary.update failed (catch-and-log): %s", exc
            )

    def get_summary(
        self,
        domain: str,
        security_id: Any,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """查询质量汇总。无数据时返回 []。"""
        if self._mongo_db is None:
            return []

        query: dict[str, Any] = {
            "domain": domain,
            "security_id": security_id.canonical,
        }
        date_filter: dict[str, Any] = {}
        if from_date is not None:
            date_filter["$gte"] = from_date
        if to_date is not None:
            date_filter["$lte"] = to_date
        if date_filter:
            query["date"] = date_filter

        try:
            return list(
                self._mongo_db[self._collection_name]
                .find(query)
                .sort("date", -1)
            )
        except Exception as exc:
            logger.warning(
                "QualitySummary.get_summary failed (catch-and-log): %s", exc
            )
            return []


__all__ = ["QualitySummary"]