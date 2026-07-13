"""Canonical financial statement (Phase 1A).

:class:`FinancialStatement` maps to ``stock_financial_data`` — the only
multi-entry TA-CN collection (8 adapter methods cover 8 collections,
but ``stock_financial_data`` is the 1 adapter method that maps to 3
different statement types: income / balance / cashflow).

The TA-CN document structure for ``stock_financial_data`` is::

    {
        "symbol": "600519",
        "full_symbol": "600519.SH",
        "market": "CN",
        "report_period": "20251231",
        "raw_data": {
            "income_statement": [ {...latest period...}, ... ],
            "balance_sheet":    [ {...latest period...}, ... ],
            "cashflow_statement":[ {...latest period...}, ... ],
        },
    }

The mapping extracts the latest entry from the requested statement
type and returns a flat ``items: dict[str, float]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


VALID_STATEMENT_TYPES: tuple[str, ...] = ("income", "balance", "cashflow")

# Mapping from the canonical ``statement_type`` (the term used in service
# APIs and ``statement_type`` field) to the actual nested bucket key
# used inside ``raw_data`` in production TA-CN documents.
_STATEMENT_BUCKET_KEYS: dict[str, str] = {
    "income": "income_statement",
    "balance": "balance_sheet",
    "cashflow": "cashflow_statement",
}


def _normalize_items(raw: Mapping[str, object] | None) -> dict[str, float]:
    """Flatten a statement mapping into ``{str_key: float_value}``.

    Metadata fields such as ``end_date`` remain excluded from the numeric
    canonical payload. A present, non-numeric line item is treated as a
    mapping error instead of being silently dropped.
    """
    if not raw:
        return {}
    out: dict[str, float] = {}
    metadata_keys = {"end_date", "ann_date", "f_ann_date", "report_type"}
    for key, value in raw.items():
        if key in metadata_keys or value is None:
            continue
        if isinstance(value, bool):
            raise ValueError(f"financial item {key!r} must be numeric, got bool")
        if isinstance(value, (int, float)):
            out[str(key)] = float(value)
            continue
        if isinstance(value, str):
            try:
                out[str(key)] = float(value)
            except ValueError as exc:
                raise ValueError(
                    f"financial item {key!r} must be numeric, got {value!r}"
                ) from exc
            continue
        raise TypeError(
            f"financial item {key!r} must be numeric, got {type(value).__name__}"
        )
    return out


def _extract_latest_period(
    raw_data: Mapping[str, object] | None,
    statement_type: str,
) -> Mapping[str, object]:
    """Return the most-recent entry in ``raw_data[bucket_key]``.

    The TA-CN list is sorted by ``end_date`` descending. We pick the
    first element when present, falling back to the empty mapping.

    The bucket key is derived from the canonical ``statement_type``
    via :data:`_STATEMENT_BUCKET_KEYS` (so ``"balance"`` maps to
    ``"balance_sheet"`` to match the production schema documented in
    DESIGN-03-007).
    """
    if not raw_data:
        return {}
    bucket_key = _STATEMENT_BUCKET_KEYS.get(statement_type, statement_type + "_statement")
    bucket = raw_data.get(bucket_key)
    if isinstance(bucket, list) and bucket:
        entries = [entry for entry in bucket if isinstance(entry, Mapping)]
        if entries:
            return max(entries, key=lambda entry: str(entry.get("end_date") or ""))
    # Fall back to a ``<statement_type>_statement`` key in case older
    # documents used the canonical suffix form.
    alt_key = statement_type + "_statement"
    if alt_key != bucket_key:
        alt_bucket = raw_data.get(alt_key)
        if isinstance(alt_bucket, list) and alt_bucket:
            entries = [entry for entry in alt_bucket if isinstance(entry, Mapping)]
            if entries:
                return max(
                    entries, key=lambda entry: str(entry.get("end_date") or "")
                )
    return {}


@dataclass
class FinancialStatement:
    """财务数据 — ``stock_financial_data`` canonical。

    ``statement_type`` 由 service 方法决定 (``"income"`` /
    ``"balance"`` / ``"cashflow"``)；同一个 TA-CN 文档可派生出多个
    ``FinancialStatement`` 实例（每个 statement type 一个）。
    """

    symbol: str
    report_period: str           # 'YYYYMMDD'
    statement_type: str          # 'income' / 'balance' / 'cashflow'
    items: dict[str, float] = field(default_factory=dict)
    currency: str = "CNY"

    @classmethod
    def from_ta_cn_doc(
        cls,
        doc: dict,
        statement_type: str,
    ) -> "FinancialStatement":
        """从 ``stock_financial_data`` 文档映射为指定报表类型的最新一期。

        抛出 :class:`ValueError` 当 ``statement_type`` 不是
        ``income`` / ``balance`` / ``cashflow`` 之一；当 ``doc`` 不是
        ``dict`` 时抛出 :class:`TypeError`。
        """
        if not isinstance(doc, dict):
            raise TypeError(
                f"FinancialStatement.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        if statement_type not in VALID_STATEMENT_TYPES:
            raise ValueError(
                f"statement_type must be one of {VALID_STATEMENT_TYPES!r}, "
                f"got {statement_type!r}"
            )
        report_period = doc.get("report_period")
        raw_data = doc.get("raw_data")
        latest = _extract_latest_period(raw_data if isinstance(raw_data, Mapping) else None, statement_type)
        items = _normalize_items(latest)
        currency = doc.get("currency") or "CNY"
        return cls(
            symbol=str(doc.get("symbol", "")),
            report_period=str(report_period) if report_period is not None else "",
            statement_type=statement_type,
            items=items,
            currency=str(currency),
        )


__all__ = ["FinancialStatement", "VALID_STATEMENT_TYPES"]
