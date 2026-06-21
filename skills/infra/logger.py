# skills/infra/logger.py
"""Unified logging utility."""

import logging
from datetime import datetime
from pathlib import Path

from .paths import logs_dir

# Log format standard
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Root log directory
LOG_ROOT = logs_dir()


def get_logger(
    module: str,
    submodule: str = None,
    level: int = logging.INFO
) -> logging.Logger:
    """Get unified logger instance.
    
    Args:
        module: Module name (e.g., 'argus', 'portfolio')
        submodule: Submodule path (e.g., 'research/argus')
        level: Log level, default INFO
    
    Output path: logs/{submodule}/{module}_{YYYYMMDD}.log
    If submodule is None: logs/{module}/{module}_{YYYYMMDD}.log
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # Build log directory
    if submodule:
        log_dir = LOG_ROOT / submodule
    else:
        log_dir = LOG_ROOT / module
    
    # Ensure directory exists
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Build log file path
    date_str = datetime.now().strftime('%Y%m%d')
    log_file = log_dir / f'{module}_{date_str}.log'
    
    # Get or create logger
    logger = logging.getLogger(f'{module}.{submodule or "root"}')
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(level)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


def get_log_file_path(module: str, submodule: str = None) -> Path:
    """Get log file path for a module.
    
    Args:
        module: Module name
        submodule: Submodule path
    
    Returns:
        Path: Full log file path
    """
    if submodule:
        log_dir = LOG_ROOT / submodule
    else:
        log_dir = LOG_ROOT / module
    
    date_str = datetime.now().strftime('%Y%m%d')
    return log_dir / f'{module}_{date_str}.log'
