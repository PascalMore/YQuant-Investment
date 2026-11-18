"""Tests of the joint four-group preparation module.

The joint module must never import the production scoring function as its own
independent numeric baseline: the independent reference below reimplements the
frozen pair arithmetic from the contract, so an accidental reuse of the
production implementation is caught by the test itself.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(LAB.parents[4]))
import phase1_joint_validation as joint  # noqa: E402

DAY_US = 86_400_000_000
FITTED = {"M1": {"fit_status": "FIT_OK", "a": 1.5, "b": 0.1},
          "M3-joint": {"fit_status": "FIT_OK", "a": 0.8, "b": -0.1}}


def independent_pair_difference(left: float, right: float, up: bool) -> float:
    """Independent paired Brier difference, written from the contract alone."""
    outcome = 1.0 if up else 0.0
    return (left - outcome) ** 2 - (right - outcome) ** 2


def independent_calibration(probability: float, a: float, b: float) -> float:
    """Independent monotone mapping, written from the contract alone."""
    import math
    clipped = min(1 - 1e-12, max(1e-12, probability))
    score = a * (math.log(clipped) - math.log1p(-clipped)) + b
    if score >= 0:
        return 1.0 / (1.0 + math.exp(-score))
    exponential = math.exp(score)
    return exponential / (1.0 + exponential)


def slot(planned: int, offset: int, p_m0: float | None, p_low: float | None,
         label: str | None, label_at: int | None, sigma: float | None = None) -> dict:
    """One joint input slot."""
    return dict(planned_start_us=planned, offset=offset, at_us=planned + offset * 1_000_000,
                ends_at_us=planned + 300_000_000, label=label, label_available_at_us=label_at,
                p_m0=p_m0, p_low=p_low, sigma_m0=sigma, sigma_low=sigma)


def fit_row(planned: int, offset: int, p_up: float, label: str, label_at: int) -> dict:
    """One row of the frozen calibration fit input."""
    return dict(at_us=planned + offset * 1_000_000, ends_at_us=planned + 300_000_000,
                label=label, label_available_at_us=label_at, planned_start_us=planned,
                p_up=p_up)


def test_joint_mapping_uses_the_floor_input_of_its_own_group():
    """M3-joint consumes the M2-low output and never the M1 parameters."""
    parameters = {"M1": {"fit_status": "FIT_OK", "a": 2.0, "b": 0.5},
                  "M3-joint": {"fit_status": "FIT_OK", "a": 0.5, "b": -0.25}}
    assert joint.group_probability("M0", 0.4, parameters) == 0.4
    assert joint.group_probability("M2-low", 0.4, parameters) == 0.4
    assert joint.group_probability("M1", 0.4, parameters) == pytest.approx(
        independent_calibration(0.4, 2.0, 0.5), rel=1e-12)
    assert joint.group_probability("M3-joint", 0.4, parameters) == pytest.approx(
        independent_calibration(0.4, 0.5, -0.25), rel=1e-12)
    assert joint.group_probability("M1", 0.4, parameters) != pytest.approx(
        joint.group_probability("M3-joint", 0.4, parameters), rel=1e-9)


def test_failed_fit_emits_no_probability():
    """A failed calibration emits no probability instead of falling back."""
    parameters = {"M1": {"fit_status": "FIT_NOT_CONVERGED", "a": None, "b": None},
                  "M3-joint": {"fit_status": "FIT_OK", "a": 1.0, "b": 0.0}}
    assert joint.group_probability("M1", 0.4, parameters) is None
    assert joint.group_probability("M3-joint", 0.4, parameters) == pytest.approx(0.4)


def test_time_filter_keeps_only_slots_ending_before_the_cutoff():
    """The frozen filter drops the slots that end after the training cutoff."""
    cutoff = 1_000_000_000
    inside = joint.fit_calibration([fit_row(0, 30, 0.6, "UP", 500_000_000),
                                    fit_row(0, 60, 0.6, "UP", 500_000_000)], cutoff, cutoff)
    assert inside["slot_count"] == 2
    assert inside["window_excluded_count"] == 0
    outside = joint.fit_calibration([fit_row(2_000_000_000, 30, 0.6, "UP", 2_500_000_000)],
                                    cutoff, cutoff)
    assert outside["slot_count"] == 0
    assert outside["window_excluded_count"] == 1


def test_frozen_parameters_do_not_change_with_the_validation_label():
    """Changing only the future label must not move the frozen parameters."""
    base = [slot(0, 30, 0.6, 0.6, "UP", 100), slot(0, 60, 0.5, 0.5, "DOWN", 100)]
    changed = [slot(0, 30, 0.6, 0.6, "DOWN", 100), slot(0, 60, 0.5, 0.5, "UP", 100)]
    first = joint.evaluate(base, FITTED, as_of_us=1_000)
    second = joint.evaluate(changed, FITTED, as_of_us=1_000)
    assert first["counts"]["M0"]["slots"] == second["counts"]["M0"]["slots"]
    assert first["primary"]["series"] == second["primary"]["series"]
    # The frozen parameters are label independent; only the scores move.
    assert first["comparisons"]["M1|M0|binary_brier"]["point"] != \
        second["comparisons"]["M1|M0|binary_brier"]["point"]
    up = joint.fit_calibration([fit_row(0, 30, 0.6, "UP", 100)], 10 ** 12, 10 ** 12)
    down = joint.fit_calibration([fit_row(0, 30, 0.6, "DOWN", 100)], 10 ** 12, 10 ** 12)
    # A single slot is a single class: no parameter is emitted in either case.
    assert up["fit_status"] == down["fit_status"] == "FIT_SINGLE_CLASS"
    assert up["a"] is None and up["b"] is None
    assert down["a"] is None and down["b"] is None


def test_four_groups_share_the_same_slot_input():
    """The four groups are computed from one and the same slot."""
    rows = [slot(0, offset, 0.5, 0.5, "UP", 100) for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=1_000)
    for name in joint.GROUPS:
        assert evaluation["counts"][name]["slots"] == len(joint.OFFSETS)
        assert evaluation["counts"][name]["valued"] == len(joint.OFFSETS)


def test_null_and_draw_labels_are_not_scored_as_binary():
    """A missing label and a draw never enter the binary comparison."""
    rows = [slot(0, offset, 0.5, 0.5, None, None) for offset in joint.OFFSETS]
    rows += [slot(0, offset, 0.5, 0.5, "DRAW", 100) for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=1_000)
    assert evaluation["counts"]["M0"].get("binary_scored", 0) == 0
    assert evaluation["counts"]["M0"]["draw_label"] == len(joint.OFFSETS)
    assert evaluation["comparisons"]["M3-joint|M0|binary_brier"]["point"] is None
    # The payout comparison still uses the draw payout of 0.5.
    assert evaluation["comparisons"]["M3-joint|M0|payout_mse"]["point"] is not None


def test_real_label_and_payout_are_scored():
    """A real binary label is scored with the real payout of the outcome."""
    rows = [slot(0, offset, 0.8, 0.8, "UP", 100) for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=1_000)
    assert evaluation["counts"]["M0"]["binary_scored"] == len(joint.OFFSETS)
    # The two models differ, so the paired difference is not zero.
    assert evaluation["comparisons"]["M3-joint|M0|binary_brier"]["point"] != \
        pytest.approx(0.0, abs=1e-12)
    assert evaluation["comparisons"]["M3-joint|M0|payout_mse"]["point"] == \
        pytest.approx(evaluation["comparisons"]["M3-joint|M0|binary_brier"]["point"], rel=1e-12)


def test_common_denominator_and_future_gate():
    """Only the slots legal for both models are scored, and the future is gated."""
    planned = 1_000_000_000
    rows = [slot(planned, offset, 0.8, 0.8, "UP", 100) for offset in joint.OFFSETS]
    rows[2]["p_m0"] = None
    rows[2]["p_low"] = None
    evaluation = joint.evaluate(rows, FITTED, as_of_us=10 ** 12)
    assert evaluation["counts"]["M0"]["valued"] == len(joint.OFFSETS) - 1
    assert evaluation["counts"]["M0"]["binary_scored"] == len(joint.OFFSETS) - 1
    gate = planned + 60 * 1_000_000
    gated = joint.evaluate(rows, FITTED, as_of_us=10 ** 12, gate_at_us=gate)
    assert gated["counts"]["M0"]["future_gate_excluded"] == 5
    assert gated["counts"]["M0"]["binary_scored"] == 1


def test_evaluation_matches_the_independent_reference_arithmetic():
    """The paired difference equals the independently written reference."""
    planned = 1_000_000_000
    rows = [slot(planned, offset, 0.55 + 0.01 * offset, 0.5 + 0.01 * offset,
                 "UP" if offset % 2 else "DOWN", 100, sigma=0.00003)
            for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=10 ** 12)
    expected = []
    for row in rows:
        left = joint.group_probability("M3-joint", row["p_low"], FITTED)
        right = joint.group_probability("M0", row["p_m0"], FITTED)
        assert left is not None and right is not None
        expected.append(independent_pair_difference(left, right, row["label"] == "UP"))
    assert evaluation["comparisons"]["M3-joint|M0|binary_brier"]["point"] == \
        pytest.approx(sum(expected) / len(expected), rel=1e-12)


def test_paired_comparison_is_a_difference_not_a_standalone_loss():
    """The comparison series is a paired difference of two models."""
    rows = [slot(0, offset, 0.9, 0.9, "DOWN", 100) for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=10 ** 12)
    assert evaluation["comparisons"]["M1|M0|binary_brier"]["point"] != \
        pytest.approx(0.0, abs=1e-12)
    assert evaluation["comparisons"]["M3-joint|M0|binary_brier"]["point"] != \
        pytest.approx(0.0, abs=1e-12)


def test_window_is_derived_from_the_actual_freeze_instant():
    """The window starts at the next UTC midnight and spans 14 half-open days."""
    window = joint.compute_window(datetime(2026, 11, 18, 21, 30, tzinfo=timezone.utc))
    assert window["start_utc"] == "2026-11-19T00:00:00+00:00"
    assert window["end_utc"] == "2026-12-03T00:00:00+00:00"
    assert window["days"] == 14
    assert (window["end_us"] - window["start_us"]) == 14 * DAY_US


def test_existing_evidence_leaf_is_refused(tmp_path, monkeypatch):
    """An existing leaf is refused without ever touching the real report tree."""
    monkeypatch.setattr(joint, "EVIDENCE_ROOT", tmp_path)
    leaf = tmp_path / "pytest-collision"
    leaf.mkdir()
    marker = leaf / "marker.txt"
    marker.write_text("untouched", encoding="utf-8")
    with pytest.raises(joint.PreflightError):
        joint.claim_leaf("pytest-collision")
    assert marker.read_text(encoding="utf-8") == "untouched"


def test_cli_maps_a_path_refusal_to_the_preflight_exit_code():
    """An invalid path argument is refused with the preflight exit code."""
    assert joint.main(["--mode", "prepare", "--evidence-leaf", "../escape"]) == 64


def test_zero_valid_days_remain_in_the_paired_bootstrap_calendar():
    import numpy as np
    start = joint.utc(joint.aware("2026-11-19T00:00:00Z"))
    rows = [slot(start + day * DAY_US + round_index * 300_000_000, offset,
                 None if day < 13 else 0.6, None if day < 13 else 0.7, "UP",
                 start + 15 * DAY_US)
            for day in range(14) for round_index in range(288) for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=start + 15 * DAY_US)
    sampled = np.random.Generator(np.random.PCG64(42)).integers(0, 14, size=(1000, 14), dtype=np.int64)
    valid = int(np.any(sampled == 13, axis=1).sum())
    assert valid == 646
    assert len(evaluation["bootstrap"]["days"]) == 14
    assert evaluation["primary"]["valid_replicates"] == valid
    assert evaluation["primary"]["invalid_replicates"] == 1000 - valid == 354
    assert evaluation["models"]["M0"]["binary_brier"]["denominator"] == 288


def test_zero_valid_entire_window_returns_null_losses_without_crashing():
    start = joint.utc(joint.aware("2026-11-19T00:00:00Z"))
    rows = [slot(start + day * DAY_US + round_index * 300_000_000, offset,
                 None, None, "UP", start + 15 * DAY_US)
            for day in range(14) for round_index in range(288) for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=start + 15 * DAY_US)
    assert len(evaluation["bootstrap"]["days"]) == 14
    assert evaluation["primary"]["point"] is None
    assert evaluation["primary"]["lo95"] is None
    assert evaluation["primary"]["hi95"] is None
    assert evaluation["primary"]["valid_replicates"] == 0
    assert evaluation["primary"]["invalid_replicates"] == 1000
    for name in joint.GROUPS:
        assert evaluation["models"][name]["binary_brier"]["denominator"] == 0
        assert evaluation["models"][name]["binary_brier"]["value"] is None
        assert evaluation["counts"][name]["unvalued"] == len(rows)


def test_absolute_scores_keep_half_probability_and_separate_abstention():
    rows = [slot(0, offset, 0.5, 0.5, "UP", 100) for offset in joint.OFFSETS]
    evaluation = joint.evaluate(rows, FITTED, as_of_us=1_000)
    assert evaluation["models"]["M0"]["binary_brier"]["value"] == pytest.approx(0.25)
    assert evaluation["counts"]["M0"]["abstain"] == len(joint.OFFSETS)
    assert evaluation["counts"]["M0"].get("direction_conflict", 0) == 0


def test_forward_cli_refuses_unfrozen_input_before_any_replay(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(joint, "EVIDENCE_ROOT", tmp_path)
    freeze = tmp_path / "unapproved.json"
    freeze.write_text(json.dumps({"verdict": "PENDING"}), encoding="utf-8")
    code = joint.main(["--mode", "forward", "--evidence-leaf", "refused",
                       "--freeze-file", str(freeze), "--as-of", "2026-12-05T00:00:00Z"])
    assert code == 64
    failure = tmp_path / "refused" / "failure.json"
    assert failure.is_file(), "forward must be a real CLI mode, not argparse rejecting an unknown mode"
    assert json.loads(failure.read_text())["error"] == "PreflightError"


def test_explicit_cutoff_config_preserves_default_and_rejects_early_cutoff():
    start = joint.utc(datetime(2026, 11, 19, tzinfo=timezone.utc))
    end = start + 14 * DAY_US
    cutoff = datetime(2026, 12, 4)
    legacy = joint.research.core_config(start, end, 0.00005)
    assert legacy["schema_version"] == "btc-arb-phase1-research-config/1"
    assert legacy["as_of_us"] == joint.research.to_us(joint.research.AS_OF)
    explicit = joint.research.core_config(start, end, 0.00005, as_of=cutoff)
    assert explicit["schema_version"] == "btc-arb-phase1-research-config/2"
    assert explicit["as_of_us"] == joint.utc(cutoff)
    with pytest.raises(joint.research.PreflightError):
        joint.research.core_config(start, end, 0.00005, as_of=datetime(2026, 11, 18))


def test_current_native_binary_refuses_future_window_before_reading_input(tmp_path):
    """Capability probe, not a fix: the frozen native contract rejects new dates."""
    import json
    import subprocess

    start = joint.utc(datetime(2026, 11, 19, tzinfo=timezone.utc))
    end = start + 14 * DAY_US
    config = joint.research.core_config(start, end, 0.00005)
    config["as_of_us"] = end + DAY_US
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run(
        [str(joint.research.BINARY), "--config", str(config_path), "--input", "-",
         "--output", str(tmp_path / "values.jsonl"),
         "--summary", str(tmp_path / "summary.json"),
         "--from-us", str(start), "--to-us", str(end)],
        input="", capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 64
    assert "invalid research config" in result.stderr
    assert not (tmp_path / "values.jsonl").exists()
    assert not (tmp_path / "summary.json").exists()


def frozen_fixture(tmp_path, monkeypatch, freeze_utc="2026-10-31T12:00:00Z") -> tuple[Path, dict, dict]:
    """Synthetic reviewer record for offline consumer tests, never a real PASS."""
    import json
    monkeypatch.setattr(joint, "EVIDENCE_ROOT", tmp_path)
    params = {name: {**record, "input_group": joint.BASE_GROUP[name]}
              for name, record in FITTED.items()}
    parameter_path = tmp_path / "parameters.json"
    parameter_path.write_text(json.dumps(dict(cutoff_us=0, as_of_us=0, calibrations=params)))
    frozen = dict(schema_version="btc5m-joint-freeze/1", verdict="PASS", freeze_utc=freeze_utc,
                  window=joint.compute_window(joint.aware(freeze_utc)),
                  parameters=dict(path=str(parameter_path), sha256=joint.digest(parameter_path)),
                  files={name: joint.digest(joint.ROOT / name) for name in joint.FORWARD_FILES},
                  state=dict(warmup_days=1, daily_reset=False))
    path = tmp_path / "fixture-freeze.json"
    path.write_text(json.dumps(frozen))
    return path, frozen, params


def test_future_window_gate_does_not_acquire_or_fit(tmp_path, monkeypatch):
    path, frozen, _ = frozen_fixture(tmp_path, monkeypatch, "2035-10-31T12:00:00Z")
    def forbidden(*args, **kwargs):
        pytest.fail("unmatured experiment accessed acquisition or fitting")
    monkeypatch.setattr(joint, "replay_forward", forbidden)
    monkeypatch.setattr(joint, "calibration_parameters", forbidden)
    assert joint.main(["--mode", "forward", "--evidence-leaf", "early",
                       "--freeze-file", str(path), "--as-of", frozen["window"]["end_utc"]]) == 64


def test_forward_consumer_uses_frozen_parameters_and_excludes_warmup(tmp_path, monkeypatch):
    import csv
    import json
    path, frozen, parameters = frozen_fixture(tmp_path, monkeypatch)
    start, end = frozen["window"]["start_us"], frozen["window"]["end_us"]
    called = []
    def acquired(leaf, observed_start, observed_end, as_of):
        called.append((joint.utc(observed_start), joint.utc(observed_end)))
        return [slot(planned, offset, 0.6, 0.7, "UP" if planned % 600_000_000 else "DOWN",
                     planned + 300_000_000, 0.00003)
                for planned in range(start - DAY_US, end, 300_000_000) for offset in joint.OFFSETS]
    def forbidden(*args, **kwargs):
        pytest.fail("forward must never fit calibrations")
    monkeypatch.setattr(joint, "replay_forward", acquired)  # fake acquisition only; real CLI/scorer/writers
    monkeypatch.setattr(joint, "calibration_parameters", forbidden)
    assert joint.main(["--mode", "forward", "--evidence-leaf", "scored",
                       "--freeze-file", str(path), "--as-of", "2026-11-16T00:00:00Z"]) == 0
    assert called == [(start, end)]
    binding = json.loads((tmp_path / "scored/binding.json").read_text())
    assert binding["warmup_slots"] == 288 * len(joint.OFFSETS)
    assert binding["scored_slots"] == 14 * 288 * len(joint.OFFSETS)
    with (tmp_path / "scored/predictions.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == binding["scored_slots"]
    assert min(int(row["planned_start_us"]) for row in rows) == start
    assert max(int(row["planned_start_us"]) for row in rows) < end
    assert float(rows[0]["M3-joint"]) == pytest.approx(independent_calibration(0.7, 0.8, -0.1))
    stats = json.loads((tmp_path / "scored/statistics.json").read_text())
    assert stats["rounds"] == 14 * 288
    assert stats["models"]["M0"]["binary_brier"]["value"] == pytest.approx(0.26)


def test_frozen_parameter_drift_is_refused(tmp_path, monkeypatch):
    path, frozen, _ = frozen_fixture(tmp_path, monkeypatch)
    Path(frozen["parameters"]["path"]).write_text("{}")
    with pytest.raises(joint.DriftError):
        joint.load_freeze(path, joint.aware("2026-11-16T00:00:00Z"), joint.aware("2026-11-18T00:00:00Z"))


def test_explicit_date_adapter_preserves_microseconds_and_utc_day():
    instant = joint.aware("2026-11-19T01:00:00.123456+08:00")
    assert joint.utc(instant) % 1_000_000 == 123456
    assert joint.compute_window(instant)["start_utc"] == "2026-11-19T00:00:00+00:00"


def test_explicit_cutoff_reaches_facade_request_and_label_clock(tmp_path, monkeypatch):
    from test_phase1_model_research import Bundle
    cutoff = datetime(2026, 11, 21)
    day = datetime(2026, 11, 19)
    received = []
    def stop_at_facade(client, request):
        received.append(request.as_of_utc)
        raise joint.research.DataError("fixture stops before acquisition")
    monkeypatch.setattr(joint.research, "open_bundle", stop_at_facade)
    budget = joint.research.RunBudget(tmp_path, 120, "small")
    with pytest.raises(joint.research.DataError):
        list(joint.research.consume_days(object(), tmp_path, day,
             datetime(2026, 11, 20), budget, [], as_of=cutoff))
    assert received == [cutoff]
    start = joint.utc(day)
    contexts, rounds = [], []
    events = list(joint.research.iter_phase1_day(Bundle(start), start, start + 300_000_000,
                                                contexts, rounds, as_of=cutoff))
    assert contexts[0]["label_status"] == "BINARY_UP"
    assert all("label" not in str(event) for event in events)


def test_explicit_v2_broadcast_uses_new_binary_and_common_input(tmp_path):
    from test_phase1_model_research import Bundle
    import json
    import time
    start = joint.utc(joint.aware("2026-11-19T00:00:00Z"))
    end = start + 300_000_000
    contexts, rounds = [], []
    events = joint.research.iter_phase1_day(Bundle(start), start, end, contexts, rounds,
                                            as_of=datetime(2026, 11, 21))
    result = joint.research.broadcast_phase1(events, tmp_path, start, end,
        time.monotonic() + 30, as_of=datetime(2026, 11, 21), binary=joint.FORWARD_BINARY)
    assert result["complete"] is True, result
    assert result["values"] == len(joint.OFFSETS)
    for name in joint.research.FLOORS:
        cfg = json.loads((tmp_path / "cores" / name / "config.json").read_text())
        assert cfg["schema_version"] == "btc-arb-phase1-research-config/2"
        assert cfg["as_of_us"] == joint.utc(datetime(2026, 11, 21))


def test_new_native_binary_crosses_midnight_without_restarting(tmp_path):
    import json
    import subprocess
    start = joint.utc(joint.aware("2026-11-19T23:55:00Z"))
    end = start + 600_000_000
    cutoff = datetime(2026, 11, 21)
    config = joint.research.core_config(start, end, 0.00005, as_of=cutoff)
    config_path = tmp_path / "v2.json"
    config_path.write_text(json.dumps(config))
    events = []
    for second in range(5, 601, 5):
        at = start + second * 1_000_000
        events.append(dict(schema_version=joint.research.SCHEMA, at_us=at,
                           payload=dict(type="spot", symbol="BTCUSDT", price=60000 + second,
                             bar_open_us=at - 1_000_000, close_exclusive_us=at, available_at_us=at,
                             prediction_source="Binance", actual_pair="BTCUSDT",
                             source_dataset="binance-vision", price_kind="trade_close", clock_basis="event_time_proxy")))
        offset = second % 300
        if offset in joint.OFFSETS:
            planned = start + (second // 300) * 300_000_000
            events.append(dict(schema_version=joint.research.SCHEMA, at_us=at,
                               payload=dict(type="value", symbol="BTCUSDT", planned_start_us=planned,
                                 offset=offset, round_id=str(planned), starts_at_us=planned,
                                 ends_at_us=planned + 300_000_000, identity_available_at_us=planned,
                                 strike=60000.0, strike_available_at_us=planned)))
    wire = "".join(json.dumps({**event, "seq": seq}) + "\n" for seq, event in enumerate(events))
    result = subprocess.run([str(joint.FORWARD_BINARY), "--config", str(config_path), "--input", "-",
                             "--output", str(tmp_path / "v2-values.jsonl"),
                             "--summary", str(tmp_path / "v2-summary.json"),
                             "--from-us", str(start), "--to-us", str(end)],
                            input=wire, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    values = [json.loads(line) for line in (tmp_path / "v2-values.jsonl").read_text().splitlines()]
    assert len(values) == 2 * len(joint.OFFSETS)
    assert values[6]["samples"] > values[5]["samples"]
    assert values[6]["valuation_status"] == "VALUED"
    assert values[6]["source_epoch"] == values[5]["source_epoch"]
    assert json.loads((tmp_path / "v2-summary.json").read_text())["complete"] is True
