"""Argus signal subscriber for Portfolio stock pool ingestion."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

from .config import ARGUS_CONFIG


DEFAULT_MONGO_URI = "mongodb://172.25.240.1:27017/"
ARGUS_TO_PORTFOLIO_ZONE = {
    "SCAN": "SCAN",
    "WATCH": "WATCH",
    "CANDIDATE": "CANDIDATE",
    "CONVICTION": "CONVICTION",
    "FOCUS": "CONVICTION",
}


class ArgusPortfolioSubscriber:
    """Read Argus signals from MongoDB and convert them for Portfolio ingestion."""

    def __init__(
        self,
        client: Optional[MongoClient] = None,
        mongo_uri: str = DEFAULT_MONGO_URI,
        database: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> None:
        """Initialize the subscriber with MongoDB connection settings."""
        mongo_config = ARGUS_CONFIG.get("mongo", {})
        collections = ARGUS_CONFIG.get("output_collections") or mongo_config.get("collections", {})
        self.client = client or MongoClient(mongo_uri)
        self.db = self.client[database or mongo_config.get("database", "tradingagents")]
        self.collection = self.db[collection or collections.get("signal", "08_research_argus_signal")]

    def get_latest_signals(
        self,
        trade_date: str,
        min_confidence: float = 0.7,
        pool_zone: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return latest Argus signals for one trade date, filtered by confidence and zone."""
        target_zone = self._normalize_zone(pool_zone) if pool_zone else None
        signals = [
            signal
            for signal in self.collection.find({})
            if self._matches_trade_date(signal, trade_date)
            and float(signal.get("confidence", 0.0)) >= min_confidence
            and (target_zone is None or self._signal_zone(signal) == target_zone)
        ]
        return list(self._deduplicate_latest(signals).values())

    def to_portfolio_ingest_payload(
        self,
        signals: List[Dict[str, Any]],
        mode: str = "upsert_scan_only",
    ) -> List[Dict[str, Any]]:
        """Convert Argus signals into StockPoolIngestionService signal payloads."""
        return [
            payload
            for signal in signals
            for payload in self._signal_to_entries(signal, mode)
        ]

    def get_stock_signals(
        self,
        wind_code: str,
        days: int = 7,
        min_confidence: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Return recent Argus signals that mention one Wind code."""
        since = datetime.utcnow() - timedelta(days=max(1, days))
        signals = [
            signal
            for signal in self.collection.find({})
            if float(signal.get("confidence", 0.0)) >= min_confidence
            and self._generated_at(signal) >= since
            and any(stock.get("wind_code") == wind_code for stock in signal.get("target_stocks", []))
        ]
        return list(self._deduplicate_latest(signals).values())

    def _signal_to_entries(self, signal: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
        zone = self._signal_zone(signal)
        if mode == "upsert_scan_only" and zone != "SCAN":
            return []
        generated_at = self._generated_at(signal)
        entries = []
        for stock in signal.get("target_stocks", []):
            wind_code = stock.get("wind_code", "")
            entries.append(
                {
                    "stock_code": wind_code.split(".")[0],
                    "wind_code": wind_code,
                    "stock_name": stock.get("stock_name", ""),
                    "pool_zone": zone,
                    "source": "argus",
                    "entry_date": generated_at,
                    "entry_reason": {
                        "signal_id": signal.get("signal_id"),
                        "signal_type": signal.get("signal_type"),
                        "direction": signal.get("direction"),
                        "confidence": signal.get("confidence"),
                        "product_code": signal.get("product_code"),
                        "product_name": signal.get("product_name"),
                        "reason": signal.get("reason", ""),
                        "holding_ratio_change": stock.get("holding_ratio_change", 0),
                        "market_value_change": stock.get("market_value_change", 0),
                        "metadata": signal.get("metadata", {}),
                    },
                    "tags": ["argus", str(signal.get("signal_type", "")).lower()],
                    "memo": signal.get("reason", ""),
                }
            )
        return entries

    def _signal_zone(self, signal: Dict[str, Any]) -> str:
        metadata = signal.get("metadata") or {}
        return self._normalize_zone(metadata.get("pool_zone") or signal.get("pool_zone") or "SCAN")

    @staticmethod
    def _normalize_zone(zone: str) -> str:
        normalized = str(zone).upper()
        if normalized not in ARGUS_TO_PORTFOLIO_ZONE:
            raise ValueError(f"Unsupported Argus pool zone: {zone}")
        return ARGUS_TO_PORTFOLIO_ZONE[normalized]

    @staticmethod
    def _matches_trade_date(signal: Dict[str, Any], trade_date: str) -> bool:
        return str(signal.get("trade_date") or signal.get("date") or signal.get("valid_until") or signal.get("generated_at", "")[:10]) == trade_date

    @staticmethod
    def _generated_at(signal: Dict[str, Any]) -> datetime:
        value = signal.get("generated_at") or signal.get("created_at")
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        return datetime.utcnow()

    def _deduplicate_latest(self, signals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        latest: Dict[str, Dict[str, Any]] = {}
        for signal in sorted(signals, key=self._generated_at):
            latest[signal.get("signal_id") or id(signal)] = signal
        return latest
