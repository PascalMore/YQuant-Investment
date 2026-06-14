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

    # -------------------------------------------------------------------------
    # Room category classification
    # -------------------------------------------------------------------------
    @staticmethod
    def _classify_room_category(room_name: str) -> str | None:
        """Classify a room name into 'twin' or 'double', or None if unmatched.

        Rule: check twin first (more specific), then double.
        - twin  : room_name contains "ツイン" or "twin" (case-insensitive)
        - double: room_name contains "ダブル" or "double" (case-insensitive)
        - None  : no match
        """
        lower = room_name.lower()
        if "ツイン" in room_name or "twin" in lower:
            return "twin"
        if "ダブル" in room_name or "double" in lower:
            return "double"
        return None

    # -------------------------------------------------------------------------
    # Record building
    # -------------------------------------------------------------------------
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
                    room_category="",
                    room_type="",
                    price=None,
                    currency=self.currency,
                    status="满房",
                )
            ]

        # Classify each room, skip None categories
        categorized: dict[str, list[tuple[str, Decimal | None]]] = {}
        for room in rooms:
            room_type = (room.get("room") or "").strip()
            category = self._classify_room_category(room_type)
            if category is None:
                continue
            price = parse_price(room.get("price"))
            categorized.setdefault(category, []).append((room_type, price))

        # Produce one record per category (lowest price)
        records: list[HotelPriceRecord] = []
        for category, items in categorized.items():
            best = min(items, key=lambda x: x[1] if x[1] is not None else float("inf"))
            best_room_type, best_price = best
            records.append(
                HotelPriceRecord(
                    hotel_name=hotel_name,
                    platform=self.platform,
                    checkin_date=checkin,
                    room_category=category,
                    room_type=best_room_type,
                    price=best_price,
                    currency=self.currency,
                    status="正常" if best_price is not None else "抓取失败",
                )
            )

        # If nothing matched, emit a "满房" record
        if not records:
            records.append(
                HotelPriceRecord(
                    hotel_name=hotel_name,
                    platform=self.platform,
                    checkin_date=checkin,
                    room_category="",
                    room_type="",
                    price=None,
                    currency=self.currency,
                    status="满房",
                )
            )
        return records


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
