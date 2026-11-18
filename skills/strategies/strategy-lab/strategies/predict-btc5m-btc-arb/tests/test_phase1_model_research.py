"""Colocated research transport/causal sampling tests; real native consumers."""
from __future__ import annotations

import json
import hashlib
import time
import os
import subprocess
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import phase1_model_research as research
from history_input import HistoryInput
from skills.data.unified_data.history_types import DATASET_KLINES, DATASET_ROUNDS


class Bundle:
    def __init__(self, start, seconds=300, missing=()):
        self.start = start
        self.seconds = seconds
        self.missing = set(missing)
        self.counts = {"features": 0, "metadata": 0, "labels": 0}
        self.verified = False
        self.content_manifest = {"fixture": True}
        self.content_sha256 = None

    def iter_metadata(self):
        self.counts["metadata"] += 1
        yield HistoryInput("round_identity", "predict.fun", self.start, self.start, False,
            dict(round_id="official", starts_at_us=self.start, ends_at_us=self.start + 300_000_000,
                 dataset=DATASET_ROUNDS))

    def iter_features(self):
        self.counts["features"] += 1
        yield HistoryInput("trade_kline_ohlc", "predict.fun", self.start, self.start, False,
            dict(round_id="official", start_price=60000, dataset=DATASET_ROUNDS))
        for second in range(1, self.seconds + 1):
            if second in self.missing:
                continue
            self.counts["features"] += 1
            closed = self.start + second * 1_000_000
            yield HistoryInput("trade_kline_ohlc", "binance-vision", closed - 1_000_000,
                closed, False, dict(open_time_us=closed - 1_000_000,
                    close_exclusive_us=closed, close=60000 + second, dataset=DATASET_KLINES))

    def iter_labels(self):
        self.counts["labels"] += 1
        yield HistoryInput("official_outcome", "predict.fun", self.start + 300_000_000,
            self.start + 301_000_000, False,
            dict(round_id="official", starts_at_us=self.start,
                 ends_at_us=self.start + 300_000_000, official_outcome="UP", dataset=DATASET_ROUNDS))

    def verify_consumed(self):
        self.verified = True
        self.content_sha256 = "fixture-content"
        return self.content_sha256


def test_five_second_causal_events_keep_every_slot_and_separate_labels():
    start = research.to_us(research.START)
    bundle = Bundle(start, missing=(30,))
    contexts, rounds = [], []
    events = list(research.iter_phase1_day(bundle, start, start + 300_000_000, contexts, rounds))
    spots = [event for event in events if event["payload"]["type"] == "spot"]
    values = [event for event in events if event["payload"]["type"] == "value"]
    assert len(spots) == 59
    assert len(values) == len(contexts) == 6
    assert [event["payload"]["offset"] for event in values] == list(research.OFFSETS)
    assert all(event["at_us"] % 5_000_000 == 0 for event in spots)
    assert all(event["payload"]["bar_open_us"] == event["at_us"] - 1_000_000 for event in spots)
    assert all("label" not in json.dumps(event) for event in events)
    assert contexts[0]["label"] == "UP"
    assert rounds[0]["round_id"] == "official"
    assert bundle.counts == {"features": 300, "metadata": 1, "labels": 1}


def test_path_collisions_and_symlinks_do_not_touch_old_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    existing = tmp_path / "developer-small"
    existing.mkdir()
    (existing / "old").write_bytes(b"unaltered")
    with pytest.raises(research.PreflightError):
        research.claim_run(existing, "small")
    assert (existing / "old").read_bytes() == b"unaltered"
    link = tmp_path / "developer-pilot"
    link.symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(research.PreflightError):
        research.claim_run(link, "pilot")
    assert link.is_symlink()


def test_real_three_native_cores_accept_identical_stream(tmp_path):
    import phase1_reference as reference
    start = research.to_us(research.START)
    bundle = Bundle(start)
    contexts, rounds = [], []
    events = list(research.iter_phase1_day(bundle, start, start + 300_000_000, contexts, rounds))
    wire = b"".join(research.encode_event(dict(event, seq=seq)) for seq, event in enumerate(events))
    summaries, values = [], []
    for model, floor in research.FLOORS.items():
        directory = tmp_path / model
        directory.mkdir()
        config = research.core_config(start, start + 300_000_000, floor)
        (directory / "config.json").write_text(json.dumps(config))
        command = research.core_command(directory, start, start + 300_000_000)
        result = subprocess.run(command, input=wire, capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
        summary = research.strict_loads((directory / "rust-summary.json").read_text())
        research.check_summary(summary, 0, len(events), 6)
        summaries.append(summary)
        values.append([research.strict_loads(line) for line in (directory / "values.jsonl").read_text().splitlines()])
    assert len({row["input_chain_keccak256"] for row in summaries}) == 1
    assert all(row["accepted_events"] == 66 for row in summaries)
    assert all(row["samples"] == 5 for row in [values[0][0], values[1][0], values[2][0]])
    assert values[0][0]["valuation_status"] == "WARMUP"
    assert values[0][-1]["valuation_status"] == "VALUED"
    assert all([row["seq"] for row in core] == [row["seq"] for row in values[0]] for core in values)
    event_rows = [research.strict_loads(line) for line in wire.decode().splitlines()]
    vectors = reference.check_vectors(event_rows,
        {model: iter(rows) for model, rows in zip(research.FLOORS, values)}, research.FLOORS)
    assert vectors["slots"] == 6
    assert vectors["valued_model_vectors"] == 12
    assert vectors["max_same_as_error"] <= 1e-12
    assert vectors["max_erf_error"] <= 2e-7
    values[0][-1]["samples"] += 1
    with pytest.raises(ValueError, match="exact mismatch"):
        reference.check_vectors(event_rows,
            {model: iter(rows) for model, rows in zip(research.FLOORS, values)}, research.FLOORS)


@pytest.mark.parametrize("spot,strike,sigma,seconds", [(1., 1., 0., 30.),
    (60000., 60000., .000025, 30.), (60000., 60000., .0001, 270.),
    (60000., 90000., .00005, 30.), (60000., 100., .00005, 270.)])
def test_independent_as_erf_boundaries(spot, strike, sigma, seconds):
    import phase1_reference as reference
    approximate, exact = reference.probabilities(spot, strike, sigma, seconds)
    assert abs(approximate - exact) <= 2e-7


@pytest.mark.parametrize("failure,expected", [("wire", 2), ("old-config", 64),
    ("collision", 64), ("io", 5)])
def test_real_native_failure_codes_and_old_target_preservation(tmp_path, failure, expected):
    start = research.to_us(research.START)
    config = research.core_config(start, start + 300_000_000, .00005)
    if failure == "old-config":
        config["schema_version"] = "btc-arb-history/1"
    (tmp_path / "config.json").write_text(json.dumps(config))
    command = research.core_command(tmp_path, start, start + 300_000_000)
    if failure == "collision":
        (tmp_path / "values.jsonl").write_bytes(b"old evidence")
    if failure == "io":
        command[command.index("--summary") + 1] = str(tmp_path / "missing" / "summary")
    result = subprocess.run(command, input=b"{}\n", capture_output=True, timeout=10)
    assert result.returncode == expected
    if failure == "wire":
        summary = research.strict_loads((tmp_path / "rust-summary.json").read_text())
        assert summary["native_exit"] == 2 and summary["complete"] is False
        assert summary["accepted_events"] == 0 and summary["last_seq"] is None
        assert summary["input_chain_keccak256"] == "0" * 64
    if failure == "collision":
        assert (tmp_path / "values.jsonl").read_bytes() == b"old evidence"
        assert not (tmp_path / "rust-summary.json").exists()


def test_strict_json_rejects_recursive_duplicates_and_nonfinite():
    for payload in ('{"payload":{"strike":1,"strike":2}}', '{"x":NaN}', '{"x":Infinity}'):
        with pytest.raises(research.DataError):
            research.strict_loads(payload)


@pytest.mark.parametrize("broken_peer", [False, True])
def test_real_broadcast_uses_low_level_transport_and_reaps_every_peer(tmp_path, monkeypatch, broken_peer):
    import history_performance as transport
    start = research.to_us(research.START)
    contexts, rounds = [], []
    events = research.iter_phase1_day(Bundle(start), start, start + 300_000_000, contexts, rounds)
    if broken_peer:
        original = transport._write_event
        calls = 0
        def fail_third_peer(fd, payload, deadline):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise BrokenPipeError("fixture third peer transport failure")
            original(fd, payload, deadline)
        monkeypatch.setattr(transport, "_write_event", fail_third_peer)
    result = research.broadcast_phase1(events, tmp_path, start, start + 300_000_000,
                                      time.monotonic() + 10)
    assert result["complete"] is not broken_peer
    assert len(result["cores"]) == 3
    assert all(core["reaped"] and core["native_exit"] == 0 for core in result["cores"])
    for core in result["cores"]:
        with pytest.raises(ProcessLookupError):
            os.kill(core["pid"], 0)
    if not broken_peer:
        assert result["events"] == 66 and result["values"] == 6
        assert all(core["complete"] for core in result["cores"])
        assert result["event_sha256"] == hashlib.sha256((tmp_path / "events.jsonl").read_bytes()).hexdigest()
        assert len({core["summary"]["input_chain_keccak256"] for core in result["cores"]}) == 1
        wide = list(research.merge_phase1_values(iter(contexts), tmp_path))
        assert len(wide) == 6 and all(row["label"] == "UP" for row in wide)
        assert wide[0]["m0_samples"] == 5
        assert wide[-1]["m0_p_up"] is not None
        raw_path = tmp_path / "cores" / "M2-high" / "values.jsonl"
        lines = raw_path.read_text().splitlines()
        corrupt = json.loads(lines[0])
        corrupt["samples"] = True
        raw_path.write_text(json.dumps(corrupt) + "\n" + "\n".join(lines[1:]) + "\n")
        with pytest.raises(research.DataError, match="integer UTC"):
            list(research.merge_phase1_values(iter(contexts), tmp_path))
    else:
        assert result["events"] == 0
        assert result["error"] == "BrokenPipeError"


@pytest.mark.parametrize("field,value", [("accepted_events", True), ("values", -1),
    ("last_seq", True), ("max_active_rounds", 2), ("schema_version", "old")])
def test_new_summary_never_accepts_weak_or_boolean_counts(field, value):
    summary = dict(schema_version="btc-arb-phase1-summary/1", native_exit=0, spots=60,
        values=6, complete=True, error=None, accepted_events=66, last_seq=65,
        input_chain_keccak256="a" * 64, max_active_rounds=1)
    summary[field] = value
    with pytest.raises(research.DataError):
        research.check_summary(summary, 0, 66, 6)


def main_args(path, mode="small"):
    return ["--mode", mode, "--as-of", "2026-11-17T15:00:00Z", "--evidence-dir", str(path)]


def qualified_bundle(start, *, defect=None):
    from types import SimpleNamespace
    from skills.data.unified_data.history_types import Coverage
    bundle = Bundle(start)
    manifest = {"content_sha256": "a" * 64, "output_sha256": "b" * 64}
    bundle.content_manifest = manifest
    bundle._window = SimpleNamespace(status="complete", content_manifest=manifest,
        provenance_manifest={"fixture": True}, coverage=Coverage(stored_rows=301,
        eligible_rows=303, main_window_rows=301), missing=[], pending=[], conflicts=[])
    def verify():
        bundle.verified = True
        bundle.content_sha256 = "b" * 64
        if defect == "verify":
            raise research.DataError("fixture verification failure")
        if defect == "drift":
            bundle.content_manifest = dict(manifest, content_sha256="c" * 64)
        return bundle.content_sha256
    bundle.verify_consumed = verify
    if defect == "pending":
        bundle._window.pending.append({"round": "official"})
    if defect == "missing":
        bundle.missing.add(17)
    return bundle


@pytest.mark.parametrize("defect,expected,leaf", [
    (None, 0, "developer-small"), ("verify", 4, "developer-small"),
    ("pending", 4, "developer-small"), ("missing", 4, "developer-small"),
    ("drift", 6, "developer-small"), (None, 0, "developer-small-retry-1")])
def test_real_main_three_cores_source_authentication_and_partial(
    tmp_path, monkeypatch, defect, expected, leaf
):
    import phase1_reference as reference
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    calls = []
    bundle = qualified_bundle(research.to_us(research.START), defect=defect)
    def open_bundle(client, request):
        calls.append(request)
        return bundle
    monkeypatch.setattr(research, "open_bundle", open_bundle)
    path = tmp_path / leaf
    code = research.main(main_args(path), client=object())
    assert code == expected
    assert len(calls) == 1 and calls[0].warmup_seconds == 0
    run = json.loads((path / "run.json").read_text())
    assert run["complete"] is (expected == 0)
    assert len(run["transport"]["cores"]) == 3
    for core in run["transport"]["cores"]:
        assert core["reaped"] and type(core["native_exit"]) is int
        with pytest.raises(ProcessLookupError):
            os.kill(core["pid"], 0)
    if expected == 0:
        import csv
        rows = list(csv.DictReader((path / "samples.csv").open()))
        assert len(rows) == 42
        assert {row["model"] for row in rows} == set(research.MODELS)
        assert sum(row["p_up"] != "N/A" for row in rows if row["model"] == "M0") == 4
        assert all(row["p_up"] == "N/A" for row in rows if row["model"] in ("M1", "B1", "B2"))
        stats = json.loads((path / "statistics.json").read_text())
        assert stats["coverage"]["M0"]["theoretical_slots"] == 6
        assert stats["coverage"]["M0"]["unvalued"] == 2
        assert reference.audit_samples(path, {}, lambda: None)["slots"] == 6
        assert reference.audit_statistics(path)["statistic_series"] > 0
        monkeypatch.setattr(reference, "EVIDENCE", tmp_path)
        assert reference.main(["--mode", "vectors", "--source-dir", str(path),
            "--evidence-dir", str(path / "reference")]) == 0
        assert json.loads((path / "reference/run.json").read_text())["complete"]
    else:
        assert (path / "failure.json").exists()


@pytest.mark.parametrize("case", ["existing", "symlink", "unknown", "wrong-asof"])
def test_main_preflight_never_opens_source_or_core(tmp_path, monkeypatch, case):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("preflight started source/core")
    monkeypatch.setattr(research, "open_bundle", forbidden)
    monkeypatch.setattr(research.subprocess, "Popen", forbidden)
    path = tmp_path / "developer-small"
    argv = main_args(path)
    if case == "existing":
        path.mkdir()
        (path / "old").write_bytes(b"original")
    elif case == "symlink":
        path.symlink_to(tmp_path / "absent")
    elif case == "unknown":
        argv += ["--floor", "1"]
    else:
        argv[argv.index("--as-of") + 1] = "2026-11-17T15:00:00.000001Z"
    assert research.main(argv, client=object()) == 64
    if case == "existing":
        assert list(path.iterdir()) == [path / "old"]
        assert (path / "old").read_bytes() == b"original"
    elif case == "symlink":
        assert path.is_symlink()
    else:
        assert not path.exists()


def test_main_midrun_identity_drift_keeps_both_states(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    monkeypatch.setattr(research, "open_bundle", lambda client, request: qualified_bundle(request.main_start_us))
    original = research.capture_identity
    calls = 0
    def drift():
        nonlocal calls
        calls += 1
        identity = original()
        if calls > 1:
            identity["fixture_drift"] = True
        return identity
    monkeypatch.setattr(research, "capture_identity", drift)
    path = tmp_path / "developer-small"
    assert research.main(main_args(path), client=object()) == 6
    assert (path / "identity-start.json").read_bytes() != (path / "identity-after.json").read_bytes()


def test_main_transport_failure_retains_actual_native_and_exit_four(tmp_path, monkeypatch):
    import history_performance as transport
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    monkeypatch.setattr(research, "open_bundle", lambda client, request: qualified_bundle(request.main_start_us))
    def fail(fd, payload, deadline):
        raise BrokenPipeError("fixture")
    monkeypatch.setattr(transport, "_write_event", fail)
    path = tmp_path / "developer-small"
    assert research.main(main_args(path), client=object()) == 4
    run = json.loads((path / "run.json").read_text())
    assert all(row["native_exit"] == 0 and row["reaped"] for row in run["transport"]["cores"])


def test_main_deadline_interrupts_read_and_does_not_open_next_day(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    monkeypatch.setattr(research, "BUSINESS_SECONDS", {"small": 2., "pilot": 2., "full": 10000})
    calls = []
    def blocked(client, request):
        calls.append(request)
        time.sleep(3)
    monkeypatch.setattr(research, "open_bundle", blocked)
    path = tmp_path / "developer-small"
    assert research.main(main_args(path), client=object()) == 5
    assert len(calls) == 1
    run = json.loads((path / "run.json").read_text())
    assert not run["complete"]
    assert run["read_registry"][0]["finished"] is True


def test_reference_refuses_incomplete_run_before_claim(tmp_path, monkeypatch):
    import phase1_reference as reference
    monkeypatch.setattr(reference, "EVIDENCE", tmp_path)
    source = tmp_path / "developer-small"
    source.mkdir()
    (source / "run.json").write_text('{"complete":false}')
    assert reference.main(["--mode", "vectors", "--source-dir", str(source),
        "--evidence-dir", str(source / "reference")]) == 4
    assert not (source / "reference").exists()


def test_main_mkdir_race_preserves_winners_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    path = tmp_path / "developer-small"
    original = Path.mkdir
    def competing_mkdir(target, *args, **kwargs):
        if target == path:
            original(target)
            (target / "winner").write_bytes(b"other run")
            raise FileExistsError()
        return original(target, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", competing_mkdir)
    monkeypatch.setattr(research, "open_bundle", lambda *args: pytest.fail("source opened"))
    assert research.main(main_args(path), client=object()) == 64
    assert [entry.name for entry in path.iterdir()] == ["winner"]
    assert (path / "winner").read_bytes() == b"other run"


def test_main_signal_cancel_reaps_real_cores(tmp_path, monkeypatch):
    import signal
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    def interrupt(client, request):
        os.kill(os.getpid(), signal.SIGINT)
    monkeypatch.setattr(research, "open_bundle", interrupt)
    path = tmp_path / "developer-small"
    assert research.main(main_args(path), client=object()) == 7
    run = json.loads((path / "run.json").read_text())
    assert all(row["reaped"] and row["native_exit"] == 0 for row in run["transport"]["cores"])


def test_owned_run_disk_budget_is_not_a_source_success(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    original = research.RunBudget.__init__
    def tiny(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.disk_limit = 1
    monkeypatch.setattr(research.RunBudget, "__init__", tiny)
    monkeypatch.setattr(research, "open_bundle", lambda *args: pytest.fail("source opened"))
    path = tmp_path / "developer-small"
    assert research.main(main_args(path), client=object()) == 5
    assert not json.loads((path / "run.json").read_text())["complete"]


@pytest.mark.parametrize("defect", ["boolean", "missing", "negative"])
def test_main_corrupt_summary_read_boundary_keeps_observed_native_zero(tmp_path, monkeypatch, defect):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    monkeypatch.setattr(research, "open_bundle", lambda client, request: qualified_bundle(request.main_start_us))
    original = research.strict_loads
    def corrupt(text):
        value = original(text)
        if isinstance(value, dict) and value.get("schema_version") == "btc-arb-phase1-summary/1":
            if defect == "boolean":
                value["accepted_events"] = True
            elif defect == "negative":
                value["values"] = -1
            else:
                value.pop("last_seq")
        return value
    monkeypatch.setattr(research, "strict_loads", corrupt)
    path = tmp_path / "developer-small"
    assert research.main(main_args(path), client=object()) == 4
    run = json.loads((path / "run.json").read_text())
    assert all(row["reaped"] and row["native_exit"] == 0 for row in run["transport"]["cores"])


class PilotBundle(Bundle):
    """Explicit external-input fixture, never a claimed real pilot."""

    def iter_metadata(self):
        for index in range(288):
            self.counts["metadata"] += 1
            start = self.start + index*300_000_000
            yield HistoryInput("round_identity", "predict.fun", start, start, False,
                dict(round_id=f"fixture-{index}", starts_at_us=start, ends_at_us=start+300_000_000,
                     dataset=DATASET_ROUNDS))

    def iter_features(self):
        for index in range(288):
            self.counts["features"] += 1
            start = self.start + index*300_000_000
            yield HistoryInput("trade_kline_ohlc", "predict.fun", start, start, False,
                dict(round_id=f"fixture-{index}", start_price=60000., dataset=DATASET_ROUNDS))
        for second in range(1, 86401):
            self.counts["features"] += 1
            closed = self.start + second*1_000_000
            yield HistoryInput("trade_kline_ohlc", "binance-vision", closed-1_000_000, closed, False,
                dict(open_time_us=closed-1_000_000, close_exclusive_us=closed,
                     close=60000.+second%100, dataset=DATASET_KLINES))

    def iter_labels(self):
        for index in range(288):
            self.counts["labels"] += 1
            start = self.start + index*300_000_000
            yield HistoryInput("official_outcome", "predict.fun", start+300_000_000, start+301_000_000, False,
                dict(round_id=f"fixture-{index}", starts_at_us=start, ends_at_us=start+300_000_000,
                     official_outcome="UP" if index%2 else "DOWN", dataset=DATASET_ROUNDS))


def test_two_fixture_pilots_real_consumers_and_full_admission_only(tmp_path, monkeypatch):
    import argparse
    import phase1_reference as reference
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    monkeypatch.setattr(reference, "EVIDENCE", tmp_path)
    def open_day(client, request):
        template = qualified_bundle(request.main_start_us)
        bundle = PilotBundle(request.main_start_us)
        bundle.content_manifest = template.content_manifest
        bundle._window = template._window
        def verify():
            bundle.verified = True
            bundle.content_sha256 = "b"*64
            return bundle.content_sha256
        bundle.verify_consumed = verify
        return bundle
    monkeypatch.setattr(research, "open_bundle", open_day)
    for name in ("developer-pilot-v01", "validate-pilot-v01"):
        path = tmp_path / name
        assert research.main(main_args(path, "pilot"), client=object()) == 0
        assert reference.main(["--mode", "vectors", "--source-dir", str(path),
            "--evidence-dir", str(path / "reference")]) == 0
        run = json.loads((path / "run.json").read_text())
        assert run["transport"]["values"] == 1728 and run["transport"]["events"] == 19008
        assert reference.audit_samples(path, {}, lambda: None)["slots"] == 1728
        assert reference.audit_statistics(path)["statistic_series"] > 0
    arguments = argparse.Namespace(pilot_dir=tmp_path / "developer-pilot-v01",
        independent_pilot_dir=tmp_path / "validate-pilot-v01", remaining_seconds=17377)
    research.full_preflight(arguments)
    arguments.remaining_seconds = 1
    with pytest.raises(research.PreflightError, match="admission"):
        research.full_preflight(arguments)
    assert not (tmp_path / "full-v01").exists()


@pytest.mark.parametrize("mode,leaf", [
    ("small", "developer-small-v01"), ("small", "validate-small-v01"),
    ("pilot", "developer-pilot-v01"), ("pilot", "validate-pilot-v01"),
    ("full", "full-v01")])
def test_v01_claim_exact_leaves_and_preserve_collisions(tmp_path, monkeypatch, mode, leaf):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    path = tmp_path / leaf
    assert research.claim_run(path, mode) == path
    (path / "original").write_bytes(b"immutable")
    with pytest.raises(research.PreflightError):
        research.claim_run(path, mode)
    assert (path / "original").read_bytes() == b"immutable"
    with pytest.raises(research.PreflightError):
        research.claim_run(tmp_path / (leaf + "-retry-1"), mode)
    assert not (tmp_path / (leaf + "-retry-1")).exists()


@pytest.mark.parametrize("remaining", [17378, 18000, 0, -1, True, 17377.0, None])
def test_v01_budget_refuses_before_reading_pilots(tmp_path, monkeypatch, remaining):
    import argparse
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    monkeypatch.setattr(research, "verify_run", lambda *args: pytest.fail("pilot read"))
    arguments = argparse.Namespace(pilot_dir=tmp_path / "developer-pilot-v01",
        independent_pilot_dir=tmp_path / "validate-pilot-v01", remaining_seconds=remaining)
    with pytest.raises(research.PreflightError, match="prerequisite"):
        research.full_preflight(arguments)


@pytest.mark.parametrize("mode,leaf", [("small", "developer-pilot-v01"),
    ("pilot", "validate-small-v01"), ("full", "audit-v01")])
def test_v01_wrong_mode_cannot_claim_leaf(tmp_path, monkeypatch, mode, leaf):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    with pytest.raises(research.PreflightError):
        research.claim_run(tmp_path / leaf, mode)
    assert not (tmp_path / leaf).exists()


@pytest.mark.parametrize("leaf", ["developer-small-v01", "validate-small-v01",
    "developer-pilot-v01", "validate-pilot-v01"])
def test_v01_vectors_scope_reaches_source_binding(tmp_path, monkeypatch, leaf):
    import phase1_reference as reference
    monkeypatch.setattr(reference, "EVIDENCE", tmp_path)
    seen = []
    def bind(source):
        seen.append(source)
        raise reference.Mismatch("intentional incomplete fixture")
    monkeypatch.setattr(reference, "bind_source", bind)
    source = tmp_path / leaf
    assert reference.main(["--mode", "vectors", "--source-dir", str(source),
        "--evidence-dir", str(source / "reference")]) == 4
    assert seen == [source]
    assert not (source / "reference").exists()


@pytest.mark.parametrize("source_leaf,audit_leaf,accepted", [
    ("full-v01", "audit-v01", True), ("full", "audit-v01", False),
    ("full-v01", "audit", False)])
def test_v01_audit_publish_exact_pair_only(tmp_path, monkeypatch, source_leaf, audit_leaf, accepted):
    import argparse
    import phase1_reference as reference
    monkeypatch.setattr(research, "EVIDENCE", tmp_path / "evidence")
    monkeypatch.setattr(reference, "EVIDENCE", research.EVIDENCE)
    source, audit = research.EVIDENCE / source_leaf, research.EVIDENCE / audit_leaf
    seen = []
    def bind(path):
        seen.append(path)
        raise reference.Mismatch("intentional incomplete fixture")
    monkeypatch.setattr(reference, "bind_source", bind)
    assert reference.main(["--mode", "audit", "--source-dir", str(source),
        "--evidence-dir", str(audit)]) == (4 if accepted else 64)
    assert seen == ([source] if accepted else [])
    assert not audit.exists()
    def verify(path):
        seen.append(path)
        raise RuntimeError("source binding reached")
    monkeypatch.setattr(research, "verify_run", verify)
    arguments = argparse.Namespace(source_dir=source, evidence_dir=source, audit_dir=audit,
        report=tmp_path / "report.md")
    if accepted:
        with pytest.raises(RuntimeError, match="source binding reached"):
            research.publish(arguments)
        assert seen == [source, source]
    else:
        with pytest.raises(research.PreflightError, match="publish scope"):
            research.publish(arguments)
        assert not seen
    assert not arguments.report.exists()


def test_publish_binds_actual_source_and_formats_display_only(tmp_path, monkeypatch):
    import argparse
    monkeypatch.setattr(research, "EVIDENCE", tmp_path / "evidence")
    source = research.EVIDENCE / "full-v01"
    audit = research.EVIDENCE / "audit-v01"
    source.mkdir(parents=True)
    audit.mkdir()
    raw = dict(rows=[], diagnostic_conflicts=[],
        effect_size=dict(difference=-.0010313598117930865,
            interval=dict(lo95=-.0015086836321085322, hi95=-.0006221704090211243)),
        complexity_cost=dict(fitted_parameters=2, fits_recorded=9,
            fit_wall_seconds=8.726426793960854),
        proxy_error="UNKNOWN", economic_value_status="NOT_VERIFIED")
    research._write_new_json(source / "run.json", dict(mode="full"))
    research._write_new_json(source / "statistics.json", raw)
    research._write_new_json(source / "parameters.json", {})
    research._write_new_json(audit / "run.json", dict(complete=True, exit_code=0,
        source_run_sha256=research.digest(source / "run.json"), artifacts={}))
    research._write_new_json(audit / "reference.json", dict(passed=True,
        research_verdict="SUPPORT_FURTHER_VALIDATION"))
    originals = {path: path.read_bytes() for path in (source / "statistics.json",
        source / "run.json", audit / "run.json")}
    monkeypatch.setattr(research, "verify_run", lambda path: dict(mode="full", wall_seconds=1.))
    report = tmp_path / "report.md"
    args = argparse.Namespace(source_dir=source, evidence_dir=source,
        audit_dir=audit, report=report)
    assert research.publish(args) == 0
    text = report.read_text()
    assert "三流完整消费与三核认证见evidence/full-v01。" in text
    assert "认证见evidence/full。" not in text
    for expected in ("-0.00103136", "-0.00150868", "-0.00062217", "8.72642679"):
        assert expected in text
    for raw_float in ("-0.0010313598117930865", "-0.0015086836321085322",
                      "-0.0006221704090211243", "8.726426793960854"):
        assert raw_float not in text
    assert all(path.read_bytes() == before for path, before in originals.items())


def test_publish_refuses_existing_target_without_source_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path / "evidence")
    output = tmp_path / "report.md"
    output.write_bytes(b"existing report")
    monkeypatch.setattr(research, "verify_run", lambda *args: pytest.fail("source read after output conflict"))
    args = ["--mode", "publish", "--as-of", "2026-11-17T15:00:00Z", "--evidence-dir", str(tmp_path / "evidence/full-v01"),
        "--source-dir", str(tmp_path / "evidence/full-v01"), "--audit-dir", str(tmp_path / "evidence/audit-v01"), "--report", str(output)]
    assert research.main(args) == 64
    assert output.read_bytes() == b"existing report"


@pytest.mark.parametrize("mode,leaf", [
    ("small", "developer-small-v01"), ("small", "validate-small-v01"),
    ("pilot", "developer-pilot-v01"), ("pilot", "validate-pilot-v01"),
    ("full", "full-v01")])
def test_v01_claims_only_fresh_exact_leaves(tmp_path, monkeypatch, mode, leaf):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    path = tmp_path / leaf
    assert research.claim_run(path, mode) == path
    marker = path / "keep"
    marker.write_bytes(b"original")
    with pytest.raises(research.PreflightError):
        research.claim_run(path, mode)
    assert marker.read_bytes() == b"original"
    with pytest.raises(research.PreflightError):
        research.claim_run(tmp_path / (leaf + "-unapproved"), mode)


@pytest.mark.parametrize("remaining", [17378, 18000, True, 0])
def test_v01_full_refuses_reset_budget_before_source_reads(tmp_path, monkeypatch, remaining):
    import argparse
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    monkeypatch.setattr(research, "verify_run", lambda *args: pytest.fail("read before budget check"))
    arguments = argparse.Namespace(pilot_dir=tmp_path / "developer-pilot-v01",
        independent_pilot_dir=tmp_path / "validate-pilot-v01", remaining_seconds=remaining)
    with pytest.raises(research.PreflightError, match="prerequisite"):
        research.full_preflight(arguments)


def test_actual_open_bundle_boundary_supplies_explicit_utc_to_facade():
    from types import SimpleNamespace
    from skills.data.unified_data.history_types import HistoryRequest, parse_utc
    received = []
    class ExplicitUTCClient:
        def read_btc5m_history(self, start_utc, end_utc, **kwargs):
            received.extend((parse_utc(start_utc), parse_utc(end_utc), parse_utc(kwargs["as_of_utc"])))
            assert kwargs["availability_mode"] == "event-time-proxy"
            return SimpleNamespace(content_manifest={}, content_sha256=None,
                availability_assumptions=[], iter_features=lambda: iter(()),
                iter_round_metadata=lambda: iter(()), iter_labels=lambda: iter(()))
    request = HistoryRequest(research.START, research.START+research.timedelta(seconds=300),
        research.AS_OF, warmup_seconds=0, availability_mode="event-time-proxy")
    research.open_bundle(ExplicitUTCClient(), request)
    assert received == [research.START, research.START+research.timedelta(seconds=300), research.AS_OF]
    assert request.start_utc.tzinfo is None  # The internal integer-time DTO is unchanged.


def test_facade_batch_uses_remaining_budget_not_a_single_page_timeout(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import pymongo
    seen = []
    @contextmanager
    def timeout(seconds):
        seen.append(seconds)
        yield
    monkeypatch.setattr(pymongo, "timeout", timeout)
    monkeypatch.setattr(research.time, "monotonic", lambda: 0.0)
    guard = SimpleNamespace(deadline=120.0, check=lambda: None)
    assert research._bounded_call(guard, lambda: "complete-window") == "complete-window"
    assert seen == [120.0]


def test_facade_bson_int64_is_normalized_without_accepting_bool():
    from bson.int64 import Int64
    value = research._required_int(Int64(1786320000000000))
    assert type(value) is int and value == 1786320000000000
    for invalid in (True, False, 1.0, "1", -1, Int64(-1)):
        with pytest.raises(research.DataError, match="invalid integer UTC"):
            research._required_int(invalid)


def test_source_manifest_preserves_typed_values_at_json_boundary(tmp_path, monkeypatch):
    from decimal import Decimal
    from typing import Any
    from skills.data.unified_data.history_types import canonical_json
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    bundle: Any = qualified_bundle(research.to_us(research.START))
    typed = {"observed_at": research.START, "source_decimal": Decimal("1.2300")}
    bundle.content_manifest["typed_provenance"] = typed
    bundle._window.content_manifest = bundle.content_manifest
    bundle._window.provenance_manifest = typed
    monkeypatch.setattr(research, "open_bundle", lambda client, request: bundle)
    output = tmp_path / "developer-small"
    assert research.main(main_args(output), client=object()) == 0
    source = json.loads((output / "source-2026-08-10.json").read_text())
    expected = json.loads(canonical_json(typed))
    assert source["content_manifest_start"]["typed_provenance"] == expected
    assert source["content_manifest_after"]["typed_provenance"] == expected
    assert source["provenance_manifest"] == expected
    assert bundle.content_manifest["typed_provenance"] is typed
    assert isinstance(typed["source_decimal"], Decimal)


def test_source_failure_records_code_location_without_private_message(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "EVIDENCE", tmp_path)
    def broken_source(client, request):
        raise TypeError("private-source-details-must-not-be-recorded")
    monkeypatch.setattr(research, "open_bundle", broken_source)
    output = tmp_path / "developer-small"
    assert research.main(main_args(output), client=object()) == 2
    text = (output / "run.json").read_text()
    transport = json.loads(text)["transport"]
    assert transport["error"] == "TypeError"
    assert transport["failure_location"]["function"] == "broken_source"
    assert transport["failure_location"]["file"] == Path(__file__).name
    assert transport["failure_location"]["line"] > 0
    assert "private-source-details" not in text
