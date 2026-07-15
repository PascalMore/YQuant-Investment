"""Pure-compute data quality scoring for Unified Data Phase 2.

The scorer evaluates completeness, freshness, consistency, and plausibility in
that order. A zero hard-fail dimension short-circuits later measurements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..models import DataResult
from .config import QualityScorerConfig

_CORE_FIELDS: dict[str, frozenset[str]] = {
    "market_data.kline_daily": frozenset({"close", "volume"}),
}
_FRESHNESS_SCORES = {
    "realtime": 1.0,
    "delayed": 1.0,
    "stale": 0.0,
    "empty": 0.0,
}
_CONSISTENCY_NO_CONFLICT = 1.0
_CONSISTENCY_RESOLVED = 0.7
_CONSISTENCY_ACTIVE_CONFLICT = 0.3
_PLAUSIBILITY_OK = 1.0
_PLAUSIBILITY_UNVERIFIABLE = 0.5
_PLAUSIBILITY_NON_CORE_VIOLATION = 0.3
_PLAUSIBILITY_HARD_FAIL = 0.0


@dataclass(frozen=True, slots=True)
class ScoredResult:
    """Return value of :meth:`QualityScorer.score`."""

    quality_score: float
    dimension_scores: dict[str, float]
    quality_tier: str
    warnings: list[str] = field(default_factory=list)


class QualityScorer:
    """Evaluate a :class:`DataResult` without performing I/O."""

    def __init__(self, config: QualityScorerConfig | None = None) -> None:
        self._config = config or QualityScorerConfig()

    def score(
        self,
        result: DataResult,
        *,
        domain: str | None = None,
        now: datetime | None = None,
    ) -> ScoredResult:
        """Score one result, short-circuiting after a hard-fail dimension."""
        effective_domain = domain or result.domain
        config = self._config.for_domain(effective_domain)
        effective_now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        scores: dict[str, float] = {}
        warnings: dict[str, list[str]] = {}

        score, messages = _score_completeness(
            result, effective_domain, result.operation
        )
        scores["completeness"], warnings["completeness"] = score, messages
        if score == 0.0:
            return _build_hard_fail_result(scores, warnings)

        score, messages = _score_freshness(
            result, effective_domain, config, effective_now
        )
        scores["freshness"], warnings["freshness"] = score, messages
        if score == 0.0:
            return _build_hard_fail_result(scores, warnings)

        score, messages = _score_consistency(result)
        scores["consistency"], warnings["consistency"] = score, messages

        score, messages = _score_plausibility(result, effective_domain)
        scores["plausibility"], warnings["plausibility"] = score, messages
        if score == 0.0:
            return _build_hard_fail_result(scores, warnings)

        return _compute_overall(scores, warnings, config, effective_domain)


def _score_completeness(
    result: DataResult,
    domain: str | None,
    operation: str | None,
) -> tuple[float, list[str]]:
    """Score payload presence and known required fields."""
    if result.is_empty():
        return 0.0, ["empty result: no usable payload"]
    if domain is None or operation is None:
        return 1.0, []

    required = _CORE_FIELDS.get(f"{domain}.{operation}")
    if required is None:
        return 1.0, []

    if isinstance(result.data, dict):
        missing = {
            name
            for name in required
            if name not in result.data or result.data.get(name) is None
        }
        if not missing:
            return 1.0, []
        score = (len(required) - len(missing)) / len(required)
        return score, [_missing_fields_warning(missing)]

    if isinstance(result.data, list):
        if not result.data:
            return 1.0, []
        total_expected = len(result.data) * len(required)
        total_present = 0
        missing: set[str] = set()
        for record in result.data:
            if not isinstance(record, dict):
                continue
            for name in required:
                if name in record and record[name] is not None:
                    total_present += 1
                else:
                    missing.add(name)
        if total_present == total_expected:
            return 1.0, []
        return total_present / total_expected, [_missing_fields_warning(missing)]

    return 1.0, []


def _missing_fields_warning(fields: set[str]) -> str:
    return f"missing required fields: {', '.join(sorted(fields))}"


def _score_freshness(
    result: DataResult,
    domain: str,
    config: QualityScorerConfig,
    now: datetime,
) -> tuple[float, list[str]]:
    """Score the freshness label and cached-result age."""
    if result.freshness in _FRESHNESS_SCORES:
        score = _FRESHNESS_SCORES[result.freshness]
        warning = ["stale data"] if result.freshness == "stale" else []
        return score, warning

    age = max(0, int((now - result.fetched_at).total_seconds()))
    ttl = config.get_ttl_for_domain(domain)
    half_ttl = 0.5 * ttl
    if age <= half_ttl:
        return 0.9, []
    if age <= 0.9 * ttl:
        return 0.6 + 0.3 * (ttl - age) / half_ttl, []
    return 0.2, ["cache near expiry"]


def _score_consistency(result: DataResult) -> tuple[float, list[str]]:
    """Score explicit source-conflict markers in ``source_trace``."""
    trace = list(result.source_trace or [])
    if not any("vs_" in entry for entry in trace):
        return _CONSISTENCY_NO_CONFLICT, []
    if any("resolved" in entry.lower() for entry in trace):
        return _CONSISTENCY_RESOLVED, [
            "source conflict resolved: price divergence"
        ]
    return _CONSISTENCY_ACTIVE_CONFLICT, ["source conflict: price divergence"]


def _score_plausibility(
    result: DataResult,
    domain: str | None,
) -> tuple[float, list[str]]:
    """Apply Phase 2 numeric boundary checks to market data."""
    if domain != "market_data":
        return _PLAUSIBILITY_OK, []

    if isinstance(result.data, dict):
        records = [result.data]
    elif isinstance(result.data, list):
        records = [record for record in result.data if isinstance(record, dict)]
    else:
        records = []
    if not records:
        return _PLAUSIBILITY_UNVERIFIABLE, ["unable to validate"]

    warnings: list[str] = []
    core_violation = False
    non_core_violation = False
    for record in records:
        value = record.get("close")
        if isinstance(value, (int, float)) and value <= 0:
            core_violation = True
            warnings.append(f"invalid close value: {value}")
        for name in ("open", "high", "low", "volume", "amount"):
            value = record.get(name)
            if isinstance(value, (int, float)) and value < 0:
                non_core_violation = True
                warnings.append(f"suspicious {name} value: {value}")

    if core_violation:
        return _PLAUSIBILITY_HARD_FAIL, warnings
    if non_core_violation:
        return _PLAUSIBILITY_NON_CORE_VIOLATION, warnings
    return _PLAUSIBILITY_OK, []


def _compute_overall(
    dimension_scores: dict[str, float],
    dimension_warnings: dict[str, list[str]],
    config: QualityScorerConfig,
    domain: str,
) -> ScoredResult:
    """Combine measured dimensions using the domain-specific weights."""
    weights = config.for_domain(domain).dimension_weights
    total = sum(
        weights.get(dimension, 0.0) * score
        for dimension, score in dimension_scores.items()
    )
    total = max(0.0, min(1.0, total))
    return ScoredResult(
        quality_score=total,
        dimension_scores=dict(dimension_scores),
        quality_tier=_compute_tier(total, config.tier_thresholds),
        warnings=_flatten_warnings(dimension_warnings),
    )


def _build_hard_fail_result(
    dimension_scores: dict[str, float],
    dimension_warnings: dict[str, list[str]],
) -> ScoredResult:
    return ScoredResult(
        quality_score=0.0,
        dimension_scores=dict(dimension_scores),
        quality_tier="reject",
        warnings=_flatten_warnings(dimension_warnings),
    )


def _compute_tier(score: float, thresholds: dict[str, float]) -> str:
    if score >= thresholds.get("direct_use", 0.9):
        return "direct_use"
    if score >= thresholds.get("warning", 0.7):
        return "warning"
    if score >= thresholds.get("degrade", 0.3):
        return "degrade"
    return "reject"


def _flatten_warnings(dimension_warnings: dict[str, list[str]]) -> list[str]:
    return [warning for warnings in dimension_warnings.values() for warning in warnings]


__all__ = ["QualityScorer", "ScoredResult"]
