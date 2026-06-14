from __future__ import annotations

import re
from datetime import date
from typing import Any

import requests
from bs4 import BeautifulSoup

from base import BaseHotelScraper
from models import HotelPriceRecord


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
                "Accept-Language": "ja,en-US;q=0.7,en;q=0.6",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Host": "www.jalan.net",
            }
        )
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def scrape(self, hotel_id: str, checkin: date, checkout: date) -> list[HotelPriceRecord]:
        url = self._build_url(hotel_id, checkin, checkout)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        html = response.content.decode("cp932", errors="replace")
        hotel_name, rooms = self._parse_page(html)
        if hotel_name == -1:
            raise RuntimeError("Jalan cookie invalid or page title not found")
        self.sleep_between_requests()
        return self.build_records(hotel_name=hotel_name, checkin=checkin, rooms=rooms)

    def _build_url(self, hotel_id: str, checkin: date, checkout: date) -> str:
        nights = (checkout - checkin).days
        return (
            f"https://www.jalan.net/yad{hotel_id}/plan/"
            f"?screenId=UWW3101&yadNo={hotel_id}"
            f"&stayYear={checkin.year}&stayMonth={checkin.month}&stayDay={checkin.day}"
            f"&stayCount={nights}&roomCount={self.rooms}"
            f"&adultNum={self.adults}&child1Num={self.children or ''}"
            f"&reSearchFlg=1&roomCrack=200000"
            f"&smlCd=260205&distCd=01"
            f"&minPrice=0&maxPrice=999999&activeSort=17"
        )

    def _parse_page(self, html: str) -> tuple[str | int, list[dict[str, Any]]]:
        soup = BeautifulSoup(html, "html.parser")

        # Hotel name: extract from <title> tag ("ホテル名の料金一覧・宿泊プラン - ...")
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text()
            name_match = re.match(r"(.+?)の料金一覧", title_text)
            hotel_name = name_match.group(1).strip() if name_match else title_text.strip()
        else:
            return -1, []

        rooms: list[dict[str, Any]] = []

        # Plan items: a.p-searchResultItem__planName contains room/plan name
        plan_els = soup.find_all("a", class_=re.compile("p-searchResultItem__planName"))

        for plan_el in plan_els:
            room_name = plan_el.get_text(strip=True)

            # Navigate up to the <tr> plan card
            card = plan_el.find_parent("tr")
            if not card:
                continue

            # Price: span.p-searchResultItem__total within the same card
            price_el = card.find(class_=re.compile("p-searchResultItem__total"))
            if price_el:
                price_text = price_el.get_text(strip=True)
                rooms.append({"room": room_name, "price": price_text})

        return hotel_name, rooms

    def validate_cookie(self) -> bool:
        return bool(self.cookie)

    def getname(self) -> str:
        return self.platform
