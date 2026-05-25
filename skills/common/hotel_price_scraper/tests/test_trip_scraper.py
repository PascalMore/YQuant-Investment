import tempfile
import unittest
from pathlib import Path

from TripScraper import TripScraper


class TripScraperTest(unittest.TestCase):
    def test_trip_cookie_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cookie_path = Path(tmpdir) / "trip_cookies.json"
            scraper = TripScraper(cookie_path=cookie_path, request_interval=0)
            self.assertFalse(scraper.validate_cookie())

            cookie_path.write_text("[]", encoding="utf-8")
            self.assertTrue(scraper.validate_cookie())


if __name__ == "__main__":
    unittest.main()
