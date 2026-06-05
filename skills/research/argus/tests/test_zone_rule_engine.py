"""Tests for the unified Argus / Portfolio zone rule engine."""

import sys

sys.path.insert(0, "/home/pascal/.openclaw/workspace-yquant")

from skills.research.argus.config import ZONE_RULES_CONFIG
from skills.research.argus.config.zone_rules import load_zone_rules_config
from skills.research.argus.core.zone_rule_engine import ZoneMetrics, ZoneRuleEngine


def _engine() -> ZoneRuleEngine:
    return ZoneRuleEngine.from_config(ZONE_RULES_CONFIG)


def test_classify_initial_zone_conviction():
    decision = _engine().classify_initial_zone(
        ZoneMetrics(bayesian_score=0.80, contributing_products_count=3, consensus_confidence=0.65)
    )
    assert decision.target_zone == "CONVICTION"


def test_classify_initial_zone_candidate():
    decision = _engine().classify_initial_zone(
        ZoneMetrics(bayesian_score=0.60, contributing_products_count=2, consensus_confidence=0.45)
    )
    assert decision.target_zone == "CANDIDATE"


def test_classify_initial_zone_watch():
    decision = _engine().classify_initial_zone(
        ZoneMetrics(bayesian_score=0.40, contributing_products_count=1, consensus_confidence=0.25)
    )
    assert decision.target_zone == "WATCH"


def test_classify_initial_zone_scan():
    decision = _engine().classify_initial_zone(
        ZoneMetrics(bayesian_score=0.30, contributing_products_count=1, consensus_confidence=0.10)
    )
    assert decision.target_zone == "SCAN"


def test_darwin_override_floor_to_candidate():
    decision = _engine().classify_initial_zone(
        ZoneMetrics(
            bayesian_score=0.50,
            contributing_products_count=1,
            consensus_confidence=0.20,
            darwin_moment=True,
        )
    )
    assert decision.target_zone == "CANDIDATE"
    assert decision.rule_name == "darwin_override"


def test_darwin_override_does_not_force_conviction():
    decision = _engine().classify_initial_zone(
        ZoneMetrics(
            bayesian_score=0.50,
            contributing_products_count=1,
            consensus_confidence=0.20,
            darwin_moment=True,
        )
    )
    assert decision.target_zone == "CANDIDATE"


def test_eval_promote_scan_to_watch():
    decision = _engine().eval_promote(
        ZoneMetrics(bayesian_score=0.36, contributing_products_count=1, consensus_confidence=0.20),
        "SCAN",
    )
    assert decision is not None
    assert decision.target_zone == "WATCH"


def test_eval_demote_watch_to_scan_hysteresis():
    decision = _engine().eval_demote(
        ZoneMetrics(bayesian_score=0.30, contributing_products_count=1, consensus_confidence=0.20),
        "WATCH",
    )
    assert decision is None


def test_eval_demote_watch_falls():
    decision = _engine().eval_demote(
        ZoneMetrics(bayesian_score=0.20, contributing_products_count=1, consensus_confidence=0.20),
        "WATCH",
    )
    assert decision is not None
    assert decision.target_zone == "SCAN"


def test_exit_missing_from_signal_pool():
    decision = _engine().eval_exit(ZoneMetrics(missing_from_signal_pool=True), "WATCH")
    assert decision is not None
    assert decision.action == "exit"


def test_crowding_zone_limits():
    decision = _engine().classify_initial_zone(
        ZoneMetrics(
            bayesian_score=0.80,
            contributing_products_count=3,
            consensus_confidence=0.65,
            crowding_level="DANGER",
        )
    )
    assert decision.target_zone == "CANDIDATE"


def test_yaml_config_loaded():
    config = load_zone_rules_config()
    for field in ("version", "zones", "score_policy", "argus_signal_pool", "portfolio_transitions"):
        assert field in config
