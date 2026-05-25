from __future__ import annotations

import importlib.util
import re
import time
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

from models import HotelPriceRecord


COMMON_DIR = Path(__file__).resolve().parents[1]
OLD_SCRAPER_DIR = COMMON_DIR / "su-scraper" / "scripts"


class BaseHotelScraper(ABC):
    platform: str

    def __init__(
        self,
        *,
        adults: int = 2,
        children: int = 0,
        rooms: int = 1,
        nights: int = 1,
        currency: str = "JPY",
        request_interval: float = 3.0,
        cookie: str | None = None,
    ) -> None:
        self.adults = adults
        self.children = children
        self.rooms = rooms
        self.nights = nights
        self.currency = currency
        self.request_interval = request_interval
        self.cookie = cookie or ""

    @abstractmethod
    def scrape(self, hotel_id: str, checkin: date, checkout: date) -> list[HotelPriceRecord]:
        pass

    @abstractmethod
    def validate_cookie(self) -> bool:
        pass

    @abstractmethod
    def getname(self) -> str:
        pass

    def sleep_between_requests(self) -> None:
        if self.request_interval > 0:
            time.sleep(self.request_interval)

    def build_records(
        self,
        *,
        hotel_name: str,
        checkin: date,
        rooms: list[dict[str, Any]] | None,
    ) -> list[HotelPriceRecord]:
        if not rooms:
            return [
                HotelPriceRecord(
                    hotel_name=hotel_name,
                    platform=self.platform,
                    checkin_date=checkin,
                    room_type="",
                    price=None,
                    currency=self.currency,
                    status="满房",
                )
            ]

        return [
            HotelPriceRecord(
                hotel_name=hotel_name,
                platform=self.platform,
                checkin_date=checkin,
                room_type=(room.get("room") or "").strip(),
                price=parse_price(room.get("price")),
                currency=self.currency,
                status="正常" if parse_price(room.get("price")) is not None else "抓取失败",
            )
            for room in rooms
        ]


def load_legacy_module(filename: str) -> ModuleType:
    path = OLD_SCRAPER_DIR / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load legacy scraper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_price(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return Decimal(match.group(0)) if match else None
