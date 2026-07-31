"""Canonical historical sector ranking row — Phase 3 (RFC-03-015).

:class:`SectorRankingDaily` is the 9-field minimal row schema for the
``03_data_ud_sector_ranking_daily`` collection (SPEC-03-015 §3.2.1
H-009 ~ H-017). Each record represents one ``sector_code`` of one
``dataset`` on one closed historical ``trade_date``, ranked by its
close-to-pre_close daily change (``pct_chg``).

Design constraints (RFC-03-015 V0.5 / SPEC-03-015 V0.5 / DESIGN-03-015
V0.5):

* 9 fields, all required, no defaults, no ``None`` tolerance.
* ``dataset`` is restricted to the frozen first-version enum
  (``sw2021_ta_cn`` only).
* ``trade_date`` must be ``YYYY-MM-DD``.
* ``pre_close`` must be non-zero (division guard for the fixed
  close-to-pre_close return formula).
* Extra keys in :meth:`from_dict` are silently ignored
  (A-015-DRIFT-2 field-name drift tolerance).

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# dataset 枚举（SPEC H-023 ~ H-025）：第一版仅 sw2021_ta_cn。
# 后续扩展（eastmoney_industry / ths_industry / sina_industry_eod）
# 由未来 RFC/Gate 授权，不得在 T3 硬编码为可用值。
KNOWN_DATASETS: frozenset[str] = frozenset({"sw2021_ta_cn"})

# 9 字段最小行 schema（SPEC H-009 ~ H-017）。
REQUIRED_FIELDS: tuple[str, ...] = (
    "dataset",
    "trade_date",
    "sector_code",
    "sector_name",
    "pct_chg",
    "rank",
    "close",
    "pre_close",
    "updated_at",
)

_TRADE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_valid_trade_date(value: Any) -> bool:
    """Return ``True`` only for a ``YYYY-MM-DD`` calendar-date string.

    Format and calendar validity are both checked (e.g. ``2026-13-45``
    is rejected). ``None`` / non-str / zero-padding violations are
    rejected too — this is the single validation path shared by the
    domain factory and the read service.
    """
    if not isinstance(value, str):
        return False
    if not _TRADE_DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def coerce_float(value: Any) -> float | None:
    """Coerce ``value`` to a finite ``float``, or ``None`` when invalid.

    Accepts int / float / numeric string (A-015-DRIFT-4 tolerant
    coercion). Rejects ``bool``, ``None``, non-numeric strings and
    non-finite floats (NaN / inf). Returns ``None`` — never raises —
    so callers can drop a row instead of failing the whole batch.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(result):
        return None
    return result


def coerce_int(value: Any) -> int | None:
    """Coerce ``value`` to an ``int``, or ``None`` when invalid.

    Accepts int / integral numeric string. Rejects ``bool``, floats
    with a fractional part and non-integral strings.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _require_nonempty_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


@dataclass
class SectorRankingDaily:
    """历史行业日涨跌幅排名行 — ``03_data_ud_sector_ranking_daily`` canonical。

    9 字段最小行 schema（SPEC-03-015 V0.5 §3.2.1 H-009 ~ H-017）。
    每条记录表示某 ``dataset`` 下某 ``sector_code`` 在某已收盘交易日的
    日涨跌幅排名。消费方通过 ``sector.ranking_history`` capability 访问。

    本数据为辅助研究数据，不构成交易指令或投资建议。
    """

    dataset: str          # (必填) 数据源与分类口径标识，如 "sw2021_ta_cn"
    trade_date: str       # (必填) 交易日，格式 "YYYY-MM-DD"，已收盘历史交易日
    sector_code: str      # (必填) 板块代码，dataset 内唯一
    sector_name: str      # (必填) 板块名称
    pct_chg: float        # (必填) 日涨跌幅 %，口径 (close-pre_close)/pre_close*100
    rank: int             # (必填) 当日涨跌幅排名（1=涨幅最高）
    close: float          # (必填) 当日收盘价/收盘指数
    pre_close: float      # (必填) 前一交易日收盘价/收盘指数
    updated_at: str       # (必填) 行写入/更新时间戳，ISO-8601

    @classmethod
    def from_dict(cls, d: dict) -> "SectorRankingDaily":
        """从字典构造。全部 9 字段必填——缺失任一 → ``ValueError``。

        不做默认值填充、不做 ``None`` 容忍（SPEC H-018 / DESIGN
        §3.3.1）。数值字段按 A-015-DRIFT-4 容错强转；强转失败 →
        ``ValueError``。多余字段静默忽略（A-015-DRIFT-2）。

        Args:
            d: 9 字段行字典。

        Returns:
            校验通过后的 :class:`SectorRankingDaily`。

        Raises:
            TypeError: ``d`` 不是 dict。
            ValueError: 任一必填字段缺失、为 ``None``、或取值非法
                （dataset 非已知枚举 / trade_date 非 ``YYYY-MM-DD`` /
                pre_close == 0 / rank < 1 / 数值不可强转）。
        """
        if not isinstance(d, dict):
            raise TypeError(
                f"SectorRankingDaily.from_dict expects dict, got {type(d).__name__}"
            )
        missing = [field for field in REQUIRED_FIELDS if field not in d]
        if missing:
            raise ValueError(
                f"SectorRankingDaily missing required field(s): {sorted(missing)}"
            )

        dataset = _require_nonempty_str(d["dataset"], field="dataset")
        if dataset not in KNOWN_DATASETS:
            raise ValueError(
                f"dataset {dataset!r} is not a known dataset; "
                f"known datasets: {sorted(KNOWN_DATASETS)}"
            )
        trade_date = _require_nonempty_str(d["trade_date"], field="trade_date")
        if not is_valid_trade_date(trade_date):
            raise ValueError(
                f"trade_date must be a valid YYYY-MM-DD string, got {d['trade_date']!r}"
            )
        sector_code = _require_nonempty_str(d["sector_code"], field="sector_code")
        sector_name = _require_nonempty_str(d["sector_name"], field="sector_name")
        updated_at = _require_nonempty_str(d["updated_at"], field="updated_at")

        pct_chg = coerce_float(d["pct_chg"])
        if pct_chg is None:
            raise ValueError(f"pct_chg must be a finite number, got {d['pct_chg']!r}")
        close = coerce_float(d["close"])
        if close is None:
            raise ValueError(f"close must be a finite number, got {d['close']!r}")
        pre_close = coerce_float(d["pre_close"])
        if pre_close is None:
            raise ValueError(
                f"pre_close must be a finite number, got {d['pre_close']!r}"
            )
        if pre_close == 0:
            raise ValueError("pre_close must be non-zero (division guard)")
        rank = coerce_int(d["rank"])
        if rank is None or rank < 1:
            raise ValueError(
                f"rank must be an integer >= 1, got {d['rank']!r}"
            )

        return cls(
            dataset=dataset,
            trade_date=trade_date,
            sector_code=sector_code,
            sector_name=sector_name,
            pct_chg=pct_chg,
            rank=rank,
            close=close,
            pre_close=pre_close,
            updated_at=updated_at,
        )


__all__ = [
    "KNOWN_DATASETS",
    "REQUIRED_FIELDS",
    "SectorRankingDaily",
    "coerce_float",
    "coerce_int",
    "is_valid_trade_date",
]
