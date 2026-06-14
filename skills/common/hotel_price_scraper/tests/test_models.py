from datetime import date
from decimal import Decimal
import unittest

from models import HotelPriceRecord


class HotelPriceRecordTest(unittest.TestCase):
    def test_hotel_price_record_fields(self):
        record = HotelPriceRecord(
            hotel_name="Test Hotel",
            platform="jalan",
            checkin_date=date(2026, 5, 26),
            room_category="double",
            room_type="Double",
            price=Decimal("12000"),
            currency="JPY",
            status="正常",
        )

        self.assertEqual(record.hotel_name, "Test Hotel")
        self.assertEqual(record.platform, "jalan")
        self.assertEqual(record.checkin_date, date(2026, 5, 26))
        self.assertEqual(record.room_category, "double")
        self.assertEqual(record.room_type, "Double")
        self.assertEqual(record.price, Decimal("12000"))
        self.assertEqual(record.currency, "JPY")
        self.assertEqual(record.status, "正常")
        self.assertIsNotNone(record.created_at)

    def test_to_dict_includes_room_category(self):
        record = HotelPriceRecord(
            hotel_name="Test Hotel",
            platform="booking",
            checkin_date=date(2026, 6, 1),
            room_category="twin",
            room_type="スーペリアツインベッドルーム",
            price=Decimal("15000"),
            currency="JPY",
            status="正常",
        )
        d = record.to_dict()
        self.assertIn("room_category", d)
        self.assertEqual(d["room_category"], "twin")


if __name__ == "__main__":
    unittest.main()
