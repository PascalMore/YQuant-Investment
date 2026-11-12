"""BTC5m 历史的批校验 — 03-018 §6.1。

``HistoryValidator`` 只校验**当前批**（按 dataset）。跨页 / 跨 chunk 的排序、
重复与日覆盖由 :mod:`btc5m_history.runner` 维护，不塞进只看单批的 validator。

fixture 明确区分：官方 schema 构造的 synthetic fixture 与真实 raw 来源，
绝不冒称真实完整窗口。
"""

from __future__ import annotations

from typing import Any

from ..validators.base import BaseValidator, ValidationResult

from .common import DATASET_KLINES, DATASET_ROUNDS
from .transforms import MICROS_PER_SECOND

#: 价格 / 数量的精度约束（Decimal128 可表示范围）。
MAX_DECIMAL_DIGITS = 34


class HistoryValidator(BaseValidator):
    """按 dataset 校验当前批记录。

    Args:
        dataset: ``predict_btc5m_rounds`` 或 ``binance_spot_btcusdt_1s``。
    """

    def __init__(self, dataset: str) -> None:
        if dataset not in (DATASET_ROUNDS, DATASET_KLINES):
            raise ValueError(f"unknown dataset {dataset!r}")
        self._dataset = dataset

    @property
    def dataset(self) -> str:
        """当前校验的 dataset。"""
        return self._dataset

    async def validate(self, records: list[dict[str, Any]]) -> ValidationResult:
        """校验当前批记录。

        Returns:
            :class:`ValidationResult`（实际结果，不是常量）。
        """
        result = ValidationResult()
        if self._dataset == DATASET_ROUNDS:
            self._validate_rounds(records, result)
        else:
            self._validate_klines(records, result)
        return result

    # -- rounds ----------------------------------------------------------
    def _validate_rounds(
        self, records: list[dict[str, Any]], result: ValidationResult
    ) -> None:
        seen: set[str] = set()
        for record in records:
            round_id = str(record.get("round_id") or "")
            if not round_id:
                result.add_error("ROUND_ID_MISSING")
                continue
            if round_id in seen:
                result.add_error(f"DUPLICATE_ROUND:{round_id}")
            seen.add(round_id)
            starts_at_us = record.get("starts_at_us")
            ends_at_us = record.get("ends_at_us")
            if starts_at_us is None or ends_at_us is None:
                result.add_error(f"ROUND_TIME_MISSING:{round_id}")
                continue
            if ends_at_us - starts_at_us != 300 * MICROS_PER_SECOND:
                result.add_error(f"ROUND_DURATION_INVALID:{round_id}")
            if record.get("settlement_state") == "resolved":
                outcome = record.get("official_outcome")
                if outcome not in ("UP", "DOWN", "DRAW"):
                    result.add_error(f"RESOLVED_WITHOUT_OUTCOME:{round_id}")

    # -- klines ----------------------------------------------------------
    def _validate_klines(
        self, records: list[dict[str, Any]], result: ValidationResult
    ) -> None:
        previous: int | None = None
        for record in records:
            open_time_us = record.get("open_time_us")
            if open_time_us is None:
                result.add_error("OPEN_TIME_MISSING")
                continue
            if open_time_us % MICROS_PER_SECOND != 0:
                result.add_error(f"NOT_SECOND_ALIGNED:{open_time_us}")
            if previous is not None and open_time_us <= previous:
                result.add_error(f"NOT_STRICTLY_ORDERED:{open_time_us}")
            previous = open_time_us


__all__ = ["HistoryValidator", "MAX_DECIMAL_DIGITS"]
