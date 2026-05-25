#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from scheduler import HotelPriceScheduler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hotel price scraper")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env", default=str(Path(__file__).resolve().parents[2] / ".env"))
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--platform", choices=["all", "jalan", "booking", "trip"], default="all")
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--send-email", action="store_true")
    args = parser.parse_args()

    result = HotelPriceScheduler(args.config, args.env).run(
        platform=args.platform,
        output_dir=args.output_dir,
        days=args.days,
        send_email=args.send_email,
    )
    print(f"records={len(result.records)} errors={len(result.errors)} output={result.output_path}")
    return 0 if result.records or result.output_path else 1


if __name__ == "__main__":
    raise SystemExit(main())
