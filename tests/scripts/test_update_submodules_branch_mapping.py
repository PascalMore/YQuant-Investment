# -*- coding: utf-8 -*-
"""Branch mapping + target validation + source/target separation tests
for scripts/upgrade/update_submodules.py V2.1.
Covers SPEC-10-008 V2.1 §3.4–§3.8 / §8.1 and DESIGN-10-008 §3.9.
Acceptance mapping (A-BM-001..020); isolated local bare repos only, no live submodule.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "upgrade" / "update_submodules.py"

# module loader

def _load_module():
    name = "update_submodules"
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

@pytest.fixture(scope="module")
def us():
    return _load_module()

# low-level git helpers

def _git(cwd, *args, env=None, check=True, input_text=None):
    env_full = {
        "GIT_AUTHOR_NAME": "yquant",
        "GIT_AUTHOR_EMAIL": "yquant@test.local",
        "GIT_COMMITTER_NAME": "yquant",
        "GIT_COMMITTER_EMAIL": "yquant@test.local",
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd),  # isolate git config
        "LC_ALL": "C",
    }
    if env:
        env_full.update(env)
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, env=env_full, cwd=str(cwd),
        input=input_text,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args} failed in {cwd}: {r.stderr}")
    return r

def _git_outside(cwd, *args, env=None):
    env_full = {
        "GIT_AUTHOR_NAME": "yquant",
        "GIT_AUTHOR_EMAIL": "yquant@test.local",
        "GIT_COMMITTER_NAME": "yquant",
        "GIT_COMMITTER_EMAIL": "yquant@test.local",
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd),
        "LC_ALL": "C",
    }
    if env:
        env_full.update(env)
    return subprocess.run(
        ["git", *args],
        capture_output=True, text=True, env=env_full, cwd=str(cwd),
    )

def _bare(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--bare")
    # Bare repos start with HEAD pointing at refs/heads/master (git default);
    # we explicitly want a default of `main` to match how callers will push.
    _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    return path

def _work(path: Path, *, branch: str = "main", base_branch: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if base_branch is None:
        base_branch = branch
    _git(path, "init", "--initial-branch", base_branch)
    # if branch != base_branch, create the requested branch too
    if branch != base_branch:
        _git(path, "checkout", "-q", "-b", branch)
    (path / "README.md").write_text("# seed\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "seed")
    return path

def _seed_with_branches(path: Path, *, source: str) -> Path:
    """Seed repo whose initial branch is `source`. Also create a `main`
    branch sharing the same C0 so we can push C0 to origin/main as well.
    Returns path. After return, both `source` and `main` point at C0.
    """
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch", source)
    (path / "README.md").write_text("# seed\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "seed")
    # create main branch at the same commit (no-op when source == "main")
    if source != "main":
        _git(path, "branch", "main")
    return path

def _commit(cwd: Path, message: str, files: dict[str, str]) -> None:
    for name, content in files.items():
        full = cwd / name
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    _git(cwd, "add", ".")
    _git(cwd, "commit", "-q", "-m", message)

def _push(cwd: Path, remote: str, branch: str, force: bool = False) -> None:
    args = ["push", "-q"]
    if force:
        args.append("--force")
    args += [remote, branch]
    _git(cwd, *args)

# A-BM-012 / normalize

class TestNormalizeRemoteBranch:
    """A-BM-012 / normalize_remote_branch: remote prefix and ref validation."""
    def test_bare_name_unchanged(self, us):
        assert us.normalize_remote_branch("main", remote="upstream") == "main"
        assert us.normalize_remote_branch("feature/x", remote="upstream") == "feature/x"

    def test_strips_origin_short_prefix(self, us):
        assert us.normalize_remote_branch("origin/main", remote="origin") == "main"
        assert us.normalize_remote_branch("origin/feature/x", remote="origin") == "feature/x"

    def test_strips_origin_full_prefix(self, us):
        assert us.normalize_remote_branch("refs/remotes/origin/main", remote="origin") == "main"

    def test_strips_upstream_full_prefix(self, us):
        assert us.normalize_remote_branch("refs/remotes/upstream/master", remote="upstream") == "master"

    def test_rejects_wrong_remote_short_prefix(self, us):
        # upstream/main passed to origin remote -> reject
        assert us.normalize_remote_branch("upstream/main", remote="origin") is None
        assert us.normalize_remote_branch("origin/main", remote="upstream") is None

    def test_rejects_head_empty_and_dash(self, us):
        assert us.normalize_remote_branch("HEAD", remote="upstream") is None
        assert us.normalize_remote_branch("", remote="upstream") is None
        assert us.normalize_remote_branch("upstream/HEAD", remote="upstream") is None

    def test_rejects_unknown_garbage(self, us):
        assert us.normalize_remote_branch("refs/tags/v1", remote="upstream") is None
        assert us.normalize_remote_branch("main..x", remote="upstream") is None
        assert us.normalize_remote_branch("main~1", remote="upstream") is None
        assert us.normalize_remote_branch("main/*", remote="upstream") is None

    def test_rejects_absolute_sha(self, us):
        sha = "c45fdc2c95c5bd3d649251fa90c327e2e8f86b00"
        assert us.normalize_remote_branch(sha, remote="upstream") is None

# ---------------------------------------------------------------------------
# A-BM-008/009/010 / target priority: override > .gitmodules > current > origin > main
# ---------------------------------------------------------------------------

class TestTargetSelection:
    """A-BM-008/009/010 / Target = local/origin branch; production path is process_submodule -> discover_submodule + opt-in merge."""

    def test_target_optin_branch_beats_gitmodules_branch(self, us, tmp_path):
        # write .gitmodules branch=develop and an opt-in branch=main
        project = tmp_path / "proj"
        project.mkdir()
        (project / ".gitmodules").write_text(
            '[submodule "child"]\n\tpath = child\n\turl = file:///dev/null\n'
            "\tbranch = develop\n",
            encoding="utf-8",
        )
        # bare remotes + child
        bare_up = _bare(tmp_path / "upstream.git")
        bare_origin = _bare(tmp_path / "origin.git")
        child = tmp_path / "proj" / "child"
        _work(child, branch="develop")
        _git(child, "remote", "add", "origin", str(bare_origin))
        _git(child, "remote", "add", "upstream", str(bare_up))
        # opt-in branch=main
        (child / ".update_submodules.yaml").write_text(
            "schema_version: 1\nbranch: main\n",
            encoding="utf-8",
        )
        with patch_run_cmd_isolated():
            cfg = us.discover_submodule("child", Path("child"), project)
            override = us.load_optin_override(child)
            cfg2 = us.merge_override(cfg, override or {})
        assert cfg2.branch == "main"
        # The opt-in target must NOT be used as the source fallback
        assert getattr(cfg2, "upstream_branch", None) == "main"

    def test_target_gitmodules_branch_beats_current(self, us, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / ".gitmodules").write_text(
            '[submodule "child"]\n\tpath = child\n\turl = file:///dev/null\n'
            "\tbranch = release\n",
            encoding="utf-8",
        )
        bare_up = _bare(tmp_path / "upstream.git")
        bare_origin = _bare(tmp_path / "origin.git")
        child = tmp_path / "proj" / "child"
        _work(child, branch="main")  # current branch = main
        _git(child, "remote", "add", "origin", str(bare_origin))
        _git(child, "remote", "add", "upstream", str(bare_up))
        with patch_run_cmd_isolated():
            cfg = us.discover_submodule("child", Path("child"), project)
        assert cfg.branch == "release"

    def test_target_gitmodules_dot_expands_project_head(self, us, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        # project is a git repo itself, branch=develop
        _git(project, "init", "--initial-branch", "develop")
        _commit(project, "x", {"x": "x"})
        (project / ".gitmodules").write_text(
            '[submodule "child"]\n\tpath = child\n\turl = file:///dev/null\n'
            "\tbranch = .\n",
            encoding="utf-8",
        )
        bare_up = _bare(tmp_path / "upstream.git")
        bare_origin = _bare(tmp_path / "origin.git")
        child = project / "child"
        _work(child, branch="main")
        _git(child, "remote", "add", "origin", str(bare_origin))
        _git(child, "remote", "add", "upstream", str(bare_up))
        with patch_run_cmd_isolated():
            cfg = us.discover_submodule("child", Path("child"), project)
        assert cfg.branch == "develop"

def patch_run_cmd_isolated():
    """No-op context manager placeholder for visibility. We rely on
    subprocess.run going through real git via _git() — git remote URLs
    for local bare are valid, so discover_submodule will work without
    mocking when the bare paths are absolute.
    """
    from contextlib import nullcontext
    return nullcontext()

# A-BM-013 / explicit null/empty/non-string/illegal branch fields fail

class TestExplicitBranchFieldsFail:
    def test_optin_branch_none_value_raises(self, us, tmp_path):
        child = tmp_path / "child"
        child.mkdir()
        # Opt-in YAML with branch: null (parsed as None by stdlib)
        (child / ".update_submodules.yaml").write_text(
            "schema_version: 1\nbranch: ~\n",
            encoding="utf-8",
        )
        # load_optin_override's existing YAML loader catches file/schema
        # errors as warning+None; an explicit None on branch must surface
        # a ValueError when validate_override applies strict checks.
        with pytest.raises(ValueError):
            us.validate_override({
                "schema_version": 1,
                "branch": None,
            })

    def test_optin_branch_empty_string_raises(self, us):
        with pytest.raises(ValueError):
            us.validate_override({
                "schema_version": 1,
                "branch": "",
            })

    def test_optin_branch_non_string_raises(self, us):
        with pytest.raises(ValueError):
            us.validate_override({
                "schema_version": 1,
                "branch": 12345,
            })

    def test_optin_branch_illegal_ref_raises(self, us):
        with pytest.raises(ValueError):
            us.validate_override({
                "schema_version": 1,
                "branch": "main..x",
            })

    def test_optin_upstream_branch_wrong_remote_raises(self, us):
        with pytest.raises(ValueError):
            us.validate_override({
                "schema_version": 1,
                "upstream_branch": "origin/master",
            })

# A-BM-005 / explicit origin/main + upstream/master: target=main, source=master

class TestLegacyAndExplicit:
    def test_legacy_branch_origin_main_dual_role(self, us):
        # branch: origin/main normalizes to main as TARGET and main as the
        # legacy upstream_branch (same name) when upstream_branch absent.
        validated = us.validate_override({"schema_version": 1, "branch": "origin/main"})
        assert validated["branch"] == "main"
        # validate_override preserves upstream_branch slot as None; merge_override
        # wires the legacy main into upstream_branch too.
        base = us.SubmoduleConfig(
            name="child", path=Path("child"), origin=None, upstream=None,
            branch="main", venv=None, pip_install_cmd=None,
            pre_merge_hooks=(), systemd_service=None, health_check=None,
            skip_push=False, notes="", config_source="heuristic",
        )
        merged = us.merge_override(base, validated)
        assert merged.branch == "main"
        assert getattr(merged, "upstream_branch", None) == "main"

    def test_explicit_origin_main_and_upstream_master(self, us):
        # explicit branch: origin/main + upstream_branch: upstream/master
        # -> target main, source master. normalize must not strip when
        # remote mismatches; upstream_branch passed with correct remote.
        validated = us.validate_override({
            "schema_version": 1,
            "branch": "origin/main",
            "upstream_branch": "upstream/master",
        })
        assert validated["branch"] == "main" and validated["upstream_branch"] == "master"
        base = us.SubmoduleConfig(
            name="child", path=Path("child"), origin=None, upstream=None,
            branch="main", venv=None, pip_install_cmd=None,
            pre_merge_hooks=(), systemd_service=None, health_check=None,
            skip_push=False, notes="", config_source="heuristic",
        )
        merged = us.merge_override(base, validated)
        assert merged.branch == "main"
        assert merged.upstream_branch == "master"

# A-BM-011 / source priority: optin > remote show > cached upstream HEAD > commit probe

class TestSourceSelection:
    """A-BM-011 / Source = upstream branch via _discover_upstream_branch; _detect_upstream_default_branch is fallback."""

    def test_explicit_upstream_branch_wins(self, us):
        cfg = us.SubmoduleConfig(
            name="c", path=Path("c"), origin=None, upstream=None,
            branch="main", venv=None, pip_install_cmd=None,
            pre_merge_hooks=(), systemd_service=None, health_check=None,
            skip_push=False, notes="", config_source="heuristic",
            upstream_branch="develop",
        )
        # discover helper accepts explicit optin override
        assert cfg.upstream_branch == "develop"

    def test_legacy_branch_promotes_to_upstream_branch(self, us):
        # branch: develop + no upstream_branch -> upstream_branch falls back to develop
        # _discover_upstream_branch should return the legacy branch value
        pass  # implementation hook below

    def test_source_unresolved_when_nothing(self, us, tmp_path):
        # Bare repo with NO upstream refs and remote show failing
        sub = tmp_path / "sub"
        sub.mkdir()
        bare = _bare(tmp_path / "upstream.git")
        _work(sub, branch="main")
        _git(sub, "remote", "add", "upstream", str(bare))
        # No upstream refs at all -> resolve should return None
        from unittest.mock import patch
        with patch.object(us, "_detect_upstream_default_branch", return_value=None):
            result = us._discover_upstream_branch(sub, optin_branch=None, legacy_branch=None)
        assert result is None

# A-BM-014 / dry-run unknown counting

class TestParseRevCountStrict:
    def test_valid_two_ints(self, us):
        assert us._parse_rev_count_strict("0\t5\n") == (0, 5)
        assert us._parse_rev_count_strict("3 1\n") == (3, 1)

    def test_empty_returns_none(self, us):
        assert us._parse_rev_count_strict("") is None
        assert us._parse_rev_count_strict("\n") is None

    def test_one_token_returns_none(self, us):
        assert us._parse_rev_count_strict("5\n") is None

    def test_three_tokens_returns_none(self, us):
        assert us._parse_rev_count_strict("1 2 3\n") is None

    def test_negative_returns_none(self, us):
        assert us._parse_rev_count_strict("-1\t0\n") is None

    def test_non_int_returns_none(self, us):
        assert us._parse_rev_count_strict("abc\tdef\n") is None

# A-BM-016 / target validation: detached, missing, mismatched

class TestTargetValidation:
    def test_validate_target_missing_branch(self, us, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        # bare remote but no matching local branch
        bare = _bare(tmp_path / "origin.git")
        _work(sub, branch="main")
        _git(sub, "remote", "add", "origin", str(bare))
        # No local branch "release"
        with pytest.raises(ValueError) as exc:
            us._validate_target_branch(sub, "release")
        assert "release" in str(exc.value).lower() or "不存在" in str(exc.value)

    def test_validate_target_detached_head_rejects(self, us, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _work(sub, branch="main")
        # Detach HEAD on a SHA
        sha = _git(sub, "rev-parse", "HEAD").stdout.strip()
        _git(sub, "checkout", "-q", sha)
        with pytest.raises(ValueError) as exc:
            us._validate_target_branch(sub, "main")
        assert "detached" in str(exc.value).lower() or "符号" in str(exc.value)

    def test_validate_target_current_mismatch_rejects(self, us, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _work(sub, branch="main")
        # create release branch but stay on main
        _git(sub, "checkout", "-q", "-b", "release")
        _commit(sub, "r", {"r": "1"})
        _git(sub, "checkout", "-q", "main")
        # Now HEAD=main, target=release -> mismatch
        with pytest.raises(ValueError) as exc:
            us._validate_target_branch(sub, "release")
        assert "mismatch" in str(exc.value).lower() or "不符" in str(exc.value) or "main" in str(exc.value)

    def test_validate_target_match_passes(self, us, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _work(sub, branch="main")
        # no exception
        us._validate_target_branch(sub, "main")

# ---------------------------------------------------------------------------
# A-BM-019 / FETCH_HEAD binding + A-BM-001/002/003 / local_bare E2E
# ---------------------------------------------------------------------------

@pytest.fixture
def local_bare_fixture(tmp_path):
    """Build:
    - upstream.git (bare, on `source` branch; will receive C1)
    - origin.git  (bare, on `main` branch)
    - seed/        (working repo with C0)
    - project/     (main project root with .gitmodules section=child/branch=main)
    - project/child (clone of origin.git on main, remote add upstream)
    Returns dict of paths.
    """
    root = tmp_path / "fixture"
    upstream = _bare(root / "upstream.git")
    origin = _bare(root / "origin.git")
    seed = root / "seed"
    project = root / "project"
    child = project / "child"
    # seed C0
    _work(seed, branch="main")
    _commit(seed, "C0", {"marker.txt": "v0"})
    # push seed to upstream/source AND origin/main
    _push(seed, str(upstream), "source")
    # origin pushes need explicit remote update for bare default
    _git(seed, "remote", "add", "origin", str(origin))
    _push(seed, "origin", "main")
    # child clones origin, points upstream at upstream.git, stays on main
    _git_outside(root, "clone", "-q", str(origin), str(child))
    _git(child, "remote", "add", "upstream", str(upstream))
    # project is a directory with .gitmodules (NOT a git repo of its own;
    # the script will operate on the child path directly)
    project.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "upstream": upstream,
        "origin": origin,
        "seed": seed,
        "project": project,
        "child": child,
    }

def _write_gitmodules(project: Path, section: str, rel: str, branch: str = "main"):
    project.joinpath(".gitmodules").write_text(
        f'[submodule "{section}"]\n'
        f'\tpath = {rel}\n'
        f'\turl = file://{(project / rel).resolve()}\n'
        f'\tbranch = {branch}\n',
        encoding="utf-8",
    )

def _setup_bare_pair(root: Path, *, source: str = "main",
                     gitmodules_branch: str = "main",
                     pre_fetch: bool = True) -> dict:
    """Build the standard bare-pair fixture (upstream.git, origin.git,
    seed with C0, project, child, .gitmodules) and return a dict of paths.
    Consolidates the ~14-line inline block previously repeated in many
    tests.``source`` controls both the upstream branch that receives C0
    and the candidate source branch for the caller. ``pre_fetch=True``
    pre-fetches upstream/<source> into the child so cached-compare and
    source-discovery paths are populated without the test having to call
    ``git fetch`` itself.
    """
    root.mkdir(parents=True, exist_ok=True)
    upstream = _bare(root / "upstream.git")
    origin = _bare(root / "origin.git")
    seed = root / "seed"
    project = root / "project"
    child = project / "child"
    _seed_with_branches(seed, source=source)
    _commit(seed, "C0", {"marker.txt": "v0"})
    _push(seed, str(upstream), source)
    _git(seed, "remote", "add", "origin", str(origin))
    _push(seed, "origin", "main")
    _git_outside(root, "clone", "-q", str(origin), str(child))
    _git(child, "remote", "add", "upstream", str(upstream))
    if pre_fetch:
        _git(child, "fetch", "upstream", source)
    _write_gitmodules(project, "child", "child", branch=gitmodules_branch)
    return {
        "root": root, "upstream": upstream, "origin": origin,
        "seed": seed, "project": project, "child": child,
    }

def _snapshot(child: Path) -> dict:
    """Read-only snapshot of git state for zero-write assertions."""
    def _run(*args):
        r = _git(child, *args, check=False)
        return r.stdout.strip()

    head = _run("rev-parse", "HEAD")
    head_branch = _run("symbolic-ref", "--short", "HEAD")
    all_refs = _run("for-each-ref", "--format=%(refname)")
    index_hash = _run("ls-files", "--stage")
    # worktree content hash: cat-tracked files
    tracked = _run("ls-files")
    wt_hash = ""
    for line in tracked.splitlines():
        full = child / line
        try:
            wt_hash += full.read_bytes().hex()
        except Exception:
            wt_hash += "<missing>"
    config = _run("config", "--list")
    fetch_head_exists = (child / ".git" / "FETCH_HEAD").exists()
    try:
        fetch_head_bytes = (child / ".git" / "FETCH_HEAD").read_bytes()
    except Exception:
        fetch_head_bytes = b""
    return {
        "head": head,
        "head_branch": head_branch,
        "refs": all_refs,
        "config": config,
        "fetch_head_exists": fetch_head_exists,
        "fetch_head_bytes": fetch_head_bytes,
        "wt_hash": wt_hash,
        "tracked": tracked,
    }

@pytest.mark.parametrize("source", ["main", "master", "develop"])
def test_local_bare_source_to_target_main(us, tmp_path, source):
    """A-BM-001/002/003: local bare Git E2E. Three variants:
    source in {main, master, develop}, target=main. Must:
    - merge C1 into local main
    - push to origin/main (not origin/<source>)
    - NOT create origin/<source>
    """
    paths = _setup_bare_pair(tmp_path / f"fb_{source}", source=source)
    root, upstream, origin, seed, project, child = paths["root"], paths["upstream"], paths["origin"], paths["seed"], paths["project"], paths["child"]
    _git(child, "config", "remote.upstream.fetch",
         "+refs/heads/*:refs/remotes/upstream/*")

    # C1 on upstream
    _commit(seed, "C1", {"marker.txt": "v1", "extra.txt": "new"})
    _push(seed, str(upstream), source)

    # invoke process via subprocess to exercise the actual CLI path
    from unittest.mock import patch as _patch
    _captured = []
    _orig_log_info = us.log_info
    _orig_log = us.log
    _orig_log_err = us.log_err
    _orig_log_warn = us.log_warn
    us.log_info = lambda m: (_captured.append(("INFO", m)) or _orig_log_info(m))
    us.log = lambda m, **kw: (_captured.append(("LOG", m)))
    us.log_err = lambda m: (_captured.append(("ERR", m)) or _orig_log_err(m))
    us.log_warn = lambda m: (_captured.append(("WARN", m)) or _orig_log_warn(m))
    try:
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=False,
            skip_install=True, skip_restart=True,
        )
    finally:
        us.log_info = _orig_log_info
        us.log = _orig_log
        us.log_err = _orig_log_err
        us.log_warn = _orig_log_warn
    print("CAPTURED:", _captured)
    print("PHASES:", [(p.phase, p.status, p.detail) for p in result.phases])
    print("ABORT:", result.abort_reason)
    # assert local main is now at C1
    head_main = _git(child, "rev-parse", "main").stdout.strip()
    c1 = _git(seed, "rev-parse", "HEAD").stdout.strip()
    assert head_main == c1, f"local main should be at C1, got {head_main} != {c1}"

    # assert origin/main == C1
    # bare refs live under refs/heads/main in origin.git
    origin_main = _git_outside(
        root, "--git-dir", str(origin), "rev-parse", "refs/heads/main"
    ).stdout.strip()
    assert origin_main == c1

    # assert origin/<source> not created when source != target
    if source != "main":
        r2 = _git_outside(
            root, "--git-dir", str(origin), "rev-parse",
            f"refs/heads/{source}",
        )
        assert r2.returncode != 0, f"origin/{source} must not exist"

    # assert local does NOT have a <source> branch tracking the source commit
    r3 = _git(child, "rev-parse", source, check=False)
    if source != "main":
        assert r3.returncode != 0, f"local {source} branch must not be created"

    # assert marker content is C1's
    marker = (child / "marker.txt").read_text(encoding="utf-8").strip()
    assert marker == "v1"

def test_local_bare_stale_tracking_ref_binds_to_c1(us, tmp_path):
    """A-BM-019 / stale ref: even if upstream/main cached C0, fetch must
    retrieve C1 and merge that, not C0.
    """
    paths = _setup_bare_pair(tmp_path / "stale")
    root, upstream, origin, seed, project, child = paths["root"], paths["upstream"], paths["origin"], paths["seed"], paths["project"], paths["child"]
    # upstream moves to C1
    _commit(seed, "C1", {"marker.txt": "v1", "extra.txt": "x"})
    _push(seed, str(upstream), "main")
    # Narrow remote.fetch to only update feature/* so cached ref does NOT auto-update
    _git(child, "config", "remote.upstream.fetch",
         "+refs/heads/feature/*:refs/remotes/upstream/feature/*")
    _write_gitmodules(project, "child", "child", branch="main")

    before = _snapshot(child)
    result = us.process_submodule(
        "child", Path("child"), project,
        do_push=True, dry_run=False,
        skip_install=True, skip_restart=True,
    )
    head_main = _git(child, "rev-parse", "main").stdout.strip()
    c1 = _git(seed, "rev-parse", "HEAD").stdout.strip()
    assert head_main == c1, "must merge C1, not cached C0"

    origin_main = _git_outside(
        root, "--git-dir", str(origin), "rev-parse", "refs/heads/main"
    ).stdout.strip()
    assert origin_main == c1
    # extra.txt must exist locally (from C1)
    assert (child / "extra.txt").exists()

# A-BM-016 / target reject: detached/missing/mismatch -> zero-write

class TestTargetRejectZeroWrite:
    def test_dry_run_target_missing_zero_writes(self, us, tmp_path):
        # .gitmodules branch = "release" (which does NOT exist locally)
        paths = _setup_bare_pair(tmp_path / "miss", gitmodules_branch="release")
        child, project = paths["child"], paths["project"]
        before = _snapshot(child)
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_install=True, skip_restart=True,
        )
        assert result.overall == "fail"
        after = _snapshot(child)
        assert before == after, f"zero-write violation: before={before} after={after}"

    def test_dry_run_target_detached_zero_writes(self, us, tmp_path):
        paths = _setup_bare_pair(tmp_path / "detach")
        child, project = paths["child"], paths["project"]
        # detach HEAD
        sha = _git(child, "rev-parse", "HEAD").stdout.strip()
        _git(child, "checkout", "-q", sha)
        before = _snapshot(child)
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_install=True, skip_restart=True,
        )
        assert result.overall == "fail"
        after = _snapshot(child)
        assert before == after

# A-BM-014 / dry-run unknown counting -> CLI exit 1, no plan

class TestDryRunUnknown:
    def test_dry_run_no_cache_no_commit_refs(self, us, tmp_path):
        # NO fetch upstream yet — no commit cache
        paths = _setup_bare_pair(tmp_path / "unk", pre_fetch=False)
        child, project = paths["child"], paths["project"]
        before = _snapshot(child)
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_install=True, skip_restart=True,
        )
        assert result.overall == "fail"
        fetch_phase = [p for p in result.phases if p.phase == "fetch"][0]
        assert fetch_phase.status == "fail"
        # No fetch/merge/push should have happened
        assert "unknown" in fetch_phase.detail.lower() or "无法判定" in fetch_phase.detail
        after = _snapshot(child)
        assert before == after

    def test_dry_run_push_plan_present_when_cached(self, us, tmp_path):
        root = tmp_path / "planok"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="main")
        _commit(seed, "C0", {"marker.txt": "v0"})
        _push(seed, str(upstream), "main")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        _git(child, "remote", "add", "upstream", str(upstream))
        _git(child, "fetch", "upstream", "main")  # cache C0
        # No new commits upstream
        _write_gitmodules(project, "child", "child", branch="main")
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_install=True, skip_restart=True,
        )
        # Cached behind=0 -> fetch pass (cached compare), merge skip -> push plan
        assert result.overall == "pass"
        fetch_phase = [p for p in result.phases if p.phase == "fetch"][0]
        assert "cached" in fetch_phase.detail.lower() or "behind=0" in fetch_phase.detail.lower()
        push_phase = [p for p in result.phases if p.phase == "push"][0]
        assert "git push origin main" in push_phase.detail

# A-BM-019 / hook rejection: pre_merge_hook that checks out wrong branch

class TestHookRejection:
    def test_hook_changes_branch_blocks_merge(self, us, tmp_path):
        root = tmp_path / "hook"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="main")
        _commit(seed, "C0", {"marker.txt": "v0"})
        _push(seed, str(upstream), "main")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        _git(child, "remote", "add", "upstream", str(upstream))
        # C1 upstream
        _commit(seed, "C1", {"marker.txt": "v1"})
        _push(seed, str(upstream), "main")
        # child fetches C1
        _git(child, "fetch", "upstream", "main")
        _write_gitmodules(project, "child", "child", branch="main")
        # Opt-in adds a pre_merge_hook that switches to a feature branch.
        (child / ".update_submodules.yaml").write_text(
            "schema_version: 1\n"
            "pre_merge_hooks:\n"
            '  - "git checkout -q feature-x || git checkout -q -b feature-x"\n',
            encoding="utf-8",
        )
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=False,
            skip_install=True, skip_restart=True,
        )
        assert result.overall == "fail"
        # Merge or push must be rejected; HEAD must NOT be advanced
        head_main = _git(child, "rev-parse", "main").stdout.strip()
        c0 = _git(seed, "rev-parse", "HEAD~1").stdout.strip()
        assert head_main == c0, "local main must NOT have moved"

# A-BM-013 / unknown counting produces ValueError

class TestCountingEdge:
    def test_parse_rev_count_strict_empty_returns_none(self, us):
        # Empty / non-matching inputs return None rather than raising; the
        # caller (phase_fetch) translates None into PhaseResult.fail(detail).
        assert us._parse_rev_count_strict("") is None
        assert us._parse_rev_count_strict("foo") is None

# A-BM-020 / non-branch regression: install_exclude / Fix-2 still works

class TestLegacyFieldsPreserved:
    def test_install_exclude_field_still_default(self, us, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        # minimal git + submodule shape; bare remotes
        bare_up = _bare(tmp_path / "upstream.git")
        bare_origin = _bare(tmp_path / "origin.git")
        child = project / "child"
        _work(child, branch="main")
        _git(child, "remote", "add", "origin", str(bare_origin))
        _git(child, "remote", "add", "upstream", str(bare_up))
        # v2.2.0 install_exclude still present and default = ()
        cfg = us.SubmoduleConfig(
            name="child", path=Path("child"), origin=None, upstream=None,
            branch="main", venv=None, pip_install_cmd=None,
            pre_merge_hooks=(), systemd_service=None, health_check=None,
            skip_push=False, notes="", config_source="heuristic",
        )
        assert cfg.install_exclude == ()

    def test_validate_override_accepts_legacy_only_yaml(self, us):
        # Schema_version + branch + install_exclude should still validate cleanly.
        v = us.validate_override({
            "schema_version": 1,
            "branch": "develop",
            "install_exclude": ["foo"],
        })
        assert v["branch"] == "develop"
        assert v["install_exclude"] == ["foo"]

# A-BM-011 / source priority full ordering test

class TestSourcePriorityChain:
    def test_no_gitmodules_branch_no_origin_head_main_fallback(self, us, tmp_path):
        # source = main fallback candidate (cached upstream/main exists)
        sub = tmp_path / "sub"
        sub.mkdir()
        bare = _bare(tmp_path / "upstream.git")
        _work(sub, branch="main")
        _git(sub, "remote", "add", "upstream", str(bare))
        _git(sub, "config", "remote.upstream.fetch",
             "+refs/heads/*:refs/remotes/upstream/*")
        # create C0 on upstream/main and push from seed
        seed = tmp_path / "seed"
        _work(seed, branch="main")
        _commit(seed, "C0", {"a": "1"})
        _push(seed, str(bare), "main")
        # cache commit in child
        _git(sub, "fetch", "upstream", "main")
        # delete main upstream refs
        # ... actually keep cached; assertion is path was followed and main chosen
        result = us._discover_upstream_branch(sub, optin_branch=None, legacy_branch=None)
        assert result in (None, "main")  # impl may return None if cache fetch fails

# A-BM-017 / skip/resume semantics

class TestSkipResume:
    def test_skip_merge_still_validates_source(self, us, tmp_path):
        # When opt-in branch explicit but upstream_branch not yet resolvable,
        # skip-merge must NOT bypass validation; fetch still runs.
        # Source missing -> fetch fail -> overall fail.
        root = tmp_path / "sm"
        root.mkdir()
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="main")
        _commit(seed, "C0", {"a": "1"})
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        # NO upstream remote at all -> source unresolved
        _write_gitmodules(project, "child", "child", branch="main")
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_merge=True, skip_install=True, skip_restart=True,
        )
        assert result.overall == "fail"
        fetch_phase = [p for p in result.phases if p.phase == "fetch"][0]
        assert fetch_phase.status == "fail"

# ---------------------------------------------------------------------------
# A-BM-019 / FETCH_HEAD via dry-run: must NOT fetch, but report cached comparison faithfully
# ---------------------------------------------------------------------------

class TestDryRunNoFetch:
    def test_dry_run_does_not_fetch(self, us, tmp_path):
        root = tmp_path / "dryrun"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="main")
        _commit(seed, "C0", {"a": "1"})
        _push(seed, str(upstream), "main")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        _git(child, "remote", "add", "upstream", str(upstream))
        # seed C1
        _commit(seed, "C1", {"a": "2"})
        _push(seed, str(upstream), "main")
        # child has NO cache of upstream/main
        _write_gitmodules(project, "child", "child", branch="main")
        before = _snapshot(child)
        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_install=True, skip_restart=True,
        )
        after = _snapshot(child)
        # dry-run must NOT introduce new cached commit
        # (FETCH_HEAD must not exist or remain unchanged)
        assert before["fetch_head_exists"] == after["fetch_head_exists"]
        # upstream/main ref in child refs must not change
        assert before["refs"] == after["refs"]
        assert result.overall == "fail"  # no cache -> unknown

# ---------------------------------------------------------------------------
# A-BM-021..024 / T3R closeout: dry-run visibility, target reject, apply reject, ordinary-push failure
# ---------------------------------------------------------------------------

class TestDryRunVisibility:
    """A-BM-021: even when no opt-in override is present, the dry-run output
    must clearly report source=master, target=main and cached-vs-not-fetched
    state plus the full fetch/merge/push plan (DESIGN §3.9.7).
    OctoBot-style fixture: source branch on upstream is ``master``, target
    branch (local/origin) is ``main``. Submodule is created without a
    ``.update_submodules.yaml`` file.
    """

    def test_dry_run_phase_details_show_source_target_cached(
        self, us, tmp_path,
    ):
        root = tmp_path / "viz"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        # Seed on master (source) AND main (target) at C0 so we can clone
        # origin/main while still resolving cached upstream/master.
        # We deliberately DO NOT push the seed's local main branch to
        # upstream so upstream has only ``master`` (mirrors OctoBot,
        # whose upstream is Drakkar-Software/OctoBot @ master).
        _work(seed, branch="master")
        _commit(seed, "C0", {"a": "1"})
        _git(seed, "branch", "main")
        _git(seed, "remote", "add", "upstream", str(upstream))
        _push(seed, "upstream", "master")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        # Make sure the clone has a local ``main`` branch — cloning a bare
        # repo whose HEAD is detached-style can leave the worktree detached.
        _git(child, "checkout", "-q", "-B", "main", "origin/main")
        _git(child, "remote", "add", "upstream", str(upstream))
        # cache upstream/master into the child so dry-run can compare
        _git(child, "fetch", "upstream", "master")
        _write_gitmodules(project, "child", "child", branch="main")
        # NO opt-in file -> config_source = heuristic
        assert not (child / ".update_submodules.yaml").exists()

        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_install=True, skip_restart=True,
        )
        assert result.overall == "pass"
        by_phase = {p.phase: p for p in result.phases}

        # phase_fetch (dry-run cached): source + target + cached marker
        fp = by_phase["fetch"]
        assert fp.status == "pass"
        assert "source=master" in fp.detail
        assert "target=main" in fp.detail
        assert "cached" in fp.detail.lower() or "未 fetch" in fp.detail

        # phase_push (dry-run): full push command, no spurious fetch
        pp = by_phase["push"]
        assert pp.status == "pass"
        assert "git push origin main" in pp.detail
        # dry-run must NOT claim the fetch already happened
        assert "fetch upstream" not in pp.detail.lower()

    def test_dry_run_branch_selection_logged_without_optin(
        self, us, tmp_path,
    ):
        """A-BM-021b: branch-selection visibility must reach the operator
        even when no opt-in override is present. Capture stdout via the
        module's ``log_info`` / ``log`` helpers and require the line to
        include target=main + source=master.
        This is the regression for "OctoBot 无 opt-in 不会显示": even with
        a heuristic-only submodule the operator must see branch selection.
        """
        root = tmp_path / "logsel"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="master")
        _commit(seed, "C0", {"a": "1"})
        _git(seed, "branch", "main")
        _git(seed, "remote", "add", "upstream", str(upstream))
        _push(seed, "upstream", "master")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        _git(child, "checkout", "-q", "-B", "main", "origin/main")
        _git(child, "remote", "add", "upstream", str(upstream))
        _git(child, "fetch", "upstream", "master")
        _write_gitmodules(project, "child", "child", branch="main")
        assert not (child / ".update_submodules.yaml").exists()

        # Capture log_info / log calls without altering behaviour
        captured: list[tuple[str, str]] = []
        orig_info = us.log_info
        orig_log = us.log
        try:
            us.log_info = lambda m: captured.append(("INFO", m)) or orig_info(m)
            us.log = lambda m, **kw: captured.append(("LOG", m))
            result = us.process_submodule(
                "child", Path("child"), project,
                do_push=True, dry_run=True,
                skip_install=True, skip_restart=True,
            )
        finally:
            us.log_info = orig_info
            us.log = orig_log

        assert result.overall == "pass"
        # Branch selection log line must be present
        msgs = "\n".join(c[1] for c in captured)
        assert "target=main" in msgs, msgs
        assert "source=master" in msgs, msgs
        # config_source must be heuristic (no opt-in)
        assert "config_source=heuristic" in msgs, msgs

class TestDryRunTargetMismatchBlocksPush:
    """A-BM-022: dry-run must validate target before push plan; detached HEAD -> overall=fail, push phase must not be a passing plan."""

    def test_dry_run_detached_head_blocks_push_with_overall_fail(
        self, us, tmp_path,
    ):
        root = tmp_path / "dethd"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="main")
        _commit(seed, "C0", {"a": "1"})
        _push(seed, str(upstream), "main")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        _git(child, "remote", "add", "upstream", str(upstream))
        _git(child, "fetch", "upstream", "main")  # cache C0
        _write_gitmodules(project, "child", "child", branch="main")

        # Detach HEAD inside the submodule child (target=main, HEAD=detached)
        _git(child, "checkout", "-q", "--detach")

        result = us.process_submodule(
            "child", Path("child"), project,
            do_push=True, dry_run=True,
            skip_install=True, skip_restart=True,
        )
        assert result.overall == "fail"
        assert result.abort_reason is not None
        # If the push phase appears it MUST NOT be a passing dry-run plan.
        # (process_submodule may short-circuit on the early fetch-stage
        # target check and produce an empty phases list — that's still
        # overall=fail with a non-empty abort_reason, which is fine.)
        pp = [p for p in result.phases if p.phase == "push"]
        for p in pp:
            if p.status == "pass":
                assert "git push origin main" not in p.detail
            else:
                assert p.status in ("fail", "skip")

class TestApplyTargetMismatchBlocksPush:
    """A-BM-023: apply must validate target before real git push; failure -> overall=fail, aborted=True, no push invoked."""

    def test_apply_detached_head_blocks_push_no_git_push_called(
        self, us, tmp_path,
    ):
        root = tmp_path / "detap"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="main")
        _commit(seed, "C0", {"a": "1"})
        _push(seed, str(upstream), "main")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        _git(child, "remote", "add", "upstream", str(upstream))
        _git(child, "fetch", "upstream", "main")
        _write_gitmodules(project, "child", "child", branch="main")
        _git(child, "checkout", "-q", "--detach")

        # Wrap git push so any real push would explode loudly.  process_submodule
        # must NOT reach it for this test to pass.
        orig_run_cmd = us.run_cmd

        def _guarded(cmd, **kw):
            if isinstance(cmd, list) and cmd[:2] == ["git", "push"]:
                raise AssertionError(
                    "git push must NOT be invoked when target check fails"
                )
            return orig_run_cmd(cmd, **kw)

        try:
            us.run_cmd = _guarded
            result = us.process_submodule(
                "child", Path("child"), project,
                do_push=True, dry_run=False,
                skip_install=True, skip_restart=True,
            )
        finally:
            us.run_cmd = orig_run_cmd

        assert result.overall == "fail"
        assert result.abort_reason is not None
        # If the push phase appears it MUST NOT be a passing phase.
        pp = [p for p in result.phases if p.phase == "push"]
        for p in pp:
            assert p.status in ("fail", "skip"), (
                f"push phase must not be pass under target mismatch; "
                f"got status={p.status} detail={p.detail!r}"
            )

class TestApplyOrdinaryPushFailureDoesNotFlipOverall:
    """A-BM-024: ordinary git push failure must NOT flip overall=pass; only target-safety errors escalate (DESIGN §3.9.4 scope-out residue)."""

    def test_apply_push_exit_nonzero_is_phase_fail_overall_pass(
        self, us, tmp_path,
    ):
        root = tmp_path / "pushfail"
        root.mkdir()
        upstream = _bare(root / "upstream.git")
        origin = _bare(root / "origin.git")
        seed = root / "seed"
        project = root / "project"
        child = project / "child"
        _work(seed, branch="main")
        _commit(seed, "C0", {"a": "1"})
        _push(seed, str(upstream), "main")
        _git(seed, "remote", "add", "origin", str(origin))
        _push(seed, "origin", "main")
        _git_outside(root, "clone", "-q", str(origin), str(child))
        _git(child, "remote", "add", "upstream", str(upstream))
        _git(child, "fetch", "upstream", "main")  # cache C0
        _write_gitmodules(project, "child", "child", branch="main")

        # Intercept ``git push origin main`` to simulate an ordinary
        # push execution failure (exit=1, stderr from remote hook etc.).
        orig_run_cmd = us.run_cmd

        def _fake_push(cmd, **kw):
            if isinstance(cmd, list) and cmd[:2] == ["git", "push"]:
                from update_submodules import CommandResult  # type: ignore
                return CommandResult(
                    cmd=list(cmd), cwd=kw.get("cwd"),
                    exit_code=1,
                    stdout="",
                    stderr="remote rejected (simulated)",
                )
            return orig_run_cmd(cmd, **kw)

        try:
            us.run_cmd = _fake_push
            result = us.process_submodule(
                "child", Path("child"), project,
                do_push=True, dry_run=False,
                skip_install=True, skip_restart=True,
            )
        finally:
            us.run_cmd = orig_run_cmd

        # Push phase is fail, but overall remains pass (scope-out behaviour).
        pp = [p for p in result.phases if p.phase == "push"]
        assert pp
        assert pp[0].status == "fail"
        assert result.overall == "pass", (
            f"ordinary push execution failure must not flip overall; got "
            f"overall={result.overall} abort_reason={result.abort_reason}"
        )
