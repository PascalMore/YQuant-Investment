from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HotelPriceRecord:
    hotel_name: str
    platform: str
    checkin_date: date
    room_type: str
    price: Decimal | None
    currency: str
    status: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checkin_date"] = self.checkin_date.isoformat()
        data["created_at"] = self.created_at.isoformat(timespec="seconds")
        data["price"] = None if self.price is None else float(self.price)
        return data


@dataclass
class RunResult:
    records: list[HotelPriceRecord] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    output_path: Path | None = None
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return bool(self.records) and not self.errors

    def finish(self) -> "RunResult":
        self.ended_at = datetime.now()
        self.summary.update(
            {
                "records": len(self.records),
                "errors": len(self.errors),
                "started_at": self.started_at.isoformat(timespec="seconds"),
                "ended_at": self.ended_at.isoformat(timespec="seconds"),
            }
        )
        return self
