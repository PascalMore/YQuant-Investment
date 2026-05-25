from __future__ import annotations

from datetime import date

import requests
from bs4 import BeautifulSoup

from base import BaseHotelScraper, load_legacy_module
from models import HotelPriceRecord


legacy_booking = load_legacy_module("booking.py")


class BookingScraper(BaseHotelScraper):
    platform = "booking"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Cache-Control": "max-age=0",
                "Upgrade-Insecure-Requests": "1",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "zh-CN,zh-TW;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            }
        )
        if self.cookie:
            cookie_dict = {
                item.split("=", 1)[0]: item.split("=", 1)[1]
                for item in self.cookie.split("; ")
                if "=" in item
            }
            self.session.cookies = requests.utils.cookiejar_from_dict(cookie_dict)

    def scrape(self, hotel_id: str, checkin: date, checkout: date) -> list[HotelPriceRecord]:
        url = legacy_booking.gen_booking_url(
            hotel_id,
            checkin.strftime("%Y-%m-%d"),
            checkout.strftime("%Y-%m-%d"),
            self.adults,
            self.children,
            self.rooms,
        )
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        hotel_name, prices = legacy_booking.parse_booking_hotel(soup)
        if hotel_name == -1:
            raise RuntimeError("Booking cookie invalid or page title not found")
        self.sleep_between_requests()
        return self.build_records(hotel_name=hotel_name.strip(), checkin=checkin, rooms=prices)

    def validate_cookie(self) -> bool:
        return bool(self.cookie)

    def getname(self) -> str:
        return self.platform
