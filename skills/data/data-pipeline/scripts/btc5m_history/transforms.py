"""BTC5m 历史的字段映射 — 03-018 §6.2 / §6.3。

精确时间、Decimal 与 hash 规则：

* UTC 输入（``Z`` / 零 offset），用整数运算得到 int64 微秒，**不用**
  ``datetime.timestamp()`` 乘浮点。
* JSON 数字 token 直接 ``Decimal``，不先经 float。
* CSV token 全部是原字符串 → ``Decimal`` → ``Decimal128``。
* 观察时间向上取毫秒（不向下截断）。

映射的字段与 SPEC §5.2 / §5.3 完全一致。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from ..transformers.base import BaseTransformer

from .common import (
    ERR_BAD_CSV,
    ERR_CONFLICT,
    SERIES_SLUG,
    SOURCE_KLINES,
    SOURCE_ROUNDS,
)

#: 1 秒 = 1_000_000 微秒；round 时长 300 秒。
MICROS_PER_SECOND = 1_000_000
ROUND_DURATION_SECONDS = 300

#: 允许的官方 outcome。
VALID_OUTCOMES = ("UP", "DOWN", "DRAW")


def _flat_evidence(
    market: Mapping[str, Any], start_price: Decimal | None, end_price: Decimal | None,
) -> dict[str, Any] | None:
    """Recognize only the official equal-price, dual-WON, equal-split rule."""
    import re

    if (not isinstance(start_price, Decimal) or not isinstance(end_price, Decimal)
            or not start_price.is_finite() or not end_price.is_finite()
            or start_price <= 0 or start_price != end_price):
        return None
    outcomes = market.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != 2:
        return None
    by_name = {}
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            return None
        name = str(outcome.get("name", "")).upper()
        if (name not in ("UP", "DOWN") or name in by_name
                or type(outcome.get("indexSet")) is not int
                or outcome["indexSet"] != {"UP": 1, "DOWN": 2}[name]
                or outcome.get("status") != "WON"):
            return None
        by_name[name] = outcome
    tokens = [item.get("onChainId") for item in outcomes]
    if any(token is not None for token in tokens) and (
            any(not isinstance(token, str) or not token.isascii() or not token.isdecimal()
                for token in tokens) or tokens[0] == tokens[1]):
        return None
    resolution = market.get("resolution")
    if resolution is not None:
        if not isinstance(resolution, dict):
            return None
        matched = by_name.get(str(resolution.get("name", "")).upper())
        if (matched is None or type(resolution.get("indexSet")) is not int
                or any(resolution.get(key) != matched.get(key)
                       for key in ("name", "indexSet", "onChainId"))):
            return None
    description = market.get("description")
    if not isinstance(description, str):
        return None
    rule = re.search(
        r"(?:^|[.!?]\s+)(If\s+the\s+two\s+prices\s+are\s+exactly\s+equal,\s+"
        r"the\s+market\s+will\s+resolve\s+50-50\.)", description.strip(), re.IGNORECASE,
    )
    if rule is None:
        return None
    return {"settlement_rule": "official-flat-50-50", "rule_source": "market.description",
            "rule_text": rule.group(1), "market_id": str(market.get("id") or ""),
            "original_resolution": resolution, "outcomes": outcomes,
            "payout_basis": "equal-split-by-market-rule-not-onchain-vector"}



class TransformError(RuntimeError):
    """字段映射失败（稳定码）。"""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def parse_utc_datetime(value: Any) -> datetime | None:
    """把官方时间文本 / 整数解析为 naive-UTC datetime。

    Args:
        value: ISO 字符串（``Z`` / 零 offset）或 epoch 秒整数。

    Returns:
        naive-UTC datetime；``None`` 输入返回 ``None``。

    Raises:
        TransformError: ``INVALID_TIMESTAMP``。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise TransformError("INVALID_TIMESTAMP", "bool is not a timestamp")
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
    if not isinstance(value, str):
        raise TransformError("INVALID_TIMESTAMP", type(value).__name__)
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TransformError("INVALID_TIMESTAMP", text) from exc
    if parsed.tzinfo is None:
        raise TransformError("INVALID_TIMESTAMP", "naive timestamp")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def datetime_to_us(value: datetime | None) -> int | None:
    """把 naive-UTC datetime 转 int64 微秒（整数运算）。"""
    if value is None:
        return None
    epoch = datetime(1970, 1, 1)
    delta = value - epoch
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


def parse_decimal(token: Any, *, field: str) -> Decimal:
    """把 token 解析成 Decimal（不经 float）。

    Raises:
        TransformError: ``INVALID_DECIMAL``。
    """
    if isinstance(token, Decimal):
        return token
    if isinstance(token, bool):
        raise TransformError("INVALID_DECIMAL", field)
    if isinstance(token, int):
        return Decimal(token)
    if isinstance(token, float):
        raise TransformError("INVALID_DECIMAL", f"{field} must not be a float")
    if not isinstance(token, str):
        raise TransformError("INVALID_DECIMAL", f"{field}: {type(token).__name__}")
    text = token.strip()
    if not text:
        raise TransformError("INVALID_DECIMAL", field)
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise TransformError("INVALID_DECIMAL", field) from exc
    if value.is_nan() or value.is_infinite():
        raise TransformError("INVALID_DECIMAL", f"{field} is not finite")
    return value


def ceil_ms_to_us(value: datetime | None) -> int | None:
    """把 BSON datetime 向上取毫秒后转微秒。"""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    epoch = datetime(1970, 1, 1)
    delta = value - epoch
    micros = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    remainder = micros % 1000
    if remainder:
        micros += 1000 - remainder
    return micros


# ---------------------------------------------------------------------------
# Predict rounds
# ---------------------------------------------------------------------------


class PredictRoundTransformer(BaseTransformer):
    """Predict round envelope → 规范 round 记录。

    身份自洽是硬要求：duration 必须 300 秒、series 必须是
    ``btc-updown-5m``、feed symbol 必须是 ``BTCUSDT``；ETH / 15m / 多市场
    / variant 矛盾一律拒绝完成。
    """

    async def transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """映射一批 round envelope。

        Raises:
            TransformError: 身份 / schema 不符。
        """
        out: list[dict[str, Any]] = []
        for record in records:
            out.append(self.transform_one(record))
        return out

    def transform_one(self, record: dict[str, Any]) -> dict[str, Any]:
        """映射单个 round envelope。

        Raises:
            TransformError: ``INVALID_IDENTITY`` / ``INVALID_SCHEMA`` /
                ``VARIANT_CONFLICT``。
        """
        category = record.get("category") or {}
        if not isinstance(category, dict):
            raise TransformError("INVALID_SCHEMA", "category is not an object")

        series_slug = str(category.get("seriesSlug") or category.get("slug") or "")
        if series_slug != SERIES_SLUG:
            raise TransformError("INVALID_IDENTITY", f"series={series_slug!r}")

        starts_at = parse_utc_datetime(category.get("startsAt"))
        ends_at = parse_utc_datetime(category.get("endsAt"))
        if starts_at is None or ends_at is None:
            raise TransformError("INVALID_SCHEMA", "startsAt/endsAt missing")
        duration = int((ends_at - starts_at).total_seconds())
        if duration != ROUND_DURATION_SECONDS:
            raise TransformError(
                "INVALID_IDENTITY", f"duration={duration}"
            )

        market = self._select_market(record, category)
        variant = self._select_variant(category, market)

        round_id = category.get("id")
        if round_id is None:
            raise TransformError("INVALID_SCHEMA", "category.id missing")
        if type(round_id) is int and round_id >= 0:
            round_id_text = str(round_id)
        elif isinstance(round_id, str) and round_id.isascii() and round_id.isdecimal():
            round_id_text = round_id
        else:
            raise TransformError("INVALID_SCHEMA", "category.id must be an ASCII decimal ID")

        start_price = self._extract_price(variant, ("startPrice",))
        end_price = self._extract_price(variant, ("endPrice",))
        feed_provider = self._first_text(variant, ("priceFeedProvider",))
        feed_symbol = self._first_text(variant, ("priceFeedSymbol",))
        if feed_symbol != "BTCUSDT":
            raise TransformError("INVALID_IDENTITY", f"feed_symbol={feed_symbol!r}")

        published_at = parse_utc_datetime(category.get("publishedAt"))
        outcome, resolution_evidence, settlement_state = self._resolve_outcome(
            record, market, category, start_price=start_price, end_price=end_price
        )
        resolved_at_us = None
        if settlement_state == "resolved":
            logs = (record.get("_status_logs") or {}).get(str(market.get("id")), [])
            from skills.data.unified_data.history_types import canonical_json

            terminal = {canonical_json(log): log for log in logs
                        if str(log.get("status", "")).upper() == "RESOLVED"}
            if len(terminal) > 1:
                outcome, resolution_evidence, settlement_state = None, None, "conflict"
            elif not terminal or start_price is None or end_price is None:
                outcome, resolution_evidence, settlement_state = None, None, "pending"
            else:
                log = next(iter(terminal.values()))
                resolved_at_us = datetime_to_us(parse_utc_datetime(log.get("timestamp")))
                if (resolved_at_us is None or start_price <= 0 or end_price <= 0
                        or ((resolution_evidence or {}).get("settlement_rule") == "official-flat-50-50"
                            and resolved_at_us < (datetime_to_us(ends_at) or 0))):
                    outcome, resolution_evidence, settlement_state = None, None, "pending"
                else:
                    resolution_evidence = dict(resolution_evidence or {})
                    resolution_evidence["final_transition"] = log
                    refs = record.get("_status_raw_refs", [])
                    if refs:
                        resolution_evidence.update(refs[0])

        return {
            "schema_version": 1,
            "source": SOURCE_ROUNDS,
            "series_slug": SERIES_SLUG,
            "round_id": round_id_text,
            "round_slug": str(category.get("slug") or ""),
            "market_id": str(market.get("id") or ""),
            "condition_id": str(market.get("conditionId") or ""),
            "published_at_us": datetime_to_us(published_at),
            "starts_at_us": datetime_to_us(starts_at),
            "ends_at_us": datetime_to_us(ends_at),
            "start_price": start_price,
            "end_price": end_price,
            "price_feed_provider": feed_provider,
            "price_feed_symbol": feed_symbol,
            "category_status": str(category.get("status") or ""),
            "market_status": str(market.get("status") or ""),
            "trading_status": str(
                market.get("tradingStatus") or category.get("tradingStatus") or ""
            ),
            "settlement_state": settlement_state,
            "official_outcome": outcome,
            "resolution_evidence": resolution_evidence,
            "resolved_at_us": resolved_at_us,
            "label_observed_at": None,
            "next_check_at": None,
        }

    # -- 身份选择 --------------------------------------------------------
    def _select_market(
        self, record: dict[str, Any], category: dict[str, Any]
    ) -> dict[str, Any]:
        """选出唯一匹配的 BTC5m market。

        Raises:
            TransformError: ``INVALID_IDENTITY``（0 个或多个候选）。
        """
        markets = record.get("markets") or []
        if not isinstance(markets, list):
            raise TransformError("INVALID_SCHEMA", "markets is not a list")
        candidates = [
            market
            for market in markets
            if isinstance(market, dict)
            and str(market.get("seriesSlug") or "") == SERIES_SLUG
        ]
        if len(candidates) != 1:
            raise TransformError(
                "INVALID_IDENTITY", f"market candidates={len(candidates)}"
            )
        return candidates[0]

    def _select_variant(
        self, category: dict[str, Any], market: dict[str, Any]
    ) -> dict[str, Any]:
        """收集所有价格候选来源（非空同语义值须 exact 一致）。

        Raises:
            TransformError: ``VARIANT_CONFLICT``。
        """
        sources: list[dict[str, Any]] = []
        for owner in (category, market):
            details = owner.get("variantDetails")
            if isinstance(details, dict):
                sources.append(details)
                for nested_key in ("upDown", "crypto"):
                    nested = details.get(nested_key)
                    if isinstance(nested, dict):
                        sources.append(nested)
            variant_data = owner.get("variantData")
            if isinstance(variant_data, dict):
                sources.append(variant_data)

        merged: dict[str, Any] = {}
        for source in sources:
            for key in ("startPrice", "endPrice", "priceFeedProvider", "priceFeedSymbol"):
                value = source.get(key)
                if value in (None, ""):
                    continue
                # Compare price semantics as Decimal, never via float or raw-token priority.
                if key in ("startPrice", "endPrice"):
                    value = parse_decimal(value, field=key)
                if key in merged and merged[key] != value:
                    raise TransformError("VARIANT_CONFLICT", key)
                merged[key] = value
        return merged

    @staticmethod
    def _extract_price(
        variant: dict[str, Any], keys: tuple[str, ...]
    ) -> Decimal | None:
        """取价格候选（非空值须 exact 一致；矛盾 → 抛错）。"""
        found: Decimal | None = None
        for key in keys:
            raw = variant.get(key)
            if raw in (None, ""):
                continue
            value = parse_decimal(raw, field=key)
            if found is not None and found != value:
                raise TransformError("VARIANT_CONFLICT", key)
            found = value
        return found

    @staticmethod
    def _first_text(variant: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = variant.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    # -- 结算 -----------------------------------------------------------
    def _resolve_outcome(
        self,
        record: dict[str, Any],
        market: dict[str, Any],
        category: dict[str, Any],
        *, start_price: Decimal | None, end_price: Decimal | None,
    ) -> tuple[str | None, dict[str, Any] | None, str]:
        """由官方 resolution / outcomes 映射 outcome。

        * ``ENDED`` **不等于** 已结算：``market.status`` /
          ``tradingStatus`` / ``category.status`` 必须是真实终态。
        * 只有明确的 ``RESOLVED`` + 唯一 WON outcome 才映射 UP / DOWN。
        * ``DRAW`` 接受显式官方结果，或 SPEC §8 的等价价格/双WON/
          同市场50-50规则联合证据；单项证据与proposed值不造标签。
        """
        status = str(market.get("status") or category.get("status") or "")
        trading_status = str(market.get("tradingStatus") or "")
        if status.upper() == "REMOVED":
            return None, None, "unavailable"
        if trading_status.upper() in ("PRICE_PROPOSED", "PRICE_DISPUTED", "PAUSED"):
            return None, None, "pending"
        if status.upper() != "RESOLVED":
            return None, None, "pending"

        resolution = market.get("resolution") or category.get("resolution")
        outcomes = market.get("outcomes") or category.get("outcomes") or []
        if not isinstance(outcomes, list):
            outcomes = []
        winners = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, dict)
            and str(outcome.get("status") or "").upper() == "WON"
        ]
        if len(winners) != 1:
            flat = _flat_evidence(market, start_price, end_price)
            if (flat is not None and trading_status.upper() in ("RESOLVED", "CLOSED")
                    and str(category.get("status", "")).upper() == "RESOLVED"):
                return "DRAW", flat, "resolved"
            return None, None, "conflict"
        winner = winners[0]
        name = str(winner.get("name") or "").upper()
        index_set = winner.get("indexSet")
        if isinstance(resolution, dict) and any(
            resolution.get(field) != winner.get(field)
            for field in ("name", "indexSet", "onChainId")
        ):
            return None, None, "conflict"
        if name == "DRAW" and not isinstance(resolution, dict):
            return None, None, "pending"
        if name in ("UP", "DOWN") and index_set != {"UP": 1, "DOWN": 2}[name]:
            return None, None, "conflict"
        if any(item.get("status") not in ("WON", "LOST") for item in outcomes):
            return None, None, "pending"

        if name not in VALID_OUTCOMES:
            return None, None, "conflict"
        mapped = name

        evidence = {
            "resolution_name": name,
            "index_set": index_set,
            "outcomes": [
                {
                    "name": outcome.get("name"),
                    "indexSet": outcome.get("indexSet"),
                    "status": outcome.get("status"),
                }
                for outcome in outcomes
                if isinstance(outcome, dict)
            ],
            "resolution_present": isinstance(resolution, dict),
        }
        return mapped, evidence, "resolved"


# ---------------------------------------------------------------------------
# Binance klines
# ---------------------------------------------------------------------------


class BinanceKlineTransformer(BaseTransformer):
    """Binance 1s CSV 行 → 规范秒线记录（SPEC §5.3 全 12 列）。"""

    async def transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """映射一批 CSV 行。

        Raises:
            TransformError: ``INVALID_CSV``。
        """
        return [self.transform_one(record) for record in records]

    def transform_one(self, record: dict[str, Any]) -> dict[str, Any]:
        """映射单行 CSV（12 列 + 行号）。

        Raises:
            TransformError: ``INVALID_CSV`` — 列数 / 时间 / 价格不合法。
        """
        cols = record.get("cols")
        row_number = int(record.get("row_number") or 0)
        if not isinstance(cols, list) or len(cols) != 12:
            raise TransformError("INVALID_CSV", f"row {row_number}: columns")

        open_time_us = _parse_epoch_us(cols[0])
        open_price = parse_decimal(cols[1], field="open")
        high = parse_decimal(cols[2], field="high")
        low = parse_decimal(cols[3], field="low")
        close = parse_decimal(cols[4], field="close")
        volume = parse_decimal(cols[5], field="volume")
        close_time_us = _parse_epoch_us(cols[6])
        quote_volume = parse_decimal(cols[7], field="quote_volume")
        number_of_trades = int(cols[8])
        taker_buy_base = parse_decimal(cols[9], field="taker_buy_base")
        taker_buy_quote = parse_decimal(cols[10], field="taker_buy_quote")

        if open_time_us % MICROS_PER_SECOND != 0:
            raise TransformError("INVALID_CSV", f"row {row_number}: not a second")
        close_exclusive_us = open_time_us + MICROS_PER_SECOND
        if close_time_us != close_exclusive_us - 1:
            raise TransformError("INVALID_CSV", f"row {row_number}: close_time")

        for name, value in (
            ("open", open_price),
            ("high", high),
            ("low", low),
            ("close", close),
        ):
            if value <= 0:
                raise TransformError("INVALID_CSV", f"row {row_number}: {name}")
        if high < low:
            raise TransformError("INVALID_CSV", f"row {row_number}: high<low")
        if not (low <= min(open_price, close) <= max(open_price, close) <= high):
            raise TransformError("INVALID_CSV", f"row {row_number}: ohlc order")
        for name, value in (
            ("volume", volume),
            ("quote_volume", quote_volume),
            ("taker_buy_base", taker_buy_base),
            ("taker_buy_quote", taker_buy_quote),
        ):
            if value < 0:
                raise TransformError("INVALID_CSV", f"row {row_number}: {name}")
        if number_of_trades < 0:
            raise TransformError("INVALID_CSV", f"row {row_number}: trades")

        return {
            "schema_version": 1,
            "source": SOURCE_KLINES,
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "interval": "1s",
            "open_time_us": open_time_us,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "close_time_us": close_time_us,
            "close_exclusive_us": close_exclusive_us,
            "quote_volume": quote_volume,
            "number_of_trades": number_of_trades,
            "taker_buy_base_volume": taker_buy_base,
            "taker_buy_quote_volume": taker_buy_quote,
            "ignore": cols[11],
            "source_timestamp_unit": "us",
            "source_row": row_number,
        }


def _parse_epoch_us(token: str) -> int:
    """把官方 epoch token（us）解析成 int64 微秒（不经 float）。"""
    try:
        return int(token.strip())
    except (TypeError, ValueError) as exc:
        raise TransformError("INVALID_CSV", f"bad timestamp {token!r}") from exc


__all__ = [
    "MICROS_PER_SECOND",
    "ROUND_DURATION_SECONDS",
    "VALID_OUTCOMES",
    "BinanceKlineTransformer",
    "PredictRoundTransformer",
    "TransformError",
    "ceil_ms_to_us",
    "datetime_to_us",
    "parse_decimal",
    "parse_utc_datetime",
]
