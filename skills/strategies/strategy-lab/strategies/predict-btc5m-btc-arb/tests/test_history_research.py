"""Offline event/CLI tests; synthetic records are never research evidence."""
import importlib.util
import json
import os
import socket
import subprocess
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

LAB = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

research = load("native_history_research", LAB/"history_research.py")
offline = load("native_history_offline", LAB/"tests/offline_exec.py")


def bundle(label="UP", metadata_at=None, candle_count=300):
    base = research.to_us(research.START.replace(tzinfo=None))
    def row(payload, at):
        return SimpleNamespace(payload=payload, available_at_us=at)
    identity = row(dict(round_id="123", starts_at_us=base, ends_at_us=base+300_000_000),
                   base if metadata_at is None else base+metadata_at)
    strike = row(dict(dataset=research.DATASET_ROUNDS, round_id="123", start_price=Decimal("100.25")), base)
    candles = [row(dict(dataset=research.DATASET_KLINES, close_exclusive_us=base+(index+1)*1_000_000,
                        close=Decimal("101")), base+(index+1)*1_000_000) for index in range(candle_count)]
    labels = [row(dict(round_id="123", starts_at_us=base, ends_at_us=base+300_000_000,
                       official_outcome=label), base+360_000_000)]
    return SimpleNamespace(iter_metadata=lambda: iter([identity]), iter_features=lambda: iter([strike, *candles]),
                           iter_labels=lambda: iter(labels))


def test_events_causal_fixed_strike_isolated_labels_and_complete_consumption():
    contexts = []
    events = list(research.day_events(bundle(), research.START, research.START+timedelta(minutes=5), contexts))
    values = [event for event in events if event["payload"]["type"] == "value"]
    assert len(values) == 6 and len(events) == 306
    assert all(event["payload"]["strike"] == 100.25 for event in values)
    assert [row["secs_left"] for row in contexts] == [270,240,180,120,60,30]
    text = json.dumps(events)
    assert not any(key in text for key in ("official_outcome", "resolved_at", "end_price"))
    contexts_changed = []
    changed = list(research.day_events(bundle("DOWN"), research.START, research.START+timedelta(minutes=5), contexts_changed))
    assert events == changed
    assert contexts[0]["label"] == "UP" and contexts_changed[0]["label"] == "DOWN"
    assert all(events[index-1]["payload"]["type"] == "spot" for index,event in enumerate(events)
               if event["payload"]["type"] == "value")


def test_future_identity_missing_exact_candle_and_no_denominator_shrink():
    contexts = []
    events = list(research.day_events(bundle(metadata_at=61_000_000,candle_count=130),
                  research.START, research.START+timedelta(minutes=5), contexts))
    assert len(contexts) == 6
    assert [event["payload"]["type"] for event in events].count("value") == 1
    assert contexts[0]["reason"] == "identity_not_available"
    assert contexts[-1]["reason"] == "missing_spot"


def cli_command(tmp_path):
    input_path = tmp_path/"input.jsonl"
    contexts = []
    events = list(research.day_events(bundle(), research.START, research.START+timedelta(minutes=5), contexts))
    input_path.write_text("".join(json.dumps(dict(event, schema_version="btc-arb-history/1", seq=index))+"\n"
                                  for index,event in enumerate(events)))
    base = research.to_us(research.START.replace(tzinfo=None))//1000
    return [str(research.BINARY), "--config", str(LAB/"config.json"), "--input", str(input_path),
            "--output", str(tmp_path/"values.jsonl"), "--summary", str(tmp_path/"summary.json"),
            "--from-ms", str(base), "--to-ms", str(base+300000)], contexts


def test_real_history_binary_under_socket_denial_and_empty_environment(tmp_path):
    pid = os.fork()
    if pid == 0:
        offline.install_filter()
        try:
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except PermissionError:
            os._exit(0)
        os._exit(1)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    command, contexts = cli_command(tmp_path)
    cwd = tmp_path/"empty"
    cwd.mkdir()
    result = subprocess.run(command, cwd=cwd, env={"LANG":"C", "TZ":"UTC"},
                            capture_output=True, close_fds=True, timeout=10,
                            preexec_fn=offline.install_filter)
    assert result.returncode == 0
    research.merge_values(contexts, tmp_path/"values.jsonl")
    assert all(row["p_up"] is not None for row in contexts)
    assert contexts[0]["samples"] == 29
    summary = json.loads((tmp_path/"summary.json").read_text())
    assert summary == {"complete":True,"error":None,"native_exit":0,"spots":300,"values":6}


@pytest.mark.parametrize("extra", [["--live"], ["--rpc-url","http://forbidden"], ["--wallet","forbidden"]])
def test_unknown_live_rpc_wallet_options_rejected_before_io(tmp_path, extra):
    command, _ = cli_command(tmp_path)
    result = subprocess.run(command+extra, capture_output=True, timeout=10, env={"LANG":"C", "TZ":"UTC"})
    assert result.returncode == 64
    assert not (tmp_path/"values.jsonl").exists()


def test_existing_outputs_are_not_overwritten(tmp_path):
    command, _ = cli_command(tmp_path)
    (tmp_path/"values.jsonl").write_text("old evidence")
    result = subprocess.run(command, capture_output=True, timeout=10, env={"LANG":"C", "TZ":"UTC"})
    assert result.returncode != 0
    assert (tmp_path/"values.jsonl").read_text() == "old evidence"


def test_missing_and_duplicate_rust_rows_fail_closed(tmp_path):
    path = tmp_path/"values.jsonl"
    path.write_text("")
    with pytest.raises(ValueError, match="missing Rust"):
        research.merge_values([dict(round_id="123", at_ms=1, reason="requested")], path)
    path.write_text(json.dumps(dict(round_id="unexpected", at_ms=1))+"\n")
    with pytest.raises(ValueError, match="unexpected"):
        research.merge_values([], path)


def test_exclusive_json_and_same_source_report_csv(tmp_path):
    research.write_json(tmp_path/"one.json", {"value":1})
    with pytest.raises(FileExistsError):
        research.write_json(tmp_path/"one.json", {"value":2})
    row = {key: 1.234567891 for key in ("total", "binary", "draw", "direction_accuracy", "binary_brier",
                                     "binary_logloss", "brier_delta_vs05", "sigma_floor_ratio")}
    row.update(partition="IS", offset=30)
    text = research.render_report([row], {"days":1}, [])
    assert "1.23456789" in text and "Sharpe：N/A" in text


def test_budget_overrun_during_final_facade_verification_is_not_success(tmp_path, monkeypatch):
    from dataclasses import dataclass
    import io

    @dataclass
    class Coverage:
        stored_rows: int = 301

    clock = [0.0]
    daily_bundle = bundle()
    daily_bundle.content_manifest = {}
    daily_bundle.availability_assumptions = []
    daily_bundle.verified = False
    daily_bundle._window = SimpleNamespace(coverage=Coverage(), provenance_manifest={},
                                          missing=[], pending=[], conflicts=[])
    def verify():
        clock[0] = 301.0
        daily_bundle.verified = True
        return "synthetic-content"
    daily_bundle.verify_consumed = verify

    class Process:
        stdin = io.BytesIO()
        returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = -15
        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(research.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(research, "iter_history_input", lambda *args: daily_bundle)
    monkeypatch.setattr(research.subprocess, "Popen", lambda *args, **kwargs: Process())
    evidence = tmp_path/"partial"
    report = evidence/"report.md"
    with pytest.raises(TimeoutError, match="budget"):
        research.run_research(None, mode="pilot", as_of=research.END, evidence=evidence, report=report)
    result = json.loads((evidence/"run.json").read_text())
    assert result["complete"] is False
    assert result["failure"] == "TimeoutError"
    assert result["verified_days"] == 1 and result["native_exit"] == -15
    assert not report.exists()
