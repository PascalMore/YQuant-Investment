from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from models import HotelPriceRecord, RunResult


RECORD_COLUMNS = ["hotel_name", "platform", "checkin_date", "room_category", "room_type", "price", "currency", "status", "created_at"]


class ExcelExporter:
    def export(self, result: RunResult, output_dir: str | Path, run_date: date | None = None) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_date = run_date or date.today()
        output_path = output_dir / f"hotel_price_report_{run_date.isoformat()}.xlsx"

        records = [record.to_dict() for record in result.records]
        by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            by_platform[record["platform"]].append(record)

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            self._summary_frame(result.records).to_excel(writer, sheet_name="Summary", index=False)
            for platform in ("jalan", "booking"):
                pd.DataFrame(by_platform.get(platform, []), columns=RECORD_COLUMNS).to_excel(
                    writer, sheet_name=platform.title(), index=False
                )
            pd.DataFrame(result.errors).to_excel(writer, sheet_name="Errors", index=False)
            pd.DataFrame([result.summary]).to_excel(writer, sheet_name="RunMeta", index=False)

        result.output_path = output_path
        return output_path

    def _summary_frame(self, records: list[HotelPriceRecord]) -> pd.DataFrame:
        """Build a cross-comparison Summary table.

        Columns: hotel_name, checkin_date, booking_double, booking_twin, jalan_double, jalan_twin
        One row per (hotel, checkin_date) with up to four price cells.
        """
        rows = [r for r in records if r.price is not None]
        if not rows:
            return pd.DataFrame(
                columns=["hotel_name", "checkin_date", "booking_double", "booking_twin", "jalan_double", "jalan_twin"]
            )

        # Group by (hotel_name, checkin_date, platform, room_category) → keep lowest price
        index: dict[tuple, list[HotelPriceRecord]] = defaultdict(list)
        for r in rows:
            index[(r.hotel_name, r.checkin_date, r.platform, r.room_category)].append(r)

        summary_rows: list[dict[str, Any]] = []
        for key, recs in index.items():
            hotel_name, checkin_date, platform, room_category = key
            best = min(recs, key=lambda r: r.price or Decimal("inf"))
            summary_rows.append(
                {
                    "hotel_name": hotel_name,
                    "checkin_date": checkin_date.isoformat(),
                    "platform": platform,
                    "room_category": room_category,
                    "price": float(best.price) if best.price else None,
                    "room_type": best.room_type,
                }
            )

        if not summary_rows:
            return pd.DataFrame(
                columns=["hotel_name", "checkin_date", "booking_double", "booking_twin", "jalan_double", "jalan_twin"]
            )

        frame = pd.DataFrame(summary_rows)
        pivot = frame.pivot_table(
            index=["hotel_name", "checkin_date"],
            columns=["platform", "room_category"],
            values="price",
            aggfunc="min",
        )
        pivot.columns = [f"{plat}_{cat}" for plat, cat in pivot.columns]
        pivot = pivot.reset_index()

        expected = ["hotel_name", "checkin_date", "booking_double", "booking_twin", "jalan_double", "jalan_twin"]
        for col in expected:
            if col not in pivot.columns:
                pivot[col] = None
        return pivot[expected]
