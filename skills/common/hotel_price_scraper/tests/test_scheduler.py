from datetime import date
from decimal import Decimal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import HotelPriceRecord
from scheduler import HotelPriceScheduler, SCRAPER_CLASSES


class FailingScraper:
    def validate_cookie(self):
        return True

    def scrape(self, hotel_id, checkin, checkout):
        raise RuntimeError("boom")


class WorkingScraper:
    def validate_cookie(self):
        return True

    def scrape(self, hotel_id, checkin, checkout):
        return [
            HotelPriceRecord(
                hotel_name=f"Hotel {hotel_id}",
                platform="booking",
                checkin_date=checkin,
                room_category="double",
                room_type="Double",
                price=Decimal("100"),
                currency="JPY",
                status="正常",
            )
        ]


class SchedulerTest(unittest.TestCase):
    def test_scheduler_isolates_single_platform_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            config = tmp_path / "config.yaml"
            config.write_text(
                """
query:
  days_ahead: 1
  nights: 1
  adults: 2
  children: 0
  rooms: 1
  currency: JPY
request_interval_seconds: 0
concurrent: 2
hotels:
  - hotel_key: test
    name: Test
    platforms:
      jalan: "bad"
      booking: "ok"
platforms:
  jalan: {}
  booking: {}
""",
                encoding="utf-8",
            )

            scheduler = HotelPriceScheduler(config)
            with patch.object(scheduler, "_selected_platforms", return_value=["jalan", "booking"]), patch.object(
                scheduler,
                "_create_scraper",
                side_effect=lambda platform: FailingScraper() if platform == "jalan" else WorkingScraper(),
            ):
                result = scheduler.run(platform="all", output_dir=tmp_path / "output", days=1, send_email=False)

            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.records[0].hotel_name, "Hotel ok")
            self.assertEqual(len(result.errors), 1)
            self.assertEqual(result.errors[0]["platform"], "jalan")
            self.assertTrue(result.output_path.exists())

    def test_scrape_classes_only_has_jalan_and_booking(self):
        """Verify TripScraper has been removed from SCRAPER_CLASSES."""
        self.assertIn("jalan", SCRAPER_CLASSES)
        self.assertIn("booking", SCRAPER_CLASSES)
        self.assertNotIn("trip", SCRAPER_CLASSES)


if __name__ == "__main__":
    unittest.main()
