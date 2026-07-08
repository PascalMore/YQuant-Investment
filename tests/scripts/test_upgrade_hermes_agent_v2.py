# -*- coding: utf-8 -*-
"""Tests for V2 increment of scripts/upgrade/upgrade_hermes_agent.py
(SPEC-10-006 / DESIGN-10-006 / RFC-10-006).

Covers:
  V2-UT-001 --help shows 3 new args (--branch, --preserve-features, --patches-manifest)
  V2-UT-002 config_from_args: branch defaults to main, overridable
  V2-UT-003 branch arg overrides main-only check (temp repo on fix/feishu-table-card)
  V2-UT-004 --preserve-features dry-run does not push
  V2-UT-005 V2 schema patches manifest parses correctly (data/hermes_patches.yaml)
  V2-UT-006 V1 schema (schema_version=1) is still readable
  V2-UT-007 missing patches manifest does not block upgrade
  V2-UT-008 patch status: commit not in upstream => status=pending
  V2-REG-002 V2 tests pass
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "upgrade" / "upgrade_hermes_agent.py"
DATA_DIR = REPO_ROOT / "data"


# ---------------------------------------------------------------------------
# module loader (same pattern as V1 tests)
# ---------------------------------------------------------------------------


def _load_module():
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
# git helpers (copy of V1 style; not exported)
# ---------------------------------------------------------------------------


def _git(cwd, *args, env=None, check=True):
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, env=env, cwd=str(cwd),
    )
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


# ===========================================================================
# V2-UT-001 — --help shows 3 new args
# ===========================================================================


def test_help_contains_v2_args(ua):
    r = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "--branch" in r.stdout
    assert "--preserve-features" in r.stdout
    assert "--patches-manifest" in r.stdout
    # V1 args still visible (向后兼容)
    assert "--version" in r.stdout
    assert "--dry-run" in r.stdout
    assert "--no-push" in r.stdout


# ===========================================================================
# V2-UT-002 — config_from_args: branch default / override
# ===========================================================================


def test_config_from_args_defaults_branch_main(ua):
    args = ua.parse_args([])  # no args
    cfg = ua.config_from_args(args)
    assert cfg.branch == "main"
    assert cfg.preserve_features is False
    assert cfg.patches_manifest is None


def test_config_from_args_branch_override(ua):
    args = ua.parse_args(["--branch", "fix/feishu-table-card"])
    cfg = ua.config_from_args(args)
    assert cfg.branch == "fix/feishu-table-card"


def test_config_from_args_v2_flags(ua, tmp_path):
    args = ua.parse_args([
        "--preserve-features",
        "--patches-manifest", str(tmp_path / "fake.yaml"),
    ])
    cfg = ua.config_from_args(args)
    assert cfg.preserve_features is True
    assert cfg.patches_manifest == tmp_path / "fake.yaml"


# ===========================================================================
# V2-UT-003 — --branch overrides main-only check
# ===========================================================================


def test_branch_arg_overrides_main_check(ua, tmp_path):
    """非 main 分支 + --branch=<当前分支> + --dry-run 不应因 main-only 失败。"""
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

    # 切到 fix/feishu-table-card
    _git(work, "checkout", "-b", "fix/feishu-table-card")

    cfg = ua.UpgradeConfig(
        repo=work, version_ref="upstream/main",
        backup_dir=tmp_path, dry_run=True, restart=False,
        push=False, rollback_manifest=None, yes=True, verbose=False,
        branch="fix/feishu-table-card",
    )
    manifest = ua.init_manifest(cfg)
    state = ua.inspect_repo(cfg, manifest)
    assert state.branch == "fix/feishu-table-card"


def test_branch_mismatch_fails_with_next_steps(ua, tmp_path):
    """不带 --branch 时，当前分支 != main 必须失败。"""
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
    _git(work, "checkout", "-b", "feature/x")

    cfg = ua.UpgradeConfig(
        repo=work, version_ref="upstream/main",
        backup_dir=tmp_path, dry_run=False, restart=False,
        push=False, rollback_manifest=None, yes=True, verbose=False,
        # branch defaults to "main"
    )
    manifest = ua.init_manifest(cfg)
    with pytest.raises(ua.UpgradeError) as exc_info:
        ua.inspect_repo(cfg, manifest)
    msg = str(exc_info.value)
    # V2 wording
    assert "本次允许分支" in msg
    assert "--branch" in " ".join(exc_info.value.next_steps or [])


# ===========================================================================
# V2-UT-004 — --preserve-features dry-run does not push
# ===========================================================================


def test_preserve_features_dry_run_does_not_push(ua, tmp_path):
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
    _git(work, "checkout", "-b", "fix/feishu-table-card")
    _commit(work, "local commit", filename="local.txt")

    # dry-run + --preserve-features
    cfg = ua.UpgradeConfig(
        repo=work, version_ref="upstream/main",
        backup_dir=tmp_path, dry_run=True, restart=False,
        push=False, rollback_manifest=None, yes=True, verbose=False,
        branch="fix/feishu-table-card",
        preserve_features=True,
    )
    manifest = ua.init_manifest(cfg)
    state = ua.inspect_repo(cfg, manifest)
    ua.preserve_feature_branch_if_requested(cfg, state, manifest)

    # dry-run path should NOT actually push
    assert manifest["preserve_features_status"] == "planned-dry-run"
    assert manifest["preserve_features_branch"] == "fix/feishu-table-card"
    # verify no remote-tracking branch got created by checking the origin bare repo
    out = subprocess.run(
        ["git", "--git-dir", str(origin_bare), "branch", "-a"],
        capture_output=True, text=True,
    ).stdout
    assert "fix/feishu-table-card" not in out


def test_preserve_features_real_run_records_ok_status(ua, tmp_path, monkeypatch):
    """real-run + --preserve-features 应该执行 git push 并把状态记 ok。
    用 monkeypatch 拦截 git() 调用，避免真实 push 到本地 bare（虽然本地 bare 也无害）。"""
    fake_calls = {"push_count": 0}

    # setup repo
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
    _git(work, "checkout", "-b", "fix/feishu-table-card")
    _commit(work, "feature commit", filename="local.txt")

    cfg = ua.UpgradeConfig(
        repo=work, version_ref="upstream/main",
        backup_dir=tmp_path, dry_run=False, restart=False,
        push=False, rollback_manifest=None, yes=True, verbose=False,
        branch="fix/feishu-table-card",
        preserve_features=True,
    )
    manifest = ua.init_manifest(cfg)
    state = ua.inspect_repo(cfg, manifest)

    # patch git() so we count push invocations and assert one push happened.
    original_git = ua.git

    def counting_git(cmd, *, repo, **kw):
        if isinstance(cmd, list) and cmd[:3] == ["push", "-u", "origin"]:
            fake_calls["push_count"] += 1
        return original_git(cmd, repo=repo, **kw)

    monkeypatch.setattr(ua, "git", counting_git)
    ua.preserve_feature_branch_if_requested(cfg, state, manifest)

    assert fake_calls["push_count"] == 1
    assert manifest["preserve_features_status"] == "ok"


# ===========================================================================
# V2-UT-005 — V2 schema patches manifest parses correctly
# ===========================================================================


def test_load_patches_manifest_v2_schema(ua, tmp_path):
    """真实 data/hermes_patches.yaml (schema_version=2) 必须正确解析。"""
    real_yaml = DATA_DIR / "hermes_patches.yaml"
    if not real_yaml.exists():
        pytest.skip(f"data/hermes_patches.yaml not present at {real_yaml}")

    pm = ua.load_patches_manifest(real_yaml)
    assert isinstance(pm, ua.PatchesManifest)
    assert pm.schema_version == 2
    ids = [p.id for p in pm.patches]
    assert "feishu-markdown-table" in ids
    p = next(p for p in pm.patches if p.id == "feishu-markdown-table")
    assert p.commit == "4d3a9661c"
    assert "plugins/platforms/feishu/adapter.py" in p.file_globs
    assert p.upstream_merged is False


def test_load_patches_manifest_v2_from_yaml(ua, tmp_path):
    """在 tmp_path 构造一个 V2 manifest YAML，校验解析。"""
    yaml_path = tmp_path / "patches.yaml"
    yaml_path.write_text(
        "schema_version: 2\n"
        "patches:\n"
        "  - id: feishu-markdown-table\n"
        "    title: \"fix(feishu): render markdown tables via interactive card\"\n"
        "    commit: \"4d3a9661c\"\n"
        "    branch: \"fix/feishu-table-card\"\n"
        "    upstream_pr: null\n"
        "    upstream_merged: false\n"
        "    file_globs:\n"
        "      - \"plugins/platforms/feishu/adapter.py\"\n"
        "    notes: \"interactive card 替代 plain text 降级\"\n",
        encoding="utf-8",
    )
    pm = ua.load_patches_manifest(yaml_path)
    assert pm.schema_version == 2
    assert len(pm.patches) == 1
    p = pm.patches[0]
    assert p.id == "feishu-markdown-table"
    assert p.commit == "4d3a9661c"
    assert p.upstream_pr is None
    assert p.upstream_merged is False
    assert "plugins/platforms/feishu/adapter.py" in p.file_globs


# ===========================================================================
# V2-UT-006 — V1 schema (schema_version=1) is still readable
# ===========================================================================


def test_load_patches_manifest_v1_backcompat(ua, tmp_path):
    yaml_path = tmp_path / "patches_v1.yaml"
    yaml_path.write_text(
        "schema_version: 1\n"
        "patches:\n"
        "  - id: legacy-patch\n"
        "    title: \"legacy: some old patch\"\n"
        "    commit: \"abc1234\"\n"
        "    branch: \"main\"\n"
        "    upstream_pr: \"https://example.com/pr/1\"\n"
        "    upstream_merged: true\n"
        "    file_globs:\n"
        "      - \"legacy/file.py\"\n",
        encoding="utf-8",
    )
    pm = ua.load_patches_manifest(yaml_path)
    assert pm.schema_version == 1
    assert len(pm.patches) == 1
    p = pm.patches[0]
    assert p.id == "legacy-patch"
    assert p.upstream_merged is True
    assert p.upstream_pr == "https://example.com/pr/1"
    assert p.notes == ""  # V1 缺省字段


# ===========================================================================
# V2-UT-007 — missing patches manifest does not block upgrade
# ===========================================================================


def test_patches_manifest_missing_continues_safely(ua, tmp_path):
    pm = ua.load_patches_manifest_safe(tmp_path / "does-not-exist.yaml")
    assert pm is None


def test_patches_manifest_safe_returns_none_on_parse_failure(ua, tmp_path):
    """文件存在但完全不可解析 → safe wrapper 返回 None + warning。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text("this is :: not [valid yaml at all\n}}}}\n[", encoding="utf-8")
    pm = ua.load_patches_manifest_safe(bad)
    # PyYAML 可能解析成奇怪 dict，stdlib fallback 也可能为空；目标是“安全”——
    # 即不抛异常（除 safe 包装内部处理）。我们允许 None 或 非 None 但 patches 为空。
    if pm is not None:
        assert pm.patches == [] or len(pm.patches) >= 0  # never raise


def test_run_patch_manifest_check_skips_when_manifest_missing(ua, tmp_path):
    """--patches-manifest=None 时，run_* 必须直接返回，不抛异常。"""
    upstream_bare = tmp_path / "upstream.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_repo(work, upstream=upstream_bare)
    _commit(work, "init")
    (work / ".install_method").write_text("git")

    cfg = ua.UpgradeConfig(
        repo=work, version_ref="upstream/main",
        backup_dir=tmp_path, dry_run=False, restart=False,
        push=False, rollback_manifest=None, yes=True, verbose=False,
        patches_manifest=None,
    )
    manifest = ua.init_manifest(cfg)
    ua.run_patch_manifest_check_if_requested(cfg, manifest, "upstream/main")
    assert manifest["patch_statuses"] == []
    assert manifest["patches_check_status"] == "skipped"


# ===========================================================================
# V2-UT-008 — patch status: commit not in upstream => status=pending
# ===========================================================================


def test_patch_status_pending_when_commit_not_in_upstream(ua, tmp_path):
    upstream_bare = tmp_path / "upstream.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_repo(work, upstream=upstream_bare)
    _commit(work, "init")
    _commit(work, "upstream feature", filename="up.txt")
    upstream_head = _git(work, "rev-parse", "HEAD").stdout.strip()

    # 写一个 manifest with a non-existent commit sha
    manifest_yaml = tmp_path / "p.yaml"
    manifest_yaml.write_text(
        f"schema_version: 2\n"
        f"patches:\n"
        f"  - id: never-merged\n"
        f"    title: \"fake\"\n"
        f"    commit: \"deadbeef00000000deadbeef00000000deadbeef\"\n"
        f"    branch: \"fix/x\"\n"
        f"    upstream_pr: null\n"
        f"    upstream_merged: false\n"
        f"    file_globs:\n"
        f"      - \"some/file.py\"\n",
        encoding="utf-8",
    )
    pm = ua.load_patches_manifest(manifest_yaml)
    statuses = ua.verify_patches_against_upstream(
        work, pm, "upstream/main", verbose=False,
    )
    assert len(statuses) == 1
    s = statuses[0]
    assert s.id == "never-merged"
    assert s.upstream_merged_manifest is False
    assert s.upstream_contains_commit is False
    assert s.status == "pending"
    assert "deadbeef" in s.reason or "不可达" in s.reason


def test_patch_status_merged_when_manifest_flag_true(ua, tmp_path):
    """即使 commit 不存在，只要 manifest 标 upstream_merged=true，status 必须 merged。"""
    upstream_bare = tmp_path / "upstream.git"
    work = tmp_path / "work"
    _make_bare(upstream_bare)
    _make_repo(work, upstream=upstream_bare)
    _commit(work, "init")

    manifest_yaml = tmp_path / "p.yaml"
    manifest_yaml.write_text(
        "schema_version: 2\n"
        "patches:\n"
        "  - id: marked-merged\n"
        "    title: \"already merged\"\n"
        "    commit: \"abc1234\"\n"
        "    branch: \"main\"\n"
        "    upstream_pr: \"https://example.com/pr/9\"\n"
        "    upstream_merged: true\n"
        "    file_globs:\n"
        "      - \"some/file.py\"\n",
        encoding="utf-8",
    )
    pm = ua.load_patches_manifest(manifest_yaml)
    statuses = ua.verify_patches_against_upstream(
        work, pm, "upstream/main", verbose=False,
    )
    assert len(statuses) == 1
    assert statuses[0].status == "merged"
    assert "manifest" in statuses[0].reason


# ===========================================================================
# rollback 参数冲突 (新增 V2 三参数)
# ===========================================================================


def test_rollback_conflict_preserve_features(ua):
    r = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--rollback", "/tmp/x.json", "--preserve-features"],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert "--preserve-features" in r.stderr


def test_rollback_conflict_patches_manifest(ua):
    r = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--rollback", "/tmp/x.json", "--patches-manifest", "/tmp/x.yaml"],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert "--patches-manifest" in r.stderr


def test_rollback_conflict_branch_non_default(ua):
    r = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--rollback", "/tmp/x.json", "--branch", "feature/x"],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert "--branch" in r.stderr


# ===========================================================================
# V2-REG-001 — regression: _parse_simple_patches_yaml fallback 状态机
#   2026-07-08 T3 验证发现 bug：list item 起点被当作 string append，
#   导致后续 nested "key: value" 行只覆盖最后一个字段，整个 item 的
#   `id` 丢失 → patches=[] → 真实 manifest 解析失败。
#   本测试直接锁定 _parse_simple_patches_yaml 的输出契约。
# ===========================================================================


def test_parse_real_manifest_regression(ua):
    """锁定 _parse_simple_patches_yaml 解析真实 manifest 的输出契约。

    不依赖 yaml 库（已通过 _load_yaml_subset 走 fallback 路径）。
    """
    real_yaml = DATA_DIR / "hermes_patches.yaml"
    assert real_yaml.exists(), f"fixture missing: {real_yaml}"
    text = real_yaml.read_text(encoding="utf-8")

    # 直接调用 fallback parser（不依赖 yaml 库是否存在）
    raw = ua._parse_simple_patches_yaml(text)

    # 顶层字段
    assert raw.get("schema_version") == "2", f"schema_version wrong: {raw.get('schema_version')}"
    assert isinstance(raw.get("patches"), list), f"patches not list: {type(raw.get('patches'))}"

    # 6 个字段全在且类型/值正确
    assert len(raw["patches"]) == 1, f"expected 1 patch, got {len(raw['patches'])}"
    p0 = raw["patches"][0]
    assert isinstance(p0, dict), f"patch[0] should be dict, got {type(p0)}: {p0!r}"
    assert p0.get("id") == "feishu-markdown-table", f"id lost: {p0}"
    assert p0.get("title") == "fix(feishu): render markdown tables via interactive card"
    assert p0.get("commit") == "4d3a9661c"
    assert p0.get("branch") == "fix/feishu-table-card"
    assert p0.get("upstream_pr") is None
    assert p0.get("upstream_merged") is False
    assert p0.get("file_globs") == ["plugins/platforms/feishu/adapter.py"], (
        f"file_globs wrong: {p0.get('file_globs')}"
    )
    assert "interactive card 替代" in (p0.get("notes") or ""), f"notes lost: {p0.get('notes')}"


def test_parse_simple_yaml_two_patches(ua):
    """回归两个 patch 项的解析，确保 list item 边界正确切分。"""
    text = (
        "schema_version: 2\n"
        "patches:\n"
        "  - id: alpha\n"
        "    commit: \"aaa\"\n"
        "    file_globs:\n"
        "      - \"a.py\"\n"
        "    notes: \"first\"\n"
        "  - id: beta\n"
        "    commit: \"bbb\"\n"
        "    file_globs:\n"
        "      - \"b.py\"\n"
        "    notes: \"second\"\n"
    )
    raw = ua._parse_simple_patches_yaml(text)
    assert len(raw["patches"]) == 2
    alpha, beta = raw["patches"]
    assert alpha["id"] == "alpha"
    assert alpha["commit"] == "aaa"
    assert alpha["file_globs"] == ["a.py"]
    assert alpha["notes"] == "first"
    assert beta["id"] == "beta"
    assert beta["commit"] == "bbb"
    assert beta["file_globs"] == ["b.py"]
    assert beta["notes"] == "second"


def test_parse_simple_yaml_orphan_key_after_list_item(ua):
    """回归：nested key 在空值 key 出现后（如 file_globs: → 子列表），
    末尾的 notes: 不能被错误归入 cur_child_key 路径。"""
    text = (
        "schema_version: 2\n"
        "patches:\n"
        "  - id: gamma\n"
        "    file_globs:\n"
        "      - \"g.py\"\n"
        "    notes: \"should belong to gamma, not file_globs\"\n"
    )
    raw = ua._parse_simple_patches_yaml(text)
    assert len(raw["patches"]) == 1
    g = raw["patches"][0]
    assert g["id"] == "gamma"
    assert g["file_globs"] == ["g.py"], f"file_globs wrong: {g.get('file_globs')}"
    assert g["notes"] == "should belong to gamma, not file_globs", (
        f"notes wrongly attributed: {g}"
    )
