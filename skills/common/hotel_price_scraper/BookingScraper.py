from __future__ import annotations

import re
import time
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from base import BaseHotelScraper
from models import HotelPriceRecord


class BookingScraper(BaseHotelScraper):
    platform = "booking"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def scrape(self, hotel_id: str, checkin: date, checkout: date) -> list[HotelPriceRecord]:
        url = self._build_url(hotel_id, checkin, checkout)
        html = self._fetch_page(url)
        hotel_name, rooms = self._parse_page(html)
        if hotel_name == -1:
            raise RuntimeError("Booking page title not found or cookie expired")
        self.sleep_between_requests()
        return self.build_records(hotel_name=hotel_name, checkin=checkin, rooms=rooms)

    def _build_url(self, hotel_id: str, checkin: date, checkout: date) -> str:
        return (
            f"https://www.booking.com/hotel/jp/{hotel_id}.html"
            f"?checkin={checkin}&checkout={checkout}"
            f"&group_adults={self.adults}&group_children={self.children}"
            f"&no_rooms={self.rooms}&selected_currency=JPY&lang=ja"
        )

    def _fetch_page(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return self._fetch_page_once(url)
            except Exception as exc:
                last_error = exc
                time.sleep(2 + attempt)
        assert last_error is not None
        raise last_error

    def _fetch_page_once(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
                viewport={"width": 1920, "height": 1080},
            )

            if self.cookie:
                cookies = []
                for item in self.cookie.split("; "):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        cookies.append(
                            {"name": k.strip(), "value": v.strip(), "domain": ".booking.com", "path": "/"}
                        )
                context.add_cookies(cookies)

            page = context.new_page()
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            self._wait_for_stable_page(page)

            # Handle PIPL consent wall (React SPA needs full render)
            if "consent" in self._safe_title(page).lower():
                # Wait for React to render checkboxes and buttons
                time.sleep(2)
                page.evaluate(
                    "() => { "
                    "const boxes = document.querySelectorAll('input[type=\"checkbox\"]'); "
                    "for (const cb of boxes) { if (!cb.checked) cb.click(); } "
                    "}"
                )
                time.sleep(1)
                page.evaluate(
                    "() => { const btns = document.querySelectorAll('button'); "
                    "for (const btn of btns) { "
                    "const text = btn.textContent || ''; "
                    "if (text.includes('同意') || text.includes('Agree')) { btn.click(); return; } } }"
                )
                # Wait for page navigation after consent
                self._wait_for_stable_page(page, timeout=20000)

            # Extra wait for hotel page content to load
            self._wait_for_stable_page(page, timeout=20000)

            html = self._safe_content(page)
            browser.close()
            return html

    def _wait_for_stable_page(self, page, timeout: int = 15000) -> None:
        """Wait through Booking's client-side navigation without failing hard."""
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass
        try:
            page.wait_for_selector("h2.pp-header__title, .hprt-roomtype-icon-link, body", timeout=timeout)
        except Exception:
            pass
        time.sleep(1)

    def _safe_title(self, page) -> str:
        for attempt in range(3):
            try:
                return page.title()
            except Exception:
                self._wait_for_stable_page(page, timeout=10000)
                time.sleep(1 + attempt)
        return ""

    def _safe_content(self, page) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return page.content()
            except Exception as exc:
                last_error = exc
                self._wait_for_stable_page(page, timeout=10000)
                time.sleep(1 + attempt)
        assert last_error is not None
        raise last_error

    def _parse_page(self, html: str) -> tuple[str | int, list[dict[str, Any]]]:
        soup = BeautifulSoup(html, "html.parser")

        # Hotel name
        title_el = soup.find("h2", class_=re.compile("pp-header__title"))
        hotel_name = title_el.get_text(strip=True) if title_el else -1
        if hotel_name == -1:
            return -1, []

        rooms: list[dict[str, Any]] = []

        # Room type name elements
        room_type_els = soup.find_all("span", class_=re.compile("hprt-roomtype-icon-link"))

        for room_el in room_type_els:
            room_name = room_el.get_text(strip=True)

            # Navigate to parent tr to find associated prices
            parent_tr = room_el.find_parent("tr")
            if not parent_tr:
                parent_tr = room_el.find_parent(["table", "div", "section"])
            if not parent_tr:
                continue

            # Sale price: span.prco-valign-middle-helper contains the final discounted price
            price_els = parent_tr.find_all("span", class_="prco-valign-middle-helper")

            if price_els:
                # Take the first (lowest) sale price for this room type
                price_text = price_els[0].get_text(strip=True)
                rooms.append({"room": room_name, "price": price_text})

        return hotel_name, rooms

    def validate_cookie(self) -> bool:
        # Playwright handles PIPL consent automatically; cookie is optional
        return True

    def getname(self) -> str:
        return self.platform
