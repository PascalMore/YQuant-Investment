import unittest

from bs4 import BeautifulSoup

from BookingScraper import legacy_booking


class BookingScraperTest(unittest.TestCase):
    def test_parse_booking_hotel_reuses_legacy_parser(self):
        html = """
        <h2 class="pp-header__title">Test Booking</h2>
        <table><tr data-block-id="room-1">
          <span class="hprt-roomtype-icon-link">Double Room</span>
          <div class="bui-price-display__value prco-text-nowrap-helper prco-inline-block-maker-helper prco-f-font-heading">JPY 13,000</div>
        </tr></table>
        """
        name, prices = legacy_booking.parse_booking_hotel(BeautifulSoup(html, "html.parser"))

        self.assertEqual(name, "Test Booking")
        self.assertEqual(prices[0]["room"], "Double Room")
        self.assertEqual(prices[0]["price"], "JPY 13,000")


if __name__ == "__main__":
    unittest.main()
