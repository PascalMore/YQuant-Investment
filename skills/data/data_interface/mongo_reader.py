# skills/data/data_interface/mongo_reader.py
"""MongoDB reader implementation."""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from dotenv import load_dotenv
from pymongo import MongoClient

from .base_reader import IReader

# Load .env from workspace root
load_dotenv('/home/pascal/.openclaw/workspace-yquant/skills/.env')

logger = logging.getLogger(__name__)


class MongoReader(IReader):
    """MongoDB read implementation implementing IReader interface."""
    
    _client: Optional[MongoClient] = None
    
    def __init__(self, connection_string: str = None, database: str = 'tradingagents'):
        """Initialize MongoDB reader.
        
        Args:
            connection_string: MongoDB connection string (reads from env if not provided)
            database: Database name, default 'tradingagents'
        """
        if connection_string is None:
            # Try MONGODB_CONNECTION_STRING first, then construct from components
            connection_string = os.getenv('MONGODB_CONNECTION_STRING')
            if connection_string is None:
                host = os.getenv('MONGODB_HOST', '172.25.240.1')
                port = os.getenv('MONGODB_PORT', '27017')
                username = os.getenv('MONGODB_USERNAME', '')
                password = os.getenv('MONGODB_PASSWORD', '')
                if username and password:
                    connection_string = f"mongodb://{username}:{password}@{host}:{port}/admin"
                else:
                    connection_string = f"mongodb://{host}:{port}/"
        
        if MongoReader._client is None:
            MongoReader._client = MongoClient(connection_string)
        
        self.db = MongoReader._client[database]
        self.database = database
    
    def read(self, date: str, **kwargs) -> List[Dict]:
        """Read data by date.
        
        Args:
            date: Date in YYYY-MM-DD format
            **kwargs: Optional params - collection_name, product_code
        
        Returns:
            List[Dict]: List of data records
        """
        collection_name = kwargs.get('collection_name', 'portfolio_position')
        product_code = kwargs.get('product_code')
        
        # Build query based on collection type
        if collection_name == 'portfolio_position':
            query = {'position_date': date}
        elif collection_name == 'portfolio_trade':
            query = {'trade_date': date}
        elif collection_name == 'portfolio_nav':
            query = {'nav_date': date}
        elif collection_name.startswith('08_research_argus_'):
            query = {'date': date}
        else:
            query = {'position_date': date}  # default to position
        
        if product_code:
            query['product_code'] = product_code
        
        collection = self.db[collection_name]
        results = list(collection.find(query, {'_id': 0}))
        
        logger.info(f"[MongoReader] read {len(results)} records from {collection_name} for {date}")
        return results
    
    def read_by_product(self, product_code: str, date: str) -> List[Dict]:
        """Read data by product and date.
        
        Args:
            product_code: Product code (e.g., 'SM001')
            date: Date in YYYY-MM-DD format
        
        Returns:
            List[Dict]: List of data records
        """
        return self.read(date, product_code=product_code)

    def read_sector_info(self, classify_system: str = 'SW', collection_name: str = 'stock_sector_info') -> List[Dict]:
        """Read stock sector mappings used by Argus industry aggregation."""
        collection = self.db[collection_name]
        query = {'classify_system': classify_system} if classify_system else {}
        results = list(collection.find(query, {'_id': 0}))
        logger.info(f"[MongoReader] read {len(results)} records from {collection_name}")
        return results

    def read_industry_weights(
        self,
        date: str,
        product_code: str = None,
        collection_name: str = '08_research_argus_industry_weight',
    ) -> List[Dict]:
        """Read Argus industry weight records for a date and optional product."""
        query = {'date': date}
        if product_code:
            query['product_code'] = product_code
        results = list(self.db[collection_name].find(query, {'_id': 0}))
        logger.info(f"[MongoReader] read {len(results)} records from {collection_name} for {date}")
        return results

    def read_industry_weights_range(
        self,
        start_date: str,
        end_date: str,
        product_code: str = None,
        collection_name: str = '08_research_argus_industry_weight',
    ) -> List[Dict]:
        """Read Argus industry weight records for a date range."""
        query = {'date': {'$gte': start_date, '$lte': end_date}}
        if product_code:
            query['product_code'] = product_code
        results = list(self.db[collection_name].find(query, {'_id': 0}))
        logger.info(f"[MongoReader] read {len(results)} records from {collection_name} for {start_date}~{end_date}")
        return results

    def read_index_quotes(
        self,
        index_code: str,
        start_date: str,
        end_date: str,
        collection_name: str = 'index_daily_quotes',
    ) -> List[Dict]:
        """Read index daily quotes for a date range.
        
        Args:
            index_code: Index code (e.g., '000300.SH' for CSI300, '801050.SI' for SW industry)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            List[Dict]: Index quotes with date, close, pct_chg, etc.
        """
        # Handle both code and full_symbol
        query = {
            '$or': [
                {'code': index_code.split('.')[0]},
                {'full_symbol': index_code}
            ],
            'trade_date': {'$gte': start_date, '$lte': end_date}
        }
        results = list(self.db[collection_name].find(query, {'_id': 0}).sort('trade_date', 1))
        logger.info(f"[MongoReader] read {len(results)} index quotes for {index_code} from {start_date} to {end_date}")
        return results

    def read_credential_scores(
        self,
        date: str,
        collection_name: str = '08_research_argus_credential_score',
    ) -> List[Dict]:
        """Read Argus credential scores for a date."""
        results = list(self.db[collection_name].find({'date': date}, {'_id': 0}))
        logger.info(f"[MongoReader] read {len(results)} credential scores for {date}")
        return results

    @classmethod
    def close(cls):
        """Close MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None