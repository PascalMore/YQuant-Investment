# skills/data/data_interface/mongo_writer.py
"""MongoDB writer implementation."""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

from dotenv import load_dotenv
from pymongo import MongoClient

from .base_writer import IWriter

# Load .env from workspace root
load_dotenv('/home/pascal/.openclaw/workspace-yquant/skills/.env')

logger = logging.getLogger(__name__)


class MongoWriter(IWriter):
    """MongoDB write implementation implementing IWriter interface."""
    
    _client: Optional[MongoClient] = None
    
    def __init__(self, connection_string: str = None, database: str = 'tradingagents'):
        """Initialize MongoDB writer.
        
        Args:
            connection_string: MongoDB connection string (reads from env if not provided)
            database: Database name, default 'tradingagents'
        """
        if connection_string is None:
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
        
        if MongoWriter._client is None:
            MongoWriter._client = MongoClient(connection_string)
        
        self.db = MongoWriter._client[database]
        self.database = database
    
    def write(self, data: List[Dict], **kwargs) -> int:
        """Write data to collection.
        
        Args:
            data: List of data records to write
            **kwargs: Optional params - collection_name
        
        Returns:
            int: Number of records written
        """
        if not data:
            return 0
        
        collection_name = kwargs.get('collection_name', 'portfolio_position')
        collection = self.db[collection_name]
        records = [self._with_created_at(record) for record in data]
        
        result = collection.insert_many(records, ordered=False)
        count = len(result.inserted_ids)
        
        logger.info(f"[MongoWriter] wrote {count} records to {collection_name}")
        return count
    
    def upsert(self, data: List[Dict], **kwargs) -> int:
        """Upsert data based on unique keys.
        
        Args:
            data: List of data records to upsert
            **kwargs: Optional params - collection_name, unique_keys
        
        Returns:
            int: Number of records affected
        """
        if not data:
            return 0
        
        collection_name = kwargs.get('collection_name', 'portfolio_position')
        unique_keys = kwargs.get('unique_keys', ['product_code', 'position_date'])
        collection = self.db[collection_name]

        logger.info(f"[MongoWriter] upserting {len(data)} records to {collection_name}")
        count = 0
        for record in data:
            filter_dict = {k: record[k] for k in unique_keys if k in record}
            if len(filter_dict) != len(unique_keys):
                logger.warning(
                    "[MongoWriter] skip upsert to %s due to missing unique keys %s: %s",
                    collection_name,
                    unique_keys,
                    record,
                )
                continue
            record = self._with_timestamps(record)
            collection.update_one(filter_dict, {'$set': record}, upsert=True)
            count += 1

        logger.info(f"[MongoWriter] upserted {count} records to {collection_name}")
        return count

    def write_argus_credential_scores(self, data: List[Dict], upsert: bool = True) -> int:
        """Upsert Argus product credibility scores."""
        return self.upsert(
            data,
            collection_name='08_research_argus_credential_score',
            unique_keys=['date', 'product_code'],
        )

    def write_argus_signals(self, data: List[Dict], upsert: bool = True) -> int:
        """Upsert Argus daily signals."""
        return self.upsert(
            data,
            collection_name='08_research_argus_signal',
            unique_keys=['date', 'signal_id'],
        )

    def write_argus_signal_pool(self, data: List[Dict], upsert: bool = True) -> int:
        """Upsert Argus four-zone signal pool state."""
        return self.upsert(
            data,
            collection_name='08_research_argus_signal_pool',
            unique_keys=['date', 'wind_code'],
        )

    # Backward compatibility alias
    def write_argus_stock_pool(self, data: List[Dict], upsert: bool = True) -> int:
        """Upsert Argus four-zone stock pool state (backward compatibility alias)."""
        return self.write_argus_signal_pool(data, upsert)

    def write_argus_industry_weights(self, data: List[Dict], upsert: bool = True) -> int:
        """Upsert Argus product industry weight time series (Phase 4A)."""
        return self.upsert(
            data,
            collection_name='08_research_argus_industry_weight',
            unique_keys=['date', 'product_code', 'sw1_code'],
        )

    def write_argus_darwin_events(self, data: List[Dict], upsert: bool = True) -> int:
        """Upsert Argus Darwin moment events (Phase 4B)."""
        return self.upsert(
            data,
            collection_name='08_research_argus_darwin_event',
            unique_keys=['date', 'sw1_code'],
        )

    def write_argus_consensus_direction(self, data: List[Dict], upsert: bool = True) -> int:
        """Upsert Argus consensus direction snapshot (Phase 4C)."""
        return self.upsert(
            data,
            collection_name='08_research_argus_consensus_direction',
            unique_keys=['date'],
        )

    def ensure_argus_indexes(self) -> None:
        """Create idempotent indexes for Argus output collections."""
        index_specs = {
            '08_research_argus_credential_score': [('date', 1), ('product_code', 1)],
            '08_research_argus_signal': [('date', 1), ('signal_id', 1)],
            '08_research_argus_signal_pool': [('date', 1), ('wind_code', 1)],
            '08_research_argus_industry_weight': [('date', 1), ('product_code', 1), ('sw1_code', 1)],
            '08_research_argus_darwin_event': [('date', 1), ('sw1_code', 1)],
            '08_research_argus_consensus_direction': [('date', 1)],
        }
        for collection_name, keys in index_specs.items():
            self.db[collection_name].create_index(keys, unique=True)

    @staticmethod
    def _with_created_at(record: Dict) -> Dict:
        enriched = dict(record)
        enriched.setdefault('created_at', datetime.now().isoformat())
        return enriched

    @staticmethod
    def _with_timestamps(record: Dict) -> Dict:
        enriched = {key: value for key, value in record.items() if key != '_id'}
        now = datetime.now().isoformat()
        enriched.setdefault('created_at', now)
        enriched['updated_at'] = now
        return enriched
    
    @classmethod
    def close(cls):
        """Close MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None