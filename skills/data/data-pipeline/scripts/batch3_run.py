#!/usr/bin/env python3
"""Batch process Smart Money images through the unified pipeline."""
import asyncio
import sys
import json
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from run_unified_image_pipeline import run_pipeline
from image_batch_state import add_image_result

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', force=True)
logger = logging.getLogger(__name__)

IMAGE_IDS = [
    "be09c427-a98a-4700-b3f7-5be04329f44c",
    "f7d37cb9-0e4c-4e2b-849e-30d145d41f5a",
    "c1b73920-e9fb-4b92-8b6d-2ea3ef3007f9",
    "a08df43f-7b02-4e3f-bf60-25b5b6ac9329",
    "8ba85c4e-2fea-41d4-8589-525684b68f65",
    "ab19d547-bc78-4a5a-b0fe-ea78a128d0b6",
    "64cd61b1-f775-41f5-8c6e-d477905a47de",
    "9a1bf3be-787b-400c-bdf9-8f7e6a71701a",
    "09c613d5-01c6-411e-9e58-ac72b5c215c1",
    "82bed154-9de6-4dd6-8521-2dac7b68b736",
    "ff1a7d0b-0117-40ea-8497-1544cb007945",
    "2276f16e-a6e0-4938-b26b-d07cb75a48e9",
]

INBOUND_DIR = Path("/home/pascal/.openclaw/media/inbound")
SOURCE_ROOT = SCRIPT_DIR.parents[4] / "skills" / "data" / "source" / "smart-money"
FOLDER_DATE = "2026-06-16"
OUT_FILE = Path("/home/pascal/.openclaw/workspace-yquant/.openclaw/batch3_results.json")


async def process_one(media_id: str) -> dict:
    image_path = INBOUND_DIR / f"{media_id}.jpg"
    if not image_path.exists():
        return {"media_id": media_id, "status": "error", "error": f"File not found: {image_path}"}
    try:
        result = await run_pipeline(
            str(image_path),
            None,
            SOURCE_ROOT,
            folder_date=FOLDER_DATE,
            dry_run=False,
        )
        add_image_result(result)
        return {"media_id": media_id, "status": "success", "result": result}
    except Exception as e:
        logger.exception(f"Error processing {media_id}")
        return {"media_id": media_id, "status": "error", "error": str(e)}


async def main():
    logger.info(f"Processing {len(IMAGE_IDS)} images...")
    results = []
    for i, mid in enumerate(IMAGE_IDS, 1):
        logger.info(f"[{i}/{len(IMAGE_IDS)}] Processing {mid}")
        r = await process_one(mid)
        results.append(r)
        if r["status"] == "success":
            res = r.get("result", {})
            pending_issues = len(res.get("pending", {}).get("issues", []))
            logger.info(f"  OK {mid}: {res.get('format','?')} {res.get('rows','?')} rows, pending={pending_issues}")
        else:
            logger.error(f"  ERR {mid}: {r.get('error')}")

    total = len(results)
    success = sum(1 for r in results if r["status"] == "success")
    errors = total - success
    logger.info(f"Summary: {total} images, {success} OK, {errors} ERR")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Raw results saved to {OUT_FILE}")
    return results


if __name__ == "__main__":
    asyncio.run(main())
