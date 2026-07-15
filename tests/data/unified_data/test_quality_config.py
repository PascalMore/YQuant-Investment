"""Tests for QualityScorerConfig (DESIGN-03-011 §3.4).

Scope:
* Default values match the frozen spec (weights sum to 1.0, tier thresholds
  cover direct_use / warning / degrade).
* ``for_domain()`` returns a merged config when an override exists and
  returns ``self`` when it does not — so downstream callers can hold a
  reference and never have to defensively check.
* Domain TTL lookup falls back to a sane default for unknown domains so
  the freshness scorer never crashes on a future domain name.
* Construction-time validation rejects misconfigured inputs (weights
  do not sum to 1.0, missing required tier keys) with ``ValueError`` —
  not a silent fallback that would mask bad config.

These tests run RED first: each behaviour is asserted before the
implementation file (``quality/config.py``) exists, so they should
initially fail with ``ImportError``. After the implementation lands
each case should GREEN with no further code changes.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data.quality.config import QualityScorerConfig


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaultValues:
    def test_dimension_weights_sum_to_one(self) -> None:
        cfg = QualityScorerConfig()
        total = sum(cfg.dimension_weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_dimension_weights_contain_all_four_dims(self) -> None:
        cfg = QualityScorerConfig()
        assert set(cfg.dimension_weights) == {
            "completeness",
            "freshness",
            "consistency",
            "plausibility",
        }

    def test_default_dimension_weights_match_spec(self) -> None:
        cfg = QualityScorerConfig()
        assert cfg.dimension_weights == {
            "completeness": 0.35,
            "freshness": 0.30,
            "consistency": 0.15,
            "plausibility": 0.20,
        }

    def test_default_tier_thresholds_match_spec(self) -> None:
        cfg = QualityScorerConfig()
        assert cfg.tier_thresholds == {
            "direct_use": 0.9,
            "warning": 0.7,
            "degrade": 0.3,
        }

    def test_default_domain_ttl_has_canonical_domains(self) -> None:
        cfg = QualityScorerConfig()
        # Spec §3.2.2: market_data=14400, financial=86400, news=3600,
        # metadata=86400, index=14400.
        assert cfg.domain_ttl == {
            "market_data": 14400,
            "financial": 86400,
            "news": 3600,
            "metadata": 86400,
            "index": 14400,
        }

    def test_minimal_factory_returns_default_config(self) -> None:
        cfg = QualityScorerConfig.minimal()
        assert cfg.dimension_weights == QualityScorerConfig().dimension_weights
        assert cfg.tier_thresholds == QualityScorerConfig().tier_thresholds


# ---------------------------------------------------------------------------
# TTL lookup
# ---------------------------------------------------------------------------


class TestDomainTtl:
    def test_known_domain_returns_configured_ttl(self) -> None:
        cfg = QualityScorerConfig()
        assert cfg.get_ttl_for_domain("market_data") == 14400
        assert cfg.get_ttl_for_domain("news") == 3600

    def test_unknown_domain_falls_back_to_default(self) -> None:
        cfg = QualityScorerConfig()
        # Spec §3.2.2: 未匹配域 → 14400（4h）兜底
        assert cfg.get_ttl_for_domain("unknown_future_domain") == 14400


# ---------------------------------------------------------------------------
# for_domain — override semantics
# ---------------------------------------------------------------------------


class TestForDomain:
    def test_no_override_returns_self(self) -> None:
        cfg = QualityScorerConfig()
        assert cfg.for_domain("market_data") is cfg

    def test_override_merges_dimension_weights(self) -> None:
        # Override only the weights; tier_thresholds and domain_ttl
        # should fall back to the parent config.
        override = QualityScorerConfig(
            dimension_weights={
                "completeness": 0.25,
                "freshness": 0.40,
                "consistency": 0.15,
                "plausibility": 0.20,
            },
        )
        cfg = QualityScorerConfig(domain_overrides={"market_data": override})

        merged = cfg.for_domain("market_data")
        assert merged.dimension_weights == override.dimension_weights
        # Tier thresholds + TTL survive from parent.
        assert merged.tier_thresholds == cfg.tier_thresholds
        assert merged.domain_ttl == cfg.domain_ttl

    def test_override_does_not_mutate_parent(self) -> None:
        override = QualityScorerConfig(
            dimension_weights={
                "completeness": 0.50,
                "freshness": 0.10,
                "consistency": 0.20,
                "plausibility": 0.20,
            },
        )
        cfg = QualityScorerConfig(domain_overrides={"financial": override})

        # Touching the merged config must not corrupt the parent.
        merged = cfg.for_domain("financial")
        assert merged.dimension_weights["completeness"] == 0.50
        assert cfg.dimension_weights["completeness"] == 0.35


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_weights_not_summing_to_one_raises(self) -> None:
        with pytest.raises(ValueError):
            QualityScorerConfig(
                dimension_weights={
                    "completeness": 0.5,
                    "freshness": 0.5,
                    "consistency": 0.5,
                    "plausibility": 0.5,
                }
            )

    def test_missing_required_tier_keys_raises(self) -> None:
        with pytest.raises(ValueError):
            QualityScorerConfig(
                tier_thresholds={"direct_use": 0.9}
            )

    def test_weights_within_tolerance_passes(self) -> None:
        # ±0.001 tolerance per spec.
        cfg = QualityScorerConfig(
            dimension_weights={
                "completeness": 0.3505,
                "freshness": 0.30,
                "consistency": 0.15,
                "plausibility": 0.1995,
            }
        )
        assert cfg is not None