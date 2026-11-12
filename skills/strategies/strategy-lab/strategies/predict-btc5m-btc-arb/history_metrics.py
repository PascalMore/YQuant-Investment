"""Official-label statistics only; no pricing, volatility or trading model."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

import numpy as np

OFFSETS = (30, 60, 120, 180, 240, 270)
RATIOS = {
    "direction_accuracy": ("correct", "directed"),
    "binary_brier": ("brier_sum", "binary"),
    "binary_logloss": ("logloss_sum", "binary"),
    "payout_brier": ("payout_sum", "scored"),
    "base05_binary_brier": ("base_brier_sum", "binary"),
    "base05_binary_logloss": ("base_logloss_sum", "binary"),
    "base05_payout_brier": ("base_payout_sum", "scored"),
    "brier_delta_vs05": ("brier_delta_sum", "binary"),
    "common_model_accuracy": ("common_correct", "common_directed"),
    "common_instant_accuracy": ("instant_correct", "common_directed"),
    "instant_accuracy": ("instant_all_correct", "instant_directed"),
    "sigma_floor_ratio": ("sigma_floor", "valued"),
    "basis_mean_bps": ("basis_sum", "basis_count"),
    "basis_abs_mean_bps": ("basis_abs_sum", "basis_count"),
}
COUNTS = ("total", "valued", "scored", "binary", "draw", "missing_label", "unvalued",
          "warmup", "abstain", "directed", "correct", "instant_directed",
          "instant_all_correct", "common_directed", "common_correct", "instant_correct",
          "sigma_floor", "basis_count")
SUMS = tuple(dict.fromkeys(key for pair in RATIOS.values() for key in pair if key not in COUNTS))
DAILY_COLUMNS = ("partition", "day", "offset", *COUNTS, *SUMS, *RATIOS)
COMPARISON_COLUMNS = ("partition", "offset", *COUNTS, *RATIOS,
                      *(f"{key}_{bound}" for key in ("direction_accuracy", "binary_brier",
                         "binary_logloss", "brier_delta_vs05") for bound in ("lo95", "hi95")))
CALIBRATION_COLUMNS = ("partition", "offset", "bin", "lower", "upper", "count", "mean_p", "up_rate")


def direction(value: float) -> int:
    """Return UP=1, DOWN=-1, abstain=0 for a signed difference."""
    return int(value > 0) - int(value < 0)


def contributions(row: dict[str, Any]) -> dict[str, float]:
    """Return additive sufficient statistics, separating binary and DRAW payout."""
    out = dict.fromkeys((*COUNTS, *SUMS), 0.0)
    out["total"] = 1
    probability = row.get("p_up")
    if probability is None:
        out["unvalued"] = 1
        out["warmup"] = int(row.get("reason") == "warmup")
        return out
    probability = float(probability)
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("probability outside [0,1]")
    out["valued"] = 1
    out["sigma_floor"] = int(row["sigma"] == 0.00005)
    if row.get("spot") is not None and row.get("strike") is not None:
        basis = (row["spot"] / row["strike"] - 1) * 10000
        out.update(basis_count=1, basis_sum=basis, basis_abs_sum=abs(basis))
    label = row.get("label")
    if label not in ("UP", "DOWN", "DRAW"):
        out["missing_label"] = 1
        return out
    out["scored"] = 1
    payout = {"UP": 1, "DOWN": 0, "DRAW": 0.5}[label]
    out["payout_sum"] = (probability - payout) ** 2
    out["base_payout_sum"] = (0.5 - payout) ** 2
    if label == "DRAW":
        out["draw"] = 1
        return out
    out["binary"] = 1
    out["brier_sum"] = (probability - payout) ** 2
    out["base_brier_sum"] = 0.25
    out["brier_delta_sum"] = out["brier_sum"] - 0.25
    clipped = min(1 - 1e-12, max(1e-12, probability))
    out["logloss_sum"] = -math.log(clipped if payout else 1 - clipped)
    out["base_logloss_sum"] = math.log(2)
    predicted = direction(probability - 0.5)
    actual = 1 if label == "UP" else -1
    instant = direction(row["spot"] - row["strike"])
    out["abstain"] = int(predicted == 0)
    out["directed"] = int(predicted != 0)
    out["correct"] = int(predicted == actual)
    out["instant_directed"] = int(instant != 0)
    out["instant_all_correct"] = int(instant == actual)
    if predicted and instant:
        out["common_directed"] = 1
        out["common_correct"] = int(predicted == actual)
        out["instant_correct"] = int(instant == actual)
    return out


def ratios(totals: dict[str, Any]) -> dict[str, float | None]:
    """Compute weighted rates from additive numerators and denominators."""
    return {key: totals[num] / totals[den] if totals[den] else None
            for key, (num, den) in RATIOS.items()}


def aggregate(rows: Iterable[dict[str, Any]], days: dict[str, list[str]]) -> tuple[list, list, list, list]:
    """Aggregate daily/monthly stability and shared-index UTC-day bootstrap CIs."""
    daily = {}
    bins = defaultdict(lambda: [0, 0.0, 0.0])
    for partition, dates in days.items():
        for day in dates:
            for offset in OFFSETS:
                daily[partition, day, offset] = dict.fromkeys((*COUNTS, *SUMS), 0.0)
    for row in rows:
        key = (row["partition"], row["day"], row["offset"])
        stats = contributions(row)
        for name, number in stats.items():
            daily[key][name] += number
        if stats["binary"]:
            probability = row["p_up"]
            cell = bins[row["partition"], row["offset"], min(9, int(10 * probability))]
            cell[0] += 1
            cell[1] += probability
            cell[2] += int(row["label"] == "UP")
    daily_rows = [{"partition": part, "day": day, "offset": offset, **totals, **ratios(totals)}
                  for (part, day, offset), totals in sorted(daily.items())]
    comparison = []
    for partition, dates in days.items():
        if not dates:
            continue
        indices = np.random.Generator(np.random.PCG64(42)).integers(
            0, len(dates), size=(1000, len(dates)), dtype=np.int64)
        for offset in OFFSETS:
            blocks = [daily[partition, day, offset] for day in sorted(dates)]
            totals = {key: math.fsum(block[key] for block in blocks) for key in (*COUNTS, *SUMS)}
            result = {"partition": partition, "offset": offset, **totals, **ratios(totals)}
            for key in ("direction_accuracy", "binary_brier", "binary_logloss", "brier_delta_vs05"):
                num, den = RATIOS[key]
                numerators = np.array([block[num] for block in blocks])[indices].sum(axis=1)
                denominators = np.array([block[den] for block in blocks])[indices].sum(axis=1)
                valid = denominators > 0
                interval = np.quantile(numerators[valid] / denominators[valid], [0.025, 0.975],
                                       method="linear") if valid.any() else (None, None)
                result[f"{key}_lo95"], result[f"{key}_hi95"] = interval
            comparison.append(result)
    calibration = []
    for partition in days:
        for offset in OFFSETS:
            for index in range(10):
                count, probability, target = bins[partition, offset, index]
                calibration.append(dict(partition=partition, offset=offset, bin=index,
                    lower=index / 10, upper=(index + 1) / 10, count=count,
                    mean_p=probability / count if count else None,
                    up_rate=target / count if count else None))
    months = defaultdict(lambda: dict.fromkeys((*COUNTS, *SUMS), 0.0))
    for (part, day, offset), totals in daily.items():
        for key, number in totals.items():
            months[part, day[:7], offset][key] += number
    monthly = [{"partition": part, "day": month, "offset": offset, **totals, **ratios(totals)}
               for (part, month, offset), totals in sorted(months.items())]
    return comparison, calibration, daily_rows, monthly
