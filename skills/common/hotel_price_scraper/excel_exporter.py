from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from models import HotelPriceRecord, RunResult


RECORD_COLUMNS = ["hotel_name", "platform", "checkin_date", "room_type", "price", "currency", "status", "created_at"]


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
            for platform in ("jalan", "booking", "trip"):
                pd.DataFrame(by_platform.get(platform, []), columns=RECORD_COLUMNS).to_excel(
                    writer, sheet_name=platform.title(), index=False
                )
            pd.DataFrame(result.errors).to_excel(writer, sheet_name="Errors", index=False)
            pd.DataFrame([result.summary]).to_excel(writer, sheet_name="RunMeta", index=False)

        result.output_path = output_path
        return output_path

    def _summary_frame(self, records: list[HotelPriceRecord]) -> pd.DataFrame:
        rows = [record for record in records if record.price is not None]
        if not rows:
            return pd.DataFrame(columns=["hotel_name", "platform", "checkin_date", "room_type", "price", "currency", "status"])

        data = [record.to_dict() for record in rows]
        frame = pd.DataFrame(data).sort_values(["hotel_name", "platform", "checkin_date", "price"])
        return frame.groupby(["hotel_name", "platform", "checkin_date"], as_index=False).first()
