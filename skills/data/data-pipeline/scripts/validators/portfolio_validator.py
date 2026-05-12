"""Portfolio data validators.

Validates data quality before database insertion.
Enhanced with financial format validation.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Wind 代码格式正则
# A股: 6位数字.SZ/.SH/.BJ（可能被误读为XXXXXXSZ少点）
# 港股: 4-5位数字.HK 或 XXXXHK（少点）
# 美股: 1-6位字母.US 或 XXXXUS（少点，如MSETUS）
# 其他: 6位数字.OF/.CN/.RI/.GB/.SG
WIND_CODE_RE = re.compile(
    r'^(\d{6}\.(SH|SZ|BJ|CN|OF|RI|GB|SG)|'  # A股有点
    r'\d{4,5}\.HK|'                              # 港股有点
    r'\d{4,5}HK|'                                 # 港股少点
    r'[A-Z]{1,6}\.(US)|'                         # 美股有点
    r'[A-Z]{1,6}[A-Z]{2}|'                       # 美股少点(最后2字母=US)
    r'\d{6}\.(OF|RI|GB|SG))$'                    # 其他
)
# 持仓比例：0-1 之间，最多 4 位小数
HOLDING_RATIO_RE = re.compile(r'^\d*\.?\d{1,4}$')
# 整数正则
INT_RE = re.compile(r'^\d+$')


@dataclass
class ValidationResult:
    """Validation result container."""
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str):
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str):
        self.warnings.append(message)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def merge(self, other: "ValidationResult"):
        """Merge another ValidationResult into this one."""
        if not other.valid:
            self.valid = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def validate_wind_code(code: Optional[str]) -> tuple[bool, str, Optional[str]]:
    """校验 Wind 代码格式，支持自动纠错。
    
    自动纠错规则:
    - A股少0: XXXX5.SH → XXXX05.SH (如68855.SH → 688055.SH)
    - 港股少点: XXXXHK → XXXX.HK
    - 美股少点: XXXXUS → XXXX.US
    
    Returns:
        (is_valid, message, corrected_code)
        corrected_code 为自动纠错后的代码，若无需纠错则为 None
    """
    if not code:
        return False, "Wind 代码为空", None
    code = str(code).strip()
    
    # 先检查是否直接匹配
    if WIND_CODE_RE.match(code):
        return True, "", None
    
    # 尝试自动纠错
    original = code
    
    # 纠错1: A股少0 (如68855.SH → 688055.SH)
    # 匹配 X{4,5}.SH 或 X{4,5}.SZ 或 X{5}.BJ 等
    m = re.match(r'^(\d{5})\.(SH|SZ|BJ|CN)$', code)
    if m:
        code = '0' + m.group(1) + '.' + m.group(2)
        if WIND_CODE_RE.match(code):
            return True, f"[自动纠错] {original} → {code}", code
    
    # 纠错2: A股少点 (如688055SH → 688055.SH)
    m = re.match(r'^(\d{6})(SH|SZ|BJ|CN)$', code)
    if m:
        code = m.group(1) + '.' + m.group(2)
        if WIND_CODE_RE.match(code):
            return True, f"[自动纠错] {original} → {code}", code
    
    # 纠错3: 港股少点 (如0123HK → 0123.HK)
    m = re.match(r'^(\d{4,5})(HK)$', code)
    if m:
        code = m.group(1) + '.' + m.group(2)
        if WIND_CODE_RE.match(code):
            return True, f"[自动纠错] {original} → {code}", code
    
    # 纠错4: 美股少点 (如AABBRUS → AABB.US, 或 MSFTUS → MSFT.US)
    m = re.match(r'^([A-Z]{1,6})(US)$', code, re.IGNORECASE)
    if m:
        code = m.group(1).upper() + '.' + m.group(2).upper()
        if WIND_CODE_RE.match(code):
            return True, f"[自动纠错] {original} → {code}", code
    
    return False, f"Wind 代码格式错误: {code} (期望 XXXXXX.SH/HK/US/SZ/CN/OF/RI/GB/SG/BJ)", None


def validate_holding_ratio(ratio: Any) -> tuple[bool, str]:
    """校验持仓比例：0-1 之间，保留 4 位小数。
    
    Returns:
        (is_valid, message)
    """
    if ratio is None or ratio == '':
        return True, ""  # 允许空（部分持仓无比例）
    try:
        val = float(ratio)
        if not (0 <= val <= 1):
            return False, f"持仓比例 {val} 超出范围 [0, 1]"
        # 检查小数位数
        ratio_str = str(ratio).strip()
        if '.' in ratio_str:
            decimals = len(ratio_str.split('.')[1])
            if decimals > 4:
                return False, f"持仓比例 {ratio} 小数位数超过 4 位"
        return True, ""
    except (ValueError, TypeError):
        return False, f"持仓比例 {ratio} 无法转换为数字"


def validate_positive_int(value: Any, field_name: str) -> tuple[bool, str]:
    """校验正整数。
    
    Returns:
        (is_valid, message)
    """
    if value is None or value == '':
        return True, ""  # 允许空
    try:
        val = int(float(str(value)))
        if val <= 0:
            return False, f"{field_name} {val} 必须为正整数"
        # 检查是否真的是整数（如 1234.0 算整数，1234.5 不算）
        if float(val) != float(str(value)):
            return False, f"{field_name} {value} 不是整数"
        return True, ""
    except (ValueError, TypeError):
        return False, f"{field_name} {value} 无法转换为整数"


def validate_basic_info(records: list[dict]) -> ValidationResult:
    """Validate basic info records.

    Args:
        records: List of basic info records.

    Returns:
        ValidationResult with errors if any validation fails.
    """
    result = ValidationResult()
    for i, rec in enumerate(records):
        code = rec.get("product_code")
        if not code:
            result.add_error(f"[{i}] product_code is empty")
        
        name = rec.get("product_name")
        if not name:
            result.add_warning(f"[{i}] product_name is empty for {code}")
        
        # 最新净值应为正数
        nav = rec.get("latest_nav")
        if nav is not None and nav != '':
            try:
                nav_val = float(nav)
                if nav_val <= 0:
                    result.add_warning(f"[{i}] latest_nav {nav} <= 0")
            except (ValueError, TypeError):
                result.add_warning(f"[{i}] latest_nav {nav} 格式错误")
        
        # 最新份额应为正整数
        share = rec.get("latest_share")
        if share is not None and share != '':
            ok, msg = validate_positive_int(share, "latest_share")
            if not ok:
                result.add_warning(f"[{i}] {msg}")
        
        # 最新规模应为正数
        aum = rec.get("latest_aum")
        if aum is not None and aum != '':
            try:
                aum_val = float(str(aum))
                if aum_val < 0:
                    result.add_warning(f"[{i}] latest_aum {aum} 为负数")
            except (ValueError, TypeError):
                result.add_warning(f"[{i}] latest_aum {aum} 格式错误")
    
    return result


def validate_nav(records: list[dict]) -> ValidationResult:
    """Validate NAV records.

    Args:
        records: List of NAV records.

    Returns:
        ValidationResult with errors if any validation fails.
    """
    result = ValidationResult()
    for i, rec in enumerate(records):
        date = rec.get("nav_date")
        if not date:
            result.add_error(f"[{i}] nav_date is empty")
        elif not re.match(r'^\d{4}-\d{2}-\d{2}$', str(date)):
            result.add_warning(f"[{i}] nav_date {date} 格式错误 (期望 YYYY-MM-DD)")
        
        code = rec.get("product_code")
        if not code:
            result.add_error(f"[{i}] product_code is empty")
        
        nav = rec.get("nav")
        if nav is not None and nav != '':
            try:
                nav_val = float(nav)
                if nav_val <= 0:
                    result.add_error(f"[{i}] nav {nav} must be positive")
            except (ValueError, TypeError):
                result.add_error(f"[{i}] nav {nav} 格式错误")
        
        # 规模应为正数
        aum = rec.get("aum")
        if aum is not None and aum != '':
            try:
                aum_val = float(str(aum))
                if aum_val < 0:
                    result.add_warning(f"[{i}] aum {aum} 为负数")
            except (ValueError, TypeError):
                result.add_warning(f"[{i}] aum {aum} 格式错误")
    
    return result


def validate_position(records: list[dict]) -> ValidationResult:
    """Validate position records with financial format checks.

    Args:
        records: List of position records.

    Returns:
        ValidationResult with errors if any validation fails.
    """
    result = ValidationResult()
    for i, rec in enumerate(records):
        # 必填字段
        date = rec.get("position_date")
        if not date:
            result.add_error(f"[{i}] position_date is empty")
        
        code = rec.get("product_code")
        if not code:
            result.add_error(f"[{i}] product_code is empty")
        
        wind_code = rec.get("asset_wind_code")
        ok, msg, corrected = validate_wind_code(wind_code)
        if not ok:
            result.add_warning(f"[{i}] asset_wind_code: {msg}")
        elif corrected:
            result.add_warning(f"[{i}] asset_wind_code: {msg}")
            # 将纠错后的代码写回记录
            rec["asset_wind_code"] = corrected
        
        # 持仓比例：0-1 之间，4 位小数
        ratio = rec.get("holding_ratio")
        ok, msg = validate_holding_ratio(ratio)
        if not ok:
            result.add_warning(f"[{i}] {msg}")
        
        # 数量：正整数
        qty = rec.get("quantity")
        if qty is not None and qty != '':
            ok, msg = validate_positive_int(qty, "quantity")
            if not ok:
                result.add_warning(f"[{i}] {msg}")
        
        # 市值：正整数
        mkt = rec.get("market_value")
        if mkt is not None and mkt != '':
            ok, msg = validate_positive_int(mkt, "market_value")
            if not ok:
                result.add_warning(f"[{i}] {msg}")
    
    return result


def validate_all(normalized: dict) -> ValidationResult:
    """Validate all normalized record types.

    Args:
        normalized: Dict with 'basic_info', 'nav', 'position' keys.

    Returns:
        Combined ValidationResult for all record types.
    """
    result = ValidationResult()
    result.merge(validate_basic_info(normalized.get("basic_info", [])))
    result.merge(validate_nav(normalized.get("nav", [])))
    result.merge(validate_position(normalized.get("position", [])))
    return result


if __name__ == "__main__":
    import json

    with open("examples/mock_3days_decoded.json") as f:
        decoded = json.load(f)

    from transformers.image_portfolio_normalizer import normalize_all

    normalized = normalize_all(decoded)
    result = validate_all(normalized)

    print("=== Validation Result ===")
    print(f"Valid: {result.valid}")
    print(f"Errors: {len(result.errors)}")
    for e in result.errors:
        print(f"  ERROR: {e}")
    print(f"Warnings: {len(result.warnings)}")
    for w in result.warnings:
        print(f"  WARNING: {w}")