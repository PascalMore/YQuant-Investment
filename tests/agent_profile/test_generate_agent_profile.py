"""Tests for scripts/generate_agent_profile.py"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the script is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_agent_profile import (
    HERMES_JOB_SCRIPT_MAP,
    _validate_cron,
    parse_heartbeat_schedule,
    scan_skills,
    generate_hermes_profile,
    AgentProfileModel,
    ScheduledJob,
    SkillEntry,
    write_outputs,
    validate_hermes_profile,
    compute_file_hash,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HEARTBEAT_SAMPLE = """
## 调度汇总

| 任务 | 调度 | 时间 | 状态 |
|------|------|------|------|
| 每日全球市场日报 | cron | `0 8 * * 1-5` | active |
| 每日SmartMoney数据报告发送 | cron | `30 20 * * 1-5` | active |
| 每日Argus数据批处理 | cron | `35 20 * * 1-5` | active |
| 每周酒店价格抓取 | cron | `10 6 * * 1` | active |
| 每日自动代码提交 | cron | `30 3 * * *` | active |
"""


HEARTBEAT_DUPLICATE = """
## 调度汇总

| 任务 | 调度 | 时间 | 状态 |
|------|------|------|------|
| 每日全球市场日报 | cron | `0 8 * * 1-5` | active |
| 每日全球市场日报 | cron | `0 9 * * 1-5` | active |
"""


HEARTBEAT_BAD_CRON = """
## 调度汇总

| 任务 | 调度 | 时间 | 状态 |
|------|------|------|------|
| 每日全球市场日报 | cron | `99 8 * * 1-5` | active |
"""


HEARTBEAT_NO_TABLE = """
## 定期检查
- 检查1
"""


@pytest.fixture
def temp_project(tmp_path):
    """Create a minimal YQuant-like project tree."""
    root = tmp_path / "yquant"
    root.mkdir()

    # Source markdown files
    (root / "SOUL.md").write_text("# SOUL", encoding="utf-8")
    (root / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    (root / "USER.md").write_text("# USER", encoding="utf-8")
    (root / "MEMORY.md").write_text("# MEMORY", encoding="utf-8")
    (root / "IDENTITY.md").write_text("# IDENTITY", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# CLAUDE", encoding="utf-8")
    (root / "TOOLS.md").write_text("# TOOLS", encoding="utf-8")
    (root / "HEARTBEAT.md").write_text(HEARTBEAT_SAMPLE, encoding="utf-8")

    # Skills structure
    skills = root / "skills"
    data = skills / "data"
    data.mkdir(parents=True)
    (data / "data-pipeline").mkdir()
    (data / "data-pipeline" / "SKILL.md").write_text(
        '---\nname: data-pipeline\ndescription: "Data pipeline framework"\n---\n# Data Pipeline',
        encoding="utf-8",
    )
    (data / "portfolio").mkdir()
    (data / "portfolio" / "SKILL.md").write_text(
        '---\nname: portfolio\ndescription: "Portfolio management"\n---\n# Portfolio',
        encoding="utf-8",
    )

    return root


# ---------------------------------------------------------------------------
# A-001: Heartbeat schedule parsing
# ---------------------------------------------------------------------------

def test_parse_heartbeat_schedule_table():
    jobs = parse_heartbeat_schedule(HEARTBEAT_SAMPLE)

    assert len(jobs) == 5
    names = [j.name for j in jobs]
    assert "每日全球市场日报" in names
    assert "每日SmartMoney数据报告发送" in names
    assert "每日Argus数据批处理" in names
    assert "每周酒店价格抓取" in names
    assert "每日自动代码提交" in names

    for job in jobs:
        assert job.enabled is True
        assert job.schedule_type == "cron"
        assert job.script in HERMES_JOB_SCRIPT_MAP.values()
        assert job.no_agent is True
        assert job.deliver == "local"


def test_parse_heartbeat_active_vs_inactive():
    inactive = HEARTBEAT_SAMPLE.replace("active", "paused")
    jobs = parse_heartbeat_schedule(inactive)
    assert all(j.enabled is False for j in jobs)


def test_parse_heartbeat_no_table():
    jobs = parse_heartbeat_schedule(HEARTBEAT_NO_TABLE)
    assert jobs == []


# ---------------------------------------------------------------------------
# A-001 / Reject: duplicate job names
# ---------------------------------------------------------------------------

def test_reject_duplicate_job_name():
    with pytest.raises(ValueError, match="Duplicate job name"):
        parse_heartbeat_schedule(HEARTBEAT_DUPLICATE)


# ---------------------------------------------------------------------------
# A-001 / Reject: invalid cron expression
# ---------------------------------------------------------------------------

def test_reject_invalid_cron_expression():
    with pytest.raises(ValueError, match="Invalid cron expression"):
        parse_heartbeat_schedule(HEARTBEAT_BAD_CRON)


def test_validate_cron_valid():
    assert _validate_cron("0 8 * * 1-5") is True
    assert _validate_cron("30 20 * * 1-5") is True
    assert _validate_cron("35 20 * * 1-5") is True
    assert _validate_cron("10 6 * * 1") is True
    assert _validate_cron("30 3 * * *") is True


def test_validate_cron_invalid():
    assert _validate_cron("99 8 * * 6") is False  # dow 6 ok but hour 99 invalid
    assert _validate_cron("0 8 * * 8") is False   # dow 8 out of range
    assert _validate_cron("not a cron") is False


# ---------------------------------------------------------------------------
# A-005: Skills scanner
# ---------------------------------------------------------------------------

def test_scan_skills_manifest(temp_project):
    skills = scan_skills(str(temp_project))

    ids = [s.id for s in skills]
    assert "data-pipeline" in ids
    assert "portfolio" in ids

    dp = next(s for s in skills if s.id == "data-pipeline")
    assert dp.description == "Data pipeline framework"
    assert "SKILL.md" in dp.path

    pf = next(s for s in skills if s.id == "portfolio")
    assert pf.description == "Portfolio management"


def test_scan_skills_empty(tmp_path):
    # No skills directory
    root = tmp_path / "empty"
    root.mkdir()
    skills = scan_skills(str(root))
    assert skills == []


def test_scan_skills_id_uniqueness_per_path(tmp_path):
    """Each skill dir gets a unique id from its path segment."""
    from generate_agent_profile import scan_skills
    root = tmp_path / "uniq"
    root.mkdir()
    skills_d = root / "skills"
    skills_d.mkdir()
    cat = skills_d / "data"
    cat.mkdir()
    (cat / "pipeline").mkdir()
    (cat / "pipeline" / "SKILL.md").write_text("---\nname: data-pipeline\ndescription: desc\n---\n# DP", encoding="utf-8")
    (cat / "portfolio").mkdir()
    (cat / "portfolio" / "SKILL.md").write_text("---\nname: portfolio\ndescription: desc\n---\n# Portfolio", encoding="utf-8")

    skills = scan_skills(str(root))
    ids = [s.id for s in skills]
    assert len(ids) == len(set(ids))  # all unique


# ---------------------------------------------------------------------------
# A-002/A-003/A-004: Hermes profile generation
# ---------------------------------------------------------------------------

def test_generate_hermes_profile_files(temp_project):
    model = AgentProfileModel(
        profile="yquant",
        platform="hermes",
        source_root=temp_project,
        soul=(temp_project / "SOUL.md").read_text(),
        user_memory=(temp_project / "USER.md").read_text(),
        project_memory=(temp_project / "MEMORY.md").read_text(),
    )
    model.scheduled_jobs = parse_heartbeat_schedule(HEARTBEAT_SAMPLE)
    model.skills = scan_skills(str(temp_project))

    outputs = generate_hermes_profile(model)

    # Check required files
    assert "profile.yaml" in outputs
    assert "config.yaml" in outputs
    assert "SOUL.md" in outputs
    assert "memories/USER.md" in outputs
    assert "skills/skills_manifest.json" in outputs
    assert "cron/jobs.json" in outputs

    # profile.yaml content
    assert "name: yquant" in outputs["profile.yaml"]
    assert "platform: hermes" in outputs["profile.yaml"]

    # skills manifest valid JSON
    skills_data = json.loads(outputs["skills/skills_manifest.json"])
    assert skills_data["schema_version"] == 1
    assert len(skills_data["skills"]) == 2

    # jobs.json valid JSON, all active
    jobs_data = json.loads(outputs["cron/jobs.json"])
    assert jobs_data["schema_version"] == 1
    assert len(jobs_data["jobs"]) == 5
    assert all(j["enabled"] for j in jobs_data["jobs"])
    assert jobs_data["_missing_scripts"] is None


def test_generate_hermes_no_overwrite_source(temp_project):
    """Generating must not modify source files."""
    import time
    mtime_before = (temp_project / "HEARTBEAT.md").stat().st_mtime
    time.sleep(0.01)

    model = AgentProfileModel(profile="yquant", platform="hermes", source_root=temp_project)
    model.scheduled_jobs = parse_heartbeat_schedule(HEARTBEAT_SAMPLE)
    generate_hermes_profile(model)

    mtime_after = (temp_project / "HEARTBEAT.md").stat().st_mtime
    assert mtime_after == mtime_before


# ---------------------------------------------------------------------------
# A-003: dry-run does not write files
# ---------------------------------------------------------------------------

def test_dry_run_no_files_written(temp_project):
    outputs = {"foo.txt": "hello"}
    with tempfile.TemporaryDirectory() as td:
        written = write_outputs(outputs, Path(td), dry_run=True)
        assert written == ["foo.txt"]
        assert not (Path(td) / "foo.txt").exists()


# ---------------------------------------------------------------------------
# A-004: output-dir writes to specified directory
# ---------------------------------------------------------------------------

def test_output_dir_writes_files(temp_project):
    model = AgentProfileModel(profile="yquant", platform="hermes", source_root=temp_project)
    model.scheduled_jobs = parse_heartbeat_schedule(HEARTBEAT_SAMPLE)
    model.skills = scan_skills(str(temp_project))
    outputs = generate_hermes_profile(model)

    with tempfile.TemporaryDirectory() as td:
        written = write_outputs(outputs, Path(td))
        assert len(written) == len(outputs)
        for rel in outputs:
            assert (Path(td) / rel).exists()


# ---------------------------------------------------------------------------
# A-006: missing Hermes script mapping
# ---------------------------------------------------------------------------

def test_missing_script_in_jobs_json():
    """Job with no script mapping produces _missing_scripts entry."""
    jobs = [
        ScheduledJob(name="未知任务", schedule="0 8 * * *", enabled=True, script=None),
    ]
    model = AgentProfileModel(
        profile="yquant", platform="hermes", source_root=Path(".")
    )
    model.scheduled_jobs = jobs
    outputs = generate_hermes_profile(model)
    data = json.loads(outputs["cron/jobs.json"])
    assert "未知任务" in data["_missing_scripts"]
    assert data["jobs"][0]["enabled"] is True


# ---------------------------------------------------------------------------
# A-008: path traversal prevention
# ---------------------------------------------------------------------------

def test_path_traversal_blocked(temp_project):
    outputs = {"../../etc/passwd": "evil"}
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(ValueError, match="Path traversal"):
            write_outputs(outputs, Path(td))


# ---------------------------------------------------------------------------
# A-002: integration test in temp directory
# ---------------------------------------------------------------------------

def test_integration_generate_full_profile(temp_project):
    """Full generate + write + validate cycle in temp dir."""
    import generate_agent_profile as gap
    import argparse

    ns = argparse.Namespace(
        platform="hermes",
        profile="yquant",
        source_root=str(temp_project),
        output_dir=str(temp_project / "dist"),
        dry_run=False,
        validate=True,
    )

    model = gap.load_profile_model(ns)
    assert len(model.scheduled_jobs) == 5
    assert len(model.skills) == 2

    outputs = gap.generate_hermes_profile(model)
    profile_dir = Path(ns.output_dir) / "hermes" / "yquant"
    written = gap.write_outputs(outputs, profile_dir)

    manifest = gap.generate_manifest(ns, model, profile_dir, written)
    assert manifest["schema_version"] == 1
    assert manifest["platform"] == "hermes"
    assert len(manifest["inputs"]) > 0
    assert len(manifest["outputs"]) > 0

    # Write manifest file (mimics main())
    manifest_dir = profile_dir / "migration"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "generated-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    errors = gap.validate_hermes_profile(profile_dir)
    assert errors == [], f"Validation errors: {errors}"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert data["schema_version"] == 1


# ---------------------------------------------------------------------------
# A-007: no .env read
# ---------------------------------------------------------------------------

def test_no_env_read(monkeypatch, temp_project):
    """Ensure .env is never opened."""
    opened = []
    original_open = open

    def tracking_open(path, *args, **kwargs):
        path_str = str(path)
        if ".env" in path_str:
            opened.append(path_str)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", tracking_open)

    import generate_agent_profile as gap
    import argparse
    ns = argparse.Namespace(
        platform="hermes", profile="test",
        source_root=str(temp_project),
    )
    gap.load_profile_model(ns)

    assert not any(".env" in p for p in opened), f".env was read: {opened}"


# ---------------------------------------------------------------------------
# Regression: all 5 current YQuant jobs
# ---------------------------------------------------------------------------

def test_all_5_yquant_jobs_present():
    jobs = parse_heartbeat_schedule(HEARTBEAT_SAMPLE)
    expected = [
        "每日全球市场日报",
        "每日SmartMoney数据报告发送",
        "每日Argus数据批处理",
        "每周酒店价格抓取",
        "每日自动代码提交",
    ]
    actual_names = [j.name for j in jobs]
    assert set(expected) == set(actual_names)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
