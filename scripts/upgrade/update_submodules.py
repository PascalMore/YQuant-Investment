#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用多 submodule 升级器 update_submodules.py (RFC/SPEC/DESIGN-10-008 V2.0)

对 yquant-investment 下任意 git submodule 执行 5 阶段流水线:
  fetch -> merge -> install -> restart -> push

核心策略 (V2.0 auto-discovery + opt-in override):
  - submodule 列表从 .gitmodules 自动解析, 无需中央 manifest.
  - 字段由启发式推断 (git remote / .venv / requirements.txt / systemctl).
  - 每个 submodule 根目录可放 .update_submodules.yaml 覆盖启发式 (opt-in).
  - 默认 dry-run, 安全; --apply 才真正执行.
  - upstream remote 缺失 -> 报清晰错误退出 (不自动 git remote add).
  - push 永远不 --force.

标准库实现, PyYAML optional + stdlib fallback.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

__version__ = "2.2.0"

OPTIN_FILENAME = ".update_submodules.yaml"
OPTIN_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log(msg: str, *, verbose: bool = False, force: bool = False) -> None:
    if verbose or force:
        print(msg, flush=True)


def log_info(msg: str) -> None:
    print(f"[INFO] {msg}", flush=True)


def log_warn(msg: str) -> None:
    print(f"[WARN] {msg}", flush=True, file=sys.stderr)


def log_ok(msg: str) -> None:
    print(f"[OK]   {msg}", flush=True)


def log_err(msg: str) -> None:
    print(f"[ERR]  {msg}", flush=True, file=sys.stderr)


# ---------------------------------------------------------------------------
# Redaction (复制自 upgrade_hermes_agent.py)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,})"),
    re.compile(r"(glpat-[A-Za-z0-9_-]{15,})"),
    re.compile(r"(xox[bpoa]-[A-Za-z0-9-]{10,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(token[=:]\s*)([A-Za-z0-9_\-/+=]{16,})", re.IGNORECASE),
    re.compile(r"(api[_-]?key[=:]\s*)([A-Za-z0-9_\-/+=]{16,})", re.IGNORECASE),
    re.compile(r"(password[=:]\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END[^-]+-----)"),
    re.compile(r"\b([A-Za-z0-9+/=_-]{40,})\b"),
]


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        def _sub(m: re.Match) -> str:
            groups = m.groups()
            if len(groups) >= 2:
                return f"{groups[0]}***REDACTED***"
            return "***REDACTED***"
        out = pat.sub(_sub, out)
    return out


def redact_command(cmd: list) -> list:
    return [redact(str(c)) for c in cmd]


# ---------------------------------------------------------------------------
# Data structures (DESIGN §3.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmoduleConfig:
    """单个 submodule 的运行时配置 (启发式 + opt-in merge 后)."""

    name: str
    path: Path
    origin: Optional[str]
    upstream: Optional[str]
    branch: str
    upstream_branch: Optional[str] = None  # V2.1: 来源分支; None 表示独立发现
    venv: Optional[Path] = None
    pip_install_cmd: Optional[tuple[str, ...]] = None
    pre_merge_hooks: tuple[str, ...] = ()
    systemd_service: Optional[str] = None
    health_check: Optional[str] = None
    skip_push: bool = False
    notes: str = ""
    config_source: str = "heuristic"  # "heuristic" | "heuristic+opt-in" | "opt-in-only"
    install_exclude: tuple[str, ...] = ()  # v2.2.0: opt-in pkg filter (PEP 503 normalized)


@dataclass
class CommandResult:
    """5 字段, no logic."""

    cmd: list
    cwd: Optional[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class SubmoduleState:
    config: SubmoduleConfig
    abs_path: Path
    pre_head: Optional[str]
    # V2.1: behind/ahead are Optional to represent "unresolved / not
    # compared yet". They must NEVER silently become 0/0.
    behind: Optional[int] = None
    ahead: Optional[int] = None
    upstream_ref: str = ""  # SHA for apply; cached/empty for dry-run


@dataclass
class PhaseResult:
    phase: str  # "fetch" | "merge" | "install" | "restart" | "push"
    status: str  # "pass" | "fail" | "skip" | "abort"
    exit_code: Optional[int]
    duration_sec: float
    detail: str


@dataclass
class PipelineResult:
    name: str
    config_source: str
    phases: list  # list[PhaseResult]
    overall: str  # "pass" | "fail"
    abort_reason: Optional[str]


# ---------------------------------------------------------------------------
# Command wrapper (复制并简化自 upgrade_hermes_agent.py)
# ---------------------------------------------------------------------------


def run_cmd(cmd: list, *, cwd: Optional[str] = None,
            capture: bool = True, env: Optional[dict] = None,
            verbose: bool = False, timeout: Optional[int] = None) -> CommandResult:
    """统一执行外部命令. 禁止 shell=True."""
    cmd_str_parts = redact_command(cmd)
    cwd_display = str(cwd) if cwd else os.getcwd()
    log(f"$ {' '.join(cmd_str_parts)}  (cwd={cwd_display})", verbose=verbose)
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=capture, text=True,
            env=env, timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(cmd=list(cmd), cwd=cwd, exit_code=127,
                             stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return CommandResult(cmd=list(cmd), cwd=cwd, exit_code=124,
                             stdout="", stderr=f"timeout after {timeout}s")
    return CommandResult(
        cmd=list(cmd), cwd=cwd, exit_code=proc.returncode,
        stdout=proc.stdout or "", stderr=proc.stderr or "",
    )


# ---------------------------------------------------------------------------
# YAML loader (PyYAML optional + stdlib fallback)
# ---------------------------------------------------------------------------


def _strip_yaml_val(v: str):
    v = v.strip()
    if not v:
        return None
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    if v.lower() in ("null", "~"):
        return None
    # try int
    try:
        return int(v)
    except ValueError:
        pass
    return v


def _parse_simple_yaml(text: str) -> dict:
    """受限 YAML 子集 parser, 支持:
      - 顶层 key: value
      - 顶层 key: 下面的 list 项 (- value 或 - key: value)
      - list item 下的子 key: value 和子 list
      - 字符串值支持双引号/单引号/无引号; 空值 = null
    解析失败返回空 dict.
    """
    out: dict = {}

    def _flush_list(list_key, items):
        if list_key is not None:
            out[list_key] = list(items)

    state = "top"
    list_key: Optional[str] = None
    items: list = []
    cur_item: Optional[dict] = None
    cur_child_key: Optional[str] = None
    cur_child_items: list = []
    list_indent = 0

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if state == "top":
            if indent == 0 and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    list_key = key
                    items = []
                    cur_item = None
                    cur_child_key = None
                    cur_child_items = []
                    list_indent = 0
                    state = "expect_list"
                else:
                    out[key] = _strip_yaml_val(val)
        elif state == "expect_list":
            if stripped.startswith("- "):
                state = "in_list"
                item_inline = stripped[2:].strip()
                cur_item = {}
                if ":" in item_inline:
                    k, _, v = item_inline.partition(":")
                    cur_item[k.strip()] = _strip_yaml_val(v)
                list_indent = indent
                items.append(cur_item)
            elif indent == 0 and ":" in stripped:
                _flush_list(list_key, items)
                list_key = None
                items = []
                state = "top"
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    list_key = key
                    items = []
                    cur_item = None
                    state = "expect_list"
                else:
                    out[key] = _strip_yaml_val(val)
        elif state == "in_list":
            if indent == 0:
                _flush_list(list_key, items)
                list_key = None
                items = []
                state = "top"
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    list_key = key
                    items = []
                    cur_item = None
                    state = "expect_list"
                else:
                    out[key] = _strip_yaml_val(val)
            elif stripped.startswith("- "):
                if indent == list_indent and cur_child_key is None:
                    item_inline = stripped[2:].strip()
                    cur_item = {}
                    if ":" in item_inline:
                        k, _, v = item_inline.partition(":")
                        cur_item[k.strip()] = _strip_yaml_val(v)
                    items.append(cur_item)
                elif cur_item is not None and cur_child_key is not None:
                    value = stripped[2:].strip()
                    cur_child_items.append(_strip_yaml_val(value))
                    cur_item[cur_child_key] = list(cur_child_items)
            elif ":" in stripped:
                # flush any pending child list
                if cur_child_key is not None and cur_child_items and cur_item is not None:
                    cur_item[cur_child_key] = list(cur_child_items)
                cur_child_key = None
                cur_child_items = []
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    cur_child_key = key
                    cur_child_items = []
                    if cur_item is not None:
                        cur_item[key] = None
                else:
                    if cur_item is not None:
                        cur_item[key] = _strip_yaml_val(val)

    _flush_list(list_key, items)
    return out


def load_yaml(path: Path) -> dict:
    """YAML 加载: 优先 PyYAML (optional), fallback 到 stdlib 子集解析."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore  # optional
        try:
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            pass
    except Exception:
        pass
    return _parse_simple_yaml(text)


# ---------------------------------------------------------------------------
# .gitmodules parser
# ---------------------------------------------------------------------------


def parse_gitmodules(project_root: Path) -> list[tuple[str, Path]]:
    """解析 .gitmodules 的 [submodule "<name>"] sections.
    返回 [(name, rel_path), ...].
    """
    gm_path = project_root / ".gitmodules"
    if not gm_path.exists():
        return []
    text = gm_path.read_text(encoding="utf-8")
    results: list[tuple[str, Path]] = []
    cur_name: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[submodule"):
            m = re.match(r'\[submodule\s+"(.+)"\]', line)
            if m:
                cur_name = m.group(1)
        elif cur_name and line.startswith("path"):
            _, _, val = line.partition("=")
            rel = val.strip()
            results.append((cur_name, Path(rel)))
    return results


# ---------------------------------------------------------------------------
# Heuristic discovery
# ---------------------------------------------------------------------------


def normalize_remote_branch(ref: str, *, remote: str = "origin") -> Optional[str]:
    """Normalize git remote branch refs to a local branch name.

    Examples:
      - refs/remotes/origin/main -> main
      - origin/main -> main
      - main -> main
      - refs/remotes/origin/feature/x -> feature/x

    V2.1: stricter — rejects refs whose remote prefix doesn't match ``remote``,
    HEAD, empty suffix, ``refs/tags/...``, full SHA IDs, refs whose remainder
    starts with ``-``, illegal-ref expressions (``main..x``, ``main~1``, globs),
    or `(unknown)`. Returns None for any unrecognised input.

    `git symbolic-ref --short refs/remotes/origin/HEAD` returns `origin/main`,
    not `refs/remotes/origin/main`.  Fetching upstream with the un-normalized
    value would run `git fetch upstream origin/main`, which fails because
    upstream has `main`, not `origin/main`.
    """
    if ref is None:
        return None
    ref = ref.strip()
    if not ref:
        return None
    full_prefix = f"refs/remotes/{remote}/"
    short_prefix = f"{remote}/"
    if ref.startswith(full_prefix):
        ref = ref[len(full_prefix):]
    elif ref.startswith(short_prefix):
        ref = ref[len(short_prefix):]
    else:
        # No prefix strip → must be a bare name with no remote namespace.
        # Reject if it carries any other remote prefix (e.g. `upstream/main`
        # passed to origin remote).
        wrong = "upstream" if remote == "origin" else "origin"
        if ref.startswith(f"{wrong}/") \
                or ref.startswith(f"refs/remotes/{wrong}/"):
            return None
    # After stripping, the remainder must look like a local branch name.
    if not ref:
        return None
    if ref == "HEAD" or ref.endswith("/HEAD"):
        return None
    if ref.startswith("-"):
        return None
    # Reject any refs/* that aren't refs/heads (e.g. refs/tags/v1)
    if ref.startswith("refs/") and not ref.startswith("refs/heads/"):
        return None
    if ref.startswith("tags/") or ref.startswith("remotes/"):
        return None
    # Illegal ref expression characters
    illegal_chars = set("*~?[]\\^:")
    if any(c in ref for c in illegal_chars):
        return None
    # Reject "main..x", "main...x", and similar ranges
    if ".." in ref:
        return None
    # SHA-like (40 hex) object id passed as branch
    if len(ref) >= 40 and all(c in "0123456789abcdef" for c in ref.lower()):
        return None
    # Verify ref format via git (best-effort); falls back to string check.
    r = run_cmd(["git", "check-ref-format", "--branch", ref])
    if r.exit_code != 0:
        return None
    return ref


def parse_origin_head(submodule_path: Path) -> Optional[str]:
    """git symbolic-ref refs/remotes/origin/HEAD -> local branch name.
    失败 -> None (fallback 'main').
    """
    r = run_cmd(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                cwd=str(submodule_path))
    if r.exit_code == 0 and r.stdout.strip():
        return normalize_remote_branch(r.stdout.strip(), remote="origin")
    return None


def _detect_upstream_default_branch(submodule_path: Path) -> Optional[str]:
    """Best-effort discovery of the upstream repo's default branch.

    Resolution order:
      1. `git symbolic-ref --short refs/remotes/upstream/HEAD` (set when
         `git remote set-head upstream --auto` has been run).
      2. `git remote show upstream` -> "HEAD branch: <name>".
      3. probe `upstream/main` then `upstream/develop` then `upstream/master`
         (whichever exists locally).

    Returns a normalized local branch name, or None when nothing matches.
    Used by :func:`discover_submodule` to avoid hard-fallback ``branch="main"``
    for upstreams whose default is `develop` (e.g. TradingAgents-CN).
    """
    # 1. cached upstream/HEAD symbolic ref
    r = run_cmd(["git", "symbolic-ref", "--short",
                 "refs/remotes/upstream/HEAD"],
                cwd=str(submodule_path))
    if r.exit_code == 0 and r.stdout.strip():
        ref = normalize_remote_branch(r.stdout.strip(), remote="upstream")
        if ref:
            return ref
    # 2. `git remote show upstream`
    r = run_cmd(["git", "remote", "show", "upstream"],
                cwd=str(submodule_path))
    if r.exit_code == 0:
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("head branch:"):
                name = line.split(":", 1)[1].strip()
                if name:
                    return name
    # 3. probe common defaults
    for candidate in ("main", "develop", "master"):
        r = run_cmd(["git", "rev-parse", "--verify", "--quiet",
                     f"upstream/{candidate}"],
                    cwd=str(submodule_path))
        if r.exit_code == 0:
            return candidate
    return None


def _read_gitmodules_branch(project_root: Path, section: str) -> Optional[str]:
    """Read `.gitmodules` section branch via ``git config --file``.

    Returns the configured branch name (normalized to bare form when
    ``branch = .`` is used), or None if the key is absent / unreadable.
    An explicit empty value or a read error does NOT silently fall back —
    the caller decides between None (absent) and a parse failure (raise).
    """
    r = run_cmd(
        ["git", "config", "--file", str(project_root / ".gitmodules"),
         "--get", f"submodule.{section}.branch"],
        cwd=str(project_root),
    )
    if r.exit_code != 0:
        return None
    val = r.stdout.strip()
    if not val:
        return None
    if val == ".":
        # Expand to the project root's current symbolic HEAD.
        head_ref = run_cmd(["git", "symbolic-ref", "--short", "HEAD"],
                           cwd=str(project_root))
        if head_ref.exit_code != 0:
            raise ValueError(
                f".gitmodules branch='.' requires a symbolic HEAD in {project_root}"
            )
        return normalize_remote_branch(head_ref.stdout.strip(), remote="origin")
    return val


def _gitmodules_target_branch(project_root: Path, section: str,
                               fallback: Optional[str] = None) -> Optional[str]:
    """Target branch from .gitmodules. The fallback argument is consulted only
    if ``.gitmodules`` is absent; explicit empty/illegal values raise so the
    caller can fail rather than silently fall back.
    """
    gm = project_root / ".gitmodules"
    if not gm.exists():
        return fallback
    return _read_gitmodules_branch(project_root, section)


def _discover_target_branch(submodule_path: Path, *,
                             project_root: Path,
                             section: str,
                             optin_branch: Optional[str]) -> str:
    """Resolve target (local/origin) branch per SPEC §3.5 priority:

      1. valid opt-in branch
      2. .gitmodules branch (per section identity; ``.`` expands to project HEAD)
      3. current submodule HEAD (must be a symbolic branch)
      4. cached origin HEAD
      5. fallback ``main``

    Returns the bare branch name. Raises ValueError when an explicit source
    (.gitmodules or opt-in) is malformed, or when .gitmodules ``branch=.`` and
    the project root is detached.
    """
    # 1. opt-in branch — caller already validated, but double-check it normalizes.
    if optin_branch:
        return optin_branch

    # 2. .gitmodules branch for THIS section (not for any other submodule).
    bm = _read_gitmodules_branch(project_root, section)
    if bm:
        return bm

    # 3. current symbolic HEAD (must NOT be a SHA)
    head_r = run_cmd(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                     cwd=str(submodule_path))
    if head_r.exit_code == 0:
        cur = head_r.stdout.strip()
        if cur:
            return cur

    # 4. cached origin HEAD
    origin_branch = parse_origin_head(submodule_path)
    if origin_branch:
        return origin_branch

    # 5. literal fallback
    return "main"


def _discover_upstream_branch(submodule_path: Path, *,
                               optin_branch: Optional[str],
                               legacy_branch: Optional[str]) -> Optional[str]:
    """Resolve the upstream source branch per SPEC §3.5 priority:

      1. opt-in upstream_branch (caller passes already-validated value)
      2. opt-in legacy ``branch`` — used as a same-name source fallback
      3. cached upstream HEAD (symbolic-ref or commit ref)
      4. read-only ``git remote show upstream`` (no fetch / no set-head)
      5. probe upstream/main, upstream/develop, upstream/master commit cache

    Returns the bare branch name, or None if every step failed (caller
    treats that as ``upstream_branch unresolved``).
    """
    if optin_branch:
        return optin_branch
    if legacy_branch:
        return legacy_branch

    # 1. cached upstream/HEAD symbolic ref
    r = run_cmd(["git", "symbolic-ref", "--short",
                 "refs/remotes/upstream/HEAD"],
                cwd=str(submodule_path))
    if r.exit_code == 0 and r.stdout.strip():
        ref = normalize_remote_branch(r.stdout.strip(), remote="upstream")
        if ref:
            # Prefer name even when commit cache is missing; dry-run will
            # then surface unknown explicitly. Don't substitute candidates.
            return ref

    # 2. read-only remote show (allow LC_ALL=C; never fetch / set-head)
    env = {**os.environ, "LC_ALL": "C"}
    r = run_cmd(["git", "remote", "show", "upstream"],
                cwd=str(submodule_path), env=env)
    if r.exit_code == 0:
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("head branch:"):
                name = line.split(":", 1)[1].strip()
                if name and name != "(unknown)":
                    norm = normalize_remote_branch(name, remote="upstream")
                    if norm:
                        return norm

    # 3. probe common cached defaults (commit ref only — never fetches)
    for candidate in ("main", "develop", "master"):
        r = run_cmd(["git", "rev-parse", "--verify", "--quiet",
                     f"refs/remotes/upstream/{candidate}"],
                    cwd=str(submodule_path))
        if r.exit_code == 0:
            return candidate

    return None


def _discover_branch(submodule_path: Path, *, optin_branch: Optional[str]) -> str:
    """Backward-compatible target-only discovery (legacy helper, now a thin
    wrapper around ``_discover_target_branch``). Uses the empty project_root
    and a synthetic section name ``""`` so no .gitmodules lookup is done.
    """
    return _discover_target_branch(
        submodule_path,
        project_root=submodule_path.parent,
        section="",
        optin_branch=optin_branch,
    )


def list_remotes(submodule_path: Path) -> list[str]:
    """Return list of remote names."""
    r = run_cmd(["git", "remote"], cwd=str(submodule_path))
    if r.exit_code != 0:
        return []
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


def match_systemd_unit(submodule_path: Path) -> Optional[str]:
    """systemctl --user list-units 中模糊匹配 path 段.
    取最长 match. 无 match -> None.
    下划线/连字符归一化匹配 (path 用 _, systemd unit 用 -).
    """
    r = run_cmd(["systemctl", "--user", "list-units", "--type=service",
                 "--no-legend", "--no-pager"])
    if r.exit_code != 0:
        return None
    # 候选 path 段: 用 path 的各段, 归一化为连字符
    parts = [p.lower().replace("_", "-") for p in submodule_path.parts if p]
    best: Optional[str] = None
    best_len = 0
    for line in r.stdout.splitlines():
        cols = line.split()
        if not cols:
            continue
        unit = cols[0].lower()
        for part in parts:
            if len(part) >= 3 and part in unit:
                if len(part) > best_len:
                    best = cols[0]
                    best_len = len(part)
                break
    return best


def discover_submodule(name: str, path: Path, project_root: Path,
                        *, override: Optional[dict] = None,
                        resolve_source: bool = True) -> SubmoduleConfig:
    """启发式推断所有字段. cwd = project_root; git 命令用 -C <path>.

    V2.1: 接受 ``override`` (validated opt-in dict) 与 ``resolve_source``。
    当 ``override`` 提供时, 启发式仅填充尚未显式给出的字段, 已覆盖字段
    不会被发现结果"反噬"。``resolve_source=False`` 表示 resume 等场景
    不需要做 upstream 默认发现, 仅返回 cfg.upstream_branch=None 交由 phase_fetch
    报 unknown。
    """
    abs_path = (project_root / path).resolve()

    # origin
    r = run_cmd(["git", "remote", "get-url", "origin"], cwd=str(abs_path))
    origin = r.stdout.strip() if r.exit_code == 0 and r.stdout.strip() else None

    # upstream: 缺失 -> None (Phase 1 报错, 不在此处 raise)
    r = run_cmd(["git", "remote", "get-url", "upstream"], cwd=str(abs_path))
    if r.exit_code == 0 and r.stdout.strip():
        upstream = r.stdout.strip()
    else:
        upstream = None

    # V2.1: 显式 opt-in 字段优先于任何发现; 但 target 仅依赖 override 与
    # .gitmodules/current/origin (不再用 upstream 默认). upstream_branch
    # 在 resolve_source=True 时走独立发现链.
    optin_branch = override.get("branch") if override else None
    optin_upstream_branch = override.get("upstream_branch") if override else None

    try:
        target_branch = _discover_target_branch(
            abs_path,
            project_root=project_root,
            section=name,
            optin_branch=optin_branch,
        )
    except ValueError as exc:
        # .gitmodules branch='.' but project detached, or similar
        raise ValueError(
            f"submodule \"{name}\" 目标发现失败: {exc}"
        ) from exc

    if resolve_source:
        # legacy same-name source: only when opt-in has explicit branch and no
        # explicit upstream_branch. computed target_branch must NOT act as legacy.
        legacy_source = None
        if override is not None and "upstream_branch" not in override \
                and "branch" in override:
            legacy_source = optin_branch
        upstream_branch = _discover_upstream_branch(
            abs_path,
            optin_branch=optin_upstream_branch,
            legacy_branch=legacy_source,
        )
    else:
        upstream_branch = None

    # venv
    venv = Path(".venv") if (abs_path / ".venv").exists() else None

    # pip_install
    if (abs_path / "requirements.txt").exists():
        pip_install_cmd: Optional[tuple[str, ...]] = ("install", "-r", "requirements.txt")
    else:
        pip_install_cmd = None

    # systemd
    systemd_service = match_systemd_unit(abs_path)

    return SubmoduleConfig(
        name=name,
        path=path,
        origin=origin,
        upstream=upstream,
        branch=target_branch,
        upstream_branch=upstream_branch,
        venv=venv,
        pip_install_cmd=pip_install_cmd,
        pre_merge_hooks=(),
        systemd_service=systemd_service,
        health_check=None,  # V2.0 默认 None
        skip_push=False,
        notes="",
        config_source="heuristic",
        install_exclude=(),  # v2.2.0 default
    )


# ---------------------------------------------------------------------------
# opt-in override
# ---------------------------------------------------------------------------


def _validate_branch_field(value: Any, *, field_name: str,
                           remote: str) -> Optional[str]:
    """Validate an explicit opt-in branch value per SPEC §3.6.

    Returns the bare normalized branch name on success. Raises ValueError
    for explicit null, empty, non-string, illegal-ref, or wrong-remote
    inputs. Returning None signals the field was absent (no opt-in entry).
    """
    if value is None:
        raise ValueError(
            f"opt-in {field_name} 显式为 null, 字段值非法"
        )
    if not isinstance(value, str):
        raise ValueError(
            f"opt-in {field_name} 必须是字符串, 收到 {type(value).__name__}"
        )
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"opt-in {field_name} 显式为空字符串")
    if stripped == "HEAD":
        raise ValueError(f"opt-in {field_name} 不能为 HEAD")
    # Wrong-remote short prefix (e.g. upstream/main passed to origin remote)
    wrong_remote = "upstream" if remote == "origin" else "origin"
    if stripped.startswith(f"{wrong_remote}/") \
            or stripped.startswith(f"refs/remotes/{wrong_remote}/"):
        raise ValueError(
            f"opt-in {field_name}={value!r} 使用了错误 remote 前缀 "
            f"(字段角色要求 {remote}/* 或裸名)"
        )
    norm = normalize_remote_branch(stripped, remote=remote)
    if norm is None:
        raise ValueError(
            f"opt-in {field_name}={value!r} 不是合法的 {remote} 分支名"
        )
    return norm


def validate_override(raw: dict) -> Optional[dict]:
    """校验 .update_submodules.yaml schema (V2.0 / V2.1).

    V2.1 变更: ``branch`` 与 ``upstream_branch`` 在 opt-in 中显式给出但
    值非法 (null/empty/non-string/illegal-ref/wrong-remote) 时必须抛
    ``ValueError``, 不能像 v2.1.0 那样静默按字段缺失处理. 文件无法
    加载 / schema_version 错误 / 其他字段类型错误保持原有 warning +
    None 回落契约不变.
    """
    if not isinstance(raw, dict):
        return None
    # schema_version (optional but if present must be int-able)
    sv = raw.get("schema_version")
    if sv is not None:
        try:
            int(sv)
        except (TypeError, ValueError):
            log_warn(f"opt-in schema_version 非法: {sv}, 跳过 override")
            return None

    # V2.1: 显式分支字段必须先单独校验, 失败直接抛 ValueError (不被
    # 既有 file-YAML 捕获吞掉).
    out: dict[str, Any] = {}
    if "branch" in raw:
        out["branch"] = _validate_branch_field(
            raw["branch"], field_name="branch", remote="origin"
        )
    if "upstream_branch" in raw:
        out["upstream_branch"] = _validate_branch_field(
            raw["upstream_branch"], field_name="upstream_branch",
            remote="upstream",
        )

    for key in ("origin", "upstream", "venv", "systemd_service",
                "health_check", "notes"):
        if key in raw:
            out[key] = raw[key]
    if "pip_install" in raw:
        pi = raw["pip_install"]
        if pi is None or isinstance(pi, list):
            out["pip_install"] = pi
    if "pre_merge_hooks" in raw:
        pmh = raw["pre_merge_hooks"]
        if pmh is None or isinstance(pmh, list):
            out["pre_merge_hooks"] = pmh
    if "skip_push" in raw:
        out["skip_push"] = bool(raw["skip_push"])
    # v2.2.0: install_exclude (list[str] -> tuple)
    if "install_exclude" in raw:
        ie = raw["install_exclude"]
        if isinstance(ie, list) and all(isinstance(x, str) and x for x in ie):
            out["install_exclude"] = ie
        else:
            log_warn(f"install_exclude 非法 (需 list[str], 非空), 丢弃该字段: {ie!r}")
    return out


def load_optin_override(submodule_path: Path) -> Optional[dict]:
    """加载 <submodule_path>/.update_submodules.yaml.

    不存在 -> None (常态).
    YAML 解析失败 -> warning + None (回落启发式).
    schema 校验失败 -> warning + None.
    V2.1 变更: 显式分支字段 (branch/upstream_branch) 值非法时抛 ValueError,
    由 process_submodule 单独捕获并 fail 该 submodule, 不被文件级 warning
    吞掉.
    """
    override_path = submodule_path / OPTIN_FILENAME
    if not override_path.exists():
        return None
    try:
        raw = load_yaml(override_path)
    except Exception as exc:
        log_warn(f".update_submodules.yaml 解析失败: {exc}, 沿用启发式")
        return None
    validated = validate_override(raw)
    if validated is None:
        log_warn(f".update_submodules.yaml schema 校验失败, 沿用启发式: {override_path}")
        return None
    return validated


def merge_override(base: SubmoduleConfig, override: dict) -> SubmoduleConfig:
    """每个字段独立合并: override 中存在的字段覆盖 base, 未指定保留.

    V2.1 变更:
      - ``upstream_branch`` 单独覆盖来源, 不影响目标.
      - 仅当 override 显式给出 ``branch`` 且未显式给出 ``upstream_branch``
        时, 把规范化的 ``branch`` 裸名同时赋给 upstream_branch (legacy 同名
        兜底); 自动算出的 ``cfg.branch`` 不充当 legacy 显式来源.
      - ``branch`` 字段如有, 仍覆盖目标 (与 v2.1.0 一致).
    """
    changes: dict[str, Any] = {}

    for field_name in ("origin", "upstream", "systemd_service",
                       "health_check", "notes"):
        if field_name in override:
            changes[field_name] = override[field_name]
            if override[field_name] is not None:
                changes[field_name] = override[field_name]

    # V2.1 branch 与 upstream_branch 严格键存在判定, 非 truthy.
    explicit_branch = "branch" in override
    explicit_upstream_branch = "upstream_branch" in override
    if explicit_branch:
        changes["branch"] = override["branch"]
    if explicit_upstream_branch:
        changes["upstream_branch"] = override["upstream_branch"]
    elif explicit_branch and override["branch"]:
        # legacy: opt-in 提供 branch 但未提供 upstream_branch, 来源同名兜底
        changes["upstream_branch"] = override["branch"]

    if "venv" in override:
        v = override["venv"]
        changes["venv"] = Path(v) if v else None

    if "pip_install" in override:
        pi = override["pip_install"]
        if pi is None:
            changes["pip_install_cmd"] = None
        else:
            changes["pip_install_cmd"] = tuple(str(x) for x in pi)

    if "pre_merge_hooks" in override:
        pmh = override["pre_merge_hooks"]
        changes["pre_merge_hooks"] = tuple(pmh) if pmh else ()

    if "skip_push" in override:
        changes["skip_push"] = bool(override["skip_push"])

    if "install_exclude" in override:
        # tuple-ize; PEP 503 normalization happens in phase_install / filter helpers
        changes["install_exclude"] = tuple(override["install_exclude"])

    if changes:
        source = "heuristic+opt-in"
    else:
        source = base.config_source

    # dataclass replace
    return _replace_config(base, changes, source)


def _replace_config(base: SubmoduleConfig, changes: dict, source: str) -> SubmoduleConfig:
    """Create new SubmoduleConfig with field overrides."""
    kwargs = {
        "name": base.name,
        "path": base.path,
        "origin": changes.get("origin", base.origin),
        "upstream": changes.get("upstream", base.upstream),
        "branch": changes.get("branch", base.branch),
        "upstream_branch": changes.get("upstream_branch", base.upstream_branch),
        "venv": changes.get("venv", base.venv),
        "pip_install_cmd": changes.get("pip_install_cmd", base.pip_install_cmd),
        "pre_merge_hooks": changes.get("pre_merge_hooks", base.pre_merge_hooks),
        "systemd_service": changes.get("systemd_service", base.systemd_service),
        "health_check": changes.get("health_check", base.health_check),
        "skip_push": changes.get("skip_push", base.skip_push),
        "notes": changes.get("notes", base.notes),
        "config_source": source,
        "install_exclude": changes.get("install_exclude", base.install_exclude),
    }
    return SubmoduleConfig(**kwargs)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_submodule(cfg: SubmoduleConfig) -> list[str]:
    """返回错误列表. 空列表 = OK."""
    errors: list[str] = []
    abs_path = cfg.path
    if not abs_path.exists():
        errors.append(f"path 不存在: {abs_path}")
    if cfg.upstream is None:
        remotes = list_remotes(abs_path)
        errors.append(
            f'submodule "{cfg.name}" 缺少 upstream remote.\n'
            f"  当前 remotes: {remotes}\n"
            f"  请手动执行: git -C {abs_path} remote add upstream <upstream-url>\n"
            f"  或在 {abs_path}/{OPTIN_FILENAME} 中声明 upstream URL"
        )
    if cfg.origin is not None:
        # basic git URL format check
        if not ("@" in cfg.origin or "://" in cfg.origin or cfg.origin.startswith("/")):
            errors.append(f"origin 不像合法 git URL: {cfg.origin}")
    return errors


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------


def _make_skip(phase: str, detail: str) -> PhaseResult:
    return PhaseResult(phase=phase, status="skip", exit_code=None,
                       duration_sec=0.0, detail=detail)


def _make_pass(phase: str, detail: str, exit_code: int = 0,
               duration: float = 0.0) -> PhaseResult:
    return PhaseResult(phase=phase, status="pass", exit_code=exit_code,
                       duration_sec=duration, detail=detail)


def _make_fail(phase: str, detail: str, exit_code: Optional[int] = None,
               duration: float = 0.0) -> PhaseResult:
    return PhaseResult(phase=phase, status="fail", exit_code=exit_code,
                       duration_sec=duration, detail=detail)


# -----------------------------------------------------------------------
# P1 helpers: requirements 行过滤 (RFC-10-012 §5.1, SPEC §4.2 / Fix-2 §3.4)
# -------------------------------------------------------------------------

# 行首包名提取边界字符: 空白 / 关系运算符 / 注释 / 环境标记 / 选项分隔
_PKG_NAME_END_CHARS = set(" \t<>=!~;#[]")

# 行首包名 token: PEP 503 允许字符
_PKG_NAME_HEAD_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")

# 行内 -r/-c 引用重写: 捕获 option + path 两组, 同时支持分离/等号形式
# 形式: -r X | --requirement X | -r=X | --requirement=X | -c X | -c=X | 同长选项
# path token 必须为非空白 token, 含等号形式时整个 token 形如 opt=path
_REQ_OPT_INLINE_RE = re.compile(
    r"^(\s*(?:-r|--requirement|-c|--constraint)(=|\s+))"
    r"(\S+)(.*)$"
)


def _normalize_pkg_name(name: str) -> str:
    """PEP 503 规范化: lower + `[-_.]+` -> `-`, strip 两侧空白."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _extract_leading_pkg_name(line: str) -> Optional[str]:
    """从 requirements 行提取行首包名 (跳过注释行 / `-` 选项行 / 空行).

    返回原始大小写包名 (未规范化), 用于 audit 回显. 不命中返回 None.
    """
    stripped = line.lstrip()
    # 注释行 / 选项行 (如 -r, --index-url, -e .)
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    m = _PKG_NAME_HEAD_RE.match(stripped)
    if not m:
        return None
    token = m.group(1)
    # 防御: 行首 token 后若紧接非合法字符 (如 '!' 出现在包名位置), 仍按 token 截断
    # PEP 503 包名不含 '!' / ';' 等, 这里依赖 _PKG_NAME_HEAD_RE 的字符集.
    return token


def _resolve_relative_ref(orig_req_dir: Path, path_str: str) -> str:
    """将副本中相对 -r/-c 引用 path_str 解析为原文件目录下的绝对路径.

    原文件是需求解析源; 副本仅是包级行的过滤, 嵌套引用 (relative)
    必须仍由 pip 读取原目录的解析目标. 绝对路径原样保留 (已显式绝对,
    包含 http URL/绝对 Unix 路径/绝对 Windows 路径). URL 与 VCS 引用
    (git+https://...) 不视为相对路径, 不修改.
    """
    p = path_str.strip()
    if not p:
        return path_str
    # 协议 / VCS / Windows 盘符等非相对引用原样保留
    if "://" in p or p.startswith("git+") or re.match(r"^[A-Za-z]:[\\/]", p):
        return path_str
    # 已显式绝对 (POSIX) 直接保留
    if p.startswith("/"):
        return path_str
    resolved = (orig_req_dir / p).resolve()
    return str(resolved)


def _rewrite_relative_refs(line: str, orig_req_dir: Path) -> str:
    """对单行做引用重写: 相对 -r/-c -> 相对于 orig_req_dir 的绝对路径.

    仅当行首匹配 `_REQ_OPT_INLINE_RE` 才重写, 其余内容原样保留 (含行尾
    注释). 行尾 keepends (即行尾 `\\n`) 由调用方负责保留; 本函数只处理
    单行内容, 但为安全起见仍把行尾 `\\n` 从 path 之后剥离并放回结果末尾,
    保证 splitlines(keepends=True) 风格下换行不丢失.
    """
    # 把可能存在的单个尾部 \n 拆出
    if line.endswith("\n"):
        body = line[:-1]
        nl = "\n"
    else:
        body = line
        nl = ""
    m = _REQ_OPT_INLINE_RE.match(body)
    if not m:
        return line  # 不动
    # group(1) = opt + sep (e.g. "-r ", "--requirement=", "  -c ")
    # group(2) = sep (仅识别 ' ' 与 '=' 两种)
    # group(3) = path
    # group(4) = 行尾 (含行尾注释)
    opt_with_sep, sep, path, rest = m.group(1), m.group(2), m.group(3), m.group(4)
    new_path = _resolve_relative_ref(orig_req_dir, path)
    # 保留 option 名 + separator (空格 / '='); path 替换为 new_path
    sep_idx = opt_with_sep.find(sep)
    opt_name = opt_with_sep[:sep_idx]
    new_prefix = f"{opt_name}{sep}{new_path}"
    return new_prefix + rest + nl


def _filter_requirements(req_path: Path, exclude: tuple[str, ...],
                          tmpdir: Optional[Path] = None
                          ) -> tuple[Path, list[str]]:
    """过滤 requirements 文件, 整行删除锚定到 exclude 包名的行; 同时对
    副本中保留的引用行做相对 -r/-c 路径重写, 指向原文件目录 (SPEC §4.2 /
    DESIGN §3.4 Fix-2). 不递归复制或排除嵌套包.

    语义:
      - 一行至多被一个排除包命中 (首包名锚定).
      - 行首包名提取后 PEP 503 规范化与 exclude 元素比对; 仅相等才删.
      - 注释行 / 选项行 / 未命中行原样保留; 仅相对 -r/-c 引用重写.
      - 不修改原文件; 返回副本路径 (调用方负责清理).
      - 多根过滤场景: 副本按 req_path.name 命名, tmpdir 内独立位置, 不
        因同名文件互相覆盖 (调用方传不同 tmpdir 或不同 name).

    返回 (filtered_path, hit_pkg_names) -- hit_pkg_names 为去重保序的原始
    大小写命中包名 (从 requirements 行首提取). 抛 OSError 由 phase_install 捕获.
    """
    import tempfile as _tempfile

    norm_exclude = {_normalize_pkg_name(x) for x in exclude}
    text = req_path.read_text(encoding="utf-8")
    orig_req_dir = req_path.parent.resolve()

    out_lines: list[str] = []
    hit_names: list[str] = []
    seen_hits: set[str] = set()
    for line in text.splitlines(keepends=True):
        # splitlines(keepends=True) 保留原始换行符
        raw_name = _extract_leading_pkg_name(line)
        if raw_name is not None and _normalize_pkg_name(raw_name) in norm_exclude:
            if raw_name not in seen_hits:
                hit_names.append(raw_name)
                seen_hits.add(raw_name)
            # 删除该整行 (不写入 out_lines)
            continue
        # Fix-2: 副本中相对 -r/-c 引用重写为原目录绝对路径,
        # 保证嵌套原件仍由 pip 解析. 注释 / 未命中行 (含行内注释) 原样保留.
        out_lines.append(_rewrite_relative_refs(line, orig_req_dir))

    if tmpdir is None:
        tmpdir = Path(_tempfile.mkdtemp(prefix="update_submodules_filter_"))
    # Fix-3: 每个根 (req_path) 一个独立的临时子目录, 避免同父目录
    # basename (serviceA/reqs/requirements.txt vs serviceB/reqs/
    # requirements.txt) 的两份副本映射到同一路径互相覆盖, 导致 pip
    # parser 只能读到第二份、第一根依赖丢失. 复用调用方传入 tmpdir
    # (由 phase_install 的 finally 清理), 仅在它下面建一个 mkdtemp 唯一
    # 子目录放本次的副本, 不引入自制哈希碰撞平台.
    subdir = Path(_tempfile.mkdtemp(prefix="req_", dir=str(tmpdir)))
    out_path = subdir / req_path.name
    out_path.write_text("".join(out_lines), encoding="utf-8")
    return out_path, hit_names


def _parse_requirement_paths(pip_cmd: tuple[str, ...]) -> list[tuple[int, str]]:
    """从 pip install 命令中提取 -r / --requirement 引用路径.

    返回 [(cmd_index, path_str), ...]. 索引 cmd_index 指向 path_str 自身,
    对于分离形式指向紧随选项的下一 token (path_str == pip_cmd[cmd_index]);
    对于等号形式指向整个 token (path_str == pip_cmd[cmd_index].split("=",1)[1]).
    不存在则返回 [].
    """
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(pip_cmd):
        tok = pip_cmd[i]
        if tok in ("-r", "--requirement") and i + 1 < len(pip_cmd):
            out.append((i + 1, pip_cmd[i + 1]))
            i += 2
            continue
        if tok.startswith("-r=") or tok.startswith("--requirement="):
            out.append((i, tok.split("=", 1)[1]))
        i += 1
    return out


# -----------------------------------------------------------------------
# P2 helper: classify_pip_failure sample 二次选择 (SPEC §4.3)
# -----------------------------------------------------------------------

# 探测正则: 包名形态 token + 紧接版本约束运算符 (单一字符串内)
_PKG_CONSTRAINT_TOKEN_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*\s*[<>=!~]"
)
# 探测: "Could not find a version that satisfies the requirement <pkg>"
_COULD_NOT_SATISFY_RE = re.compile(
    r"Could not find a version that satisfies the requirement\s+\S+"
)


def _prefer_constraint_sample(matched_lines: list[str]) -> str:
    """在分类命中的行集合中按 SPEC §4.3 三级优先选 sample.

    1. 同时含包名形态 token + 版本约束运算符的行;
    2. 含 'Could not find a version that satisfies the requirement <pkg>' 的行;
    3. 回落 matched_lines[0] (v2.1.0 行为).
    """
    if not matched_lines:
        return ""
    for ln in matched_lines:
        if _PKG_CONSTRAINT_TOKEN_RE.search(ln):
            return ln.strip()
    for ln in matched_lines:
        if _COULD_NOT_SATISFY_RE.search(ln):
            return ln.strip()
    return matched_lines[0].strip()


def phase_fetch(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 1: fetch upstream.

    V2.1:
      - cfg.upstream is None -> ABORT (V2.0 行为保留).
      - cfg.upstream_branch is None -> unknown, fail (来源 unresolved, 不回填
        目标 main).
      - dry-run: 不 fetch, 只读 ``refs/remotes/upstream/<upstream_branch>^{commit}``
        与 HEAD 比较; 缺缓存或计数非法时 unknown, 停止后续阶段; 标记 cached/not
        fetched, 不声称"远端最新"。
      - apply: 严格 ``git fetch upstream refs/heads/<upstream_branch>`` (单
        refspec 避免同名 tag / tracking refspec 偷换), 成功后立即解析
        ``FETCH_HEAD^{commit}`` 存到 ``state.upstream_ref``, 比较与 merge 都
        使用该 SHA (避免 hooks 改 tracking ref 后偷换来源)。
    """
    cfg = state.config
    if cfg.upstream is None:
        return _make_fail("fetch",
                          f'upstream remote 缺失: submodule "{cfg.name}"; '
                          "请手动 git remote add upstream <url> "
                          f"或在 {cfg.path}/{OPTIN_FILENAME} 声明")
    if cfg.upstream_branch is None:
        state.behind = None
        state.ahead = None
        state.upstream_ref = ""
        return _make_fail(
            "fetch",
            f'upstream 来源 unresolved: submodule "{cfg.name}"; '
            "未配置 upstream_branch 且无缓存可比较",
        )

    src_refspec = f"refs/heads/{cfg.upstream_branch}"

    if dry_run:
        # read-only: only consult cached refs/remotes/upstream/<branch>
        cache_ref = f"refs/remotes/upstream/{cfg.upstream_branch}"
        rev_r = run_cmd(["git", "rev-parse", "--verify", "--quiet",
                         f"{cache_ref}^{{commit}}"],
                        cwd=str(state.abs_path))
        if rev_r.exit_code != 0:
            state.behind = None
            state.ahead = None
            state.upstream_ref = ""
            return _make_fail(
                "fetch",
                f"unknown: 缺缓存 ref {cache_ref}; "
                "dry-run 未 fetch, 无法判定 behind/ahead",
            )
        sha = rev_r.stdout.strip()
        state.upstream_ref = sha
        count_r = run_cmd(["git", "rev-list", "--left-right", "--count",
                           f"{sha}...HEAD"], cwd=str(state.abs_path))
        parsed = _parse_rev_count_strict(count_r.stdout)
        if parsed is None:
            state.behind = None
            state.ahead = None
            return _make_fail(
                "fetch",
                f"unknown: rev-list 输出无法解析 "
                f"({count_r.stdout!r}); cached 比较无法判定",
            )
        state.behind, state.ahead = parsed
        if state.behind == 0:
            return _make_pass(
                "fetch",
                f"[dry-run cached] source={cfg.upstream_branch} target={cfg.branch} "
                f"behind=0 ahead={state.ahead}; 未 fetch; "
                f"merge/push 计划仅按缓存比较",
            )
        return _make_pass(
            "fetch",
            f"[dry-run cached] source={cfg.upstream_branch} target={cfg.branch} "
            f"behind={state.behind} ahead={state.ahead}; "
            f"将执行 git fetch upstream {src_refspec} + "
            f"git merge {'--ff-only' if state.ahead == 0 else '--no-ff'} <commit> "
            f"+ git push origin {cfg.branch}",
        )

    t0 = time.time()
    fetch_r = run_cmd(["git", "fetch", "upstream", src_refspec],
                      cwd=str(state.abs_path))
    if fetch_r.exit_code != 0:
        state.behind = None
        state.ahead = None
        state.upstream_ref = ""
        return _make_fail("fetch",
                          f"git fetch 失败: {redact(fetch_r.stderr)[:300]}",
                          exit_code=fetch_r.exit_code, duration=time.time() - t0)
    rev_r = run_cmd(["git", "rev-parse", "--verify", "--quiet",
                     "FETCH_HEAD^{commit}"], cwd=str(state.abs_path))
    if rev_r.exit_code != 0:
        state.behind = None
        state.ahead = None
        state.upstream_ref = ""
        return _make_fail(
            "fetch",
            "FETCH_HEAD^{commit} 解析失败, 拒绝使用旧缓存计数",
            exit_code=rev_r.exit_code, duration=time.time() - t0,
        )
    sha = rev_r.stdout.strip()
    state.upstream_ref = sha
    count_r = run_cmd(["git", "rev-list", "--left-right", "--count",
                       f"{sha}...HEAD"], cwd=str(state.abs_path))
    parsed = _parse_rev_count_strict(count_r.stdout)
    if parsed is None:
        state.behind = None
        state.ahead = None
        return _make_fail(
            "fetch",
            f"rev-list 输出无法解析 ({count_r.stdout!r}); "
            "拒绝伪造 behind/ahead, 停止后续阶段",
            exit_code=count_r.exit_code, duration=time.time() - t0,
        )
    state.behind, state.ahead = parsed
    return _make_pass("fetch",
                      f"source={cfg.upstream_branch} commit={sha[:12]} "
                      f"behind={state.behind} ahead={state.ahead}",
                      exit_code=0, duration=time.time() - t0)


def _parse_rev_count(stdout: str) -> tuple[int, int]:
    """Parse 'N\\tM' -> (behind, ahead).

    DEPRECATED: retained for backward compatibility but never used by
    phase_fetch / dry-run. New callers must use ``_parse_rev_count_strict``.
    """
    parts = stdout.strip().split()
    if len(parts) >= 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return 0, 0


def _parse_rev_count_strict(stdout: str) -> Optional[tuple[int, int]]:
    """Parse ``git rev-list --left-right --count`` output strictly.

    Returns ``(behind, ahead)`` only when the output is exactly two
    non-negative integers separated by whitespace. Returns None for empty,
    one-token, three-or-more-token, negative, or non-integer inputs.
    """
    if stdout is None:
        return None
    parts = stdout.strip().split()
    if len(parts) != 2:
        return None
    try:
        a = int(parts[0])
        b = int(parts[1])
    except ValueError:
        return None
    if a < 0 or b < 0:
        return None
    return a, b


def _validate_target_branch(abs_path: Path, branch: str) -> None:
    """Verify that ``refs/heads/<branch>`` resolves to a commit AND that
    the current symbolic HEAD equals ``branch``.

    Raises ValueError on:
      - detached HEAD (symbolic-ref fails)
      - target branch missing locally
      - HEAD branch not equal to the requested branch

    Hooks / external state changes that move HEAD after this check are
    not auto-recovered; the caller is expected to re-check before merge
    and before push (DESIGN §3.9.4).
    """
    # 1. symbolic HEAD must be a branch, not a detached SHA
    head_r = run_cmd(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                     cwd=str(abs_path))
    if head_r.exit_code != 0:
        raise ValueError(
            f"目标分支 {branch!r} 校验失败: HEAD 处于 detached 状态"
        )
    cur = head_r.stdout.strip()
    if cur != branch:
        raise ValueError(
            f"目标分支 {branch!r} 校验失败: 当前符号 HEAD={cur!r} 与目标不符"
        )

    # 2. refs/heads/<branch> must resolve to a commit
    rev_r = run_cmd(["git", "rev-parse", "--verify", "--quiet",
                     f"refs/heads/{branch}"], cwd=str(abs_path))
    if rev_r.exit_code != 0:
        raise ValueError(
            f"目标分支 {branch!r} 校验失败: refs/heads/{branch} 不存在"
        )


_CONFLICT_STATUS_PREFIXES = ("UU", "AA", "DD", "AU", "UA", "DU", "UD")


def _collect_conflict_files(status_porcelain: str) -> list[str]:
    """Extract file paths that show up in conflict under ``git status --porcelain``.

    Returns paths in stable order; duplicates removed.  Empty list when no
    conflict markers are present.  P-15 — the audit log shows up to 8 entries
    so users don't have to grep manually.
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in status_porcelain.splitlines():
        if len(line) < 4:
            continue
        prefix = line[:2]
        if prefix not in _CONFLICT_STATUS_PREFIXES:
            continue
        path = line[3:].strip()
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def phase_merge(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 2: merge upstream/<upstream_branch>.

    V2.1:
      - state.behind/ahead=None -> refuse (unknown), fail.
      - known behind=0 -> skip (cached or fetched).
      - dry-run 文本必须含 ``git merge [--ff-only] <source-commit>`` 完整命令,
        不能截断为 ``git --ff-only ...``.
      - apply 前再调一次 ``_validate_target_branch`` (hooks 可能已经切走 HEAD).
      - merge ref 使用 ``state.upstream_ref`` (apply) 或缓存 commit (dry-run),
        永远是单一 SHA, 不是 ``upstream/<branch>`` 跟踪 ref.
    """
    cfg = state.config
    if state.behind is None or state.ahead is None:
        return _make_fail(
            "merge",
            "unknown: behind/ahead 未比较, 拒绝进入 merge",
        )
    if state.behind == 0:
        return _make_skip("merge", "behind=0, skip (cached/fetched)")
    if not state.upstream_ref:
        return _make_fail("merge",
                        "upstream_ref SHA 未绑定, 拒绝执行 merge")
    if dry_run:
        mode = "--ff-only" if state.ahead == 0 else "--no-ff"
        return _make_pass(
            "merge",
            f"[dry-run] git merge {mode} {state.upstream_ref}",
        )
    # Hooks may have changed HEAD; re-validate target before merge.
    try:
        _validate_target_branch(state.abs_path, cfg.branch)
    except ValueError as exc:
        return _make_fail("merge", str(exc))

    # pre_merge_hooks
    for hook in cfg.pre_merge_hooks:
        r = run_cmd(["sh", "-c", hook], cwd=str(state.abs_path))
        if r.exit_code != 0:
            log_warn(f"pre_merge_hook 失败 (不阻塞): {hook}")

    t0 = time.time()
    if state.ahead == 0:
        r = run_cmd(["git", "merge", "--ff-only", state.upstream_ref],
                    cwd=str(state.abs_path))
    else:
        r = run_cmd(["git", "merge", "--no-ff", state.upstream_ref],
                    cwd=str(state.abs_path))
    dur = time.time() - t0
    if r.exit_code != 0:
        status = run_cmd(["git", "status", "--porcelain"],
                         cwd=str(state.abs_path))
        conflict_files = _collect_conflict_files(status.stdout)
        if conflict_files:
            run_cmd(["git", "merge", "--abort"], cwd=str(state.abs_path))
            shown = conflict_files[:8]
            extra = len(conflict_files) - len(shown)
            file_list = ", ".join(shown)
            if extra > 0:
                file_list += f" (+{extra} more)"
            detail = (
                f"merge 冲突 ({len(conflict_files)} files): {file_list}  | "
                "已 git merge --abort; 手动解决后用 --resume-after-merge"
            )
            return _make_fail("merge", detail,
                              exit_code=r.exit_code, duration=dur)
        return _make_fail("merge", f"merge 失败: {redact(r.stderr)[:300]}",
                          exit_code=r.exit_code, duration=dur)
    return _make_pass("merge",
                      f"merged {state.upstream_ref[:12]}",
                      exit_code=0, duration=dur)


def phase_install(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 3: pip install.

    On failure (exit_code != 0) the stderr is classified by
    :func:`classify_pip_failure` so the audit log can attribute the failure
    to one of: missing_dependency / platform_incompatible / network_error /
    resolution_conflict / source_build_error / other.  This is P-6 — the
    longbridge 4.x incident showed that a generic "pip install error" line
    gives no actionable hint.

    v2.2.0 (RFC-10-012 P1): when ``cfg.install_exclude`` is non-empty,
    pip_install_cmd 中 -r/--requirement 引用的 requirements 文件会被过滤
    (整行锚定该包); pip 命令指向临时副本, 成功且发生排除 -> degraded detail.
    Fix-2 最小修复: 等号形式 requirement 选项保留前缀 (-r=path / --requirement=path),
    副本中相对 -r/-c 引用重写为原目录绝对路径, 临时目录从创建起就在 try/finally
    作用域内 (源缺失/写失败/pip 失败/成功/dry-run 全路径清理).
    """
    cfg = state.config
    if cfg.venv is None or cfg.pip_install_cmd is None:
        return _make_skip("install", "venv 或 pip_install 缺失, skip")
    pip_bin = state.abs_path / cfg.venv / "bin" / "pip"
    if not pip_bin.exists():
        return _make_skip("install", f"venv pip 不存在: {pip_bin}, skip")
    cmd = [str(pip_bin)] + list(cfg.pip_install_cmd)

    # v2.2.0 P1: requirements 过滤 (opt-in)
    # Fix-2: 临时目录一旦创建就在 try/finally 作用域内, 确保源缺失/写失败/
    # pip 失败/成功/dry-run 所有退出路径都清理. 提前返回 fail 也走 finally.
    tmpdir_to_clean: Optional[Path] = None
    excluded_hit: list[str] = []
    excluded_miss: list[str] = []
    try:
        if cfg.install_exclude:
            ref_specs = _parse_requirement_paths(cfg.pip_install_cmd)
            if not ref_specs:
                log_warn(
                    f'submodule "{cfg.name}" install_exclude={cfg.install_exclude} '
                    "但 pip_install_cmd 无 -r/--requirement 引用, 排除 no-op"
                )
            else:
                import tempfile
                try:
                    tmpdir_to_clean = Path(
                        tempfile.mkdtemp(prefix="update_submodules_filter_")
                    )
                except OSError as exc:
                    dur = 0.0
                    return _make_fail(
                        "install",
                        f"install_exclude 创建临时目录失败: {exc}",
                        exit_code=None, duration=dur,
                    )
                # 替换 cmd 中 -r 引用的路径 -> 副本路径
                # 用 list 重组 (tuple 不可改)
                # 注意: ref_specs 的索引相对 cfg.pip_install_cmd, 而 cmd 前置了
                # pip_bin, 替换时须加该偏移 (Fix-1), 否则会误覆盖 -r 标志本身.
                # Fix-2: 等号形式 (-r=X / --requirement=X) cmd_idx 指向整个
                # token, 不能把整个 token 替换为裸副本路径 (会丢失选项前缀),
                # 必须保留 '<opt>=' 部分. 分离形式 (-r X / --requirement X)
                # cmd_idx 指向 path 所在 token, 直接替换为副本路径即可.
                cmd_list = list(cmd)
                pip_prefix_len = len(cmd) - len(cfg.pip_install_cmd)
                try:
                    for idx, path_str in ref_specs:
                        cmd_idx = idx + pip_prefix_len
                        src = state.abs_path / path_str
                        if not src.exists():
                            return _make_fail(
                                "install",
                                f"requirements 文件不存在: {src}",
                                exit_code=None, duration=0.0,
                            )
                        filtered, hits = _filter_requirements(
                            src, cfg.install_exclude, tmpdir=tmpdir_to_clean
                        )
                        excluded_hit.extend(h for h in hits
                                            if h not in excluded_hit)
                        orig_tok = cmd_list[cmd_idx]
                        if "=" in orig_tok and (
                            orig_tok.startswith("-r=")
                            or orig_tok.startswith("--requirement=")
                        ):
                            # 等号形式: 保留 '<opt>=' 前缀, 只替换 path
                            opt_name = orig_tok.split("=", 1)[0]
                            cmd_list[cmd_idx] = f"{opt_name}={filtered}"
                        else:
                            cmd_list[cmd_idx] = str(filtered)
                except OSError as exc:
                    # 临时文件写失败 -> fail, 不静默回退为不过滤执行
                    dur = 0.0
                    return _make_fail(
                        "install",
                        f"install_exclude 写副本失败: {exc}",
                        exit_code=None, duration=dur,
                    )
                cmd = cmd_list
                # 记录声明中未命中的包 (A-106 audit 透明)
                req_names: set[str] = set()
                for _, path_str in ref_specs:
                    src = state.abs_path / path_str
                    try:
                        text = src.read_text(encoding="utf-8")
                    except OSError:
                        continue
                    for ln in text.splitlines():
                        raw = _extract_leading_pkg_name(ln)
                        if raw:
                            req_names.add(_normalize_pkg_name(raw))
                excluded_miss = [
                    p for p in cfg.install_exclude
                    if _normalize_pkg_name(p) not in req_names
                    and _normalize_pkg_name(p) not in {
                        _normalize_pkg_name(h) for h in excluded_hit
                    }
                ]

        if dry_run:
            return _make_pass("install", f"[dry-run] {' '.join(cmd)}")
        t0 = time.time()
        r = run_cmd(cmd, cwd=str(state.abs_path))
        dur = time.time() - t0
        if r.exit_code == 0:
            if excluded_hit:
                pkgs = ", ".join(excluded_hit)
                detail = f"install (excluded: {pkgs}): OK (degraded)"
            else:
                detail = "pip install OK"
                if excluded_miss:
                    detail += f" | exclude miss: {', '.join(excluded_miss)}"
            return _make_pass("install", detail, exit_code=0, duration=dur)
        classification, sample = classify_pip_failure(r.stderr or r.stdout)
        detail = (
            f"pip install 失败 ({classification}): {redact(sample)[:240]}"
            f"  | hint: {_PIP_HINTS.get(classification, '')}"
        )
        return _make_fail("install", detail, exit_code=r.exit_code, duration=dur)
    finally:
        if tmpdir_to_clean is not None:
            import shutil
            try:
                shutil.rmtree(tmpdir_to_clean, ignore_errors=True)
            except OSError:
                pass


# P-6: pip error classification ------------------------------------------------
# Pattern order matters — first match wins.

_PIP_ERROR_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("platform_incompatible", re.compile(
        r"none of the wheel's tags .* are compatible|"
        r"is not a supported wheel on this platform|"
        r"no matching distribution found for .* from .*linux|manylinux_"
    )),
    ("missing_dependency", re.compile(
        r"No matching distribution found for .+|"
        r"Could not find a version that satisfies the requirement|"
        r"ERROR: Ignored the following yanked versions"
    )),
    ("resolution_conflict", re.compile(
        r"ResolutionImpossible|Requirements conflict|"
        r"ResolutionTooDeep|conflict in dependencies"
    )),
    ("network_error", re.compile(
        r"Could not fetch URL|"
        r"NewConnectionError|"
        r"could not connect to|"
        r"Temporary failure in name resolution"
    )),
    ("source_build_error", re.compile(
        r"feature `\w+` is required|"
        r"metadata-generation-failed|"
        r"BackendUnavailable|"
        r"cargo: error|"
        r"Microsoft Visual C\+\+"
    )),
]

_PIP_HINTS = {
    "missing_dependency": "包名/版本约束在 PyPI 上无匹配。检查 requirements.txt 平台 marker 或与上游 release notes。",
    "platform_incompatible": "wheel 与系统不匹配 (glibc / arch)。WSL/Ubuntu 升级 longbridge 等 manylinux_2_39 包需要 glibc>=2.39 或 Docker base image。",
    "resolution_conflict": "依赖冲突: 两个包对同一依赖要求不同版本。考虑 upgrade 全部依赖或用 pip-compile。",
    "network_error": "网络问题: PyPI 不可达 / 镜像不通 / 代理。检查 PIP_INDEX_URL / 镜像 / 网络。",
    "source_build_error": "源码构建失败: 依赖 Rust/C++ 工具链。pip 默认会无 wheel 时回源构建。",
    "other": "未识别原因, 看 stderr 全文。"
}


def classify_pip_failure(text: str) -> tuple[str, str]:
    """Classify a pip / maturin failure into one of the canonical buckets.

    Returns (classification, representative_sample_line).  The sample is the
    full last non-empty line that triggered the match — useful for putting
    concrete guidance into the audit log.

    v2.2.0 (RFC-10-012 P2): classification pattern first-match unchanged,
    but the sample line selection among the matched-set is upgraded by
    :func:`_prefer_constraint_sample` to prefer the line that contains a
    package name + version constraint token over a generic yanked-warning
    line that happens to appear earlier in the stderr.
    """
    if not text:
        return ("other", "")
    # look at last 60 lines so wheels and yanked warnings don't shadow real
    # cause lines that come later.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    head = "\n".join(lines[-60:])
    for name, pat in _PIP_ERROR_PATTERNS:
        m = pat.search(head)
        if m:
            # pick the first matching sample line as the "smoking gun"
            matched = [ln for ln in lines if pat.search(ln)]
            sample = _prefer_constraint_sample(matched)
            return (name, sample)
    return ("other", lines[-1] if lines else "")


def _wait_for_active_state(service: str, *, timeout_s: float = 15.0,
                           poll_s: float = 0.5) -> tuple[bool, str]:
    """Block until ``systemctl --user is-active <service>`` reports active.

    Returns ``(ok, detail)``.  ``ok`` is True only when the unit reached
    "active" within ``timeout_s``.  P-7/P-13 — we saw daily-stock-analysis
    service restart succeed while FastAPI was still trying to bind 8888; the
    extra wait surfaces this transient race so the audit log can flag it.
    """
    deadline = time.time() + timeout_s
    last_status = ""
    while time.time() < deadline:
        r = run_cmd(["systemctl", "--user", "is-active", service])
        last_status = (r.stdout or r.stderr or "").strip()
        if r.exit_code == 0 and last_status == "active":
            return True, f"active after probe {last_status}"
        time.sleep(poll_s)
    return False, f"timed out (last={last_status or 'unknown'} after {timeout_s:.1f}s)"


def phase_restart(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 4: restart + active wait + health_check (opt-in cmd 时).

    After ``systemctl restart`` returns 0 we proactively wait for the unit
    to enter ``active`` state (P-7/P-13).  An early "restart OK" return code
    used to mask bind races that surfaced seconds later — see the
    longbridge/daily_stock_analysis incident write-up.
    """
    cfg = state.config
    if cfg.systemd_service is None:
        return _make_skip("restart", "systemd_service 缺失, skip")
    restart_cmd = ["systemctl", "--user", "restart", cfg.systemd_service]
    if dry_run:
        detail = f"[dry-run] {' '.join(restart_cmd)}"
        if cfg.health_check:
            detail += f"\n[dry-run] sh -c '{cfg.health_check}'"
        else:
            detail += "\nhealth_check: SKIP (None)"
        detail += "\n[dry-run] wait_for_active: timeout=15s poll=0.5s"
        return _make_pass("restart", detail)
    t0 = time.time()
    r = run_cmd(restart_cmd, cwd=str(state.abs_path))
    dur = time.time() - t0
    if r.exit_code != 0:
        return _make_fail("restart",
                          f"systemctl restart 失败: {redact(r.stderr)[:300]}",
                          exit_code=r.exit_code, duration=dur)
    # P-7/P-13: wait for unit to actually become active before reporting PASS
    ok, wait_detail = _wait_for_active_state(cfg.systemd_service)
    if not ok:
        dur_w = time.time() - t0
        return _make_fail(
            "restart",
            f"systemctl restart 返回 0 但 service 未进入 active: {wait_detail}",
            exit_code=0, duration=dur_w,
        )
    # health_check (V2.0: None = skip)
    if cfg.health_check is None:
        dur_w = time.time() - t0
        return _make_pass("restart",
                          f"restart + wait_for_active OK ({wait_detail}), "
                          f"health_check SKIP (None)",
                          exit_code=0, duration=dur_w)
    # health_check is opt-in shell cmd
    time.sleep(2)
    hc = run_cmd(["sh", "-c", cfg.health_check], cwd=str(state.abs_path))
    dur2 = time.time() - t0
    if hc.exit_code != 0:
        return _make_fail("restart",
                          f"health check 失败: {redact(hc.stderr)[:300]}",
                          exit_code=hc.exit_code, duration=dur2)
    return _make_pass("restart",
                      f"restart + wait_for_active + health_check OK ({wait_detail})",
                      exit_code=0, duration=dur2)


def phase_push(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 5: push origin <branch>. 永远不 --force.

    V2.1 (T3R closeout): target safety is enforced by the caller
    (``process_submodule``) BEFORE this phase is invoked, for both
    dry-run and apply, so a dry-run plan only ever appears after the
    local target branch has been validated.  This function therefore
    only performs the actual ``git push`` (or renders its dry-run text)
    and never re-runs ``_validate_target_branch`` — that helper belongs
    to the process boundary, not the phase itself (DESIGN §3.9.4).

    Ordinary ``git push`` execution failures (non-zero exit, network
    errors, remote rejection, etc.) are recorded as ``status=fail`` but
    deliberately do NOT escalate to ``aborted=True`` at the process
    boundary: that escalation is reserved for target-safety errors
    caught earlier in ``process_submodule``.
    """
    cfg = state.config
    if cfg.skip_push:
        return _make_skip("push", "skip_push=true (opt-in)")
    if dry_run:
        return _make_pass("push",
                          f"[dry-run] git push origin {cfg.branch} "
                          f"(target={cfg.branch})")
    t0 = time.time()
    # NEVER use --force
    r = run_cmd(["git", "push", "origin", cfg.branch],
                cwd=str(state.abs_path))
    dur = time.time() - t0
    if r.exit_code != 0:
        return _make_fail("push", f"push 失败 (不 --force): {redact(r.stderr)[:300]}",
                          exit_code=r.exit_code, duration=dur)
    return _make_pass("push", f"pushed origin/{cfg.branch}",
                      exit_code=0, duration=dur)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


def process_submodule(name: str, path: Path, project_root: Path, *,
                      skip_merge: bool = False, skip_install: bool = False,
                      skip_restart: bool = False,
                      resume_after_merge: bool = False,
                      do_push: bool = False, dry_run: bool = True,
                      force_dirty: bool = False,
                      fail_fast: bool = False) -> PipelineResult:
    """Process a single submodule through the 5-phase pipeline.

    V2.1 变更:
      - 先 ``load_optin_override`` 再 ``discover_submodule(override=...)``;
        显式 opt-in 字段在发现阶段就被尊重, 不会被启发式"反噬"。
      - 任何写阶段 (fetch / hooks / install / restart / push) 之前调用
        ``_validate_target_branch``, 错误直接 fail/exit 1, 不 checkout,
        不 reset, 不创建/重建本地分支.
      - ``resume_after_merge``: 跳过 source 发现 (``resolve_source=False``)
        与 fetch/merge; detail 明确"未比较", 不写 behind=0/latest; 保留目标
        检查, 仍可走原 install/restart/目标 push 流程.
      - ``skip_merge``: 仍 fetch/比较, 只跳 merge.
      - push 失败时令 aborted=True (确保本次目标安全错误 overall fail);
        既有非目标异常已阻断的总体结果仍按主控原 scope 外保留.
    """
    abs_path = (project_root / path).resolve()

    # dirty worktree check (apply only; dry-run never mutates; force_dirty
    # explicitly allows through).
    if dry_run or force_dirty:
        pass
    else:
        dirty = run_cmd(["git", "status", "--porcelain"], cwd=str(abs_path))
        if dirty.exit_code == 0 and dirty.stdout.strip():
            log_warn(f'submodule "{name}" 有 dirty worktree (--force-dirty 可放行)')
            return PipelineResult(
                name=name, config_source="heuristic", phases=[],
                overall="fail",
                abort_reason="dirty_worktree (use --force-dirty to override)",
            )

    # V2.1: load opt-in FIRST, then discover with override context so
    # explicit opt-in fields win without heuristic re-fighting them.
    override: Optional[dict] = None
    override_load_error: Optional[Exception] = None
    try:
        override = load_optin_override(abs_path)
    except ValueError as exc:
        # Explicit branch/upstream_branch illegal value; field-level error
        # cannot be swallowed by file-level warning.
        override_load_error = exc
    if override_load_error is not None:
        log_err(
            f'submodule "{name}" opt-in 分支字段非法: {override_load_error}'
        )
        return PipelineResult(
            name=name, config_source="opt-in-only", phases=[],
            overall="fail",
            abort_reason=str(override_load_error),
        )

    try:
        cfg = discover_submodule(
            name, path, project_root,
            override=override,
            resolve_source=not resume_after_merge,
        )
    except ValueError as exc:
        log_err(f'submodule "{name}" 目标发现失败: {exc}')
        return PipelineResult(
            name=name, config_source=cfg_source(override),
            phases=[],
            overall="fail",
            abort_reason=str(exc),
        )

    # merge opt-in AFTER discover so cfg.upstream_branch fallback (legacy
    # same-name) does not overwrite an explicit upstream_branch=.
    if override:
        cfg = merge_override(cfg, override)
    # V2.1 (T3R closeout): always log branch selection so the operator
    # sees source/target even on heuristic-only submodules (e.g. OctoBot
    # with no .update_submodules.yaml).  The log line is the canonical
    # visibility hook that DESIGN §3.9.7 calls out for both opt-in and
    # heuristic flows.
    log_info(
        f"submodule \"{name}\" branch selection: "
        f"target={cfg.branch} source={cfg.upstream_branch} "
        f"(config_source={cfg.config_source})"
    )

    # Target safety check — runs even in dry-run and resume, because all
    # modes need to validate the local target before any read/write.
    if not resume_after_merge:
        # In normal flow, validate target before fetch.
        try:
            _validate_target_branch(abs_path, cfg.branch)
        except ValueError as exc:
            log_err(f'submodule "{name}" 目标校验失败: {exc}')
            return PipelineResult(
                name=name, config_source=cfg.config_source, phases=[],
                overall="fail",
                abort_reason=str(exc),
            )
    else:
        # resume: still validate target (DESIGN §3.9.4) before install/push.
        try:
            _validate_target_branch(abs_path, cfg.branch)
        except ValueError as exc:
            log_err(f'submodule "{name}" 目标校验失败: {exc}')
            return PipelineResult(
                name=name, config_source=cfg.config_source, phases=[],
                overall="fail",
                abort_reason=str(exc),
            )

    state = SubmoduleState(
        config=cfg,
        abs_path=abs_path,
        pre_head=None,
    )

    # record pre_head for merge conflict recovery
    head_r = run_cmd(["git", "rev-parse", "HEAD"], cwd=str(abs_path))
    if head_r.exit_code == 0:
        state.pre_head = head_r.stdout.strip()

    phases: list[PhaseResult] = []
    aborted = False
    abort_reason: Optional[str] = None

    def _should_abort(phase_result: PhaseResult) -> bool:
        return phase_result.status == "fail"

    # Phase 1: fetch
    if resume_after_merge:
        phases.append(_make_skip("fetch", "resume_after_merge, skip"))
        # resume must not claim behind=0/latest — leave state.behind/ahead None.
    else:
        pr = phase_fetch(state, dry_run=dry_run)
        phases.append(pr)
        # V2.1 (T3R closeout): surface the fetch plan on plain CLI without
        # --verbose (DESIGN §3.9.1 / §3.9.5).  Re-use the existing log_info
        # so --no-audit & no-verbose still show cached/not-fetched and the
        # resolved git fetch upstream refs/heads/<source> plan.
        log_info(f'fetch {pr.status}: {pr.detail}')
        if _should_abort(pr):
            aborted = True
            abort_reason = pr.detail

    # Phase 2: merge
    if not aborted and not skip_merge and not resume_after_merge:
        pr = phase_merge(state, dry_run=dry_run)
        phases.append(pr)
        # V2.1 (T3R closeout): surface the merge plan on plain CLI without
        # --verbose (DESIGN §3.9.1 / §3.9.5).  Re-use the existing log_info
        # to reveal the resolved ``git merge [--ff-only] <commit>`` plan
        # even when behind=0 triggers a cached skip.
        log_info(f'merge {pr.status}: {pr.detail}')
        if _should_abort(pr):
            aborted = True
            abort_reason = pr.detail
    elif not aborted:
        phases.append(_make_skip("merge", "skip_merge or resume_after_merge"))

    # Phase 3: install
    if not aborted and not skip_install:
        pr = phase_install(state, dry_run=dry_run)
        phases.append(pr)
        if _should_abort(pr):
            aborted = True
            abort_reason = pr.detail
    elif not aborted:
        phases.append(_make_skip("install", "skip_install"))

    # Phase 4: restart
    if not aborted and not skip_restart:
        pr = phase_restart(state, dry_run=dry_run)
        phases.append(pr)
        if _should_abort(pr):
            aborted = True
            abort_reason = pr.detail
    elif not aborted:
        phases.append(_make_skip("restart", "skip_restart"))

    # Phase 5: push (only if --push and not aborted)
    #
    # V2.1 (T3R closeout): the target-safety check is unified at the
    # process boundary (DESIGN §3.9.4) — runs for both dry-run and
    # apply so a dry-run push plan never appears without a validated
    # local target.  When the safety check fails the push phase is
    # recorded as ``fail`` AND ``aborted`` flips to True, mirroring the
    # existing target-safety semantics for fetch/merge.  An ordinary
    # ``git push`` execution failure (handled by ``phase_push`` itself)
    # does NOT touch ``aborted``: only target-safety errors do, and
    # the historical push-aggregation behaviour is preserved as scope-
    # out residue.
    if do_push and not aborted:
        if cfg.skip_push:
            phases.append(_make_skip("push", "skip_push=true"))
        else:
            try:
                _validate_target_branch(abs_path, cfg.branch)
            except ValueError as exc:
                phases.append(_make_fail("push", f"目标校验失败: {exc}"))
                # V2.1 (T3R closeout): surface the push target check failure
                # on plain CLI without --verbose (DESIGN §3.9.1 / §3.9.4).
                log_info(f'push fail (目标校验): {exc}')
                aborted = True
                abort_reason = f"目标校验失败 (push 前): {exc}"
            else:
                pr = phase_push(state, dry_run=dry_run)
                phases.append(pr)
                # V2.1 (T3R closeout): surface the push plan on plain CLI
                # without --verbose (DESIGN §3.9.1 / §3.9.5).  Always re-use
                # the existing log_info so --no-audit & no-verbose still show
                # the resolved git push origin <branch> command or the error.
                log_info(f'push {pr.status}: {pr.detail}')
                # V2.1 (T3R closeout): preserve non-empty abort_reason from
                # ordinary ``git push`` execution failures without flipping
                # ``aborted`` to True.  The aggregation behaviour is the
                # scope-out residue explicitly preserved by DESIGN §3.9.4:
                # only target-safety errors escalate to overall=fail; an
                # ordinary push execution failure records abort_reason for
                # callers/diagnostics but keeps overall=pass.
                if pr.status == "fail" and not abort_reason:
                    abort_reason = pr.detail
    else:
        reason = "no --push" if not do_push else ("aborted" if aborted else "")
        phases.append(_make_skip("push", reason))

    overall = "fail" if aborted else "pass"
    return PipelineResult(
        name=name, config_source=cfg.config_source,
        phases=phases, overall=overall, abort_reason=abort_reason,
    )


def cfg_source(override: Optional[dict]) -> str:
    """Helper used by process_submodule when discover_submodule raises
    before merging; if any opt-in keys exist we declare opt-in-only so
    the audit reflects that load happened.
    """
    if override:
        return "opt-in-only"
    return "heuristic"


# ---------------------------------------------------------------------------
# --only filter
# ---------------------------------------------------------------------------


def filter_by_only(submodules: list[tuple[str, Path]],
                   only_names: list[str]) -> list[tuple[str, Path]]:
    """按 --only 过滤.
    匹配: section name 精确匹配 或 path basename 后缀匹配.
    下划线/连字符归一化匹配 (用户习惯用 - 但 path 用 _).
    缺名 -> exit 1 (不静默 fallback).
    """
    if not only_names:
        return submodules
    result: list[tuple[str, Path]] = []
    unmatched: list[str] = []
    for want in only_names:
        found = False
        want_norm = want.replace("-", "_").lower()
        for name, path in submodules:
            name_norm = name.replace("-", "_").lower()
            path_norm = str(path).replace("-", "_").lower()
            if name_norm == want_norm:
                result.append((name, path))
                found = True
                break
            # path basename suffix match (normalized)
            if path_norm.endswith(want_norm) or path.name.replace("-", "_").lower() == want_norm:
                result.append((name, path))
                found = True
                break
        if not found:
            unmatched.append(want)
    if unmatched:
        all_names = [n for n, _ in submodules]
        log_err(f"--only 未匹配: {unmatched}")
        log_err(f"  可用 submodule names: {all_names}")
        sys.exit(1)
    # dedupe
    seen: set[str] = set()
    deduped: list[tuple[str, Path]] = []
    for item in result:
        if item[0] not in seen:
            seen.add(item[0])
            deduped.append(item)
    return deduped


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def write_audit(results: list[PipelineResult], audit_path: Path,
                *, mode: str, push: bool, only: Optional[list[str]],
                skip_merge: bool, skip_install: bool, skip_restart: bool,
                fail_fast: bool) -> None:
    """Write Markdown audit log."""
    lines: list[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"# update_submodules audit {ts}")
    lines.append("")
    lines.append("## Config")
    lines.append(f"- mode: {mode}")
    lines.append(f"- push: {'enabled' if push else 'disabled'}")
    lines.append(f"- only: {only if only else 'null'}")
    lines.append(f"- skip_merge: {skip_merge}")
    lines.append(f"- skip_install: {skip_install}")
    lines.append(f"- skip_restart: {skip_restart}")
    lines.append(f"- fail_fast: {fail_fast}")
    lines.append("")
    lines.append("## Summary")
    lines.append("| submodule | config_source | fetch | merge | install | restart | push | result |")
    lines.append("|---|---|---|---|---|---|---|---|")

    def _phase_status(pr: PipelineResult, phase: str) -> str:
        for ph in pr.phases:
            if ph.phase == phase:
                return ph.status.upper()
        return "-"
    for r in results:
        lines.append(
            f"| {r.name} | {r.config_source} | "
            f"{_phase_status(r, 'fetch')} | {_phase_status(r, 'merge')} | "
            f"{_phase_status(r, 'install')} | {_phase_status(r, 'restart')} | "
            f"{_phase_status(r, 'push')} | {r.overall.upper()} |"
        )

    lines.append("")
    lines.append("## Details")
    lines.append("")
    for r in results:
        lines.append(f"### {r.name}")
        for ph in r.phases:
            lines.append(f"- Phase {ph.phase}: {ph.status} — {ph.detail}")
        if r.abort_reason:
            lines.append(f"- ABORT reason: {r.abort_reason}")
        lines.append("")

    audit_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="update_submodules.py",
        description="通用多 submodule 升级器 (RFC/SPEC/DESIGN-10-008 V2.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--only", action="append", default=[],
                        help="指定单 submodule (可重复); 支持 section name 或 path basename")
    parser.add_argument("--push", action="store_true",
                        help="推到 origin (默认不推)")
    parser.add_argument("--apply", action="store_true",
                        help="实际执行 (默认 dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="显式 dry-run (与不带 --apply 等价)")
    parser.add_argument("--skip-merge", action="store_true",
                        help="跳过 Phase 2 (merge)")
    parser.add_argument("--skip-install", action="store_true",
                        help="跳过 Phase 3 (install)")
    parser.add_argument("--skip-restart", action="store_true",
                        help="跳过 Phase 4 (restart)")
    parser.add_argument("--resume-after-merge", action="store_true",
                        help="跳过 Phase 1+2 (fetch+merge), 从 install 开始")
    parser.add_argument("--fail-fast", action="store_true",
                        help="任一 submodule 失败时立即停止")
    parser.add_argument("--force-dirty", action="store_true",
                        help="允许 dirty worktree (默认拒跑)")
    parser.add_argument("--verbose", action="store_true",
                        help="输出每条命令的 stdout/stderr")
    parser.add_argument("--no-audit", action="store_true",
                        help="不写审计日志文件")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(),
                        help="项目根目录 (默认 cwd)")
    parser.add_argument("--audit-dir", type=Path, default=Path("/tmp"),
                        help="审计日志目录 (默认 /tmp)")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 互斥检查: --apply 与 --dry-run
    if args.apply and args.dry_run:
        log_err("--apply 与 --dry-run 互斥")
        return 2
    # 互斥检查: --skip-merge 与 --resume-after-merge
    if args.skip_merge and args.resume_after_merge:
        log_err("--skip-merge 与 --resume-after-merge 互斥")
        return 2

    dry_run = not args.apply
    mode = "dry-run" if dry_run else "apply"

    project_root = args.repo_root.resolve()
    log_info(f"update_submodules.py v{__version__} | mode={mode} | push={args.push}")
    log_info(f"project_root={project_root}")

    # parse .gitmodules
    submodules = parse_gitmodules(project_root)
    if not submodules:
        log_warn(f".gitmodules 未找到 submodule 或文件不存在: {project_root}")
        return 0

    log_info(f"发现 {len(submodules)} 个 submodule: {[n for n, _ in submodules]}")

    # filter by --only
    selected = filter_by_only(submodules, args.only)
    log_info(f"处理 {len(selected)} 个 submodule")

    # serial process
    results: list[PipelineResult] = []
    for name, path in selected:
        log_info(f"--- {name} ({path}) ---")
        result = process_submodule(
            name, path, project_root,
            skip_merge=args.skip_merge,
            skip_install=args.skip_install,
            skip_restart=args.skip_restart,
            resume_after_merge=args.resume_after_merge,
            do_push=args.push,
            dry_run=dry_run,
            force_dirty=args.force_dirty,
            fail_fast=args.fail_fast,
        )
        results.append(result)
        if result.overall == "fail":
            log_err(f'{name}: FAIL — {result.abort_reason or "see phases above"}')
            if args.fail_fast:
                log_warn("--fail-fast, 停止后续 submodule")
                break
        else:
            log_ok(f"{name}: PASS")

    # audit log
    if not args.no_audit:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_path = args.audit_dir / f"update_submodules_audit_{ts}.md"
        write_audit(results, audit_path,
                    mode=mode, push=args.push,
                    only=args.only or None,
                    skip_merge=args.skip_merge,
                    skip_install=args.skip_install,
                    skip_restart=args.skip_restart,
                    fail_fast=args.fail_fast)
        log_info(f"audit log: {audit_path}")

    # summary
    n_pass = sum(1 for r in results if r.overall == "pass")
    n_fail = sum(1 for r in results if r.overall == "fail")
    log_info(f"Summary: {n_pass} PASS, {n_fail} FAIL (共 {len(results)})")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
