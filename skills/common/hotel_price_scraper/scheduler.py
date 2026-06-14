from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from BookingScraper import BookingScraper
from JalanScraper import JalanScraper
from email_service import EmailService
from excel_exporter import ExcelExporter
from models import HotelPriceRecord, RunResult


SCRAPER_CLASSES = {
    "jalan": JalanScraper,
    "booking": BookingScraper,
}


class HotelPriceScheduler:
    def __init__(self, config_path: str | Path = "config.yaml", env_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)
        self.env_path = env_path
        self.concurrent = int(self.config.get("concurrent", 2))
        self.request_interval = float(self.config.get("request_interval_seconds", 3))

    def run(
        self,
        *,
        platform: str = "all",
        output_dir: str | Path = "output",
        days: int | None = None,
        send_email: bool = False,
    ) -> RunResult:
        result = RunResult()
        platforms = self._selected_platforms(platform)
        jobs = [(name, self._create_scraper(name)) for name in platforms]

        with ThreadPoolExecutor(max_workers=self.concurrent) as executor:
            futures = {executor.submit(self._run_platform, name, scraper, days): name for name, scraper in jobs}
            for future in as_completed(futures):
                platform_name = futures[future]
                try:
                    records, errors = future.result()
                    result.records.extend(records)
                    result.errors.extend(errors)
                except Exception as exc:
                    result.errors.append(
                        {
                            "platform": platform_name,
                            "hotel_id": "",
                            "checkin_date": "",
                            "error": repr(exc),
                            "created_at": datetime.now().isoformat(timespec="seconds"),
                        }
                    )

        result.summary = self._build_summary(result, platforms)
        result.finish()
        output_path = ExcelExporter().export(result, output_dir)

        if send_email:
            EmailService(self.env_path or Path(__file__).resolve().parents[2] / ".env").send_report(
                subject=f"【YQuant】酒店价格周报 {date.today().isoformat()}",
                content=self._email_content(result),
                attachment_path=output_path,
            )
        return result

    def _run_platform(self, platform: str, scraper, days: int | None) -> tuple[list[HotelPriceRecord], list[dict[str, Any]]]:
        records: list[HotelPriceRecord] = []
        errors: list[dict[str, Any]] = []
        query = self.config.get("query", {})
        days_ahead = int(days or query.get("days_ahead", 30))
        nights = int(query.get("nights", 1))
        start_date = date.today()

        try:
            for hotel in self.config.get("hotels", []):
                hotel_id = str(hotel.get("platforms", {}).get(platform, "")).strip()
                if not hotel_id:
                    continue
                for offset in range(days_ahead):
                    checkin = start_date + timedelta(days=offset)
                    checkout = checkin + timedelta(days=nights)
                    try:
                        records.extend(scraper.scrape(hotel_id, checkin, checkout))
                    except Exception as exc:
                        errors.append(self._error(platform, hotel_id, checkin, exc))
        except Exception as exc:
            errors.append(self._error(platform, "", None, exc))
        return records, errors

    def _create_scraper(self, platform: str):
        query = self.config.get("query", {})
        platform_config = self.config.get("platforms", {}).get(platform, {})
        common = {
            "adults": int(query.get("adults", 2)),
            "children": int(query.get("children", 0)),
            "rooms": int(query.get("rooms", 1)),
            "nights": int(query.get("nights", 1)),
            "currency": query.get("currency", "JPY"),
            "request_interval": self.request_interval,
            "cookie": platform_config.get("cookie", ""),
        }
        return SCRAPER_CLASSES[platform](**common)

    def _selected_platforms(self, platform: str) -> list[str]:
        if platform == "all":
            return list(SCRAPER_CLASSES)
        if platform not in SCRAPER_CLASSES:
            raise ValueError(f"Unsupported platform: {platform}")
        return [platform]

    def _build_summary(self, result: RunResult, platforms: list[str]) -> dict[str, Any]:
        return {
            "platforms": ",".join(platforms),
            "hotel_count": len(self.config.get("hotels", [])),
            "record_count": len(result.records),
            "error_count": len(result.errors),
        }

    def _email_content(self, result: RunResult) -> str:
        return "\n".join(
            [
                f"酒店数: {result.summary.get('hotel_count', 0)}",
                f"有效报价记录数: {len(result.records)}",
                f"错误数: {len(result.errors)}",
                f"附件: {result.output_path}",
            ]
        )

    def _error(self, platform: str, hotel_id: str, checkin: date | None, exc: Exception) -> dict[str, Any]:
        return {
            "platform": platform,
            "hotel_id": hotel_id,
            "checkin_date": "" if checkin is None else checkin.isoformat(),
            "error": repr(exc),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _load_config(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}
