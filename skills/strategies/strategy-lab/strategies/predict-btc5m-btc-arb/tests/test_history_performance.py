"""Performance-path tests: result reuse, shared input, bounded prefetch.

Synthetic bundles are counterexamples only; the CLI pilot uses the real facade.
"""
import importlib.util
import json
import os
import signal
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
