import unittest

from bs4 import BeautifulSoup

from JalanScraper import legacy_jalan


class JalanScraperTest(unittest.TestCase):
    def test_parse_jalan_hotel_reuses_legacy_parser(self):
        html = """
        <div class="yado_header_hotel" id="yado_header_hotel_name"> Test Jalan </div>
        <p class="yado_header_access">Kyoto</p>
        <table><tr id="room-1">
          <a class="p-searchResultItem__planName">Double Room</a>
          <span class="p-searchResultItem__total">12,000円</span>
        </tr></table>
        """
        name, prices = legacy_jalan.parse_jalan_hotel(BeautifulSoup(html, "html.parser"))

        self.assertEqual(name.strip(), "Test Jalan")
        self.assertEqual(prices[0]["room"], "Double Room")
        self.assertEqual(prices[0]["price"], "12,000円")


if __name__ == "__main__":
    unittest.main()
