"""FastAPI dependency providers for Portfolio stock pool services.

This module intentionally does not define HTTP routes. TradingAgents-CN or
another app layer can import these providers and mount routes in its own API.
"""

from functools import lru_cache

from .repository import StockPoolRepository
from .service import StockPoolService
from .ingestion import StockPoolIngestionService


@lru_cache(maxsize=1)
def get_stock_pool_repository() -> StockPoolRepository:
    """Return the shared stock pool repository dependency."""
    return StockPoolRepository()


def get_stock_pool_service() -> StockPoolService:
    """Return a stock pool service bound to the shared repository dependency."""
    return StockPoolService(get_stock_pool_repository())


def get_stock_pool_ingestion_service() -> StockPoolIngestionService:
    """Return a signal ingestion service for POST /ingest-signals handlers."""
    return StockPoolIngestionService(get_stock_pool_service())
