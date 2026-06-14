from datetime import date
from decimal import Decimal
import unittest

from base import BaseHotelScraper
from JalanScraper import JalanScraper


class JalanScraperTest(unittest.TestCase):
    def test_parse_page_extracts_hotel_name_and_rooms(self):
        scraper = JalanScraper(request_interval=0)
        html = """
        <html><head><title>京都ホテルの料金一覧・宿泊プラン - じゃらんnet</title></head><body>
        <tr class="js-searchYadoRoomPlanCd">
          <td class="p-searchResultItem__planNameCell">
            <a class="p-searchResultItem__planName jsc-planDetailLink">スタンダードツイン</a>
          </td>
          <td class="p-searchResultItem__totalCell">
            <span class="p-searchResultItem__total">12,000円</span>
          </td>
        </tr>
        <tr class="js-searchYadoRoomPlanCd">
          <td class="p-searchResultItem__planNameCell">
            <a class="p-searchResultItem__planName jsc-planDetailLink">エコノミーダブル</a>
          </td>
          <td class="p-searchResultItem__totalCell">
            <span class="p-searchResultItem__total">8,500円</span>
          </td>
        </tr>
        </body></html>
        """
        name, rooms = scraper._parse_page(html)
        self.assertEqual(name, "京都ホテル")
        self.assertEqual(len(rooms), 2)
        self.assertEqual(rooms[0]["room"], "スタンダードツイン")
        self.assertEqual(rooms[0]["price"], "12,000円")
        self.assertEqual(rooms[1]["room"], "エコノミーダブル")
        self.assertEqual(rooms[1]["price"], "8,500円")

    def test_parse_page_returns_minus1_on_missing_title(self):
        scraper = JalanScraper(request_interval=0)
        html = "<html><body>No title here</body></html>"
        name, rooms = scraper._parse_page(html)
        self.assertEqual(name, -1)
        self.assertEqual(rooms, [])

    def test_build_url(self):
        scraper = JalanScraper(request_interval=0)
        url = scraper._build_url("377340", date(2026, 7, 1), date(2026, 7, 2))
        self.assertIn("yadNo=377340", url)
        self.assertIn("stayYear=2026", url)
        self.assertIn("stayMonth=7", url)
        self.assertIn("stayDay=1", url)

    def test_room_category_classification_jalan(self):
        """Jalan room names can contain Japanese keywords."""
        self.assertEqual(BaseHotelScraper._classify_room_category("ＪＤツイン"), "twin")
        self.assertEqual(BaseHotelScraper._classify_room_category("デラックスダブル"), "double")
        self.assertEqual(BaseHotelScraper._classify_room_category("スタンダードツイン"), "twin")
        self.assertIsNone(BaseHotelScraper._classify_room_category("スタンダード"))

    def test_build_records_jalan(self):
        scraper = JalanScraper(request_interval=0)
        scraper.currency = "JPY"

        rooms = [
            {"room": "ツインルーム", "price": "20000"},
            {"room": "ダブルルーム", "price": "18000"},
        ]
        records = scraper.build_records(
            hotel_name="Jalan Hotel",
            checkin=date(2026, 6, 1),
            rooms=rooms,
        )

        self.assertEqual(len(records), 2)
        by_cat = {r.room_category: r for r in records}
        self.assertEqual(by_cat["twin"].price, Decimal("20000"))
        self.assertEqual(by_cat["double"].price, Decimal("18000"))

    def test_getname_returns_platform(self):
        scraper = JalanScraper(request_interval=0)
        self.assertEqual(scraper.getname(), "jalan")


if __name__ == "__main__":
    unittest.main()
