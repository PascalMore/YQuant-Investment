"""Data models and validators for the Portfolio stock pool."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PoolZone(str, Enum):
    """Research lifecycle zones for stock pool entries."""

    SCAN = "SCAN"
    WATCH = "WATCH"
    CANDIDATE = "CANDIDATE"
    CONVICTION = "CONVICTION"


class StockPoolSource(str, Enum):
    """Allowed sources that can create stock pool entries."""

    ARGUS = "argus"
    SMART_MONEY_INSTITUTION = "smart_money_institution"
    SMART_MONEY_RETAIL = "smart_money_retail"
    SMART_MONEY_KOL = "smart_money_kol"
    MANUAL = "manual"
    RESEARCHER = "researcher"
    FACTOR_SCAN = "factor_scan"
    NEWS = "news"
    OTHER = "other"


class StockPoolStatus(str, Enum):
    """Lifecycle status for a stock pool entry."""

    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass
class AuditInfo:
    """Creation and update metadata embedded in stock pool records."""

    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a MongoDB-serializable dictionary."""
        return {
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }


@dataclass
class StockPoolEntry:
    """Validated stock pool entry payload."""

    stock_code: str
    wind_code: str
    stock_name: str
    pool_zone: PoolZone
    source: StockPoolSource
    entry_reason: Dict[str, Any]
    source_project: str = "portfolio"
    source_detail: Optional[str] = None
    source_signal_id: Optional[str] = None
    entry_date: datetime = field(default_factory=datetime.utcnow)
    exit_date: Optional[datetime] = None
    status: StockPoolStatus = StockPoolStatus.ACTIVE
    tags: List[str] = field(default_factory=list)
    memo: str = ""
    audit: Optional[AuditInfo] = None
    pending_transition: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Normalize enum values and validate required fields after init."""
        self.pool_zone = PoolZone(self.pool_zone)
        self.source = StockPoolSource(self.source)
        self.status = StockPoolStatus(self.status)
        self._validate()

    def _validate(self) -> None:
        """Validate required fields and lifecycle constraints."""
        required = {
            "stock_code": self.stock_code,
            "wind_code": self.wind_code,
            "stock_name": self.stock_name,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        if not isinstance(self.entry_reason, dict) or not self.entry_reason:
            raise ValueError("entry_reason must be a non-empty dict")
        if self.status == StockPoolStatus.INACTIVE and self.exit_date is None:
            raise ValueError("exit_date is required for inactive entries")
        if not isinstance(self.tags, list) or any(not isinstance(tag, str) for tag in self.tags):
            raise ValueError("tags must be a list of strings")

    def to_dict(self, actor: Optional[str] = None) -> Dict[str, Any]:
        """Return a MongoDB-ready dictionary for the entry."""
        now = datetime.utcnow()
        audit = self.audit or AuditInfo(created_at=now, updated_at=now, created_by=actor or "system")
        return {
            "stock_code": self.stock_code,
            "wind_code": self.wind_code,
            "stock_name": self.stock_name,
            "pool_zone": self.pool_zone.value,
            "source": self.source.value,
            "source_detail": self.source_detail,
            "source_project": self.source_project,
            "source_signal_id": self.source_signal_id,
            "entry_reason": dict(self.entry_reason),
            "entry_date": self.entry_date,
            "exit_date": self.exit_date,
            "status": self.status.value,
            "tags": list(self.tags),
            "memo": self.memo,
            "audit": audit.to_dict(),
            "pending_transition": self.pending_transition,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StockPoolEntry":
        """Build a validated entry from a dictionary."""
        audit_data = data.get("audit")
        audit = AuditInfo(**audit_data) if isinstance(audit_data, dict) else None
        return cls(
            stock_code=data["stock_code"],
            wind_code=data["wind_code"],
            stock_name=data["stock_name"],
            pool_zone=data["pool_zone"],
            source=data["source"],
            entry_reason=data["entry_reason"],
            source_detail=data.get("source_detail"),
            source_project=data.get("source_project") or data.get("source") or "portfolio",
            source_signal_id=data.get("source_signal_id") or data.get("signal_id"),
            entry_date=data.get("entry_date", datetime.utcnow()),
            exit_date=data.get("exit_date"),
            status=data.get("status", StockPoolStatus.ACTIVE.value),
            tags=data.get("tags", []),
            memo=data.get("memo", ""),
            audit=audit,
            pending_transition=data.get("pending_transition"),
        )


def validate_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a partial stock pool update."""
    normalized = dict(patch)
    if "pool_zone" in normalized:
        normalized["pool_zone"] = PoolZone(normalized["pool_zone"]).value
    if "source" in normalized:
        normalized["source"] = StockPoolSource(normalized["source"]).value
    for field_name in ("source_detail", "source_project", "source_signal_id"):
        if field_name in normalized and normalized[field_name] is not None:
            normalized[field_name] = str(normalized[field_name])
    if "status" in normalized:
        normalized["status"] = StockPoolStatus(normalized["status"]).value
    if "entry_reason" in normalized:
        if isinstance(normalized["entry_reason"], dict):
            pass  # OK
        elif normalized["entry_reason"] is None or normalized["entry_reason"] == "":
            normalized["entry_reason"] = {}  # Coerce empty/None to empty dict
        else:
            raise ValueError("entry_reason must be a dict")
    if "tags" in normalized and (
        not isinstance(normalized["tags"], list)
        or any(not isinstance(tag, str) for tag in normalized["tags"])
    ):
        raise ValueError("tags must be a list of strings")
    return normalized
