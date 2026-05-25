from __future__ import annotations

from datetime import date

import requests
from bs4 import BeautifulSoup

from base import BaseHotelScraper, load_legacy_module
from models import HotelPriceRecord


legacy_jalan = load_legacy_module("jalan.py")


class JalanScraper(BaseHotelScraper):
    platform = "jalan"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "zh-CN,zh-TW;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Host": "www.jalan.net",
            }
        )
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def scrape(self, hotel_id: str, checkin: date, checkout: date) -> list[HotelPriceRecord]:
        url = legacy_jalan.gen_jalan_url(hotel_id, checkin, (checkout - checkin).days, self.adults, self.children, self.rooms)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content.decode("cp932", errors="ignore"), "html.parser")
        hotel_name, prices = legacy_jalan.parse_jalan_hotel(soup)
        if hotel_name == -1:
            raise RuntimeError("Jalan cookie invalid or page title not found")
        self.sleep_between_requests()
        return self.build_records(hotel_name=hotel_name, checkin=checkin, rooms=prices)

    def validate_cookie(self) -> bool:
        return bool(self.cookie)

    def getname(self) -> str:
        return self.platform
