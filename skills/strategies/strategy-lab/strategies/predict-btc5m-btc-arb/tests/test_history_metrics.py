"""Deterministic statistics tests against controller-owned independent references."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

LAB = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("history_metrics", LAB/"history_metrics.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)
REFERENCE = LAB.parents[4]/"data/reports/2026-11-12-btc5m-native-history-research/evidence/reference/metric-reference.json"


def reference_rows():
    reference = json.loads(REFERENCE.read_text())
    rows = [dict(partition="OOS", day=row["day"], offset=30, p_up=float(row["p"]),
                 label=row["label"], spot=float(row["spot"]), strike=float(row["strike"]),
                 sigma=0.00005, reason="valued") for row in reference["rows"]]
    return reference, rows


def test_fixed_independent_metrics_and_bootstrap():
    reference, rows = reference_rows()
    comparison, calibration, daily, monthly = metrics.aggregate(rows, {"OOS": ["2026-10-10", "2026-10-11"]})
    result = comparison[0]
    for key, expected in reference["float_numpy"].items():
        assert result[key] == pytest.approx(expected, rel=1e-12, abs=1e-12)
    for key, expected in reference["dayblock95"].items():
        name = {"accuracy":"direction_accuracy", "brier":"binary_brier", "logloss":"binary_logloss"}[key]
        assert [result[name+"_lo95"], result[name+"_hi95"]] == pytest.approx(expected)
    assert result["total"] == 5
    assert result["binary"] == 4
    assert result["draw"] == 1
    assert result["abstain"] == 1
    assert sum(row["count"] for row in calibration) == 4
    assert len(daily) == 12
    assert len(monthly) == 6


def test_zero_denominators_and_draw_are_not_binary():
    comparison, _, _, _ = metrics.aggregate([], {"IS":["2026-08-10"]})
    assert all(row["binary_brier"] is None for row in comparison)
    row = dict(p_up=0.5, sigma=0.00005, spot=100., strike=100., label="DRAW")
    stats = metrics.contributions(row)
    assert stats["binary"] == 0 and stats["scored"] == 1
    assert stats["payout_sum"] == 0


def test_extreme_probabilities_clipped_only_for_logloss():
    stats = metrics.contributions(dict(p_up=0., label="UP", sigma=0.00005, spot=99., strike=100.))
    assert stats["brier_sum"] == 1
    assert np.isfinite(stats["logloss_sum"])
    assert stats["logloss_sum"] > 27
    with pytest.raises(ValueError):
        metrics.contributions(dict(p_up=float("nan")))


def test_weighted_day_blocks_not_mean_daily_rates():
    _, rows = reference_rows()
    rows.extend([rows[0]] * 10)
    comparison, _, _, _ = metrics.aggregate(rows, {"OOS":["2026-10-10", "2026-10-11"]})
    assert comparison[0]["binary_brier"] == pytest.approx((.82+10*.04)/14)
