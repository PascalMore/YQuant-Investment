"""Performance-path tests: result reuse, shared input, bounded prefetch.

Synthetic bundles are counterexamples only; the CLI pilot uses the real facade.
"""
import importlib.util
import json
import os
import signal
import sys
import threading
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

LAB = Path(__file__).resolve().parents[1]
ROOT = LAB.parents[4]


def load(name, path):
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


perf = load("btc5m_history_performance", LAB / "history_performance.py")
research = load("btc5m_history_research", LAB / "history_research.py")
LEGACY = (ROOT / "data/reports/2026-11-12-btc5m-native-history-research"
          "/evidence/research/full-run3646")


def bundle(label="UP", metadata_at=None, candle_count=300):
    base = research.to_us(research.START.replace(tzinfo=None))

    def row(payload, at):
        return SimpleNamespace(payload=payload, available_at_us=at)

    identity = row(dict(round_id="123", starts_at_us=base, ends_at_us=base + 300_000_000),
                   base if metadata_at is None else base + metadata_at)
    strike = row(dict(dataset=research.DATASET_ROUNDS, round_id="123",
                       start_price=Decimal("100.25")), base)
    candles = [row(dict(dataset=research.DATASET_KLINES,
                        close_exclusive_us=base + (index + 1) * 1_000_000,
                        close=Decimal("101")), base + (index + 1) * 1_000_000)
               for index in range(candle_count)]
    labels = [row(dict(round_id="123", starts_at_us=base, ends_at_us=base + 300_000_000,
                       official_outcome=label), base + 360_000_000)]
    return SimpleNamespace(iter_metadata=lambda: iter([identity]),
                           iter_features=lambda: iter([strike, *candles]),
                           iter_labels=lambda: iter(labels),
                           verify_consumed=lambda: "synthetic-content",
                           coverage=SimpleNamespace(stored_rows=301),
                           missing=[], pending=[], conflicts=[],
                           content_manifest={}, provenance_manifest={})


def copy_archive(tmp_path):
    """Copy the signed-off archive so a test can tamper with one file."""
    import shutil

    target = tmp_path / "archive"
    shutil.copytree(LEGACY, target)
    return target


def trusted_for(archive):
    """Return the trusted hashes of a tampered copy, so the content gate is skipped.

    The file hashes are recomputed here only so the test can reach the *content*
    gate; the production path never trusts a self-computed hash.
    """
    return {name: perf.sha256_file(archive / name) for name in perf.TRUSTED_ARCHIVE_SHA256}


def allow_evidence_root(tmp_path, monkeypatch):
    """Point the authorized evidence subtree at a temporary directory."""
    root = tmp_path / "perf-root"
    (root / "evidence").mkdir(parents=True)
    monkeypatch.setattr(perf, "PERF_ROOT", root)
    return root


# ------------------------------------------------------------------ result reuse


def test_rescore_rebuilds_archived_statistics_without_rust_or_mongo(tmp_path):
    result = perf.rescore(LEGACY, tmp_path / "rescore", None)
    assert result["all_identical"] is True
    assert result["db_calls"] == 0 and result["core_calls"] == 0
    assert result["samples_rows"] == 162432
    identity = json.loads((tmp_path / "rescore" / "identity.json").read_text())
    assert identity["samples_sha256"] == perf.sha256_file(LEGACY / "samples.csv")
    assert identity["capture_time_identities"]
    assert "NOT_RECHECKED" in identity["current_raw_database_state"]
    assert (tmp_path / "rescore" / "comparison.csv").exists()


def test_rescore_refuses_a_hash_mismatch(tmp_path):
    with pytest.raises(ValueError, match="hash mismatch"):
        perf.rescore(LEGACY, tmp_path / "rescore", "0" * 64)


def test_evidence_directory_must_stay_inside_the_authorized_subtree(tmp_path):
    with pytest.raises(ValueError, match="authorized performance subtree"):
        perf._require_subtree(tmp_path / "elsewhere")


def test_validate_subtree_is_allowed_for_independent_verification():
    allowed = perf.PERF_ROOT / "evidence" / "validate" / "run-01"
    assert perf._require_subtree(allowed) == allowed.resolve()


def test_fix1_subtree_is_allowed_for_this_round():
    allowed = perf.PERF_ROOT / "evidence" / "fix1" / "run-01"
    assert perf._require_subtree(allowed) == allowed.resolve()


def test_instances_are_capped_at_three(capsys):
    assert perf.MAX_INSTANCES == 3
    code = perf.main(["--mode", "window", "--instances", "4",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir",
                       str(perf.PERF_ROOT / "evidence" / "validate" / "cap-check")])
    assert code == 2
    assert "performance run failed: ValueError" in capsys.readouterr().err


# ------------------------------------------------------- F1: trusted identity gate


def test_rescore_refuses_an_archive_whose_samples_were_edited(tmp_path):
    """A self-computed hash cannot certify a modified sample file."""
    archive = copy_archive(tmp_path)
    rows = (archive / "samples.csv").read_text().splitlines()
    rows[1] = rows[1].replace('"123"', '"999"')
    (archive / "samples.csv").write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError, match="untrusted archive"):
        perf.rescore(archive, tmp_path / "rescore", None)


def test_rescore_refuses_a_non_statistical_identity_change(tmp_path):
    """Changing only an identity column is still a hash break, not a pass."""
    archive = copy_archive(tmp_path)
    text = (archive / "samples.csv").read_text()
    (archive / "samples.csv").write_text(text.replace(",123,", ",124,", 1))
    with pytest.raises(ValueError, match="untrusted archive"):
        perf.rescore(archive, tmp_path / "rescore", None)


def test_rescore_refuses_empty_capture_time_identities(tmp_path):
    archive = copy_archive(tmp_path)
    (archive / "identities.json").write_text("{}")
    with pytest.raises(ValueError, match="empty capture-time identities"):
        perf.rescore(archive, tmp_path / "rescore", None, trusted_for(archive))


def test_rescore_refuses_missing_capture_time_identities(tmp_path):
    archive = copy_archive(tmp_path)
    identities = json.loads((archive / "identities.json").read_text())
    identities.pop("skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/"
                    "history_research.py")
    (archive / "identities.json").write_text(json.dumps(identities))
    with pytest.raises(ValueError, match="missing capture-time identities"):
        perf.rescore(archive, tmp_path / "rescore", None, trusted_for(archive))


def test_rescore_refuses_a_config_window_or_manifest_mismatch(tmp_path):
    archive = copy_archive(tmp_path)
    params = json.loads((archive / "params.json").read_text())
    params["config"]["vol_floor"] = 0.0005
    (archive / "params.json").write_text(json.dumps(params))
    with pytest.raises(ValueError, match="untrusted archive"):
        perf.rescore(archive, tmp_path / "rescore", None, trusted_for(archive))


def test_rescore_refuses_a_manifest_window_mismatch(tmp_path):
    archive = copy_archive(tmp_path)
    manifests = json.loads((archive / "source-manifests.json").read_text())
    manifests[0]["day"] = "1999-01-01"
    (archive / "source-manifests.json").write_text(json.dumps(manifests))
    with pytest.raises(ValueError, match="untrusted archive"):
        perf.rescore(archive, tmp_path / "rescore", None, trusted_for(archive))


def test_rescore_refuses_an_untrusted_source_directory(tmp_path):
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    with pytest.raises(ValueError, match="untrusted archive"):
        perf.rescore(empty, tmp_path / "rescore", None)


def test_sample_identity_gate_rejects_a_broken_round(tmp_path):
    params = json.loads((LEGACY / "params.json").read_text())
    rows = perf.read_samples(LEGACY / "samples.csv")
    rows[0]["ends_at_ms"] = rows[0]["starts_at_ms"] + 1
    with pytest.raises(ValueError, match="invalid round duration"):
        perf.verify_sample_identity(rows, params)


def test_rescore_does_not_call_the_database_or_the_core(tmp_path, monkeypatch):
    def refuse():
        raise AssertionError("rescore must not open the database")

    monkeypatch.setattr(perf, "_open_client", refuse)
    monkeypatch.setattr(perf, "_start_core", refuse)
    result = perf.rescore(LEGACY, tmp_path / "rescore", None)
    assert result["db_calls"] == 0
    assert result["core_calls"] == 0


def test_the_rescore_mode_also_persists_its_run_identity(tmp_path, monkeypatch):
    root = allow_evidence_root(tmp_path, monkeypatch)
    code = perf.main(["--mode", "rescore",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 0
    identity = json.loads((root / "evidence" / "run" / "identity-start.json").read_text())
    assert identity["cwd"] == os.getcwd()
    assert "--mode" in identity["argv"]
    assert "rescore" in identity["argv"]
    source = "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/" \
             "history_performance.py"
    assert source in identity["sources"]
    after = json.loads((root / "evidence" / "run" / "identity-after.json").read_text())
    assert after["sources_unchanged"] is True


# -------------------------------------------------------------------- shared input


def test_shared_broadcast_gives_identical_cores_identical_input(tmp_path, monkeypatch):
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    instances = [perf.Instance(name="core-1"), perf.Instance(name="core-2")]
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END, instances=instances,
                                 output_dir=tmp_path / "shared", budget_seconds=120,
                                 prefetch=False, label="shared", strategy="shared")
    assert metrics["events"] == 306
    hashes = {item["event_sha256"] for item in metrics["instances"]}
    assert len(hashes) == 1
    values = {item["values_sha256"] for item in metrics["instances"]}
    assert len(values) == 1
    assert all(item["native_exit"] == 0 for item in metrics["instances"])
    assert all(item["status"] == "EXECUTED" for item in metrics["instances"])
    assert metrics["bundle_opens"] == 1
    assert metrics["complete"] is True


def test_independent_repeated_reads_match_the_shared_arm(tmp_path, monkeypatch):
    import history_input

    opens = []

    def opener(client, request):
        opens.append(request.start_utc)
        return bundle()

    monkeypatch.setattr(history_input, "iter_history_input", opener)
    shared = perf.run_instances(None, start=research.START,
                                end=research.START + timedelta(minutes=5),
                                as_of=research.END,
                                instances=[perf.Instance(name="core-1"),
                                           perf.Instance(name="core-2")],
                                output_dir=tmp_path / "shared", budget_seconds=120,
                                prefetch=False, label="shared", strategy="shared")
    opens.clear()
    independent = perf.run_independent(None, start=research.START,
                                       end=research.START + timedelta(minutes=5),
                                       as_of=research.END,
                                       instances=[perf.Instance(name="core-1"),
                                                  perf.Instance(name="core-2")],
                                       output_dir=tmp_path / "independent",
                                       budget_seconds=120, label="independent")
    assert len(opens) == 2, "the control arm must read the facade once per instance"
    assert shared["bundle_opens"] == 1
    assert {item["values_sha256"] for item in independent["instances"]} == \
           {item["values_sha256"] for item in shared["instances"]}
    assert {item["event_sha256"] for item in independent["instances"]} == \
           {item["event_sha256"] for item in shared["instances"]}


def test_a_different_vol_floor_is_refused_by_the_rust_config_gate(tmp_path):
    """The frozen parameters are not relaxed for a performance experiment."""
    import subprocess

    config = json.loads((LAB / "config.json").read_text())
    assert perf.instance_config(config)["vol_floor"] == perf.FROZEN_VOL_FLOOR
    relaxed = dict(config, vol_floor=0.000025)
    config_path = tmp_path / "relaxed.json"
    config_path.write_text(json.dumps(relaxed))
    result = subprocess.run(
        [str(research.BINARY), "--config", str(config_path), "--input", "-",
         "--output", str(tmp_path / "values.jsonl"), "--summary", str(tmp_path / "summary.json"),
         "--from-ms", "0", "--to-ms", "1000"],
        input="", capture_output=True, text=True, timeout=10)
    assert result.returncode == 64
    assert not (tmp_path / "values.jsonl").exists()


# ------------------------------------------------- F2: failure propagates to the CLI


def test_a_refused_core_makes_the_batch_incomplete(tmp_path, monkeypatch):
    """The counterexample travels through run_instances, not a direct Rust call."""
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    instances = [perf.Instance(name="core-1", vol_floor=0.000025),
                 perf.Instance(name="core-2")]
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END, instances=instances,
                                 output_dir=tmp_path / "shared", budget_seconds=60,
                                 prefetch=False, label="shared", strategy="shared")
    refused = [item for item in metrics["instances"] if item["name"] == "core-1"][0]
    healthy = [item for item in metrics["instances"] if item["name"] == "core-2"][0]
    assert refused["native_exit"] == 64
    assert refused["status"] == "REFUSED"
    assert refused["complete"] is False
    assert healthy["status"] == "EXECUTED"
    assert metrics["complete"] is False


def test_a_missing_values_output_fails_the_instance(tmp_path):
    state = {"instance": perf.Instance(name="core-1"), "dir": tmp_path,
             "process": SimpleNamespace(pid=0, returncode=0, poll=lambda: 0),
             "stderr": SimpleNamespace(close=lambda: None), "write_fd": -1,
             "error": None, "fd_closed": True, "handles_closed": True,
             "reaped": True, "native_exit": 0}
    perf._finish_core(state, "hash", 1, time.monotonic() + 1)
    assert state["instance"].status == "FAILED"
    assert "missing values" in state["instance"].error


def test_a_partial_summary_fails_the_instance(tmp_path):
    (tmp_path / "rust-summary.json").write_text(json.dumps({"complete": False}))
    (tmp_path / "values.jsonl").write_text("{}\n")
    state = {"instance": perf.Instance(name="core-1"), "dir": tmp_path,
             "process": SimpleNamespace(pid=0, returncode=0, poll=lambda: 0),
             "stderr": SimpleNamespace(close=lambda: None), "write_fd": -1,
             "error": None, "fd_closed": True, "handles_closed": True,
             "reaped": True, "native_exit": 0}
    perf._finish_core(state, "hash", 1, time.monotonic() + 1)
    assert state["instance"].status == "FAILED"
    assert "incomplete native summary" in state["instance"].error


def test_main_fails_when_an_arm_did_not_complete(tmp_path, monkeypatch):
    root = allow_evidence_root(tmp_path, monkeypatch)

    def incomplete(*args, **kwargs):
        return dict(label="shared", complete=False, instances=[], bundle_opens=0,
                    events=0, event_sha256="", contexts=0, row_counts={},
                    day_content_sha256={}, wall_seconds=0.0, prepare_seconds=0.0,
                    verify_seconds=0.0, instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", incomplete)
    monkeypatch.setattr(perf, "run_independent", incomplete)
    code = perf.main(["--mode", "candidates", "--instances", "1", "--strategy", "serial",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 4
    runs = json.loads((root / "evidence" / "run" / "runs.json").read_text())
    assert all(run["complete"] is False for run in runs)


# -------------------------------------------------------- F3: bounded deadline


def test_a_blocked_core_cannot_freeze_the_writer(tmp_path, monkeypatch):
    """A core that never reads stdin must not block the orchestrator forever."""
    import history_input

    script = tmp_path / "never-exits.sh"
    script.write_text("#!/bin/sh\nsleep 300\n")
    script.chmod(0o755)
    monkeypatch.setattr(perf, "BINARY", script)
    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle(candle_count=20000))
    instances = [perf.Instance(name="core-1")]
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        perf.run_instances(None, start=research.START,
                           end=research.START + timedelta(hours=6),
                           as_of=research.END, instances=instances,
                           output_dir=tmp_path / "blocked", budget_seconds=5,
                           prefetch=False, label="blocked", strategy="serial")
    assert time.monotonic() - started < 90, "the deadline must bound the run"
    assert instances[0].status == "FAILED"
    assert instances[0].native_exit != 0


def test_a_core_that_never_exits_is_terminated_and_reaped(tmp_path, monkeypatch):
    script = tmp_path / "sleepy.sh"
    pid_file = tmp_path / "child.pid"
    script.write_text(f"#!/bin/sh\necho $$ > {pid_file}\nsleep 300\n")
    script.chmod(0o755)
    monkeypatch.setattr(perf, "BINARY", script)
    instance = perf.Instance(name="core-1")
    state = perf._start_core(instance, tmp_path / "core", 0, 1)
    deadline = time.monotonic() + 2
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    child_pid = int(pid_file.read_text().strip())
    outcome = perf._finish_core(state, "hash", 0, time.monotonic() + 0.2)
    perf._close_handles(state)
    assert outcome["terminated"] is True
    assert instance.native_exit != 0
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_an_unreclaimed_prefetch_read_blocks_the_batch_from_succeeding(tmp_path,
                                                                     monkeypatch):
    release = threading.Event()

    def slow_open(day):
        release.wait(10)
        return bundle()

    prefetcher = perf.BoundedPrefetcher(None, research.END)
    prefetcher._open = slow_open
    prefetcher.submit(research.START)
    with pytest.raises(TimeoutError, match="did not arrive"):
        prefetcher.take(research.START, timeout=0.2)
    closed = prefetcher.close(join_timeout=0.2)
    assert closed["unreclaimed"] == 1
    assert closed["still_tracked"] == 1, "an unreclaimed read must stay visible"
    release.set()


def test_a_prefetch_cancel_prevents_the_read_from_running():
    opened = []

    def slow_open(day):
        opened.append(day)
        return bundle()

    prefetcher = perf.BoundedPrefetcher(None, perf.END)
    prefetcher._open = slow_open
    day = research.START
    prefetcher.submit(day)
    closed = prefetcher.close(join_timeout=0.2)
    assert closed["unreclaimed"] == 0
    assert closed["cancelled"] == 1
    assert opened == [], "a cancelled pending day must never run"


# --------------------------------------------------- F4: complete sample evidence


def test_each_core_exports_its_own_complete_samples(tmp_path, monkeypatch):
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    instances = [perf.Instance(name="core-1"), perf.Instance(name="core-2")]
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END, instances=instances,
                                 output_dir=tmp_path / "shared", budget_seconds=120,
                                 prefetch=False, label="shared", strategy="shared")
    assert metrics["instance_comparison"]["identical"] is True
    for name in ("core-1", "core-2"):
        rows = perf.read_sample_csv(tmp_path / "shared" / name / "samples.csv")
        assert rows, "each core must export its own samples"
        for column in ("label", "label_available_at_us", "reason", "partition", "day"):
            assert column in rows[0]
        assert (tmp_path / "shared" / name / "comparison.csv").exists()
    left = perf.read_sample_csv(tmp_path / "shared" / "core-1" / "samples.csv")
    right = perf.read_sample_csv(tmp_path / "shared" / "core-2" / "samples.csv")
    check = perf.compare_sample_rows(left, right, research.SAMPLE_COLUMNS)
    assert check["identical"] is True


def test_the_sample_comparison_detects_a_changed_label():
    left = [dict(round_id="1", label="UP"), dict(round_id="2", label="DOWN")]
    right = [dict(round_id="1", label="DRAW"), dict(round_id="2", label="DOWN")]
    check = perf.compare_sample_rows(left, right, ("round_id", "label"))
    assert check["identical"] is False
    assert "label" in check["reason"]


def test_each_day_keeps_its_facade_coverage_and_gap_manifest(tmp_path, monkeypatch):
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END,
                                 instances=[perf.Instance(name="core-1")],
                                 output_dir=tmp_path / "shared", budget_seconds=120,
                                 prefetch=False, label="shared", strategy="shared")
    manifest = json.loads((tmp_path / "shared" / "source-2026-08-10.json").read_text())
    assert manifest["verified"] is True
    for key in ("coverage", "missing", "pending", "conflicts", "row_counts"):
        assert key in manifest
    assert metrics["day_content_sha256"]


# ------------------------------------------------------------ F5: default strategy


def test_the_default_strategy_is_serial_and_prefetch_is_opt_in(tmp_path, monkeypatch):
    root = allow_evidence_root(tmp_path, monkeypatch)
    strategies = []

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        strategies.append(strategy)
        return dict(label=label, strategy=strategy, complete=True, instances=[],
                    bundle_opens=1, events=1, event_sha256="h", contexts=0,
                    row_counts={}, day_content_sha256={}, wall_seconds=0.0,
                    prepare_seconds=0.0, verify_seconds=0.0,
                    instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    monkeypatch.setattr(perf, "run_independent", fake_run)
    code = perf.main(["--mode", "window", "--instances", "1",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 0
    assert strategies == ["serial"], "prefetch must not run unless asked for"


def test_the_candidates_mode_always_runs_the_independent_control_arm(tmp_path,
                                                                     monkeypatch):
    root = allow_evidence_root(tmp_path, monkeypatch)
    labels = []

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        labels.append(label)
        return dict(label=label, strategy=strategy, complete=True, instances=[],
                    bundle_opens=1, events=1, event_sha256="h", contexts=0,
                    row_counts={}, day_content_sha256={}, wall_seconds=0.0,
                    prepare_seconds=0.0, verify_seconds=0.0,
                    instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    monkeypatch.setattr(perf, "run_independent", fake_run)
    code = perf.main(["--mode", "candidates", "--instances", "1", "--strategy", "serial",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 0
    assert labels == ["shared", "independent"]


# ------------------------------------------------------- F6: run identity binding


def test_a_run_persists_its_argv_cwd_and_source_identity(tmp_path, monkeypatch):
    root = allow_evidence_root(tmp_path, monkeypatch)

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        return dict(label=label, strategy=strategy, complete=True, instances=[],
                    bundle_opens=1, events=1, event_sha256="h", contexts=0,
                    row_counts={}, day_content_sha256={}, wall_seconds=0.0,
                    prepare_seconds=0.0, verify_seconds=0.0,
                    instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    code = perf.main(["--mode", "window", "--instances", "1",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 0
    identity = json.loads((root / "evidence" / "run" / "identity-start.json").read_text())
    assert identity["cwd"] == os.getcwd()
    assert "--mode" in identity["argv"]
    assert "window" in identity["argv"]
    source = "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/" \
             "history_performance.py"
    assert source in identity["sources"]
    assert len(identity["sources"][source]) == 64


# ---------------------------------------------------- F7: independent arm accounting


def test_the_independent_arm_reports_every_part(tmp_path, monkeypatch):
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    independent = perf.run_independent(None, start=research.START,
                                       end=research.START + timedelta(minutes=5),
                                       as_of=research.END,
                                       instances=[perf.Instance(name="core-1"),
                                                  perf.Instance(name="core-2")],
                                       output_dir=tmp_path / "independent",
                                       budget_seconds=120, label="independent")
    assert independent["bundle_opens"] == 2
    assert len(independent["parts"]) == 2
    assert independent["content_identities_consistent"] is True
    assert independent["row_counts"]["features"] == 2 * 301
    assert independent["per_instance_events"]["core-1"] > 0
    assert "parent_ru_maxrss_note" in independent


# ------------------------------------------------------------------ bounded prefetch


def test_prefetch_keeps_pending_results_bounded():
    gate = threading.Event()

    def slow_open(day):
        gate.wait(5)
        return bundle()

    prefetcher = perf.BoundedPrefetcher(None, perf.END)
    prefetcher._open = slow_open
    days = [research.START + timedelta(days=index) for index in range(5)]
    for day in days[:perf.MAX_PREFETCH_DEPTH]:
        prefetcher.submit(day)
    assert len(prefetcher._tasks) == perf.MAX_PREFETCH_DEPTH
    gate.set()
    taken = prefetcher.take(days[0], timeout=5)
    assert taken is not None
    prefetcher.close()


def test_prefetch_cancel_reports_a_running_read_as_unreclaimable():
    started = threading.Event()
    release = threading.Event()

    def slow_open(day):
        started.set()
        release.wait(5)
        return bundle()

    prefetcher = perf.BoundedPrefetcher(None, perf.END)
    prefetcher._open = slow_open
    day = research.START
    prefetcher.submit(day)
    with pytest.raises(TimeoutError, match="did not arrive"):
        prefetcher.take(day, timeout=0.2)
    assert started.is_set()
    closed = prefetcher.close(join_timeout=0.2)
    assert closed["unreclaimed"] == 1
    assert closed["cancelled"] == 0
    assert closed["still_tracked"] == 1, "an unreclaimed read must stay visible"
    release.set()


def test_prefetch_close_joins_a_finished_read_as_reclaimed():
    prefetcher = perf.BoundedPrefetcher(None, perf.END)
    prefetcher._open = lambda day: bundle()
    day = research.START
    prefetcher.submit(day)
    assert prefetcher.take(day, timeout=5) is not None
    closed = prefetcher.close(join_timeout=1.0)
    assert closed["reclaimed"] == 0
    assert closed["unreclaimed"] == 0


def test_a_prefetch_timeout_keeps_the_running_task_tracked():
    release = threading.Event()

    def slow_open(day):
        release.wait(5)
        return bundle()

    prefetcher = perf.BoundedPrefetcher(None, perf.END)
    prefetcher._open = slow_open
    day = research.START
    prefetcher.submit(day)
    with pytest.raises(TimeoutError, match="did not arrive"):
        prefetcher.take(day, timeout=0.2)
    assert day in prefetcher._tasks, "a timed-out read must stay tracked for close()"
    closed = prefetcher.close(join_timeout=0.2)
    assert closed["unreclaimed"] == 1
    release.set()


def test_prefetch_error_propagates_to_the_consumer():
    def failing_open(day):
        raise RuntimeError("read failed")

    prefetcher = perf.BoundedPrefetcher(None, perf.END)
    prefetcher._open = failing_open
    day = research.START
    prefetcher.submit(day)
    with pytest.raises(RuntimeError, match="read failed"):
        prefetcher.take(day, timeout=5)


def test_deadline_is_enforced():
    with pytest.raises(TimeoutError, match="budget"):
        perf.check_deadline(time.monotonic() - 1)


# ------------------------------------------------- Fix2: R2-1 failure persistence


def _state_for(tmp_path, *, values=None, summary=None, native_exit=0):
    """Build a finished-core state whose outputs are under the test's control."""
    if values is not None:
        (tmp_path / "values.jsonl").write_text(values)
    if summary is not None:
        (tmp_path / "rust-summary.json").write_text(json.dumps(summary))
    return {"instance": perf.Instance(name="core-1"), "dir": tmp_path,
            "process": SimpleNamespace(pid=0, returncode=native_exit, poll=lambda: 0),
            "stderr": SimpleNamespace(close=lambda: None), "write_fd": -1,
            "error": None, "fd_closed": True, "handles_closed": True,
            "reaped": True, "native_exit": native_exit}


def _complete_summary(values=1, spots=0):
    """Return a summary that satisfies the Rust summary contract."""
    return {"native_exit": 0, "spots": spots, "values": values,
            "complete": True, "error": None}


def test_a_summary_that_only_claims_completion_fails_the_instance(tmp_path):
    """`{"complete": true}` alone is not a proof of a complete native run."""
    state = _state_for(tmp_path, values="{}\n", summary={"complete": True})
    perf._finish_core(state, "hash", 1, time.monotonic() + 1)
    assert state["instance"].status == "FAILED"
    assert "missing fields" in state["instance"].error


def test_a_summary_whose_value_count_disagrees_fails_the_instance(tmp_path):
    state = _state_for(tmp_path, values="{}\n", summary=_complete_summary(values=7))
    perf._finish_core(state, "hash", 1, time.monotonic() + 1)
    assert state["instance"].status == "FAILED"
    assert "value count" in state["instance"].error


def test_a_summary_with_a_boolean_in_an_integer_field_fails_the_instance(tmp_path):
    summary = _complete_summary(values=1)
    summary["values"] = True
    state = _state_for(tmp_path, values="{}\n", summary=summary)
    perf._finish_core(state, "hash", 1, time.monotonic() + 1)
    assert state["instance"].status == "FAILED"
    assert "not an integer" in state["instance"].error


def test_a_summary_with_a_nonzero_native_exit_fails_the_instance(tmp_path):
    summary = _complete_summary(values=1)
    summary["native_exit"] = 2
    state = _state_for(tmp_path, values="{}\n", summary=summary)
    perf._finish_core(state, "hash", 1, time.monotonic() + 1)
    assert state["instance"].status == "FAILED"
    assert "nonzero native exit" in state["instance"].error


def test_a_complete_summary_passes_the_instance(tmp_path):
    state = _state_for(tmp_path, values="{}\n", summary=_complete_summary(values=1))
    perf._finish_core(state, "hash", 1, time.monotonic() + 1)
    assert state["instance"].status == "EXECUTED"
    assert state["instance"].reaped is True


def test_a_failed_run_persists_its_partial_state_before_raising(tmp_path, monkeypatch):
    """The failure evidence is written before the original exception escapes."""
    import history_input

    def refuse(client, request):
        raise RuntimeError("facade open failed")

    monkeypatch.setattr(history_input, "iter_history_input", refuse)
    instances = [perf.Instance(name="core-1"), perf.Instance(name="core-2")]
    with pytest.raises(RuntimeError, match="facade open failed"):
        perf.run_instances(None, start=research.START,
                           end=research.START + timedelta(minutes=5),
                           as_of=research.END, instances=instances,
                           output_dir=tmp_path / "shared", budget_seconds=60,
                           prefetch=False, label="shared", strategy="shared")
    failure = json.loads((tmp_path / "shared" / "failure.json").read_text())
    assert failure["failure"] == "RuntimeError"
    assert len(failure["instances"]) == 2
    for item in failure["instances"]:
        assert item["status"] == "FAILED"
        assert item["native_exit"] is not None
        assert item["reaped"] is True
    assert failure["prefetch_cleanup"]["unreclaimed"] == 0


def test_main_records_a_failure_and_exits_nonzero(tmp_path, monkeypatch):
    root = allow_evidence_root(tmp_path, monkeypatch)

    def refuse(*args, **kwargs):
        raise RuntimeError("core failed")

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", refuse)
    monkeypatch.setattr(perf, "run_independent", refuse)
    code = perf.main(["--mode", "candidates", "--instances", "1", "--strategy", "serial",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 2
    failure = json.loads((root / "evidence" / "run" / "failure.json").read_text())
    assert failure["failure"] == "RuntimeError"


def test_a_core_that_survives_terminate_is_reported_as_killed_and_not_reaped(
        tmp_path, monkeypatch):
    """A child that ignores SIGTERM is killed and never claimed as reaped early."""
    script = tmp_path / "stubborn.sh"
    script.write_text("#!/bin/sh\ntrap '' TERM\nsleep 300\n")
    script.chmod(0o755)
    monkeypatch.setattr(perf, "BINARY", script)
    monkeypatch.setattr(perf, "CORE_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(perf, "CORE_KILL_SECONDS", 1.0)
    instance = perf.Instance(name="core-1")
    state = perf._start_core(instance, tmp_path / "core", 0, 1)
    outcome = perf._finish_core(state, "hash", 0, time.monotonic() + 0.2)
    perf._close_handles(state)
    assert outcome["terminated"] is True
    assert outcome["killed"] is True
    assert outcome["reaped"] is True
    assert instance.native_exit != 0


def test_prefetch_close_respects_the_remaining_deadline():
    """The prefetch join never waits longer than the cleanup budget allows."""
    release = threading.Event()

    def slow_open(day):
        release.wait(10)
        return bundle()

    prefetcher = perf.BoundedPrefetcher(None, research.END)
    prefetcher._open = slow_open
    day = research.START
    prefetcher.submit(day)
    with pytest.raises(TimeoutError, match="did not arrive"):
        prefetcher.take(day, timeout=0.2)
    started = time.monotonic()
    closed = prefetcher.close(join_timeout=10.0, deadline=time.monotonic() + 0.3)
    assert time.monotonic() - started < 3.0
    assert closed["unreclaimed"] == 1
    assert closed["still_tracked"] == 1
    release.set()


# ------------------------------------------------------ Fix2: R2-2 identity gate


def test_a_source_drift_during_the_run_is_rejected(tmp_path, monkeypatch):
    """A run whose sources changed mid-flight must not report success."""
    root = allow_evidence_root(tmp_path, monkeypatch)
    identities = iter([{"a.py": "1" * 64}, {"a.py": "2" * 64}])
    monkeypatch.setattr(perf, "_arm_source_identity", lambda: next(identities))

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        return dict(label=label, strategy=strategy, complete=True, instances=[],
                    bundle_opens=1, events=1, event_sha256="h", contexts=0,
                    row_counts={}, day_content_sha256={}, day_sources={},
                    wall_seconds=0.0, prepare_seconds=0.0, verify_seconds=0.0,
                    instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    monkeypatch.setattr(perf, "run_independent", fake_run)
    code = perf.main(["--mode", "window", "--instances", "1",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 6
    after = json.loads((root / "evidence" / "run" / "identity-after.json").read_text())
    assert after["sources_unchanged"] is False


def test_the_start_identity_is_the_one_compared_against_the_end(tmp_path, monkeypatch):
    """The gate compares the start snapshot with the end snapshot."""
    root = allow_evidence_root(tmp_path, monkeypatch)
    seen = []

    def fake_identity():
        seen.append(dict(perf._source_identity()))
        return {"a.py": "1" * 64}

    monkeypatch.setattr(perf, "_arm_source_identity", fake_identity)
    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances",
                        lambda *a, **k: dict(label="serial", strategy="serial", complete=True,
                                             instances=[], bundle_opens=1, events=1,
                                             event_sha256="h", contexts=0, row_counts={},
                                             day_content_sha256={}, day_sources={},
                                             wall_seconds=0.0, prepare_seconds=0.0,
                                             verify_seconds=0.0,
                                             instance_comparison={"identical": True}))
    code = perf.main(["--mode", "window", "--instances", "1",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 0
    after = json.loads((root / "evidence" / "run" / "identity-after.json").read_text())
    assert after["sources_unchanged"] is True
    assert "a.py" in after["arm_sources"]


def test_the_arm_identity_covers_the_public_facade_files():
    """The facade the arms read through is part of the recorded identity."""
    identity = perf._arm_source_identity()
    for name in ("client.py", "history_reader.py", "history_types.py", "storage.py"):
        assert f"skills/data/unified_data/{name}" in identity


# ------------------------------------------------------- Fix2: R2-3 cross-arm gate


def _arm_run(label, strategy, output_dir, *, event_sha="h", samples_sha="s",
             rows=6, valued=1, missing=None):
    """Build one arm result row for the cross-arm comparison."""
    return dict(label=label, strategy=strategy, complete=True, output_dir=str(output_dir),
                events=1, event_sha256=event_sha, contexts=0, row_counts={},
                day_content_sha256={"2026-08-10": "content"},
                day_sources={"2026-08-10": dict(day="2026-08-10", verified=True,
                                                content_sha256="content", events=1,
                                                row_counts={"features": 1},
                                                coverage={}, missing=[], pending=[],
                                                conflicts=[])},
                wall_seconds=0.0, prepare_seconds=0.0, verify_seconds=0.0,
                instances=[dict(name="core-1", status="EXECUTED", native_exit=0,
                                error=None, complete=True, values_sha256="v",
                                event_sha256=event_sha, events=1, samples_sha256=samples_sha,
                                samples_rows=rows, valued_rows=valued,
                                missing_by_reason=missing or {}, summary={},
                                child_cpu_seconds=0.0, child_max_rss_kib=0,
                                terminated=False, killed=False, reaped=True,
                                timed_out=False)],
                instance_comparison={"identical": True})


def test_arms_with_different_event_identities_are_rejected(tmp_path):
    shared = _arm_run("shared", "shared", tmp_path / "shared")
    other = _arm_run("prefetch", "prefetch", tmp_path / "shared-prefetch",
                     event_sha="other")
    result = perf._compare_arms([shared, other])
    assert result["identical"] is False
    assert any("event identity drift" in reason for reason in result["reasons"])


def test_arms_with_a_different_label_source_are_rejected(tmp_path):
    shared = _arm_run("shared", "shared", tmp_path / "shared")
    other = _arm_run("prefetch", "prefetch", tmp_path / "shared-prefetch")
    other["day_sources"]["2026-08-10"]["coverage"] = {"stored_rows": 2}
    result = perf._compare_arms([shared, other])
    assert result["identical"] is False
    assert any("coverage drift" in reason for reason in result["reasons"])


def test_arms_with_different_statistical_denominators_are_rejected(tmp_path):
    """Two arms that complete but disagree on the sample denominators fail."""
    shared = _arm_run("shared", "shared", tmp_path / "shared")
    other = _arm_run("prefetch", "prefetch", tmp_path / "shared-prefetch")
    other["instances"][0]["samples_rows"] = 7
    other["instances"][0]["missing_by_reason"] = {"missing_spot": 1}
    result = perf._compare_arms([shared, other])
    assert result["identical"] is False
    assert any("sample row count drift" in reason for reason in result["reasons"])
    assert any("missing-reason denominators drift" in reason
               for reason in result["reasons"])


def test_an_independent_arm_with_different_samples_is_rejected(tmp_path):
    shared = _arm_run("shared", "shared", tmp_path / "shared")
    independent = dict(label="independent", strategy="independent", complete=True,
                       output_dir=str(tmp_path / "independent"), events=2,
                       event_sha256="h", contexts=0, row_counts={},
                       day_content_sha256={"2026-08-10": "content"},
                       day_sources={}, wall_seconds=0.0, prepare_seconds=0.0,
                       verify_seconds=0.0, instances=[],
                       instance_comparison={"identical": True},
                       parts=[dict(label="core-1", events=1,
                                   output_dir=str(tmp_path / "independent" / "core-1"),
                                   samples_sha256="different", samples_rows=6,
                                   valued_rows=1, missing_by_reason={},
                                   complete=True)])
    result = perf._compare_arms([shared, independent])
    assert result["identical"] is False
    assert any("samples identity drift" in reason for reason in result["reasons"])


def test_identical_arms_are_accepted(tmp_path):
    shared = _arm_run("shared", "shared", tmp_path / "shared")
    other = _arm_run("prefetch", "prefetch", tmp_path / "shared-prefetch")
    result = perf._compare_arms([shared, other])
    assert result["identical"] is True
    assert result["reasons"] == []


def test_main_rejects_arms_that_disagree(tmp_path, monkeypatch):
    """The CLI refuses a run whose arms disagree on the source identity."""
    root = allow_evidence_root(tmp_path, monkeypatch)

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        row = _arm_run(label, strategy, output_dir)
        row["event_sha256"] = "h" if label == "shared" else "other"
        return row

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    monkeypatch.setattr(perf, "run_independent", fake_run)
    code = perf.main(["--mode", "candidates", "--instances", "1", "--strategy", "serial",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 4
    arms = json.loads((root / "evidence" / "run" / "arm-comparison.json").read_text())
    assert arms["identical"] is False


# ------------------------------------------------------ Fix2: R2-4 native summary


def _fake_core(path, *, summary=None, write_values=True, write_summary=True):
    """Write a temporary executable that behaves like the Rust history core.

    The core reads the event stream from stdin and writes the values output
    and the native summary. `summary=None` means the core writes the real
    contract; any other value overrides the written summary.
    """
    script = path.with_suffix(".py")
    script.write_text(
        "import json, sys\n"
        "args = dict(zip(sys.argv[1::2], sys.argv[2::2]))\n"
        "values, spots = [], 0\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if not line:\n"
        "        continue\n"
        "    event = json.loads(line)\n"
        "    payload = event['payload']\n"
        "    if payload['type'] == 'spot':\n"
        "        spots += 1\n"
        "        continue\n"
        "    values.append({'round_id': payload['round_id'], 'at_ms': event['at_ms'],\n"
        "        'starts_at_ms': payload['starts_at_ms'], 'ends_at_ms': payload['ends_at_ms'],\n"
        "        'strike': payload['strike'], 'spot': 100.0, 'spot_at_ms': event['at_ms'],\n"
        "        'secs_left': (payload['ends_at_ms'] - event['at_ms']) / 1000.0,\n"
        "        'samples': 10, 'sigma': 0.001, 'p_up': 0.5, 'reason': 'valued'})\n"
        + (f"with open(args['--output'], 'w') as out:\n"
           "    for value in values:\n"
           "        out.write(json.dumps(value) + '\\n')\n"
           if write_values else "")
        + (f"summary = {summary!r}\n"
           "with open(args['--summary'], 'w') as out:\n"
           "    json.dump(summary, out)\n"
           if write_summary else "")
        + ("summary = {'native_exit': 0, 'spots': spots, 'values': len(values),"
           " 'complete': True, 'error': None}\n"
           "with open(args['--summary'], 'w') as out:\n"
           "    json.dump(summary, out)\n"
           if summary is None and write_summary else "")
    )
    path.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
    path.chmod(0o755)
    return path


def test_main_fails_when_a_core_reports_an_incomplete_summary(tmp_path, monkeypatch):
    """The consumer path rejects a core whose native summary is not complete."""
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    script = _fake_core(tmp_path / "partial.sh", summary={"complete": True})
    monkeypatch.setattr(perf, "BINARY", script)
    instances = [perf.Instance(name="core-1")]
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END, instances=instances,
                                 output_dir=tmp_path / "shared", budget_seconds=60,
                                 prefetch=False, label="shared", strategy="shared")
    assert metrics["complete"] is False
    assert metrics["instances"][0]["status"] == "FAILED"
    assert "missing fields" in metrics["instances"][0]["error"]


def test_main_fails_when_the_core_writes_no_summary(tmp_path, monkeypatch):
    """A missing summary is a failure, not an implicit success."""
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    script = _fake_core(tmp_path / "no-summary.sh", write_summary=False)
    monkeypatch.setattr(perf, "BINARY", script)
    instances = [perf.Instance(name="core-1")]
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END, instances=instances,
                                 output_dir=tmp_path / "shared", budget_seconds=60,
                                 prefetch=False, label="shared", strategy="shared")
    assert metrics["complete"] is False
    assert metrics["instances"][0]["status"] == "FAILED"


def test_main_fails_when_the_core_writes_no_values(tmp_path, monkeypatch):
    """A summary without a values output is a failure."""
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    script = _fake_core(tmp_path / "no-values.sh", write_values=False)
    monkeypatch.setattr(perf, "BINARY", script)
    instances = [perf.Instance(name="core-1")]
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END, instances=instances,
                                 output_dir=tmp_path / "shared", budget_seconds=60,
                                 prefetch=False, label="shared", strategy="shared")
    assert metrics["complete"] is False
    assert metrics["instances"][0]["status"] == "FAILED"
    assert "missing values" in metrics["instances"][0]["error"]


def test_a_healthy_core_still_passes_the_summary_gate(tmp_path, monkeypatch):
    """The complete-summary counterexample must not reject a healthy core."""
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    script = _fake_core(tmp_path / "healthy.sh")
    monkeypatch.setattr(perf, "BINARY", script)
    instances = [perf.Instance(name="core-1")]
    metrics = perf.run_instances(None, start=research.START,
                                 end=research.START + timedelta(minutes=5),
                                 as_of=research.END, instances=instances,
                                 output_dir=tmp_path / "shared", budget_seconds=60,
                                 prefetch=False, label="shared", strategy="shared")
    assert metrics["instances"][0]["status"] == "EXECUTED"
    assert metrics["instances"][0]["complete"] is True


def test_the_explicit_both_strategy_runs_the_prefetch_branch(tmp_path, monkeypatch):
    """The explicit `both` branch must really count its prefetch arm."""
    root = allow_evidence_root(tmp_path, monkeypatch)
    labels = []

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        labels.append((label, prefetch))
        return dict(label=label, strategy=strategy, complete=True, instances=[],
                    bundle_opens=1, events=1, event_sha256="h", contexts=0,
                    row_counts={}, day_content_sha256={}, day_sources={},
                    wall_seconds=0.0, prepare_seconds=0.0, verify_seconds=0.0,
                    instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    monkeypatch.setattr(perf, "run_independent", fake_run)
    code = perf.main(["--mode", "candidates", "--instances", "1", "--strategy", "both",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 0
    assert labels == [("shared", False), ("prefetch", True), ("independent", False)]


def test_a_timeout_persists_its_failure_state_and_reaps_the_cores(tmp_path, monkeypatch):
    """A real timeout leaves the partial state on disk and reaps the cores."""
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle(candle_count=20000))
    script = tmp_path / "never-exits.sh"
    script.write_text("#!/bin/sh\nsleep 300\n")
    script.chmod(0o755)
    monkeypatch.setattr(perf, "BINARY", script)
    instances = [perf.Instance(name="core-1"), perf.Instance(name="core-2")]
    with pytest.raises(TimeoutError):
        perf.run_instances(None, start=research.START,
                           end=research.START + timedelta(hours=6),
                           as_of=research.END, instances=instances,
                           output_dir=tmp_path / "blocked", budget_seconds=5,
                           prefetch=False, label="blocked", strategy="serial")
    failure = json.loads((tmp_path / "blocked" / "failure.json").read_text())
    assert failure["failure"] == "TimeoutError"
    assert len(failure["instances"]) == 2
    for item in failure["instances"]:
        assert item["status"] == "FAILED"
        assert item["native_exit"] is not None
        assert item["reaped"] is True
        assert item["timed_out"] is True


def test_an_interrupt_persists_its_failure_state(tmp_path, monkeypatch):
    """A KeyboardInterrupt leaves the partial state on disk and re-raises."""
    import history_input

    def interrupt(client, request):
        raise KeyboardInterrupt

    monkeypatch.setattr(history_input, "iter_history_input", interrupt)
    instances = [perf.Instance(name="core-1")]
    with pytest.raises(KeyboardInterrupt):
        perf.run_instances(None, start=research.START,
                           end=research.START + timedelta(minutes=5),
                           as_of=research.END, instances=instances,
                           output_dir=tmp_path / "interrupted", budget_seconds=60,
                           prefetch=False, label="shared", strategy="shared")
    failure = json.loads((tmp_path / "interrupted" / "failure.json").read_text())
    assert failure["failure"] == "KeyboardInterrupt"
    assert failure["instances"][0]["status"] == "FAILED"


def test_main_records_an_interrupt_and_exits_nonzero(tmp_path, monkeypatch):
    root = allow_evidence_root(tmp_path, monkeypatch)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", interrupt)
    monkeypatch.setattr(perf, "run_independent", interrupt)
    code = perf.main(["--mode", "candidates", "--instances", "1", "--strategy", "serial",
                       "--start", "2026-11-16T00:00:00Z",
                       "--end", "2026-11-16T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 7
    failure = json.loads((root / "evidence" / "run" / "failure.json").read_text())
    assert failure["failure"] == "KeyboardInterrupt"


def test_a_healthy_candidates_run_passes_the_cross_arm_gate(tmp_path, monkeypatch):
    """A complete run through the real arms is accepted and recorded."""
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle())
    script = _fake_core(tmp_path / "core.sh")
    monkeypatch.setattr(perf, "BINARY", script)
    root = allow_evidence_root(tmp_path, monkeypatch)
    monkeypatch.setattr(perf, "_open_client", lambda: object())
    code = perf.main(["--mode", "candidates", "--instances", "2", "--strategy", "serial",
                       "--start", "2026-08-10T00:00:00Z",
                       "--end", "2026-08-10T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 0
    arms = json.loads((root / "evidence" / "run" / "arm-comparison.json").read_text())
    assert arms["identical"] is True
    runs = json.loads((root / "evidence" / "run" / "runs.json").read_text())
    assert [run["label"] for run in runs] == ["shared", "independent"]
    assert all(run["complete"] for run in runs)


# ------------------------------------------- Fix3: real main two-core failure chain


def _fake_core_with_failure(path, *, fail_core=None, mode="exit"):
    """Write a local fake core whose behaviour depends on the instance name.

    `fail_core` names the instance directory that must fail and `mode`
    selects the failure shape: an early nonzero exit, an exit after the
    first event (a real broken pipe in the writer), a missing values
    output, a missing summary or a summary that only claims completion.
    """
    script = path.with_suffix(".py")
    script.write_text("\n".join([
        "import json, os, sys",
        "args = dict(zip(sys.argv[1::2], sys.argv[2::2]))",
        "instance = os.path.dirname(os.path.abspath(args['--config']))",
        "name = os.path.basename(instance)",
        f"FAIL = {fail_core!r}",
        f"MODE = {mode!r}",
        "if name == FAIL and MODE == 'exit':",
        "    sys.exit(3)",
        "events = []",
        "for line in sys.stdin:",
        "    line = line.strip()",
        "    if line:",
        "        events.append(json.loads(line))",
        "    if name == FAIL and MODE == 'exit_after_read':",
        "        sys.exit(4)",
        "values, spots = [], 0",
        "for event in events:",
        "    payload = event['payload']",
        "    if payload['type'] == 'spot':",
        "        spots += 1",
        "        continue",
        "    values.append({'round_id': payload['round_id'], 'at_ms': event['at_ms'],",
        "        'starts_at_ms': payload['starts_at_ms'],",
        "        'ends_at_ms': payload['ends_at_ms'], 'strike': payload['strike'],",
        "        'spot': 100.0, 'spot_at_ms': event['at_ms'],",
        "        'secs_left': (payload['ends_at_ms'] - event['at_ms']) / 1000.0,",
        "        'samples': 10, 'sigma': 0.001, 'p_up': 0.5, 'reason': 'valued'})",
        "summary = {'native_exit': 0, 'spots': spots, 'values': len(values),",
        "           'complete': True, 'error': None}",
        "if name == FAIL and MODE == 'no_values':",
        "    summary = {'native_exit': 0, 'spots': spots, 'values': 0,",
        "               'complete': True, 'error': None}",
        "if name == FAIL and MODE == 'no_summary':",
        "    summary = None",
        "if name == FAIL and MODE == 'partial_summary':",
        "    summary = {'complete': True}",
        "if name == FAIL and MODE in ('negative_spots', 'wrong_spots'):",
        "    summary['spots'] = -1 if MODE == 'negative_spots' else spots + 1",
        "if name == FAIL and MODE == 'warmup' and os.path.basename(os.path.dirname(instance)) == 'independent':",
        "    for value in values:",
        "        value.update(p_up=None, reason='warming_up')",
        "if not (name == FAIL and MODE == 'no_values'):",
        "    with open(args['--output'], 'w') as out:",
        "        for value in values:",
        "            out.write(json.dumps(value) + '\\n')",
        "if summary is not None:",
        "    with open(args['--summary'], 'w') as out:",
        "        json.dump(summary, out)",
        "",
    ]))
    path.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
    path.chmod(0o755)
    return path


def _assert_child_reaped(pid):
    """Assert the child is really gone, not merely reported as reaped."""
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def _assert_all_cores_reaped(rows):
    """Assert every recorded core PID is really gone."""
    assert rows, "the run must report its cores"
    for row in rows:
        assert row["pid"] is not None, "every core must record its PID"
        _assert_child_reaped(row["pid"])


def _failure_core_rows(failure):
    """Return the per-core rows of a failed run, whichever path wrote them.

    An arm that fails without raising keeps its rows in the CLI record; an
    arm that raised persists its own `failure.json`, which the CLI embeds.
    """
    rows = failure.get("cores") or []
    for partial in failure.get("partial_failures", []):
        rows.extend(partial["record"]["instances"])
    return rows


def _run_real_main_two_cores(tmp_path, monkeypatch, *, script, mode="exit",
                              fail_core="core-2", candle_count=5000,
                              budget_seconds=120.0, start="2026-08-10T00:00:00Z",
                              end="2026-08-10T02:00:00Z"):
    """Run the real CLI main over two local cores and a bounded facade.

    Only the database client, the facade input and the native binary are
    replaced; `main`, `run_instances` and the core lifecycle stay real.
    """
    import history_input

    monkeypatch.setattr(history_input, "iter_history_input",
                        lambda client, request: bundle(candle_count=candle_count))
    monkeypatch.setattr(perf, "BINARY", script)
    root = allow_evidence_root(tmp_path, monkeypatch)
    monkeypatch.setattr(perf, "_open_client", lambda: object())
    code = perf.main(["--mode", "window", "--instances", "2", "--strategy", "serial",
                       "--start", start, "--end", end, "--as-of", "2026-11-17T00:00:00Z",
                       "--budget-seconds", str(budget_seconds),
                       "--evidence-dir", str(root / "evidence" / "run")])
    return code, root / "evidence" / "run"


def test_the_arm_identity_covers_the_four_performance_test_files():
    """The inline fixtures of all four performance tests bind the run identity."""
    identity = perf._arm_source_identity()
    base = "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/"
    for name in ("test_history_performance.py", "test_history_research.py",
                 "test_history_metrics.py", "test_history_input.py"):
        assert f"{base}{name}" in identity
        assert len(identity[f"{base}{name}"]) == 64


def test_the_arm_identity_records_the_installed_dependency_versions():
    """The dependencies the arms really import are part of the identity."""
    identity = perf._arm_source_identity()
    assert "dependencies" in identity
    versions = identity["dependencies"]
    assert set(versions) == set(perf.DEPENDENCY_DISTRIBUTIONS)
    assert all(isinstance(value, str) and value for value in versions.values())


def test_main_rejects_a_run_whose_dependency_identity_changed(tmp_path, monkeypatch):
    """A dependency version drift is a real rejection, not a recorded note."""
    root = allow_evidence_root(tmp_path, monkeypatch)
    versions = iter(["deps-v1", "deps-v2"])
    monkeypatch.setattr(perf, "_dependency_identity", lambda: next(versions))

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        return dict(label=label, strategy=strategy, complete=True, instances=[],
                    bundle_opens=1, events=1, event_sha256="h", contexts=0,
                    row_counts={}, day_content_sha256={}, day_sources={},
                    wall_seconds=0.0, prepare_seconds=0.0, verify_seconds=0.0,
                    instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    code = perf.main(["--mode", "window", "--instances", "1",
                       "--start", "2026-08-10T00:00:00Z",
                       "--end", "2026-08-10T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 6
    after = json.loads((root / "evidence" / "run" / "identity-after.json").read_text())
    assert after["sources_unchanged"] is False


def test_main_rejects_a_run_whose_test_fixture_identity_changed(tmp_path, monkeypatch):
    """A changed inline fixture of a performance test is a real rejection."""
    root = allow_evidence_root(tmp_path, monkeypatch)
    real_hash = perf.sha256_file
    seen = {"count": 0}

    def hashed(path):
        if path.name == "test_history_input.py":
            seen["count"] += 1
            return "a" * 64 if seen["count"] == 1 else "b" * 64
        return real_hash(path)

    monkeypatch.setattr(perf, "sha256_file", hashed)

    def fake_run(client, *, start, end, as_of, instances, output_dir, budget_seconds,
                 label, prefetch=False, strategy="shared", flat=False):
        return dict(label=label, strategy=strategy, complete=True, instances=[],
                    bundle_opens=1, events=1, event_sha256="h", contexts=0,
                    row_counts={}, day_content_sha256={}, day_sources={},
                    wall_seconds=0.0, prepare_seconds=0.0, verify_seconds=0.0,
                    instance_comparison={"identical": True})

    monkeypatch.setattr(perf, "_open_client", lambda: object())
    monkeypatch.setattr(perf, "run_instances", fake_run)
    code = perf.main(["--mode", "window", "--instances", "1",
                       "--start", "2026-08-10T00:00:00Z",
                       "--end", "2026-08-10T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 6
    after = json.loads((root / "evidence" / "run" / "identity-after.json").read_text())
    assert after["sources_unchanged"] is False


def test_main_with_two_cores_records_the_failing_core_and_reaps_both_cores(
        tmp_path, monkeypatch):
    """A real main run with two cores keeps the per-core failure state."""
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core="core-2",
                                     mode="exit")
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script)
    assert code == 4
    runs = json.loads((evidence / "runs.json").read_text())
    assert len(runs) == 1
    instances = {item["name"]: item for item in runs[0]["instances"]}
    assert set(instances) == {"core-1", "core-2"}
    failed = instances["core-2"]
    healthy = instances["core-1"]
    assert failed["status"] != "EXECUTED"
    assert failed["native_exit"] == 3
    assert failed["reaped"] is True
    assert healthy["status"] == "EXECUTED"
    assert healthy["native_exit"] == 0
    assert healthy["reaped"] is True
    assert runs[0]["complete"] is False
    _assert_all_cores_reaped(runs[0]["instances"])


def test_main_with_two_cores_reports_a_real_broken_pipe(tmp_path, monkeypatch):
    """A core that dies mid-stream produces a real broken pipe in the writer."""
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core="core-2",
                                     mode="exit_after_read")
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script)
    assert code == 4
    failure = json.loads((evidence / "failure.json").read_text())
    assert failure["failure"] == "IncompleteRun"
    rows = _failure_core_rows(failure)
    failed = [row for row in rows if row["name"] == "core-2"][0]
    assert failed["status"] == "FAILED"
    assert failed["error"].startswith(("BrokenPipeError:", "OSError:"))
    assert failed["native_exit"] == 4
    assert failed["reaped"] is True
    healthy = next(row for row in rows if row["name"] == "core-1")
    assert (healthy["status"], healthy["native_exit"], healthy["reaped"]) == ("EXECUTED", 0, True)
    _assert_all_cores_reaped(rows)


def test_main_with_two_cores_reports_a_core_without_values(tmp_path, monkeypatch):
    """A core that writes no values fails and is reaped like any other core."""
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core="core-2",
                                     mode="no_values")
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script)
    assert code == 4
    runs = json.loads((evidence / "runs.json").read_text())
    healthy = runs[0]["instances"][0]
    assert (healthy["status"], healthy["native_exit"], healthy["reaped"]) == ("EXECUTED", 0, True)
    failed = {item["name"]: item for item in runs[0]["instances"]}["core-2"]
    assert failed["status"] == "FAILED"
    assert "missing values" in failed["error"]
    assert failed["native_exit"] == 0
    assert failed["reaped"] is True
    _assert_all_cores_reaped(runs[0]["instances"])


def test_main_with_two_cores_reports_a_core_without_a_summary(tmp_path, monkeypatch):
    """A core that writes no summary fails and is reaped like any other core."""
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core="core-2",
                                     mode="no_summary")
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script)
    assert code == 4
    runs = json.loads((evidence / "runs.json").read_text())
    healthy = runs[0]["instances"][0]
    assert (healthy["status"], healthy["native_exit"], healthy["reaped"]) == ("EXECUTED", 0, True)
    failed = {item["name"]: item for item in runs[0]["instances"]}["core-2"]
    assert failed["status"] == "FAILED"
    assert "missing fields" in failed["error"]
    assert failed["native_exit"] == 0
    assert failed["reaped"] is True
    _assert_all_cores_reaped(runs[0]["instances"])


def test_main_with_two_cores_reports_an_incomplete_summary(tmp_path, monkeypatch):
    """A summary that only claims completion fails and is reaped."""
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core="core-2",
                                     mode="partial_summary")
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script)
    assert code == 4
    runs = json.loads((evidence / "runs.json").read_text())
    healthy = runs[0]["instances"][0]
    assert (healthy["status"], healthy["native_exit"], healthy["reaped"]) == ("EXECUTED", 0, True)
    failed = {item["name"]: item for item in runs[0]["instances"]}["core-2"]
    assert failed["status"] == "FAILED"
    assert "missing fields" in failed["error"]
    assert failed["native_exit"] == 0
    assert failed["reaped"] is True
    _assert_all_cores_reaped(runs[0]["instances"])


def test_main_with_two_healthy_cores_completes(tmp_path, monkeypatch):
    """The healthy two-core control must keep passing through the real main."""
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core=None)
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script)
    assert code == 0
    runs = json.loads((evidence / "runs.json").read_text())
    assert runs[0]["complete"] is True
    assert [item["name"] for item in runs[0]["instances"]] == ["core-1", "core-2"]
    _assert_all_cores_reaped(runs[0]["instances"])


def test_main_persists_a_failure_record_for_the_failing_core(tmp_path, monkeypatch):
    """The per-core failure state is persisted, not only printed."""
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core="core-2",
                                     mode="no_values")
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script)
    assert code == 4
    failure = json.loads((evidence / "failure.json").read_text())
    assert failure["failure"] == "IncompleteRun"
    rows = _failure_core_rows(failure)
    assert rows, "the per-core failure state must be persisted"
    assert {row["name"] for row in rows} == {"core-1", "core-2"}
    failed = [row for row in rows if row["name"] == "core-2"][0]
    assert failed["native_exit"] == 0
    assert failed["reaped"] is True
    assert "missing values" in failed["error"]
    _assert_all_cores_reaped(rows)


def test_main_reports_a_timeout_and_reaps_both_cores(tmp_path, monkeypatch):
    """A real timeout through main keeps the exception class and the reaping."""
    script = tmp_path / "sleepy.sh"
    script.write_text("#!/bin/sh\nexec sleep 300\n")
    script.chmod(0o755)
    code, evidence = _run_real_main_two_cores(tmp_path, monkeypatch, script=script,
                                               budget_seconds=2.0)
    assert code == 5
    failure = json.loads((evidence / "failure.json").read_text())
    assert failure["failure"] == "TimeoutError"
    rows = _failure_core_rows(failure)
    assert len(rows) == 2
    for row in rows:
        assert row["status"] == "FAILED"
        assert row["native_exit"] is not None
        assert row["reaped"] is True
    _assert_all_cores_reaped(rows)


def test_main_reports_a_reader_failure_and_reaps_both_cores(tmp_path, monkeypatch):
    """A facade read failure keeps its exception class and reaps the cores."""
    import history_input

    def refuse(client, request):
        raise RuntimeError("facade open failed")

    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core=None)
    monkeypatch.setattr(perf, "BINARY", script)
    monkeypatch.setattr(history_input, "iter_history_input", refuse)
    root = allow_evidence_root(tmp_path, monkeypatch)
    monkeypatch.setattr(perf, "_open_client", lambda: object())
    code = perf.main(["--mode", "window", "--instances", "2", "--strategy", "serial",
                       "--start", "2026-08-10T00:00:00Z",
                       "--end", "2026-08-10T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 2
    evidence = root / "evidence" / "run"
    failure = json.loads((evidence / "failure.json").read_text())
    assert failure["failure"] == "RuntimeError"
    rows = _failure_core_rows(failure)
    assert len(rows) == 2
    for row in rows:
        assert row["native_exit"] is not None
        assert row["reaped"] is True
    _assert_all_cores_reaped(rows)


def test_main_reports_an_interrupt_and_reaps_both_cores(tmp_path, monkeypatch):
    """A KeyboardInterrupt through main keeps its class and the reaping."""
    import history_input

    def interrupt(client, request):
        raise KeyboardInterrupt

    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core=None)
    monkeypatch.setattr(perf, "BINARY", script)
    monkeypatch.setattr(history_input, "iter_history_input", interrupt)
    root = allow_evidence_root(tmp_path, monkeypatch)
    monkeypatch.setattr(perf, "_open_client", lambda: object())
    code = perf.main(["--mode", "window", "--instances", "2", "--strategy", "serial",
                       "--start", "2026-08-10T00:00:00Z",
                       "--end", "2026-08-10T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 7
    evidence = root / "evidence" / "run"
    failure = json.loads((evidence / "failure.json").read_text())
    assert failure["failure"] == "KeyboardInterrupt"
    rows = _failure_core_rows(failure)
    assert len(rows) == 2
    for row in rows:
        assert row["native_exit"] is not None
        assert row["reaped"] is True
    _assert_all_cores_reaped(rows)


def test_an_independent_arm_with_a_different_label_is_rejected(tmp_path, monkeypatch):
    """Both arms complete, but the control arm read a different label."""
    import history_input

    opens = []

    def opener(client, request):
        opens.append(request.start_utc)
        # The first read is the shared arm; the later reads are the control arm.
        label = "UP" if len(opens) == 1 else "DOWN"
        return bundle(label=label)

    monkeypatch.setattr(history_input, "iter_history_input", opener)
    script = _fake_core(tmp_path / "core.sh")
    monkeypatch.setattr(perf, "BINARY", script)
    root = allow_evidence_root(tmp_path, monkeypatch)
    monkeypatch.setattr(perf, "_open_client", lambda: object())
    code = perf.main(["--mode", "candidates", "--instances", "2", "--strategy", "serial",
                       "--start", "2026-08-10T00:00:00Z",
                       "--end", "2026-08-10T00:05:00Z", "--as-of", "2026-11-17T00:00:00Z",
                       "--evidence-dir", str(root / "evidence" / "run")])
    assert code == 4
    arms = json.loads((root / "evidence" / "run" / "arm-comparison.json").read_text())
    assert arms["identical"] is False
    assert arms["reasons"]


# ------------------------------------------------------------------ Fix4 main gates


def _fix4_argv(evidence, *, mode="window", strategy="serial", budget=30.0):
    """Use the actual CLI on a single five-minute synthetic counterexample."""
    return ["--mode", mode, "--instances", "2", "--strategy", strategy,
            "--start", "2026-08-10T00:00:00Z", "--end", "2026-08-10T00:05:00Z",
            "--as-of", "2026-11-17T00:00:00Z", "--budget-seconds", str(budget),
            "--evidence-dir", str(evidence)]


def _fix4_setup(tmp_path, monkeypatch, *, opener=None, fail_core=None, core_mode="exit"):
    """Replace only the DB, facade input and binary, not the run/lifecycle."""
    import history_input

    root = allow_evidence_root(tmp_path, monkeypatch)
    script = _fake_core_with_failure(tmp_path / "core.sh", fail_core=fail_core,
                                     mode=core_mode)
    monkeypatch.setattr(perf, "BINARY", script)
    monkeypatch.setattr(perf, "_open_client", lambda: object())

    def facade_input(client, request):
        selected = opener(client, request) if opener else bundle()
        # HistoryInputBundle exposes its facade facts through _window. Keep
        # that actual consumer shape instead of leaving this mock's facts invisible.
        selected._window = selected
        return selected

    monkeypatch.setattr(history_input, "iter_history_input", facade_input)
    return root / "evidence" / "run"


def _evidence_snapshot(evidence):
    """Capture entries and original bytes, including directories and binary files."""
    return {str(path.relative_to(evidence)): path.read_bytes() if path.is_file() else None
            for path in evidence.rglob("*")}


@pytest.mark.parametrize("mode", ["window", "candidates", "rescore"])
@pytest.mark.parametrize("collision", ["existing", "mkdir_race"])
@pytest.mark.parametrize("has_failure", [True, False])
def test_fix4_main_collision_preserves_all_old_evidence(
        tmp_path, monkeypatch, mode, collision, has_failure):
    """A rejected directory is never owned by this invocation, even on an EEXIST race."""
    evidence = _fix4_setup(tmp_path, monkeypatch)
    opens = []
    monkeypatch.setattr(perf, "_open_client", lambda: opens.append("DB must not open"))
    old_mkdir = Path.mkdir

    def old_evidence():
        old_mkdir(evidence, parents=True)
        (evidence / "nested").mkdir()
        if has_failure:
            (evidence / "failure.json").write_bytes(b'OLD FAILURE\n\x00\xff')
        (evidence / "nested" / "raw.bin").write_bytes(b'\x01old raw evidence\x02')

    if collision == "existing":
        old_evidence()
    else:
        def collide(path, *args, **kwargs):
            if path == evidence:
                old_evidence()
                raise FileExistsError("another invocation owns this evidence")
            return old_mkdir(path, *args, **kwargs)
        monkeypatch.setattr(Path, "mkdir", collide)
    expected = {"nested": None, "failure.json": b'OLD FAILURE\n\x00\xff',
                "nested/raw.bin": b'\x01old raw evidence\x02'}
    if not has_failure:
        expected.pop("failure.json")
    before = (perf.COUNTERS.db_calls, perf.COUNTERS.core_calls)
    assert perf.main(_fix4_argv(evidence, mode=mode)) == 2
    assert _evidence_snapshot(evidence) == expected
    assert opens == []
    assert (perf.COUNTERS.db_calls, perf.COUNTERS.core_calls) == before


@pytest.mark.parametrize("field", ["coverage", "missing", "pending", "conflicts",
                                   "content_manifest", "provenance_manifest"])
def test_fix4_main_checks_sources_of_later_independent_parts(tmp_path, monkeypatch, field):
    """Only core-2's repeated read changes; event/value/sample identities stay equal."""
    opens = []

    def opener(client, request):
        opens.append(request.start_utc)
        selected = bundle()
        selected.coverage = {"stored_rows": 301}
        if len(opens) == 3:
            if field == "coverage":
                selected.coverage["stored_rows"] += 1
            elif field in ("missing", "pending", "conflicts"):
                setattr(selected, field, [{"dataset": research.DATASET_ROUNDS,
                                           "reason": "later-part-only"}])
            elif field == "content_manifest":
                selected.content_manifest = {"content_sha256": "later-manifest"}
            else:
                selected.provenance_manifest = {
                    research.DATASET_ROUNDS: {"raw_references_sha256": "later-origin"}}
        return selected

    evidence = _fix4_setup(tmp_path, monkeypatch, opener=opener)
    assert perf.main(_fix4_argv(evidence, mode="candidates")) == 4
    runs = json.loads((evidence / "runs.json").read_text())
    shared, independent = runs
    assert len(opens) == 3
    assert independent["complete"] is False
    parts = independent["parts"]
    assert len({part["event_sha256"] for part in parts} | {shared["event_sha256"]}) == 1
    assert len({part["samples_sha256"] for part in parts} |
               {shared["instances"][0]["samples_sha256"]}) == 1
    assert parts[0]["day_sources"] == shared["day_sources"]
    assert parts[1]["day_sources"] != parts[0]["day_sources"]
    assert any(field in reason and "core-2" in reason
               for reason in independent["source_comparison_reasons"])
    # Exercise the cross-arm gate on the actual main outputs as well as the
    # independent arm's own check, without mocking either execution function.
    comparison = perf._compare_arms(runs)
    assert comparison["identical"] is False
    assert any(field in reason and "core-2" in reason for reason in comparison["reasons"])
    _assert_all_cores_reaped([item for run in runs for item in run["instances"]])


@pytest.mark.parametrize("core_mode", ["negative_spots", "wrong_spots"])
def test_fix4_main_rejects_inconsistent_spot_counts(tmp_path, monkeypatch, core_mode):
    """A zero native exit and intact values do not excuse negative/wrong input counts."""
    evidence = _fix4_setup(tmp_path, monkeypatch, fail_core="core-2", core_mode=core_mode)
    assert perf.main(_fix4_argv(evidence)) == 4
    run, = json.loads((evidence / "runs.json").read_text())
    healthy, failed = run["instances"]
    assert healthy["status"] == "EXECUTED" and healthy["native_exit"] == 0
    assert healthy["summary"]["spots"] + healthy["summary"]["values"] == run["events"]
    assert failed["status"] == "FAILED" and failed["native_exit"] == 0
    assert "negative" in failed["error"] or "input count" in failed["error"]
    assert failed["summary"]["values"] == healthy["summary"]["values"]
    assert failed["values_sha256"] == healthy["values_sha256"]
    assert json.loads((evidence / "failure.json").read_text())["failure"] == "IncompleteRun"
    _assert_all_cores_reaped(run["instances"])


@pytest.mark.parametrize("relative", [
    "skills/data/unified_data/client.py", "skills/data/unified_data/history_reader.py",
    "skills/data/unified_data/history_types.py", "skills/data/unified_data/storage.py",
    *[str(LAB.relative_to(ROOT) / "tests" / name) for name in perf.ARM_TEST_FILES],
])
def test_fix4_main_refuses_missing_required_identity(tmp_path, monkeypatch, relative):
    """Simulate a missing path; never delete/rename a shared source to test refusal."""
    evidence = _fix4_setup(tmp_path, monkeypatch)
    missing = ROOT / relative
    old_is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path: False if path == missing else old_is_file(path))
    opens = []
    monkeypatch.setattr(perf, "_open_client", lambda: opens.append("DB must not open"))
    assert perf.main(_fix4_argv(evidence)) == 2
    failure = json.loads((evidence / "failure.json").read_text())
    assert failure["failure"] == "ValueError"
    assert "missing required identity" in failure["message"]
    assert missing.name in failure["message"]
    assert opens == []
    assert not (evidence / "shared-serial").exists()


@pytest.mark.parametrize("error_type,expected_code", [(RuntimeError, 2), (KeyboardInterrupt, 7)])
def test_fix4_main_prefetch_open_failures_keep_partial_state(
        tmp_path, monkeypatch, error_type, expected_code):
    """Prefetch-thread exceptions reach main with native exits and real PID reaping."""
    def opener(client, request):
        raise error_type("controlled prefetch open failure")

    evidence = _fix4_setup(tmp_path, monkeypatch, opener=opener)
    assert perf.main(_fix4_argv(evidence, strategy="prefetch")) == expected_code
    failure = json.loads((evidence / "failure.json").read_text())
    assert failure["failure"] == error_type.__name__
    partial, = failure["partial_failures"]
    assert partial["record"]["failure"] == error_type.__name__
    assert partial["record"]["prefetch_cleanup"] == {
        "cancelled": 0, "reclaimed": 0, "unreclaimed": 0, "still_tracked": 0}
    rows = partial["record"]["instances"]
    assert len(rows) == 2
    assert all(row["native_exit"] == 0 and row["reaped"] for row in rows)
    _assert_all_cores_reaped(rows)


@pytest.mark.parametrize("reclaim_read", [True, False])
def test_fix4_main_prefetch_timeout_reports_actual_cleanup(tmp_path, monkeypatch, reclaim_read):
    """A timed-out read is either joined or truthfully tracked; the fixture releases it."""
    release = threading.Event()
    readers, timers = [], []

    def opener(client, request):
        readers.append(threading.current_thread())
        if reclaim_read:
            timer = threading.Timer(1.25, release.set)
            timers.append(timer)
            timer.start()
        release.wait()
        return bundle()

    evidence = _fix4_setup(tmp_path, monkeypatch, opener=opener)
    started = time.monotonic()
    try:
        assert perf.main(_fix4_argv(evidence, strategy="prefetch", budget=1.0)) == 5
        failure = json.loads((evidence / "failure.json").read_text())
        assert failure["failure"] == "TimeoutError"
        partial, = failure["partial_failures"]
        assert partial["record"]["prefetch_cleanup"] == {
            "cancelled": 0, "reclaimed": int(reclaim_read),
            "unreclaimed": int(not reclaim_read), "still_tracked": int(not reclaim_read)}
        rows = partial["record"]["instances"]
        assert len(rows) == 2
        assert all(row["native_exit"] == -signal.SIGTERM and row["reaped"]
                   and row["terminated"] and row["timed_out"] for row in rows)
        _assert_all_cores_reaped(rows)
        assert len(readers) == 1
        assert readers[0].is_alive() is not reclaim_read
        assert time.monotonic() - started < 1.0 + perf.CORE_WAIT_SECONDS + 3.0
    finally:
        release.set()
        for timer in timers:
            timer.cancel()
            timer.join(2.0)
        for reader in readers:
            reader.join(2.0)
            assert not reader.is_alive()


@pytest.mark.parametrize("drift,expected_column", [
    ("draw", "label"), ("availability", "label_available_at_us"),
    ("missing", "spot"), ("warmup", "p_up"),
])
def test_fix4_main_rejects_full_sample_and_denominator_drifts(
        tmp_path, monkeypatch, drift, expected_column):
    """Actual later-part input/value changes exercise DRAW, causal time and denominators."""
    opens = []

    def opener(client, request):
        opens.append(request.start_utc)
        if len(opens) != 3:
            return bundle()
        selected = bundle(label="DRAW" if drift == "draw" else "UP",
                          candle_count=0 if drift == "missing" else 300)
        if drift == "availability":
            labels = list(selected.iter_labels())
            labels[0].available_at_us += 1
            selected.iter_labels = lambda: iter(labels)
        return selected

    evidence = _fix4_setup(tmp_path, monkeypatch, opener=opener,
                           fail_core="core-2" if drift == "warmup" else None,
                           core_mode="warmup")
    assert perf.main(_fix4_argv(evidence, mode="candidates")) == 4
    shared, independent = json.loads((evidence / "runs.json").read_text())
    assert shared["complete"] is True
    assert independent["complete"] is False
    assert any(expected_column in reason for reason in independent["sample_comparison_reasons"])
    first, later = independent["instances"]
    if drift in ("missing", "warmup"):
        reason = "missing_spot" if drift == "missing" else "warming_up"
        assert later["missing_by_reason"][reason] == later["samples_rows"]
        assert later["valued_rows"] == 0 < first["valued_rows"]
    _assert_all_cores_reaped(shared["instances"] + independent["instances"])


def test_fix4_main_healthy_three_arm_control_preserves_single_stream_counts(tmp_path, monkeypatch):
    """The actual shared/prefetch/repeated-read paths must still succeed without total-count confusion."""
    evidence = _fix4_setup(tmp_path, monkeypatch)
    assert perf.main(_fix4_argv(evidence, mode="candidates", strategy="both")) == 0
    shared, prefetched, independent = json.loads((evidence / "runs.json").read_text())
    assert all(run["complete"] for run in (shared, prefetched, independent))
    assert shared["events"] == prefetched["events"]
    assert independent["events"] == 2 * shared["events"]
    assert independent["bundle_opens"] == 2 and shared["bundle_opens"] == 1
    assert prefetched["prefetch_opened"] == 1
    assert len(independent["parts"]) == 2
    assert independent["source_comparison_reasons"] == []
    for part in independent["parts"]:
        assert part["day_sources"] == shared["day_sources"]
        assert part["events"] == shared["events"]
        assert part["row_counts"] == shared["row_counts"]
    comparison = json.loads((evidence / "arm-comparison.json").read_text())
    assert comparison["identical"] is True
    _assert_all_cores_reaped(shared["instances"] + prefetched["instances"] + independent["instances"])
