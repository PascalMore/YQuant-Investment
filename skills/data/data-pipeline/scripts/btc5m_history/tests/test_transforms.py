"""BTC5m 历史 transform 测试 — 03-018 UT06–UT08 / UT11。

fixture 明确标注：**官方 schema 构造的 synthetic fixture**（不是真实样本）。
"""

from __future__ import annotations

import importlib
import json
from decimal import Decimal

import pytest

# Directory name contains a hyphen (``data-pipeline``) so the module must be
# loaded through importlib with the real package path (Design 3.3). We do
# NOT inject a flat ``scripts/`` path into sys.path.
_transforms = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.transforms"
)
BinanceKlineTransformer = _transforms.BinanceKlineTransformer
PredictRoundTransformer = _transforms.PredictRoundTransformer
TransformError = _transforms.TransformError
parse_decimal = _transforms.parse_decimal
parse_utc_datetime = _transforms.parse_utc_datetime


def _round_envelope(
    *,
    starts_at: str = "2026-08-10T00:00:00Z",
    ends_at: str = "2026-08-10T00:05:00Z",
    series_slug: str = "btc-updown-5m",
    round_id: int = 4450895,
    market_status: str = "RESOLVED",
    trading_status: str = "RESOLVED",
    variant_details: dict | None = None,
    market_variant_details: dict | None = None,
    outcomes: list | None = None,
    feed_symbol: str = "BTCUSDT",
) -> dict:
    """构造官方 schema 的 synthetic round envelope（不是真实样本）。"""
    details = variant_details
    if details is None:
        details = {
            "startPrice": "100.5",
            "endPrice": "101.5",
            "priceFeedProvider": "CHAINLINK",
            "priceFeedSymbol": feed_symbol,
        }
    market = {
        "id": "4450895",
        "conditionId": "0xabc",
        "seriesSlug": series_slug,
        "status": market_status,
        "tradingStatus": trading_status,
        "outcomes": outcomes
        if outcomes is not None
        else [
            {"name": "Up", "indexSet": 1, "status": "WON"},
            {"name": "Down", "indexSet": 2, "status": "LOST"},
        ],
    }
    if market_variant_details is not None:
        market["variantDetails"] = market_variant_details
    winners = [item for item in market["outcomes"] if item.get("status") == "WON"]
    if len(winners) == 1:
        market["resolution"] = dict(winners[0])
    return {
        "_status_logs": {"4450895": [{
            "status": "RESOLVED", "timestamp": "2026-08-10T00:06:00Z",
            "transactionHash": "synthetic-final-transition", "logIndex": 1,
            "resolutionProvider": "synthetic-schema-fixture",
        }]},
        "category": {
            "id": round_id,
            "slug": "btc-updown-5m-2026-08-10-00-00",
            "seriesSlug": series_slug,
            "status": "RESOLVED",
            "publishedAt": "2026-08-09T23:59:00Z",
            "startsAt": starts_at,
            "endsAt": ends_at,
            "variantDetails": details,
        },
        "markets": [market],
    }


@pytest.fixture()
def transformer() -> PredictRoundTransformer:
    return PredictRoundTransformer()


# ---------------------------------------------------------------------------
# UT06 — 只有合格 RESOLVED 才出标签
# ---------------------------------------------------------------------------


def test_ut06_resolved_round_produces_label(transformer: PredictRoundTransformer) -> None:
    record = transformer.transform_one(_round_envelope())
    assert record["settlement_state"] == "resolved"
    assert record["official_outcome"] == "UP"
    assert record["ends_at_us"] - record["starts_at_us"] == 300_000_000


def test_ut06_ended_but_open_is_pending(transformer: PredictRoundTransformer) -> None:
    record = transformer.transform_one(
        _round_envelope(market_status="OPEN", trading_status="OPEN")
    )
    assert record["settlement_state"] == "pending"
    assert record["official_outcome"] is None


def test_ut06_price_proposed_is_pending(transformer: PredictRoundTransformer) -> None:
    record = transformer.transform_one(
        _round_envelope(market_status="RESOLVED", trading_status="PRICE_PROPOSED")
    )
    assert record["settlement_state"] == "pending"
    assert record["official_outcome"] is None


def test_ut06_removed_is_unavailable(transformer: PredictRoundTransformer) -> None:
    record = transformer.transform_one(
        _round_envelope(market_status="REMOVED", trading_status="REMOVED")
    )
    assert record["settlement_state"] == "unavailable"


def test_ut06_multiple_winners_is_conflict(transformer: PredictRoundTransformer) -> None:
    record = transformer.transform_one(
        _round_envelope(
            outcomes=[
                {"name": "Up", "indexSet": 1, "status": "WON"},
                {"name": "Down", "indexSet": 2, "status": "WON"},
            ]
        )
    )
    assert record["settlement_state"] == "conflict"
    assert record["official_outcome"] is None


def test_ut06_draw_requires_explicit_official_name(
    transformer: PredictRoundTransformer,
) -> None:
    record = transformer.transform_one(
        _round_envelope(
            outcomes=[
                {"name": "Draw", "indexSet": 3, "status": "WON"},
            ]
        )
    )
    assert record["settlement_state"] == "resolved"
    assert record["official_outcome"] == "DRAW"


def test_ut06_final_log_must_belong_to_the_same_market(transformer) -> None:
    envelope = _round_envelope()
    envelope["_status_logs"]["other-market"] = envelope["_status_logs"].pop("4450895")
    record = transformer.transform_one(envelope)
    assert record["settlement_state"] == "pending"
    assert record["official_outcome"] is None
    assert record["resolved_at_us"] is None


def test_ut06_conflicting_final_transitions_are_not_guessed(transformer) -> None:
    envelope = _round_envelope()
    logs = envelope["_status_logs"]["4450895"]
    logs.append(dict(logs[0], timestamp="2026-08-10T00:07:00Z"))
    record = transformer.transform_one(envelope)
    assert record["settlement_state"] == "conflict"
    assert record["official_outcome"] is None


def test_ut06_draw_without_resolution_is_not_a_final_label(transformer) -> None:
    envelope = _round_envelope(outcomes=[{"name": "Draw", "indexSet": 3, "status": "WON"}])
    del envelope["markets"][0]["resolution"]
    assert transformer.transform_one(envelope)["settlement_state"] == "pending"


# ---------------------------------------------------------------------------
# UT07 — 身份不符 / variant 矛盾
# ---------------------------------------------------------------------------


def test_ut07_wrong_series_is_rejected(transformer: PredictRoundTransformer) -> None:
    with pytest.raises(TransformError) as excinfo:
        transformer.transform_one(_round_envelope(series_slug="btc-updown-15m"))
    assert excinfo.value.code == "INVALID_IDENTITY"


def test_ut07_wrong_duration_is_rejected(transformer: PredictRoundTransformer) -> None:
    with pytest.raises(TransformError) as excinfo:
        transformer.transform_one(
            _round_envelope(ends_at="2026-08-10T00:15:00Z")
        )
    assert excinfo.value.code == "INVALID_IDENTITY"


def test_ut07_wrong_feed_symbol_is_rejected(transformer: PredictRoundTransformer) -> None:
    with pytest.raises(TransformError) as excinfo:
        transformer.transform_one(_round_envelope(feed_symbol="ETHUSDT"))
    assert excinfo.value.code == "INVALID_IDENTITY"


def test_ut07_multiple_market_candidates_are_rejected(
    transformer: PredictRoundTransformer,
) -> None:
    envelope = _round_envelope()
    envelope["markets"].append(dict(envelope["markets"][0]))
    with pytest.raises(TransformError) as excinfo:
        transformer.transform_one(envelope)
    assert excinfo.value.code == "INVALID_IDENTITY"


def test_ut07_variant_conflict_is_not_masked_by_priority(
    transformer: PredictRoundTransformer,
) -> None:
    with pytest.raises(TransformError) as excinfo:
        transformer.transform_one(
            _round_envelope(
                market_variant_details={
                    "startPrice": "999.0",
                    "priceFeedProvider": "CHAINLINK",
                    "priceFeedSymbol": "BTCUSDT",
                }
            )
        )
    assert excinfo.value.code == "VARIANT_CONFLICT"


# Fix1 F1–F3: synthetic schema regression cases (not real API samples).
_VARIANT_SOURCES = (
    ("category", "variantDetails", None),
    ("category", "variantDetails", "upDown"),
    ("category", "variantDetails", "crypto"),
    ("category", "variantData", None),
    ("market", "variantDetails", None),
    ("market", "variantDetails", "upDown"),
    ("market", "variantDetails", "crypto"),
    ("market", "variantData", None),
)


def _set_variant_source(envelope: dict, source: tuple, values: dict) -> None:
    """Set one synthetic category/selected-market variant source."""
    owner, field, nested = source
    target = envelope["category"] if owner == "category" else envelope["markets"][0]
    if nested is None:
        target[field] = values
    else:
        target.setdefault(field, {})[nested] = values


@pytest.mark.parametrize("source", _VARIANT_SOURCES)
def test_fix1_f1_each_variant_source_preserves_prices_and_feed(transformer, source) -> None:
    envelope = _round_envelope()
    values = envelope["category"].pop("variantDetails")
    values["startPrice"] = "1234567890123456789.123456789"
    _set_variant_source(envelope, source, values)
    record = transformer.transform_one(envelope)
    assert record["start_price"] == Decimal(values["startPrice"])
    assert str(record["start_price"]) == values["startPrice"]
    assert record["end_price"] == Decimal("101.5")
    assert record["price_feed_provider"] == "CHAINLINK"
    assert record["price_feed_symbol"] == "BTCUSDT"


@pytest.mark.parametrize("source", _VARIANT_SOURCES[1:])
@pytest.mark.parametrize("field,value", [
    ("startPrice", "999.5"),
    ("endPrice", "999.5"),
    ("priceFeedProvider", "OTHER"),
    ("priceFeedSymbol", "ETHUSDT"),
])
def test_fix1_f1_conflicting_source_stops_before_load(
    transformer, source, field, value,
) -> None:
    envelope = _round_envelope()
    _set_variant_source(envelope, source, {field: value})
    loaded = []
    with pytest.raises(TransformError) as excinfo:
        loaded.append(transformer.transform_one(envelope))
    assert excinfo.value.code == "VARIANT_CONFLICT"
    assert loaded == []


def test_fix1_f1_equivalent_decimal_tokens_and_empty_fields_agree(transformer) -> None:
    envelope = _round_envelope()
    envelope["category"]["variantDetails"]["upDown"] = {
        "startPrice": Decimal("100.500"), "endPrice": None, "priceFeedSymbol": "",
    }
    envelope["markets"][0]["variantData"] = {"endPrice": "101.5000"}
    record = transformer.transform_one(envelope)
    assert record["start_price"] == Decimal("100.5")
    assert record["end_price"] == Decimal("101.5")
    assert record["price_feed_symbol"] == "BTCUSDT"


@pytest.mark.parametrize("bad_id", [
    True, False, 12.75, -1, "12.75", "+12", "-12", " 12", "12 ",
    "1_2", "1e2", "１２", "١٢", "", None,
])
def test_fix1_f2_invalid_category_id_is_not_repaired(transformer, bad_id) -> None:
    envelope = _round_envelope()
    envelope["category"]["id"] = bad_id
    loaded = []
    with pytest.raises(TransformError) as excinfo:
        loaded.append(transformer.transform_one(envelope))
    assert excinfo.value.code == "INVALID_SCHEMA"
    assert loaded == []


@pytest.mark.parametrize("token", ["12.75", "12.0001", "1e-1"])
def test_fix1_f2_json_decimal_id_is_rejected(transformer, token) -> None:
    envelope = _round_envelope()
    envelope["category"]["id"] = json.loads(token, parse_float=Decimal)
    assert isinstance(envelope["category"]["id"], Decimal)
    with pytest.raises(TransformError) as excinfo:
        transformer.transform_one(envelope)
    assert excinfo.value.code == "INVALID_SCHEMA"


@pytest.mark.parametrize("round_id", [4450895, 123456789012345678901234567890,
                                      "123456789012345678901234567890", "0012"])
def test_fix1_f2_exact_category_id_is_independent_of_market(transformer, round_id) -> None:
    envelope = _round_envelope()
    envelope["category"]["id"] = round_id
    record = transformer.transform_one(envelope)
    assert record["round_id"] == str(round_id)
    assert record["market_id"] == "4450895"
    assert record["condition_id"] == "0xabc"


@pytest.mark.parametrize("name", ["NOT_AN_OFFICIAL_DIRECTION", "", "YES"])
@pytest.mark.parametrize("index_set", [1, 2, 3])
def test_fix1_f3_unknown_name_cannot_use_index_as_direction(
    transformer, name, index_set,
) -> None:
    envelope = _round_envelope(outcomes=[
        {"name": name, "indexSet": index_set, "status": "WON"},
    ])
    record = transformer.transform_one(envelope)
    assert record["settlement_state"] == "conflict"
    assert record["official_outcome"] is None
    assert record["resolved_at_us"] is None
    assert record["resolution_evidence"] is None


@pytest.mark.parametrize("name,index_set", [("Up", 1), ("Down", 2), ("Draw", 3)])
def test_fix1_f3_explicit_official_direction_remains_resolved(
    transformer, name, index_set,
) -> None:
    envelope = _round_envelope(outcomes=[
        {"name": name, "indexSet": index_set, "status": "WON"},
    ])
    record = transformer.transform_one(envelope)
    assert record["settlement_state"] == "resolved"
    assert record["official_outcome"] == name.upper()
    assert record["resolved_at_us"] is not None


# ---------------------------------------------------------------------------
# UT08 — Decimal 精度 / 微秒 / close+1
# ---------------------------------------------------------------------------


def test_ut08_decimal_token_keeps_precision() -> None:
    value = parse_decimal("1234567890123456789.123456789", field="px")
    assert isinstance(value, Decimal)
    assert str(value) == "1234567890123456789.123456789"


def test_ut08_float_input_is_rejected() -> None:
    with pytest.raises(TransformError) as excinfo:
        parse_decimal(1.5, field="px")
    assert excinfo.value.code == "INVALID_DECIMAL"


def test_ut08_microsecond_precision_is_preserved() -> None:
    parsed = parse_utc_datetime("2026-08-10T00:00:00.123456Z")
    assert parsed.microsecond == 123456


def test_ut08_close_exclusive_is_open_plus_one_second() -> None:
    _parse_epoch_us = _transforms._parse_epoch_us
    transformer = BinanceKlineTransformer()
    row = {
        "cols": [
            "1786320000000000",
            "100.1",
            "100.2",
            "100.0",
            "100.15",
            "1.5",
            "1786320000999999",
            "150.0",
            "12",
            "0.75",
            "75.0",
            "0",
        ],
        "row_number": 1,
    }
    record = transformer.transform_one(row)
    assert record["open_time_us"] == 1786320000000000
    assert record["close_exclusive_us"] == 1786320001000000
    assert record["close_time_us"] == 1786320000999999
    assert _parse_epoch_us("1786320000000000") == 1786320000000000


def test_ut08_invalid_close_time_is_rejected() -> None:
    transformer = BinanceKlineTransformer()
    row = {
        "cols": [
            "1786320000000000",
            "100.1",
            "100.2",
            "100.0",
            "100.15",
            "1.5",
            "1786320000000000",
            "150.0",
            "12",
            "0.75",
            "75.0",
            "0",
        ],
        "row_number": 1,
    }
    with pytest.raises(TransformError) as excinfo:
        transformer.transform_one(row)
    assert excinfo.value.code == "INVALID_CSV"


def test_ut08_json_number_token_goes_directly_to_decimal() -> None:
    payload = json.loads('{"startPrice": 0.1}', parse_float=Decimal)
    assert isinstance(payload["startPrice"], Decimal)
    assert str(payload["startPrice"]) == "0.1"
    # 官方 API 以字符串给出价格；字符串 token 保持原样由 transform 解析。
    text_payload = json.loads('{"startPrice": "0.1"}', parse_float=Decimal)
    assert text_payload["startPrice"] == "0.1"


# Public field excerpts, not full archive bytes; no ignored-file dependency.
# First four: 148a34e4...c.json; last: dbfb5d6f...7f.json (triage report).
# Prices retain the original JSON decimal token precision as text.
_FLAT_EXCERPTS = [
    (297861, 1295388, "1786447500", "11:25", "64340.325",
     "0xb62fe56d382712e484035a32eb5ffdcecdbba478a3e333c159df021fa1869464",
     "110867910736369178262675751800439436718869201403196191283369802518005352479460",
     "8267265843756085282480773948220970374110764100433046093436655273944931337594"),
    (297246, 1290102, "1786426800", "05:40", "64035.995",
     "0xc0e1c861b284e4d273e04c1c24ee6d0de928702eacbba659a1663ed4107eb8e2",
     "43773745198378273932618847847227693270929049190536776490927936073705030546420",
     "63884571076952760892099288992539118799170142341827026374552993149783325993881"),
    (297164, 1289231, "1786423200", "04:40", "64100.345",
     "0x4e9ff1329649e8e8d0e17b6ffe42f3a06cb33ef7f4a83a92c63a2a60256fb956",
     "22611383852911011383350635375349353197240979367177346201942643011136445305907",
     "75394276860384849776125542673582366560140504663886812440321333522567476360015"),
    (297160, 1289207, "1786422900", "04:35", "64100.345",
     "0x979e73b354eb5e8b0ace06efc87233ab07315acf763b0964a51c345888b9adb5",
     "51604532393491743330775296054962449947332997997933199920933687377889423383036",
     "24207628976329604520951859397161963430834866432854315349064288532716695683198"),
    (296915, 1287648, "1786416600", "02:50", "64041.555",
     "0x419ab343fbc7c202712ae1df0d35953ecd9d5586a7bcbd849b0fb224143f8587",
     "80692530305957933530175418182502052451174110569769011029430052596821659995704",
     "33255813648551975281569206058049589420282409660295358345829821742715697882975"),
]
_FLAT_RULE = "If the two prices are exactly equal, the market will resolve 50-50."


def _official_flat_excerpt(index=0, *, with_synthetic_log=True):
    """Actual public identity/price/rule excerpt plus explicitly synthetic log.

    No final status-log evidence for these five is claimed to have been captured.
    """
    import copy
    from datetime import datetime, timedelta

    round_id, market_id, slug_time, clock, price, condition, up_id, down_id = _FLAT_EXCERPTS[index]
    start = datetime.fromisoformat("2026-08-11T" + clock + ":00")
    end = start + timedelta(minutes=5)
    outcomes = [{"name": name, "indexSet": number, "status": "WON", "onChainId": token}
                for name, number, token in (("Up", 1, up_id), ("Down", 2, down_id))]
    details = {"startPrice": price, "endPrice": price, "priceFeedProvider": "CHAINLINK",
               "priceFeedSymbol": "BTCUSDT"}
    envelope = {"category": {
        "id": round_id, "slug": "btc-updown-5m-" + slug_time, "seriesSlug": "btc-updown-5m",
        "status": "RESOLVED", "startsAt": start.isoformat() + "Z", "endsAt": end.isoformat() + "Z",
        "variantDetails": {"upDown": dict(details), "crypto": dict(details)},
    }, "markets": [{
        "id": market_id, "conditionId": condition, "seriesSlug": "btc-updown-5m",
        "status": "RESOLVED", "tradingStatus": "CLOSED", "description": _FLAT_RULE,
        "outcomes": outcomes, "resolution": copy.deepcopy(outcomes[0]), "variantData": dict(details),
    }]}
    if with_synthetic_log:
        envelope["_status_logs"] = {str(market_id): [{
            "status": "RESOLVED", "timestamp": (end + timedelta(minutes=1)).isoformat() + "Z",
            "transactionHash": "synthetic-flat-final-transition-not-captured", "logIndex": 1,
        }]}
    return envelope


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("with_log", [False, True])
def test_official_flat_five_excerpts_require_final_log(index, with_log):
    import copy

    envelope = _official_flat_excerpt(index, with_synthetic_log=with_log)
    before = copy.deepcopy(envelope)
    record = PredictRoundTransformer().transform_one(envelope)
    assert envelope == before
    assert record["start_price"] == record["end_price"] == Decimal(_FLAT_EXCERPTS[index][4])
    assert record["settlement_state"] == ("resolved" if with_log else "pending")
    assert record["official_outcome"] == ("DRAW" if with_log else None)
    if with_log:
        evidence = record["resolution_evidence"]
        assert evidence["settlement_rule"] == "official-flat-50-50"
        assert evidence["rule_text"] == _FLAT_RULE
        assert evidence["rule_source"] == "market.description"
        assert evidence["original_resolution"] == envelope["markets"][0]["resolution"]
        assert evidence["outcomes"] == envelope["markets"][0]["outcomes"]
        assert evidence["payout_basis"] == "equal-split-by-market-rule-not-onchain-vector"
        assert record["resolved_at_us"] is not None


@pytest.mark.parametrize("fault", [
    "unequal", "epsilon", "no_rule", "category_rule_only", "negated_rule", "not_terminal",
    "no_log", "wrong_log_market", "two_logs", "bad_log_time", "third", "duplicate",
    "index", "bool_index", "unknown", "resolution_id", "resolution_index", "resolution_name",
    "duplicate_token", "zero", "nan", "float", "variant", "wrong_series", "wrong_duration",
])
def test_official_flat_joint_evidence_negative(fault):
    import copy

    envelope = _official_flat_excerpt()
    market, category = envelope["markets"][0], envelope["category"]
    if fault in ("unequal", "epsilon", "zero", "nan", "float"):
        price = {"unequal": "999", "epsilon": "64340.325000000000000000001",
                 "zero": "0", "nan": "NaN", "float": 64340.325}[fault]
        for details in (category["variantDetails"]["upDown"], category["variantDetails"]["crypto"],
                        market["variantData"]):
            details["endPrice"] = price
    elif fault in ("no_rule", "category_rule_only", "negated_rule"):
        category["description"] = _FLAT_RULE
        market["description"] = "Not true: " + _FLAT_RULE if fault == "negated_rule" else "50-50"
    elif fault == "not_terminal":
        market["status"] = "ENDED"
    elif fault == "no_log":
        envelope.pop("_status_logs")
    elif fault == "wrong_log_market":
        envelope["_status_logs"] = {"other": next(iter(envelope["_status_logs"].values()))}
    elif fault in ("two_logs", "bad_log_time"):
        logs = envelope["_status_logs"][str(market["id"])]
        if fault == "two_logs":
            logs.append(dict(logs[0], transactionHash="another-final-transition"))
        else:
            logs[0]["timestamp"] = "bad timestamp"
    elif fault in ("third", "duplicate"):
        market["outcomes"].append(dict(market["outcomes"][0], name="Other") if fault == "third"
                                  else copy.deepcopy(market["outcomes"][0]))
    elif fault in ("index", "bool_index", "unknown", "duplicate_token"):
        field = {"index": "indexSet", "bool_index": "indexSet", "unknown": "name",
                 "duplicate_token": "onChainId"}[fault]
        market["outcomes"][1][field] = {"index": 1, "bool_index": True, "unknown": "Other",
                                       "duplicate_token": market["outcomes"][0]["onChainId"]}[fault]
    elif fault.startswith("resolution_"):
        field = {"resolution_id": "onChainId", "resolution_index": "indexSet",
                 "resolution_name": "name"}[fault]
        market["resolution"][field] = "wrong"
    elif fault == "variant":
        category["variantDetails"]["crypto"]["startPrice"] = "1"
    elif fault == "wrong_series":
        category["seriesSlug"] = "eth-updown-5m"
    else:
        category["endsAt"] = category["startsAt"]
    try:
        record = PredictRoundTransformer().transform_one(envelope)
    except TransformError:
        return
    assert record["settlement_state"] != "resolved"
    assert record["official_outcome"] is None


@pytest.mark.parametrize("mode", ["down_resolution", "no_resolution", "whitespace_case", "reversed"])
def test_official_flat_supported_wire_variants(mode):
    import copy

    envelope = _official_flat_excerpt()
    market = envelope["markets"][0]
    if mode == "down_resolution":
        market["resolution"] = copy.deepcopy(market["outcomes"][1])
    elif mode == "no_resolution":
        market.pop("resolution")
    elif mode == "whitespace_case":
        market["description"] = "Earlier sentence.\n\n" + _FLAT_RULE.upper().replace(" ", "\t \n")
    else:
        market["outcomes"].reverse()
    result = PredictRoundTransformer().transform_one(envelope)
    assert (result["settlement_state"], result["official_outcome"]) == ("resolved", "DRAW")
    assert result["resolution_evidence"]["original_resolution"] == market.get("resolution")


@pytest.mark.parametrize("fault", ["early_log", "no_log_time", "trading_open", "category_open", "resolution_bool"])
def test_official_flat_terminal_proof_is_not_relaxed(fault):
    envelope = _official_flat_excerpt()
    market = envelope["markets"][0]
    if fault in ("early_log", "no_log_time"):
        envelope["_status_logs"][str(market["id"])][0]["timestamp"] = (
            envelope["category"]["startsAt"] if fault == "early_log" else None)
    elif fault == "trading_open":
        market["tradingStatus"] = "OPEN"
    elif fault == "category_open":
        envelope["category"]["status"] = "OPEN"
    else:
        market["resolution"]["indexSet"] = True
    result = PredictRoundTransformer().transform_one(envelope)
    assert result["official_outcome"] is None
    assert result["settlement_state"] != "resolved"

