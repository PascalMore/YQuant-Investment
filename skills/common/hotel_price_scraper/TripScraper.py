from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from base import BaseHotelScraper, OLD_SCRAPER_DIR, load_legacy_module
from models import HotelPriceRecord


try:
    legacy_trip = load_legacy_module("trip.py")
except ModuleNotFoundError:
    legacy_trip = SimpleNamespace(
        CONST_PARAM_TIMEOUT=10,
        CONST_ROOM_CARD_XPATH='//div[@data-test-id="mainRoomList"]//div[@class="commonRoomCard__BpNjl"]',
        gen_trip_url=lambda n, s, e, q_ad, q_ch, q_ro: (
            f"https://www.trip.com/hotels/detail/?hotelId={n}&checkIn={s}&checkOut={e}"
            f"&adult={q_ad}&children={q_ch}&crn={q_ro}&curr=JPY"
        ),
        parse_trip_hotel=None,
    )


class TripScraper(BaseHotelScraper):
    platform = "trip"

    def __init__(self, *, cookie_path: str | Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cookie_path = Path(cookie_path) if cookie_path else OLD_SCRAPER_DIR / "trip_cookies.json"

    def scrape(self, hotel_id: str, checkin: date, checkout: date) -> list[HotelPriceRecord]:
        if legacy_trip.parse_trip_hotel is None:
            raise RuntimeError("selenium is required for TripScraper")

        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        url = legacy_trip.gen_trip_url(
            hotel_id,
            checkin.strftime("%Y-%m-%d"),
            checkout.strftime("%Y-%m-%d"),
            self.adults,
            self.children,
            self.rooms,
        )
        driver = self._init_driver(webdriver, url)
        try:
            driver.get(url)
            WebDriverWait(driver, legacy_trip.CONST_PARAM_TIMEOUT).until(
                EC.presence_of_all_elements_located((By.XPATH, legacy_trip.CONST_ROOM_CARD_XPATH)),
                message="没有找到酒店报价",
            )
            hotel_name, prices = legacy_trip.parse_trip_hotel(driver)
            if hotel_name == -1:
                raise RuntimeError("Trip page title not found")
            self.sleep_between_requests()
            return self.build_records(hotel_name=hotel_name, checkin=checkin, rooms=prices)
        finally:
            driver.quit()

    def validate_cookie(self) -> bool:
        return self.cookie_path.exists() and self.cookie_path.stat().st_size > 0

    def getname(self) -> str:
        return self.platform

    def _init_driver(self, webdriver, url: str):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument(
            "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.3"
        )
        chrome_options.add_argument("Upgrade-Insecure-Requests=1")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--ignore-ssl-errors")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(legacy_trip.CONST_PARAM_TIMEOUT)
        driver.set_script_timeout(legacy_trip.CONST_PARAM_TIMEOUT)
        driver.get(url)
        with self.cookie_path.open("r", encoding="utf-8") as file:
            for cookie in json.load(file):
                driver.add_cookie(cookie)
        time.sleep(1)
        driver.refresh()
        return driver
