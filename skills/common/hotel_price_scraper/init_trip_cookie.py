#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from selenium import webdriver


DEFAULT_COOKIE_PATH = Path(__file__).resolve().parents[1] / "su-scraper" / "scripts" / "trip_cookies.json"
DEFAULT_URL = "https://www.trip.com/hotels/detail/?hotelId=107897404"


def init_cookie(url: str = DEFAULT_URL, cookie_path: str | Path = DEFAULT_COOKIE_PATH, wait_seconds: int = 60) -> Path:
    cookie_path = Path(cookie_path)
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument(
        "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.3"
    )
    chrome_options.add_argument("Upgrade-Insecure-Requests=1")
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(url)
        time.sleep(wait_seconds)
        cookies = driver.get_cookies()
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        return cookie_path
    finally:
        driver.quit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize Trip.com cookies via Selenium")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--cookie-path", default=str(DEFAULT_COOKIE_PATH))
    parser.add_argument("--wait-seconds", type=int, default=60)
    args = parser.parse_args()
    path = init_cookie(args.url, args.cookie_path, args.wait_seconds)
    print(f"Trip cookies saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
