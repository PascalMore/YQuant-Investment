"""Fundamental data domain service (Phase 1A).

Single TA-CN collection: ``stock_financial_data`` (1 adapter method →
3 statement types → 3 service entry points → 3 client APIs).

The service is the mapping surface where the raw nested
``raw_data.{income,balance,cashflow}_statement`` lists get flattened
into the canonical ``FinancialStatement.items`` field.
"""

from __future__ import annotations

from ..adapters import TA_CNMongoAdapter
from ..models import DataResult, SecurityId
from ..models.domain import FinancialStatement, VALID_STATEMENT_TYPES
from . import SERVICE_ERRORS, wrap_empty, wrap_error, wrap_success


class FundamentalService:
    """财务域服务（Phase 1A — TA-CN MongoDB 只读）。"""

    DOMAIN = "financial"

    def __init__(self, adapter: TA_CNMongoAdapter) -> None:
        self._adapter = adapter

    # ── helpers ───────────────────────────────────────────────
    def _get_statement(
        self,
        security_id: SecurityId,
        statement_type: str,
        report_period: str | None,
    ) -> DataResult:
        if statement_type not in VALID_STATEMENT_TYPES:
            raise ValueError(
                f"statement_type must be one of {VALID_STATEMENT_TYPES!r}, "
                f"got {statement_type!r}"
            )
        operation = f"{statement_type}_statement"
        try:
            doc = self._adapter.get_financials(
                security_id.symbol,
                report_period=report_period,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, self.DOMAIN, operation, exc)
        if not doc:
            return wrap_empty(security_id, self.DOMAIN, operation)
        try:
            statement = FinancialStatement.from_ta_cn_doc(doc, statement_type)
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, self.DOMAIN, operation, exc)
        return wrap_success(statement, security_id, self.DOMAIN, operation)

    # ── stock_financial_data ──────────────────────────────────
    def get_income_statement(
        self,
        security_id: SecurityId,
        report_period: str | None = None,
    ) -> DataResult:
        return self._get_statement(security_id, "income", report_period)

    def get_balance_sheet(
        self,
        security_id: SecurityId,
        report_period: str | None = None,
    ) -> DataResult:
        return self._get_statement(security_id, "balance", report_period)

    def get_cash_flow(
        self,
        security_id: SecurityId,
        report_period: str | None = None,
    ) -> DataResult:
        return self._get_statement(security_id, "cashflow", report_period)


__all__ = ["FundamentalService"]
