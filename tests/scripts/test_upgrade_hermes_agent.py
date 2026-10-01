# -*- coding: utf-8 -*-
"""Tests for scripts/upgrade/upgrade_hermes_agent.py (SPEC-10-005 / DESIGN-10-005).

Covers:
  Unit:  --help, arg conflicts, manifest serialization, command wrapper,
         zip exclude, ref classify, secret redaction, dry-run no-mutation,
         rollback dry-run plan.
  Integ: temp git repo matrix — ff, local-commit merge, conflict, rollback.
"""
import importlib.util
import json
import os
from datetime import datetime
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "upgrade" / "upgrade_hermes_agent.py"


def _load_module():
    """Import the upgrade script as a module (it's not a package).

    Must register in sys.modules BEFORE exec so the dataclass decorator
    can resolve cls.__module__ during class definition.
    """
    name = "upgrade_hermes_agent"
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ua():
    return _load_module()


# ---------------------------------------------------------------------------
# git helper for temp repos
# ---------------------------------------------------------------------------


def _git(cwd, *args, env=None, check=True):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                       text=True, env=env, cwd=str(cwd))
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args} failed in {cwd}: {r.stderr}")
    return r


def _make_bare(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(path)], capture_output=True, check=True)


def _make_repo(path, origin=None, upstream=None):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@test.com"],
                   capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"],
                   capture_output=True, check=True)
    if origin:
        _git(path, "remote", "add", "origin", str(origin))
    if upstream:
        _git(path, "remote", "add", "upstream", str(upstream))
    return path


def _commit(path, msg, filename="README.md", content=None):
    f = Path(path) / filename
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content if content is not None else msg)
    _git(path, "add", "-A")
    _git(path, "commit", "-m", msg)


# ---------------------------------------------------------------------------
# UT-001: --help
# ---------------------------------------------------------------------------


def test_help_exit_zero(ua):
    r = subprocess.run([sys.executable, str(SCRIPT_PATH), "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "--version" in r.stdout
    assert "--dry-run" in r.stdout
    assert "--rollback" in r.stdout
    assert "--no-restart" in r.stdout
    assert "--no-push" in r.stdout


# ---------------------------------------------------------------------------
# UT-002: arg conflict (--rollback + --no-restart/--no-push/--version)
# ---------------------------------------------------------------------------


def test_rollback_conflict_no_restart(ua):
    r = subprocess.run([sys.executable, str(SCRIPT_PATH),
                        "--rollback", "/tmp/x.json", "--no-restart"],
                       capture_output=True, text=True)
    assert r.returncode == 2


def test_rollback_conflict_no_push(ua):
    r = subprocess.run([sys.executable, str(SCRIPT_PATH),
                        "--rollback", "/tmp/x.json", "--no-push"],
                       capture_output=True, text=True)
    assert r.returncode == 2


def test_rollback_conflict_version(ua):
    r = subprocess.run([sys.executable, str(SCRIPT_PATH),
                        "--rollback", "/tmp/x.json", "--version", "v1.0"],
                       capture_output=True, text=True)
    assert r.returncode == 2


# ---------------------------------------------------------------------------
# UT-003: manifest serialization round-trip
# ---------------------------------------------------------------------------


def test_manifest_round_trip(ua, tmp_path):
    cfg = ua.UpgradeConfig(
        repo=tmp_path, version_ref="upstream/main", backup_dir=tmp_path,
        dry_run=False, restart=True, push=True, rollback_manifest=None,
        yes=True, verbose=False,
    )
    m = ua.init_manifest(cfg)
    m["pre_head"] = "abc123"
    m["target_sha"] = "def456"
    m["backup_zip"] = str(tmp_path / "backup.zip")
    m["dirty_files"] = ["a.py", "b.py"]
    mpath = tmp_path / "manifest.json"
    ua.write_manifest(m, mpath)
    assert mpath.exists()
    loaded = json.loads(mpath.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == "1"
    assert loaded["pre_head"] == "abc123"
    assert loaded["target_sha"] == "def456"
    assert loaded["dirty_files"] == ["a.py", "b.py"]
    assert loaded["repo"] == str(tmp_path)
    # load_manifest should round-trip
    loaded2 = ua.load_manifest(mpath)
    assert loaded2 == loaded


def test_load_manifest_rejects_bad_schema(ua, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": "99", "repo": "x"}))
    with pytest.raises(ua.UpgradeError):
        ua.load_manifest(bad)


# ---------------------------------------------------------------------------
# UT-004: command wrapper records cmd/cwd/exit_code, failure no secret leak
# ---------------------------------------------------------------------------


def test_run_cmd_records_success(ua):
    log = []
    r = ua.run_cmd(["true"], manifest=log)
    assert r.exit_code == 0
    assert len(log) == 1
    assert log[0]["exit_code"] == 0
    assert log[0]["cmd"] == ["true"]


def test_run_cmd_records_failure(ua):
    log = []
    r = ua.run_cmd(["false"], manifest=log)
    assert r.exit_code != 0
    assert log[0]["exit_code"] != 0


def test_run_cmd_missing_command(ua):
    r = ua.run_cmd(["definitely-not-a-cmd-xyz"])
    assert r.exit_code == 127


# ---------------------------------------------------------------------------
# UT-005 / zip exclude: .env, venv, .git/objects, node_modules not in zip
# ---------------------------------------------------------------------------


def test_zip_exclude_secrets_and_build(ua, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("# config")
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hi')")
    (repo / ".env").write_text("SECRET=token123")
    (repo / "auth.json").write_text("{}")
    (repo / "venv").mkdir()
    (repo / "venv" / "big.bin").write_text("x" * 1000)
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "pkg").write_text("x")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "m.pyc").write_text("x")
    (repo / "secret.pem").write_text("key")
    (repo / ".install_method").write_text("git")
    (repo / ".git").mkdir()
    (repo / ".git" / "objects").mkdir()
    (repo / ".git" / "objects" / "aa").write_text("gitobject")

    zpath = tmp_path / "backup.zip"
    manifest = {"commands": []}
    ua.create_zip_backup(repo, zpath, manifest, verbose=False)

    import zipfile
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    assert "pyproject.toml" in names
    assert "src/main.py" in names
    assert ".install_method" in names
    # excluded
    assert ".env" not in names
    assert "auth.json" not in names
    assert "secret.pem" not in names
    assert not any(n.startswith("venv/") for n in names)
    assert not any(n.startswith("node_modules/") for n in names)
    assert not any("__pycache__" in n for n in names)
    assert not any(n.startswith(".git/objects/") for n in names)
    assert not any(n.endswith(".pyc") for n in names)


def test_safe_unzip_rejects_zip_slip(ua, tmp_path):
    import zipfile
    zpath = tmp_path / "slip.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../../escape.txt", "malicious")
    with pytest.raises(ua.UpgradeError):
        ua.safe_unzip(zpath, tmp_path / "dest")


# ---------------------------------------------------------------------------
# UT-006: ref classify
# ---------------------------------------------------------------------------


def _make_classify_repo(tmp_path):
    """Create a repo with upstream/main and origin remotes for classify testing."""
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    return work


def test_classify_already_up_to_date(ua, tmp_path):
    work = _make_classify_repo(tmp_path)
    head = _git(work, "rev-parse", "HEAD").stdout.strip()
    state = ua.RepoState(repo=work, branch="main", pre_head=head,
                         origin_url="", upstream_url="", install_method="git",
                         dirty_files=[], local_only_commits=[],
                         origin_main_sha=head)
    manifest = {"commands": []}
    plan = ua.classify_git_relation(
        ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                         backup_dir=tmp_path, dry_run=False, restart=False,
                         push=False, rollback_manifest=None, yes=True, verbose=False),
        state, head, manifest)
    assert plan.merge_mode == "already-up-to-date"


def test_classify_ff_only(ua, tmp_path):
    work = _make_classify_repo(tmp_path)
    head = _git(work, "rev-parse", "HEAD").stdout.strip()
    # advance upstream
    _commit(work, "upstream change")
    _git(work, "push", "upstream", "main")
    target = _git(work, "rev-parse", "HEAD").stdout.strip()
    # reset local back to old head (so local is behind)
    _git(work, "reset", "--hard", head)
    state = ua.RepoState(repo=work, branch="main", pre_head=head,
                         origin_url="", upstream_url="", install_method="git",
                         dirty_files=[], local_only_commits=[], origin_main_sha=head)
    manifest = {"commands": []}
    plan = ua.classify_git_relation(
        ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                         backup_dir=tmp_path, dry_run=False, restart=False,
                         push=False, rollback_manifest=None, yes=True, verbose=False),
        state, target, manifest)
    assert plan.merge_mode == "ff-only"


def test_classify_merge_diverged(ua, tmp_path):
    work = _make_classify_repo(tmp_path)
    head = _git(work, "rev-parse", "HEAD").stdout.strip()
    # local commits a new change
    _commit(work, "local change", filename="local.txt")
    local_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    # upstream also advances: reset to old head, commit, push, then restore local
    # easier: clone upstream state into a temp and advance it
    tmp_up = tmp_path / "tmp_up"
    _make_repo(tmp_up, origin=tmp_path / "upstream.git")
    _git(tmp_up, "pull", "origin", "main")
    _commit(tmp_up, "upstream change", filename="up.txt")
    _git(tmp_up, "push", "origin", "main")
    # fetch in work so it sees upstream/main
    _git(work, "fetch", "upstream", "main")
    target = _git(work, "rev-parse", "upstream/main").stdout.strip()
    state = ua.RepoState(repo=work, branch="main", pre_head=local_head,
                         origin_url="", upstream_url="", install_method="git",
                         dirty_files=[], local_only_commits=["local change"],
                         origin_main_sha=head)
    manifest = {"commands": []}
    plan = ua.classify_git_relation(
        ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                         backup_dir=tmp_path, dry_run=False, restart=False,
                         push=False, rollback_manifest=None, yes=True, verbose=False),
        state, target, manifest)
    assert plan.merge_mode == "merge"
    assert plan.local_commits_need_protection is True


# ---------------------------------------------------------------------------
# UT-006b: secret redaction
# ---------------------------------------------------------------------------


def test_redact_github_token(ua):
    text = "using ghp_1234567890abcdefghijklmnop to auth"
    out = ua.redact(text)
    assert "ghp_1234567890abcdefghijklmnop" not in out
    assert "REDACTED" in out


def test_redact_token_assignment(ua):
    text = "token=abcdefghijklmnopqrstuvwxyz123456"
    out = ua.redact(text)
    assert "abcdefghijklmnopqrstuvwxyz123456" not in out


def test_redact_private_key(ua):
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOQIBAA\n-----END RSA PRIVATE KEY-----"
    out = ua.redact(text)
    assert "MIIBOQIBAA" not in out


# ---------------------------------------------------------------------------
# IT-001: temp git repo ff merge
# ---------------------------------------------------------------------------


def test_integration_ff_merge(ua, tmp_path):
    """IT-001: local behind upstream, ff merge to target."""
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    base = _git(work, "rev-parse", "HEAD").stdout.strip()

    # advance upstream via temp clone
    tmp_up = tmp_path / "tmp_up"
    _make_repo(tmp_up, origin=upstream_bare)
    _git(tmp_up, "pull", "origin", "main")
    _commit(tmp_up, "upstream feature")
    _git(tmp_up, "push", "origin", "main")
    target = _git(tmp_up, "rev-parse", "HEAD").stdout.strip()

    # run upgrade on work (no restart, no push, no real install since not hermes)
    # We can't run full upgrade (install/verify will fail on non-hermes repo),
    # so test the git layer directly: fetch + classify + merge.
    cfg = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                           backup_dir=tmp_path, dry_run=False, restart=False,
                           push=False, rollback_manifest=None, yes=True, verbose=False)
    manifest = ua.init_manifest(cfg)
    state = ua.inspect_repo(cfg, manifest)
    assert state.pre_head == base

    ua.fetch_remotes(cfg, manifest, "upstream/main")
    target_sha = ua.resolve_target_ref(cfg, manifest, "upstream/main")
    assert target_sha == target
    plan = ua.classify_git_relation(cfg, state, target_sha, manifest)
    assert plan.merge_mode == "ff-only"
    ua.apply_merge(cfg, plan, manifest)
    post = _git(work, "rev-parse", "HEAD").stdout.strip()
    assert post == target


# ---------------------------------------------------------------------------
# IT-002: local commit + upstream commit -> merge commit, local preserved
# ---------------------------------------------------------------------------


def test_integration_local_commit_merge(ua, tmp_path):
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    base = _git(work, "rev-parse", "HEAD").stdout.strip()

    # local commit (Pascal fork)
    _commit(work, "local fix", filename="local_fix.txt")
    local_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    _git(work, "push", "origin", "main")

    # upstream advance
    tmp_up = tmp_path / "tmp_up"
    _make_repo(tmp_up, origin=upstream_bare)
    _git(tmp_up, "pull", "origin", "main")
    _commit(tmp_up, "upstream feature", filename="up_feature.txt")
    _git(tmp_up, "push", "origin", "main")

    cfg = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                           backup_dir=tmp_path, dry_run=False, restart=False,
                           push=False, rollback_manifest=None, yes=True, verbose=False)
    manifest = ua.init_manifest(cfg)
    state = ua.inspect_repo(cfg, manifest)
    ua.fetch_remotes(cfg, manifest, "upstream/main")
    target_sha = ua.resolve_target_ref(cfg, manifest, "upstream/main")
    plan = ua.classify_git_relation(cfg, state, target_sha, manifest)
    assert plan.merge_mode == "merge"
    assert plan.local_commits_need_protection is True
    # protect (origin already has local commit, so no push needed)
    ua.protect_local_commits(cfg, state, plan, manifest)
    ua.apply_merge(cfg, plan, manifest)
    post = _git(work, "rev-parse", "HEAD").stdout.strip()
    # merge commit differs from both local_head and target
    assert post != local_head
    assert post != target_sha
    # local fix commit is still reachable
    reachable = _git(work, "merge-base", "--is-ancestor", local_head, "HEAD",
                     check=False).returncode
    assert reachable == 0
    # both files present
    assert (work / "local_fix.txt").exists()
    assert (work / "up_feature.txt").exists()
    assert manifest["merge_mode"] == "merge"


# ---------------------------------------------------------------------------
# IT-003: conflict -> merge abort, exit non-zero, stash/manifest preserved
# ---------------------------------------------------------------------------


def test_integration_conflict_abort(ua, tmp_path):
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    # base file
    _commit(work, "init", filename="conflict.txt", content="line1\n")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")

    # local modifies same file
    _commit(work, "local edit", filename="conflict.txt", content="line1-local\n")
    local_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    _git(work, "push", "origin", "main")

    # upstream modifies same file differently
    tmp_up = tmp_path / "tmp_up"
    _make_repo(tmp_up, origin=upstream_bare)
    _git(tmp_up, "pull", "origin", "main")
    _commit(tmp_up, "upstream edit", filename="conflict.txt", content="line1-upstream\n")
    _git(tmp_up, "push", "origin", "main")

    cfg = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                           backup_dir=tmp_path, dry_run=False, restart=False,
                           push=False, rollback_manifest=None, yes=True, verbose=False)
    manifest = ua.init_manifest(cfg)
    state = ua.inspect_repo(cfg, manifest)
    ua.fetch_remotes(cfg, manifest, "upstream/main")
    target_sha = ua.resolve_target_ref(cfg, manifest, "upstream/main")
    plan = ua.classify_git_relation(cfg, state, target_sha, manifest)
    assert plan.merge_mode == "merge"
    ua.protect_local_commits(cfg, state, plan, manifest)

    with pytest.raises(ua.UpgradeError) as exc_info:
        ua.apply_merge(cfg, plan, manifest)
    assert "conflict" in str(exc_info.value).lower() or "冲突" in str(exc_info.value)
    # HEAD should be back to local (merge aborted)
    post = _git(work, "rev-parse", "HEAD").stdout.strip()
    assert post == local_head
    assert manifest["merge_mode"] == "abort-conflict"


# ---------------------------------------------------------------------------
# IT-004: rollback from manifest restores HEAD
# ---------------------------------------------------------------------------


def test_integration_rollback(ua, tmp_path):
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init", filename="keep.txt", content="keep\n")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    pre_head = _git(work, "rev-parse", "HEAD").stdout.strip()

    # do a ff upgrade
    tmp_up = tmp_path / "tmp_up"
    _make_repo(tmp_up, origin=upstream_bare)
    _git(tmp_up, "pull", "origin", "main")
    _commit(tmp_up, "upstream feature", filename="new.txt")
    _git(tmp_up, "push", "origin", "main")

    cfg = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                           backup_dir=tmp_path, dry_run=False, restart=False,
                           push=False, rollback_manifest=None, yes=True, verbose=False)
    manifest = ua.init_manifest(cfg)
    manifest["pre_head"] = pre_head
    manifest["pre_branch"] = "main"
    manifest["repo"] = str(work)
    state = ua.inspect_repo(cfg, manifest)
    ua.fetch_remotes(cfg, manifest, "upstream/main")
    target_sha = ua.resolve_target_ref(cfg, manifest, "upstream/main")
    plan = ua.classify_git_relation(cfg, state, target_sha, manifest)
    ua.apply_merge(cfg, plan, manifest)
    assert _git(work, "rev-parse", "HEAD").stdout.strip() != pre_head

    # create backup zip before rollback
    zpath = tmp_path / "backup.zip"
    ua.create_zip_backup(work, zpath, manifest, verbose=False)
    manifest["backup_zip"] = str(zpath)
    mpath = tmp_path / "manifest.json"
    ua.write_manifest(manifest, mpath)

    # rollback
    cfg2 = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                            backup_dir=tmp_path, dry_run=False, restart=False,
                            push=False, rollback_manifest=mpath, yes=True, verbose=False)
    code = ua.rollback_from_manifest(cfg2)
    assert code == 0
    restored = _git(work, "rev-parse", "HEAD").stdout.strip()
    assert restored == pre_head


# ---------------------------------------------------------------------------
# UT-008: rollback dry-run prints plan, does not execute
# ---------------------------------------------------------------------------


def test_rollback_dry_run_no_mutation(ua, tmp_path):
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    pre_head = _git(work, "rev-parse", "HEAD").stdout.strip()

    manifest = {
        "schema_version": "1",
        "repo": str(work),
        "pre_head": pre_head,
        "pre_branch": "main",
        "backup_zip": None,
        "stash_ref": None,
        "dirty_files": [],
    }
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))

    cfg = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                           backup_dir=tmp_path, dry_run=True, restart=False,
                           push=False, rollback_manifest=mpath, yes=True, verbose=False)
    code = ua.rollback_from_manifest(cfg)
    assert code == 0
    # HEAD unchanged
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == pre_head


# ---------------------------------------------------------------------------
# IT-005: executable bit
# ---------------------------------------------------------------------------


def test_executable_bit():
    assert os.access(str(SCRIPT_PATH), os.X_OK)


# ---------------------------------------------------------------------------
# UT-009: dry-run does not mutate repo
# ---------------------------------------------------------------------------


def test_dry_run_no_mutation(ua, tmp_path):
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    pre_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    # add a .install_method so inspect passes (needs git install_method)
    (work / ".install_method").write_text("git")

    cfg = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                           backup_dir=tmp_path, dry_run=True, restart=False,
                           push=False, rollback_manifest=None, yes=True, verbose=False)
    code = ua.upgrade(cfg)
    assert code == 0
    # HEAD unchanged
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == pre_head
    # no stash created
    r = _git(work, "stash", "list", check=False)
    assert r.stdout.strip() == ""
    # no zip / manifest written in backup_dir
    zips = list(tmp_path.glob("hermes-backup-*.zip"))
    manifests = list(tmp_path.glob("hermes-upgrade-*.json"))
    assert zips == []
    assert manifests == []


# ---------------------------------------------------------------------------
# Regression: successful already-up-to-date upgrade must have a complete
# manifest and must not crash while rendering its final summary.
# ---------------------------------------------------------------------------


def test_finalize_upgrade_success_records_complete_terminal_state(ua):
    manifest = ua.init_manifest(
        ua.UpgradeConfig(
            repo=Path("/tmp/hermes-agent"), version_ref="upstream/main",
            backup_dir=Path("/tmp"), dry_run=False, restart=False,
            push=False, rollback_manifest=None, yes=True, verbose=False,
        )
    )

    ua.finalize_upgrade_success(
        manifest,
        post_head="a" * 40,
        effective_version="v0.21.4+test",
    )

    assert manifest["outcome"] == "succeeded"
    completed_at = datetime.fromisoformat(manifest["completed_at"])
    assert completed_at.tzinfo is not None
    assert manifest["post_head"] == "a" * 40
    assert manifest["effective_version"] == "v0.21.4+test"
    assert ua.__version__ == "2.3.0"


def test_upgrade_already_up_to_date_writes_success_manifest(ua, tmp_path, monkeypatch):
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    (work / ".install_method").write_text("git")

    monkeypatch.setattr(ua, "install_editable", lambda *_args: None)
    monkeypatch.setattr(ua, "verify_cli", lambda *_args: "v0.21.4+test")
    monkeypatch.setattr(ua, "verify_import", lambda *_args: None)
    monkeypatch.setattr(ua, "verify_gateway_pre", lambda *_args: "healthy")

    cfg = ua.UpgradeConfig(
        repo=work, version_ref="upstream/main", backup_dir=tmp_path,
        dry_run=False, restart=False, push=False, rollback_manifest=None,
        yes=True, verbose=False,
    )
    assert ua.upgrade(cfg) == 0

    manifests = list(tmp_path.glob("hermes-upgrade-*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["merge_mode"] == "already-up-to-date"
    assert manifest["outcome"] == "succeeded"
    assert manifest["completed_at"] is not None
    assert manifest["post_head"] == _git(work, "rev-parse", "HEAD").stdout.strip()
    assert manifest["effective_version"] == "v0.21.4+test"


# ---------------------------------------------------------------------------
# Regression: T5 Review Finding 1 — rollback --dry-run --yes must NOT stash
# ---------------------------------------------------------------------------


def test_rollback_dry_run_dirty_no_stash(ua, tmp_path):
    """Finding 1 regression: --rollback --dry-run --yes 在 dirty repo 上
    必须只打印计划，不能 git stash push。"""
    upstream_bare = tmp_path / "upstream.git"
    origin_bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_bare(origin_bare)
    _make_repo(work, origin=origin_bare, upstream=upstream_bare)
    _commit(work, "init")
    _git(work, "push", "origin", "main")
    _git(work, "push", "upstream", "main")
    pre_head = _git(work, "rev-parse", "HEAD").stdout.strip()

    # introduce a dirty file
    (work / "scratch.txt").write_text("wip")
    assert (work / "scratch.txt").exists()

    manifest = {
        "schema_version": "1",
        "repo": str(work),
        "pre_head": pre_head,
        "pre_branch": "main",
        "backup_zip": None,
        "stash_ref": None,
        "dirty_files": ["scratch.txt"],
    }
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))

    cfg = ua.UpgradeConfig(repo=work, version_ref="upstream/main",
                           backup_dir=tmp_path, dry_run=True, restart=False,
                           push=False, rollback_manifest=mpath, yes=True,
                           verbose=False)
    code = ua.rollback_from_manifest(cfg)
    assert code == 0

    # HEAD unchanged
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == pre_head
    # stash list MUST be empty — dry-run must not actually stash
    r = _git(work, "stash", "list", check=False)
    assert r.stdout.strip() == "", f"dry-run leaked stash: {r.stdout!r}"
    # dirty file MUST still exist
    assert (work / "scratch.txt").exists()
    # dry-run plan must print the dirty-state hint for the real-execute path
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--rollback", str(mpath), "--dry-run", "--yes",
         "--repo", str(work), "--backup-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "DRY-RUN" in proc.stdout
    assert "未修改" in proc.stdout


# ---------------------------------------------------------------------------
# Regression: T5 Review Finding 2 — zip backup fail-fast on unreadable file
# ---------------------------------------------------------------------------


def test_zip_backup_fail_on_unreadable_file(ua, tmp_path):
    """Finding 2 regression: 普通候选文件读/写失败必须 raise UpgradeError，
    不能继续静默跳过（SPEC F-004）。"""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root, chmod 000 不生效")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("# config")
    (repo / ".install_method").write_text("git")

    # 创建一个权限为 000 的普通文件（不在 ZIP_EXCLUDE_PATTERNS 中）
    bad = repo / "unreadable.txt"
    bad.write_text("data")
    os.chmod(bad, 0o000)
    try:
        zpath = tmp_path / "backup.zip"
        manifest = {"commands": []}
        with pytest.raises(ua.UpgradeError) as exc_info:
            ua.create_zip_backup(repo, zpath, manifest, verbose=False)
        assert exc_info.value.stage == "backup"
        # manifest 必须记录 backup 错误
        assert any(e.get("stage") == "backup" for e in manifest.get("errors", []))
    finally:
        # restore permission so tmp_path cleanup 能成功
        os.chmod(bad, 0o644)


# ---------------------------------------------------------------------------
# Regression: T5 Review Finding 3 — restart helper must not be shell-injectable
# ---------------------------------------------------------------------------


def test_schedule_detached_restart_uses_argv(ua, tmp_path, monkeypatch):
    """Finding 3 regression: detached restart 必须用 argv 启动 helper，且 helper
    脚本不能把 hermes_bin/rlog 拼接进 shell 字符串里。
    """
    # 配置：backup_dir 含空格 + 元字符，hermes_bin 含 `$()` 注入
    backup_dir = tmp_path / "backup with space;rm -rf"
    backup_dir.mkdir()
    hermes_bin = tmp_path / "fake hermes$(echo INJECTED).sh"
    hermes_bin.write_text("#!/bin/sh\necho fake\n")
    hermes_bin.chmod(0o755)

    cfg = ua.UpgradeConfig(
        repo=tmp_path, version_ref="upstream/main",
        backup_dir=backup_dir, dry_run=False, restart=True,
        push=False, rollback_manifest=None, yes=True, verbose=False,
        hermes_bin=hermes_bin,
    )
    manifest = {"commands": []}

    # 拦截 subprocess.Popen，验证 argv 形式调用 helper
    captured = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    import subprocess as _sp
    monkeypatch.setattr(_sp, "Popen", _FakePopen)

    # 拦截 sleep 让 health poll 立刻退出
    monkeypatch.setattr(ua.time, "sleep", lambda _s: None)
    # 拦截 health check 让它报告 healthy，避开 90s 超时
    monkeypatch.setattr(ua, "verify_gateway_post",
                        lambda *a, **kw: "healthy")

    ua.schedule_detached_restart(cfg, manifest)

    argv = captured["args"]
    # 不再使用 `bash -lc <拼字符串>`
    assert "bash" not in argv
    assert "-lc" not in argv
    # argv 形式必须包含 helper、hermes_bin、rlog
    assert len(argv) >= 3
    helper_path = Path(argv[2])
    assert helper_path.exists()
    # helper 内容中不能有 hermes_bin / rlog 的字面量（防注入）
    helper_body = helper_path.read_text(encoding="utf-8")
    assert "INJECTED" not in helper_body
    assert str(hermes_bin) not in helper_body
    # argv 中 hermes_bin 必须以原值（含元字符）传入，而不是 quoted 后的安全串
    assert str(hermes_bin) in argv
    assert str(manifest["restart_log"]) in argv
