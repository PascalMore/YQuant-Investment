"""
MiniMax CLI Image-to-Excel Extractor.

Uses the minimax CLI (mmx vision) to extract structured data from portfolio
table images, then parses the output into a pandas DataFrame.

Step 2 of the Image Portfolio Data Pipeline (replaces PaddleOCRImageExtractor).
"""
import subprocess
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .base import BaseExtractor


# Prompt for extracting table data from images (handles both portfolio and trade formats)
VISION_PROMPT = """请仔细分析这张图片，这是一张Excel表格截图（可能是持仓记录或交易记录）。

请提取所有数据行，每行数据用 JSON 对象表示，包含所有可见列的字段。
请根据图片实际内容判断格式，不要假设：

持仓格式字段：截止日期、产品名称、产品代码、Wind代码、资产名称、持仓比例、数量、市值(本币)、最新净值、最新份额、最新规模
交易格式字段：日期/截止日期、产品名称、产品代码、Wind代码、资产名称、变化比例（不是持仓比例）、变化金额（不是数量）、方向（买入/卖出）

重要：
- 如果看到"变化比例"、"变化金额"、"方向"等列，请使用这些确切的列名
- 如果看到"持仓比例"、"数量"等列，请使用这些确切的列名
- 不要混淆两种格式

返回格式：直接输出 JSON 数组，不要有额外的解释文字。"""


class MiniMaxImageExtractor(BaseExtractor):
    """
    Extracts structured DataFrame from portfolio table images using MiniMax CLI vision.

    Uses the command: mmx vision describe --image <path> --prompt "<prompt>"

    Then parses the JSON output and returns it as a DataFrame-wrapped dict.

    Output records format (for Transformer):
        [{"df": pd.DataFrame, "source_path": str}]
    """

    def __init__(
        self,
        output_dir: str = None,
        date_str: str = None,
    ):
        """
        Args:
            output_dir: Directory to save intermediate JSON files for debugging.
            date_str: Date string (YYYY-MM-DD) for organizing debug output under {date}/image/.
        """
        if output_dir is None:
            output_dir = (
                Path(__file__).resolve().parents[4]
                / "data"
                / "source"
                / "smart-money"
            )
        self.output_dir = Path(output_dir)
        self.date_str = date_str  # e.g. "2026-05-10"
        # output_dir is the full path (already includes date when passed from run_pipeline).
        # date_str is for OCR context only (not used for folder path when output_dir was explicit).
        self.debug_dir = self.output_dir
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    @property
    def source_type(self) -> str:
        return "image_minimax"

    async def extract(self, source: str | list[str], **kwargs) -> list[dict]:
        """
        Run MiniMax vision on one or more images.

        Args:
            source: Single image path (str) or list of image paths.

        Returns:
            List of dicts, each containing:
                - "df": DataFrame from parsed vision output
                - "source_path": original image path
        """
        images = [source] if isinstance(source, str) else source
        results = []

        for img_path in images:
            img_path = Path(img_path)
            if not img_path.exists():
                raise FileNotFoundError(f"Image not found: {img_path}")

            # Run MiniMax vision command
            df = await self._run_vision_extraction(img_path)

            results.append({
                "df": df,
                "source_path": str(img_path),
            })

        return results

    async def _run_vision_extraction(self, img_path: Path) -> pd.DataFrame:
        """
        Execute mmx vision describe and parse the output.
        Retries up to 3 times on timeout.

        Args:
            img_path: Path to the image file.

        Returns:
            DataFrame with extracted table data.
        """
        # Run mmx vision describe command
        cmd = [
            "mmx", "vision", "describe",
            "--image", str(img_path),
            "--prompt", VISION_PROMPT,
        ]

        loop = __import__("asyncio").get_event_loop()
        max_retries = 3

        for attempt in range(max_retries):
            try:
                proc = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,  # 2 min timeout for vision
                    ),
                )
                break  # Success, exit loop
            except subprocess.TimeoutExpired:
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"MiniMax vision timed out after {max_retries} attempts for {img_path.name}"
                    )
                print(f"  [MiniMax Vision] Timeout, retrying ({attempt + 1}/{max_retries})...")
                continue

        if proc.returncode != 0:
            raise RuntimeError(
                f"MiniMax vision failed for {img_path.name}:\n{proc.stderr}"
            )

        output = proc.stdout.strip()
        print(f"  [MiniMax Vision] {img_path.name}: {len(output)} chars output")

        # Unwrap JSON wrapper from mmx CLI ({"content": "...", "base_resp": {...}})
        output = self._unwrap_mmx_response(output)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_json = self.debug_dir / f"pic_{timestamp}_vision_raw.json"
        debug_json.write_text(output)

        # Parse JSON from output
        df = self._parse_vision_output(output)

        return df

    def _parse_vision_output(self, output: str) -> pd.DataFrame:
        """
        Parse the JSON output from MiniMax vision.

        Handles common patterns:
        - Direct JSON array: [...]
        - JSON wrapped in markdown: ```json ... ```
        - Text before/after JSON

        Args:
            output: Raw stdout from mmx vision describe.

        Returns:
            DataFrame with extracted data.
        """
        # Try to extract JSON from the output
        json_str = self._extract_json(output)

        if not json_str:
            raise ValueError("No valid JSON found in vision output")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}\nContent: {json_str[:500]}")

        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array, got {type(data)}")

        if not data:
            raise ValueError("Empty data array returned")

        df = pd.DataFrame(data)

        # Normalize column names
        df = self._normalize_columns(df)

        # Clean data
        df = self._clean_data(df)

        print(f"  [Parsed] {len(df)} rows, {len(df.columns)} columns")

        return df

    def _unwrap_mmx_response(self, raw_output: str) -> str:
        """
        Unwrap MiniMax CLI JSON wrapper.

        The mmx CLI returns output in JSON wrapper format:
            {"content": "...", "base_resp": {"status_code": 0, ...}}

        We need to extract the actual content string before parsing.

        Args:
            raw_output: Raw stdout from mmx CLI.

        Returns:
            The unwrapped content string (actual vision output).
        """
        try:
            wrapper = json.loads(raw_output)
            if isinstance(wrapper, dict) and "content" in wrapper:
                return wrapper["content"]
        except (json.JSONDecodeError, TypeError):
            pass
        # Not wrapped, return as-is
        return raw_output

    def _extract_json(self, text: str) -> str | None:
        """
        Extract JSON string from vision output.

        Handles:
        - ```json ... ```
        - ``` ... ```
        - Raw JSON
        """
        # Pattern 1: JSON in code block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1).strip()

        # Pattern 2: Look for JSON array/object at the start
        match = re.search(r"(\[[\s\S]*\])", text)
        if match:
            return match.group(1).strip()

        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            return match.group(1).strip()

        # No JSON found
        return None

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names to match expected format.

        Column mapping:
        - 截止日期/date/日期 -> 截止日期
        - 产品名称/name/基金名称 -> 产品名称
        - 产品代码/code/产品代码/基金代码 -> 产品代码
        - Wind代码/windCode/Wind代码 -> Wind代码
        - 资产名称/assetName/持仓名称/证券名称 -> 资产名称
        - 持仓比例/ratio/比例/占比 -> 持仓比例
        - 数量/shares/持有数量/股数 -> 数量
        - 市值(本币)/marketValue/市值/万/万份 -> 市值(本币)
        - 最新净值/nav/净值 -> 最新净值
        - 最新份额/share/份额/持有份额 -> 最新份额
        - 最新规模/aum/规模/总规模 -> 最新规模
        """
        column_mapping = {
            "截止日期": "截止日期",
            "date": "截止日期",
            "日期": "截止日期",
            "产品名称": "产品名称",
            "name": "产品名称",
            "基金名称": "产品名称",
            "产品代码": "产品代码",
            "code": "产品代码",
            "基金代码": "产品代码",
            "Wind代码": "Wind代码",
            "windCode": "Wind代码",
            "wind_code": "Wind代码",
            "资产名称": "资产名称",
            "assetName": "资产名称",
            "持仓名称": "资产名称",
            "证券名称": "资产名称",
            "持仓比例": "持仓比例",
            "ratio": "持仓比例",
            "比例": "持仓比例",
            "占比": "持仓比例",
            "数量": "数量",
            "shares": "数量",
            "持有数量": "数量",
            "股数": "数量",
            "市值(本币)": "市值(本币)",
            "marketValue": "市值(本币)",
            "市值": "市值(本币)",
            "最新净值": "最新净值",
            "nav": "最新净值",
            "净值": "最新净值",
            "最新份额": "最新份额",
            "share": "最新份额",
            "份额": "最新份额",
            "持有份额": "最新份额",
            "最新规模": "最新规模",
            "aum": "最新规模",
            "规模": "最新规模",
            "总规模": "最新规模",
        }

        # Rename columns that exist in the mapping
        rename_dict = {}
        for col in df.columns:
            if col in column_mapping:
                rename_dict[col] = column_mapping[col]
            else:
                # Try partial match
                for key, value in column_mapping.items():
                    if key.lower() in col.lower():
                        rename_dict[col] = value
                        break

        if rename_dict:
            df = df.rename(columns=rename_dict)

        return df

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean extracted data:
        - Strip whitespace from all string columns
        - Normalize percentage values
        - Clean numeric values
        - Fill missing values appropriately
        """
        # Strip whitespace from string columns
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

        # Normalize date format
        date_cols = [c for c in df.columns if "日期" in c or "date" in c.lower()]
        for col in date_cols:
            df[col] = df[col].apply(self._parse_date)

        # Clean percentage values
        pct_cols = [c for c in df.columns if "比例" in c or "ratio" in c.lower()]
        for col in pct_cols:
            df[col] = df[col].apply(self._parse_percentage)

        # Clean numeric values
        numeric_cols = ["数量", "市值(本币)", "最新净值", "最新份额", "最新规模"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(self._parse_number)

        return df

    def _parse_date(self, value: Any) -> str | None:
        """Parse date string to YYYY-MM-DD format."""
        if pd.isna(value) or value == "" or value is None:
            return None

        value = str(value).strip()

        # Already in correct format
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value

        # Try various date formats
        date_formats = [
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%Y%m%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]

        for fmt in date_formats:
            try:
                from datetime import datetime
                dt = datetime.strptime(value, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Clean date with extra text like "2026-04-23 (1)"
        match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
        if match:
            return match.group(1)

        return value

    def _parse_percentage(self, value: Any) -> float | None:
        """Parse percentage string to decimal (e.g., 5.77% -> 0.0577)."""
        if pd.isna(value) or value == "" or value is None:
            return None

        value = str(value).strip().replace("%", "").replace("％", "")

        try:
            return float(value) / 100  # Convert percentage to decimal
        except ValueError:
            return None

    def _parse_number(self, value: Any) -> float | None:
        """Parse numeric string to float."""
        if pd.isna(value) or value == "" or value is None:
            return None

        value = str(value).strip()

        # Remove thousand separators and common suffixes
        value = re.sub(r"[,\s]", "", value)

        # Handle suffixes: 万, 亿, K, M, B
        multipliers = {
            "万": 10000,
            "亿": 100000000,
            "K": 1000,
            "M": 1000000,
            "B": 1000000000,
        }

        for suffix, mult in multipliers.items():
            if suffix in value:
                try:
                    num = float(value.replace(suffix, ""))
                    return num * mult
                except ValueError:
                    pass

        try:
            return float(value)
        except ValueError:
            return None

    async def validate_source(self, source: str | list[str]) -> bool:
        """Check that all image files exist."""
        images = [source] if isinstance(source, str) else source
        return all(Path(p).exists() for p in images)
