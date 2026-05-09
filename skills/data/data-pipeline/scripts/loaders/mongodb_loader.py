"""
MongoDB Loader — Portfolio Pipeline

Upserts portfolio data into MongoDB with compound unique keys per collection.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient, ReplaceOne
from pymongo.database import Database

logger = logging.getLogger(__name__)


class PortfolioMongoLoader:
    """
    MongoDB data loader for portfolio pipeline.

    Connects to a remote MongoDB and upserts:
      - portfolio_basic_info  (UK: product_code)
      - portfolio_nav          (UK: nav_date + product_code)
      - portfolio_position    (UK: position_date + product_code + asset_wind_code)
      - portfolio_trade        (UK: trade_date + product_code + asset_wind_code + direction)

    Config can be passed as a dict or loaded from environment variables:
      MONGODB_HOST, MONGODB_PORT, MONGODB_USERNAME, MONGODB_PASSWORD, MONGODB_DATABASE
    """

    def __init__(self, config: Optional[dict] = None):
        if config:
            self.host = config.get("host", os.getenv("MONGODB_HOST", "localhost"))
            self.port = config.get("port", int(os.getenv("MONGODB_PORT", "27017")))
            self.username = config.get("username", os.getenv("MONGODB_USERNAME", ""))
            self.password = config.get("password", os.getenv("MONGODB_PASSWORD", ""))
            self.database = config.get("database", os.getenv("MONGODB_DATABASE", "tradingagents"))
        else:
            self.host = os.getenv("MONGODB_HOST", "172.25.240.1")
            self.port = int(os.getenv("MONGODB_PORT", "27017"))
            self.username = os.getenv("MONGODB_USERNAME", "myq")
            self.password = os.getenv("MONGODB_PASSWORD", "6812345")
            self.database = os.getenv("MONGODB_DATABASE", "tradingagents")

        self._client: Optional[MongoClient] = None

    def _get_client(self) -> MongoClient:
        if self._client is None:
            if self.username and self.password:
                uri = (
                    f"mongodb://{self.username}:{self.password}"
                    f"@{self.host}:{self.port}/"
                    f"?authSource=admin"
                )
            else:
                uri = f"mongodb://{self.host}:{self.port}/"
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            logger.info(f"MongoDB connected to {self.host}:{self.port}/{self.database}")
        return self._client

    def _db(self) -> Database:
        return self._get_client()[self.database]

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # Public upsert methods
    # -------------------------------------------------------------------------

    def upsert_basic_info(self, records: list[dict]) -> int:
        """Bulk upsert portfolio_basic_info by product_code."""
        if not records:
            return 0
        coll = self._db()["portfolio_basic_info"]
        now = self._now()
        ops = [
            ReplaceOne(
                {"product_code": r["product_code"]},
                {**r, "updated_at": now},
                upsert=True,
            )
            for r in records
            if r.get("product_code")
        ]
        if not ops:
            return 0
        result = coll.bulk_write(ops, ordered=False)
        total = (result.upserted_count or 0) + (result.modified_count or 0)
        logger.info(f"[portfolio_basic_info] upserted={result.upserted_count}, modified={result.modified_count}")
        return total

    def upsert_nav(self, records: list[dict]) -> int:
        """Bulk upsert portfolio_nav by compound key (nav_date, product_code)."""
        if not records:
            return 0
        coll = self._db()["portfolio_nav"]
        now = self._now()
        ops = [
            ReplaceOne(
                {"nav_date": r["nav_date"], "product_code": r["product_code"]},
                {**r, "updated_at": now},
                upsert=True,
            )
            for r in records
            if r.get("nav_date") and r.get("product_code")
        ]
        if not ops:
            return 0
        result = coll.bulk_write(ops, ordered=False)
        logger.info(f"[portfolio_nav] upserted={result.upserted_count}, modified={result.modified_count}")
        return (result.upserted_count or 0) + (result.modified_count or 0)

    def upsert_position(self, records: list[dict]) -> int:
        """Bulk upsert portfolio_position by compound key."""
        if not records:
            return 0
        coll = self._db()["portfolio_position"]
        now = self._now()
        ops = [
            ReplaceOne(
                {
                    "position_date": r["position_date"],
                    "product_code": r["product_code"],
                    "asset_wind_code": r["asset_wind_code"],
                },
                {**r, "updated_at": now},
                upsert=True,
            )
            for r in records
            if r.get("position_date") and r.get("product_code") and r.get("asset_wind_code")
        ]
        if not ops:
            return 0
        result = coll.bulk_write(ops, ordered=False)
        logger.info(f"[portfolio_position] upserted={result.upserted_count}, modified={result.modified_count}")
        return (result.upserted_count or 0) + (result.modified_count or 0)

    def upsert_trade(self, records: list[dict]) -> int:
        """Bulk upsert portfolio_trade by compound key (trade_date, product_code, asset_wind_code, direction)."""
        if not records:
            return 0
        coll = self._db()["portfolio_trade"]
        now = self._now()
        ops = [
            ReplaceOne(
                {
                    "trade_date": r["trade_date"],
                    "product_code": r["product_code"],
                    "asset_wind_code": r["asset_wind_code"],
                    "direction": r["direction"],
                },
                {**r, "updated_at": now},
                upsert=True,
            )
            for r in records
            if r.get("trade_date") and r.get("product_code") and r.get("asset_wind_code") and r.get("direction")
        ]
        if not ops:
            return 0
        result = coll.bulk_write(ops, ordered=False)
        logger.info(f"[portfolio_trade] upserted={result.upserted_count}, modified={result.modified_count}")
        return (result.upserted_count or 0) + (result.modified_count or 0)

    def _update_basic_info_latest_from_nav(self, product_codes: list[str]) -> None:
        """Update latest nav/share/aum fields from portfolio_nav for each product."""
        db = self._db()
        now = self._now()
        for code in product_codes:
            row = db["portfolio_nav"].find_one(
                {"product_code": code},
                sort=[("nav_date", -1)],
                projection={"nav": 1, "share": 1, "aum": 1},
            )
            if not row:
                continue
            aum = row.get("aum")
            if (aum is None or aum == "") and row.get("nav") and row.get("share"):
                try:
                    aum = float(row["nav"]) * float(row["share"])
                except (ValueError, TypeError):
                    aum = None
            db["portfolio_basic_info"].update_one(
                {"product_code": code},
                {
                    "$set": {
                        "latest_nav": row.get("nav"),
                        "latest_share": row.get("share"),
                        "latest_aum": aum,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"product_code": code},
                },
                upsert=True,
            )
        logger.info(f"[_update_basic_info_latest_from_nav] updated {len(product_codes)} products")

    def load_all(self, data: dict) -> dict:
        """Load all normalized portfolio data into MongoDB."""
        counts = {"basic_info": 0, "nav": 0, "position": 0}
        if data.get("nav"):
            counts["nav"] = self.upsert_nav(data["nav"])
        if data.get("position"):
            counts["position"] = self.upsert_position(data["position"])
        if data.get("basic_info"):
            counts["basic_info"] = self.upsert_basic_info(data["basic_info"])
        if data.get("nav"):
            codes = list({r["product_code"] for r in data["nav"] if r.get("product_code")})
            self._update_basic_info_latest_from_nav(codes)
        logger.info(f"[load_all] completed: {counts}")
        return counts

    def load_trade(self, data: dict) -> dict:
        """Load normalized trade data into MongoDB."""
        counts = {"trade": 0}
        if data.get("trade"):
            counts["trade"] = self.upsert_trade(data["trade"])
        logger.info(f"[load_trade] completed: {counts}")
        return counts

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
            logger.info("MongoDB connection closed")
