"""Standard stock basic information lookup API."""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any
from urllib.parse import quote_plus

from pymongo import MongoClient

logger = logging.getLogger(__name__)

A_SHARE_WIND_RE = re.compile(r"^(6\d{5}\.SH|[03]\d{5}\.SZ|[489]\d{5}\.BJ)$")
BARE_A_SHARE_RE = re.compile(r"^[603489]\d{5}$")


def normalize_a_share_code(code: Any) -> str | None:
    """Normalize an A-share code to Wind/Tushare format."""
    if code is None:
        return None

    value = str(code).strip().upper().replace(" ", "")
    if not value or value in {"NAN", "NONE"}:
        return None
    if A_SHARE_WIND_RE.match(value):
        return value
    if not BARE_A_SHARE_RE.match(value):
        return None
    if value.startswith("6"):
        return f"{value}.SH"
    if value.startswith(("0", "3")):
        return f"{value}.SZ"
    return f"{value}.BJ"


def is_valid_a_share_code(code: str) -> bool:
    """Return whether code is a valid A-share code format."""
    return normalize_a_share_code(code) is not None


def get_stock_name(code: str) -> str | None:
    """Return the standard stock name for an A-share code."""
    info = get_stock_info(code)
    return str(info["name"]) if info and info.get("name") else None


def get_stock_info(code: str) -> dict[str, Any] | None:
    """Return normalized stock basic information for an A-share code."""
    normalized_code = normalize_a_share_code(code)
    if not normalized_code:
        return None
    return _get_stock_info_cached(normalized_code)


def batch_get_stock_names(codes: list[str]) -> dict[str, str]:
    """Batch lookup stock names and return a mapping from input code to name."""
    result: dict[str, str] = {}
    for code in codes or []:
        name = get_stock_name(code)
        if name:
            result[code] = name
    return result


def get_all_stock_names() -> dict[str, str]:
    """Return all available A-share code -> stock name mappings."""
    return _get_all_stock_names_cached()


@lru_cache(maxsize=4096)
def _get_stock_info_cached(normalized_code: str) -> dict[str, Any] | None:
    try:
        return _fetch_stock_info(normalized_code)
    except Exception as exc:
        logger.warning("[StockInfoAPI] lookup failed for %s: %s", normalized_code, exc)
        return None


@lru_cache(maxsize=1)
def _get_all_stock_names_cached() -> dict[str, str]:
    try:
        return _fetch_all_stock_names()
    except Exception as exc:
        logger.warning("[StockInfoAPI] full name mapping lookup failed: %s", exc)
        return {}


def _fetch_stock_info(normalized_code: str) -> dict[str, Any] | None:
    client, database, collection_name = _mongo_collection_config()
    if client is None or database is None or collection_name is None:
        return None

    bare_code = normalized_code.split(".", 1)[0]
    query = {
        "$or": [
            {"full_symbol": normalized_code},
            {"ts_code": normalized_code},
            {"code": bare_code},
            {"symbol": bare_code},
        ]
    }

    try:
        doc = client[database][collection_name].find_one(query, {"_id": 0})
        return _normalize_stock_info_doc(doc, normalized_code) if doc else None
    finally:
        client.close()


def _fetch_all_stock_names() -> dict[str, str]:
    client, database, collection_name = _mongo_collection_config()
    if client is None or database is None or collection_name is None:
        return {}

    projection = {
        "_id": 0,
        "code": 1,
        "symbol": 1,
        "ts_code": 1,
        "full_symbol": 1,
        "name": 1,
        "stock_name": 1,
    }
    try:
        mapping: dict[str, str] = {}
        for doc in client[database][collection_name].find({}, projection):
            name = str(doc.get("name") or doc.get("stock_name") or "").strip()
            if not name:
                continue
            for code in _candidate_codes(doc):
                mapping[code] = name
        logger.info("[StockInfoAPI] loaded %s stock_basic_info mappings", len(mapping))
        return mapping
    finally:
        client.close()


def _mongo_collection_config() -> tuple[MongoClient | None, str | None, str | None]:
    client = _mongo_client_from_env()
    database = os.getenv("MONGODB_DATABASE")
    collection_name = os.getenv("STOCK_BASIC_INFO_COLLECTION", "stock_basic_info")
    if client is None:
        logger.warning("[StockInfoAPI] skipped: MongoDB connection env is not configured")
    if not database:
        logger.warning("[StockInfoAPI] skipped: MONGODB_DATABASE env is not configured")
        if client is not None:
            client.close()
        client = None
    return client, database, collection_name


def _mongo_client_from_env() -> MongoClient | None:
    uri = (
        os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
        or os.getenv("MONGODB_CONNECTION_STRING")
    )
    if not uri:
        host = os.getenv("MONGODB_HOST")
        if not host:
            return None
        port = os.getenv("MONGODB_PORT")
        if not port:
            return None
        username = os.getenv("MONGODB_USERNAME")
        password = os.getenv("MONGODB_PASSWORD")
        if username and password:
            auth_source = os.getenv("MONGODB_AUTH_SOURCE")
            uri = (
                f"mongodb://{quote_plus(username)}:{quote_plus(password)}"
                f"@{host}:{port}/"
            )
            if auth_source:
                uri = f"{uri}?authSource={quote_plus(auth_source)}"
        else:
            uri = f"mongodb://{host}:{port}/"

    timeout_ms = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000"))
    return MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)


def _normalize_stock_info_doc(doc: dict[str, Any], fallback_code: str) -> dict[str, Any]:
    normalized_code = (
        normalize_a_share_code(doc.get("full_symbol"))
        or normalize_a_share_code(doc.get("ts_code"))
        or normalize_a_share_code(doc.get("code"))
        or normalize_a_share_code(doc.get("symbol"))
        or fallback_code
    )
    market = normalized_code.rsplit(".", 1)[1] if "." in normalized_code else None
    name = doc.get("name") or doc.get("stock_name")

    normalized = dict(doc)
    normalized.update(
        {
            "code": normalized_code,
            "name": str(name).strip() if name else None,
            "market": doc.get("market") or market,
            "list_date": doc.get("list_date") or doc.get("listDate"),
        }
    )
    return normalized


def _candidate_codes(doc: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for field in ("full_symbol", "ts_code", "code", "symbol"):
        code = normalize_a_share_code(doc.get(field))
        if code and code not in codes:
            codes.append(code)
    return codes


def clear_stock_info_cache() -> None:
    """Clear stock info lookup cache, mainly for tests and data refresh jobs."""
    _get_stock_info_cached.cache_clear()
    _get_all_stock_names_cached.cache_clear()
