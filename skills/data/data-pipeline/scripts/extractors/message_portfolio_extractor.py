"""
Message Portfolio Extractor

从 source/smart-money/YYYY-MM-DD/ 目录读取 Excel 文件，
输出为 pandas DataFrame，供后续 transformer 使用。

Step 1 of String Portfolio Pipeline（替代 Image OCR 步骤）。
"""
from pathlib import Path
from typing import Optional

import pandas as pd

from .base import BaseExtractor


class MessagePortfolioExtractor(BaseExtractor):
    """
    从 Excel 文件读取持仓数据（由用户文本生成的 Excel）。

    支持格式：source/smart-money/{date}/portfolio_{YYYYMMDD}.xlsx

    输出 records 格式（供 transformer 使用）：
        [{"df": pd.DataFrame, "source_path": str}]
    """

    def __init__(self, source_dir: Optional[str] = None):
        """
        Args:
            source_dir: Excel 文件所在目录，
                        默认 `skills/data/source/smart-money/`
        """
        if source_dir is None:
            source_dir = (
                Path(__file__).resolve().parents[5]
                / "skills" / "data" / "source" / "smart-money"
            )
        self.source_dir = Path(source_dir)

    @property
    def source_type(self) -> str:
        return "excel_message_portfolio"

    async def extract(self, source: str, **kwargs) -> list[dict]:
        """
        读取指定日期目录下的 Excel 文件。

        Args:
            source: 日期字符串，如 "2026-05-03"
                    或直接传入 Excel 文件路径

        Returns:
            [{"df": DataFrame, "source_path": str}]
        """
        # 判断是日期还是文件路径
        date_str = source.strip()
        excel_path = self.source_dir / date_str

        if excel_path.is_dir():
            # 传入日期：查找对应的 Excel 文件
            # 格式：portfolio_YYYYMMDD.xlsx
            date_clean = date_str.replace("-", "")
            candidates = list(excel_path.glob(f"portfolio_{date_clean}.xlsx"))
            if not candidates:
                # 尝试 glob *portfolio*.xlsx
                candidates = list(excel_path.glob("*portfolio*.xlsx"))
            if not candidates:
                raise FileNotFoundError(
                    f"在 {excel_path} 下未找到 portfolio_*.xlsx 文件"
                )
            excel_path = candidates[0]
        else:
            excel_path = Path(source)

        if not excel_path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {excel_path}")

        df = pd.read_excel(excel_path, dtype=str, keep_default_na=False)
        # 清理空白列
        df = df.dropna(how="all")
        df = df.rename(columns={c: c.strip() for c in df.columns})

        return [{"df": df, "source_path": str(excel_path)}]

    async def validate_source(self, source: str) -> bool:
        """检查 Excel 文件是否存在。"""
        date_str = source.strip()
        excel_path = self.source_dir / date_str
        if excel_path.is_dir():
            return bool(list(excel_path.glob("*portfolio*.xlsx")))
        return Path(source).exists()
