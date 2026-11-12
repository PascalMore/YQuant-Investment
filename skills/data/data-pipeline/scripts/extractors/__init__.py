# Extractor 基类
#
# 03-018 §3.3：``MiniMaxImageExtractor`` / ``MessagePortfolioExtractor`` 与
# ``PortfolioTableOCR`` 一样改为按名 lazy 导出。``minimax_image_extractor``
# 在模块顶层 import ``providers``（需要 ``scripts/`` 在 sys.path 上），
# 这会让"仅导入 DataPipeline / 四基类"的包级导入直接失败，与本题历史入口
# 无关。``BaseExtractor`` 仍然立即导出（无外部依赖）。
from .base import BaseExtractor

__all__ = ["BaseExtractor", "MiniMaxImageExtractor",
           "PortfolioTableOCR", "MessagePortfolioExtractor"]


def __getattr__(name):
    if name == "PortfolioTableOCR":
        from .portfolio_ocr import PortfolioTableOCR
        return PortfolioTableOCR
    if name == "MiniMaxImageExtractor":
        from .minimax_image_extractor import MiniMaxImageExtractor
        return MiniMaxImageExtractor
    if name == "MessagePortfolioExtractor":
        from .message_portfolio_extractor import MessagePortfolioExtractor
        return MessagePortfolioExtractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
