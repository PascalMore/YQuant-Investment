"""
Validation rules for trade data.
"""
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def validate_trade(records: list[dict]) -> ValidationResult:
    """
    Validate a list of trade records.

    Rules:
    - trade_date must be non-empty and in YYYY-MM-DD format
    - product_code must be non-empty
    - asset_wind_code must be non-empty
    - direction must be "买入" or "卖出"
    - change_ratio should be in range [-1, 1] (warning if outside)
    - change_amount should be non-zero (warning if zero)
    """
    result = ValidationResult()

    for i, rec in enumerate(records, 1):
        # trade_date
        trade_date = rec.get("trade_date")
        if not trade_date:
            result.errors.append(f"[{i}] trade_date is empty")

        # product_code
        if not rec.get("product_code"):
            result.errors.append(f"[{i}] product_code is empty")

        # asset_wind_code
        if not rec.get("asset_wind_code"):
            result.errors.append(f"[{i}] asset_wind_code is empty")

        # direction
        direction = rec.get("direction")
        if direction not in ("买入", "卖出"):
            result.errors.append(f"[{i}] direction '{direction}' is not 买入/卖出")

        # change_ratio range
        ratio = rec.get("change_ratio")
        if ratio is not None and (ratio < -1 or ratio > 1):
            result.warnings.append(f"[{i}] change_ratio {ratio} outside [-1, 1]")

        # change_amount zero
        amount = rec.get("change_amount")
        if amount == 0:
            result.warnings.append(f"[{i}] change_amount is zero")

    return result
