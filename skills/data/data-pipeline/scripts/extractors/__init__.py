# Extractor 基类
from .base import BaseExtractor
from .minimax_image_extractor import MiniMaxImageExtractor
from .message_portfolio_extractor import MessagePortfolioExtractor

__all__ = ["BaseExtractor", "MiniMaxImageExtractor",
           "PortfolioTableOCR", "MessagePortfolioExtractor"]


def __getattr__(name):
    if name == "PortfolioTableOCR":
        from .portfolio_ocr import PortfolioTableOCR
        return PortfolioTableOCR
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
