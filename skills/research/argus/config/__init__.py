# skills/research/argus/config/__init__.py
"""Argus configuration module."""

from .config import ARGUS_COLLECTIONS, ARGUS_CONFIG, ARGUS_UNIQUE_KEYS, INDUSTRY_GROUPS, PRODUCT_ALIAS
from .zone_rules import ZONE_RULES_CONFIG, load_zone_rules_config

__all__ = [
    'ARGUS_CONFIG',
    'PRODUCT_ALIAS',
    'ARGUS_COLLECTIONS',
    'ARGUS_UNIQUE_KEYS',
    'INDUSTRY_GROUPS',
    'ZONE_RULES_CONFIG',
    'load_zone_rules_config',
]
