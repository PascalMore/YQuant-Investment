from datetime import date
from decimal import Decimal
import unittest

from bs4 import BeautifulSoup

from base import BaseHotelScraper
from BookingScraper import BookingScraper


class BookingScraperTest(unittest.TestCase):
    def test_room_category_classification(self):
        """Verify _classify_room_category returns correct categories."""
        self.assertEqual(BaseHotelScraper._classify_room_category("スーペリアツインベッドルーム"), "twin")
        self.assertEqual(BaseHotelScraper._classify_room_category("ダブルベッドルーム"), "double")
        self.assertEqual(BaseHotelScraper._classify_room_category("Twin Room"), "twin")
        self.assertEqual(BaseHotelScraper._classify_room_category("DOUBLE SUITE"), "double")
        self.assertIsNone(BaseHotelScraper._classify_room_category("ベッドルーム"))
        self.assertIsNone(BaseHotelScraper._classify_room_category("スイート"))

    def test_build_records_multiple_rooms(self):
        """Verify build_records picks lowest price per category from multiple rooms."""
        scraper = BookingScraper(request_interval=0)
        scraper.currency = "JPY"

        rooms = [
            {"room": "ツインルーム", "price": "15000"},
            {"room": "ダブルルーム", "price": "13000"},
            {"room": "ツインルーム", "price": "12000"},  # lower twin price
            {"room": "ベッドルーム", "price": "11000"},  # no category → skipped
        ]
        records = scraper.build_records(
            hotel_name="Test Hotel",
            checkin=date(2026, 6, 1),
            rooms=rooms,
        )

        self.assertEqual(len(records), 2)
        by_cat = {r.room_category: r for r in records}
        self.assertEqual(by_cat["twin"].price, Decimal("12000"))
        self.assertEqual(by_cat["twin"].room_type, "ツインルーム")
        self.assertEqual(by_cat["double"].price, Decimal("13000"))
        self.assertEqual(by_cat["double"].room_type, "ダブルルーム")

    def test_build_records_empty(self):
        scraper = BookingScraper(request_interval=0)
        scraper.currency = "JPY"
        records = scraper.build_records(hotel_name="X", checkin=date(2026, 1, 1), rooms=None)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, "满房")
        self.assertEqual(records[0].room_category, "")

    def test_parse_page_extracts_hotel_name(self):
        """Verify _parse_page extracts hotel name from page title element."""
        scraper = BookingScraper(request_interval=0)
        html = '<h2 class="pp-header__title">テストホテル名</h2>'
        name, rooms = scraper._parse_page(html)
        self.assertEqual(name, "テストホテル名")

    def test_parse_page_returns_minus1_on_missing_title(self):
        """Verify _parse_page returns -1 when title element is absent."""
        scraper = BookingScraper(request_interval=0)
        name, rooms = scraper._parse_page("<html><body>no title</body></html>")
        self.assertEqual(name, -1)
        self.assertEqual(rooms, [])

    def test_parse_page_extracts_room_types_and_prices(self):
        """Verify _parse_page extracts room types and prices from Booking HTML structure."""
        scraper = BookingScraper(request_interval=0)
        html = """
        <html><body>
        <h2 class="pp-header__title">テストホテル</h2>
        <table>
          <tr>
            <span class="hprt-roomtype-icon-link">ダブルルーム</span>
            <span class="prco-valign-middle-helper">￥7,087</span>
          </tr>
          <tr>
            <span class="hprt-roomtype-icon-link">ツインルーム</span>
            <span class="prco-valign-middle-helper">￥8,500</span>
          </tr>
          <tr>
            <span class="hprt-roomtype-icon-link">ダブルルーム</span>
            <span class="prco-valign-middle-helper">￥7,500</span>
          </tr>
        </table>
        </body></html>
        """
        name, rooms = scraper._parse_page(html)
        self.assertEqual(name, "テストホテル")
        self.assertEqual(len(rooms), 3)
        # double rooms: prices 7087, 7500 → lowest 7087
        # twin room: price 8500
        double_prices = [r for r in rooms if "ダブル" in r["room"]]
        twin_prices = [r for r in rooms if "ツイン" in r["room"]]
        self.assertEqual(len(double_prices), 2)
        self.assertEqual(len(twin_prices), 1)
        # Lowest double price
        lowest_double = min(double_prices, key=lambda r: float(r["price"].replace(",", "").replace("￥", "").replace("¥", "")))
        self.assertEqual(lowest_double["price"], "￥7,087")

    def test_parse_page_with_yen_symbol(self):
        """Verify price parsing handles ¥ symbol (used in some Booking variants)."""
        scraper = BookingScraper(request_interval=0)
        html = """
        <html><body>
        <h2 class="pp-header__title">京都ホテル</h2>
        <tr>
          <span class="hprt-roomtype-icon-link">ツインルーム</span>
          <span class="prco-valign-middle-helper">¥9,000</span>
        </tr>
        </body></html>
        """
        name, rooms = scraper._parse_page(html)
        self.assertEqual(name, "京都ホテル")
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]["room"], "ツインルーム")
        # Price text contains ¥
        self.assertIn("9,000", rooms[0]["price"])

    def test_build_records_parsed_rooms(self):
        """Verify build_records works with the room dict format from _parse_page."""
        scraper = BookingScraper(request_interval=0)
        scraper.currency = "JPY"
        rooms = [
            {"room": "ツインルーム", "price": "8500"},
            {"room": "ダブルルーム", "price": "7087"},
        ]
        records = scraper.build_records(
            hotel_name="テストホテル",
            checkin=date(2026, 6, 22),
            rooms=rooms,
        )
        self.assertEqual(len(records), 2)
        by_cat = {r.room_category: r for r in records}
        self.assertEqual(by_cat["twin"].price, Decimal("8500"))
        self.assertEqual(by_cat["double"].price, Decimal("7087"))
        self.assertEqual(by_cat["double"].status, "正常")

    def test_validate_cookie_returns_true(self):
        """Verify validate_cookie returns True (Playwright handles consent automatically)."""
        scraper = BookingScraper()
        self.assertTrue(scraper.validate_cookie())

    def test_getname_returns_platform(self):
        scraper = BookingScraper()
        self.assertEqual(scraper.getname(), "booking")

    def test_build_url(self):
        """Verify _build_url constructs correct Booking URL."""
        scraper = BookingScraper()
        url = scraper._build_url("legasta-kyoto-shirakawa-sanjo", date(2026, 6, 22), date(2026, 6, 23))
        self.assertIn("booking.com/hotel/jp/legasta-kyoto-shirakawa-sanjo", url)
        self.assertIn("checkin=2026-06-22", url)
        self.assertIn("checkout=2026-06-23", url)
        self.assertIn("selected_currency=JPY", url)
        self.assertIn("lang=ja", url)


if __name__ == "__main__":
    unittest.main()