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

__version__ = "1.0.0"

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
    venv: Optional[Path]
    pip_install_cmd: Optional[tuple[str, ...]]
    pre_merge_hooks: tuple[str, ...]
    systemd_service: Optional[str]
    health_check: Optional[str]
    skip_push: bool
    notes: str
    config_source: str  # "heuristic" | "heuristic+opt-in" | "opt-in-only"


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
    behind: int
    ahead: int
    upstream_ref: str


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

    `git symbolic-ref --short refs/remotes/origin/HEAD` returns `origin/main`,
    not `refs/remotes/origin/main`.  Fetching upstream with the un-normalized
    value would run `git fetch upstream origin/main`, which fails because
    upstream has `main`, not `origin/main`.
    """
    ref = (ref or "").strip()
    if not ref:
        return None
    full_prefix = f"refs/remotes/{remote}/"
    short_prefix = f"{remote}/"
    if ref.startswith(full_prefix):
        ref = ref[len(full_prefix):]
    elif ref.startswith(short_prefix):
        ref = ref[len(short_prefix):]
    if not ref or ref == "HEAD" or ref.endswith("/HEAD"):
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


def discover_submodule(name: str, path: Path, project_root: Path) -> SubmoduleConfig:
    """启发式推断所有字段. cwd = project_root; git 命令用 -C <path>."""
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

    # branch
    branch = parse_origin_head(abs_path) or "main"

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
        branch=branch,
        venv=venv,
        pip_install_cmd=pip_install_cmd,
        pre_merge_hooks=(),
        systemd_service=systemd_service,
        health_check=None,  # V2.0 默认 None
        skip_push=False,
        notes="",
        config_source="heuristic",
    )


# ---------------------------------------------------------------------------
# opt-in override
# ---------------------------------------------------------------------------


def validate_override(raw: dict) -> Optional[dict]:
    """校验 .update_submodules.yaml schema (V2.0).
    返回 validated dict 或 None (schema 错误).
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

    out: dict[str, Any] = {}
    for key in ("origin", "upstream", "branch", "venv", "systemd_service",
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
    return out


def load_optin_override(submodule_path: Path) -> Optional[dict]:
    """加载 <submodule_path>/.update_submodules.yaml.
    不存在 -> None (常态).
    YAML 解析失败 -> warning + None (回落启发式).
    schema 校验失败 -> warning + None.
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
    """每个字段独立合并: override 中存在的字段覆盖 base, 未指定保留."""
    changes: dict[str, Any] = {}

    for field_name in ("origin", "upstream", "branch", "systemd_service",
                       "health_check", "notes"):
        if field_name in override:
            changes[field_name] = override[field_name]
            if override[field_name] is not None:
                changes[field_name] = override[field_name]

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
        "venv": changes.get("venv", base.venv),
        "pip_install_cmd": changes.get("pip_install_cmd", base.pip_install_cmd),
        "pre_merge_hooks": changes.get("pre_merge_hooks", base.pre_merge_hooks),
        "systemd_service": changes.get("systemd_service", base.systemd_service),
        "health_check": changes.get("health_check", base.health_check),
        "skip_push": changes.get("skip_push", base.skip_push),
        "notes": changes.get("notes", base.notes),
        "config_source": source,
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


def phase_fetch(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 1: fetch upstream.
    config.upstream is None -> ABORT.
    """
    cfg = state.config
    if cfg.upstream is None:
        return _make_fail("fetch",
                          f'upstream remote 缺失: submodule "{cfg.name}"; '
                          "请手动 git remote add upstream <url> "
                          f"或在 {cfg.path}/{OPTIN_FILENAME} 声明")
    if dry_run:
        # still try to compute behind/ahead for plan output
        ref = f"upstream/{cfg.branch}"
        state.upstream_ref = ref
        r = run_cmd(["git", "rev-list", "--left-right", "--count",
                     f"{ref}...HEAD"], cwd=str(state.abs_path))
        behind, ahead = _parse_rev_count(r.stdout)
        state.behind = behind
        state.ahead = ahead
        return _make_pass("fetch",
                          f"[dry-run] git fetch upstream {cfg.branch} "
                          f"(behind={behind}, ahead={ahead})")
    t0 = time.time()
    r = run_cmd(["git", "fetch", "upstream", cfg.branch],
                cwd=str(state.abs_path))
    dur = time.time() - t0
    if r.exit_code != 0:
        return _make_fail("fetch", f"git fetch 失败: {redact(r.stderr)[:300]}",
                          exit_code=r.exit_code, duration=dur)
    ref = f"upstream/{cfg.branch}"
    state.upstream_ref = ref
    r2 = run_cmd(["git", "rev-list", "--left-right", "--count",
                  f"{ref}...HEAD"], cwd=str(state.abs_path))
    behind, ahead = _parse_rev_count(r2.stdout)
    state.behind = behind
    state.ahead = ahead
    return _make_pass("fetch", f"behind={behind}, ahead={ahead}",
                      exit_code=0, duration=dur)


def _parse_rev_count(stdout: str) -> tuple[int, int]:
    """Parse 'N\\tM' -> (behind, ahead)."""
    parts = stdout.strip().split()
    if len(parts) >= 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return 0, 0


def phase_merge(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 2: merge upstream/<branch>."""
    cfg = state.config
    if state.behind == 0:
        return _make_skip("merge", "behind=0, skip (up-to-date)")
    if dry_run:
        mode = "--ff-only" if state.ahead == 0 else "merge"
        return _make_pass("merge", f"[dry-run] git {mode} {state.upstream_ref}")
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
        # conflict detection
        status = run_cmd(["git", "status", "--porcelain"],
                         cwd=str(state.abs_path))
        has_conflict = any(
            line.startswith(("UU", "AA", "DD", "AU", "UA", "DU", "UD"))
            for line in status.stdout.splitlines()
        )
        if has_conflict:
            run_cmd(["git", "merge", "--abort"], cwd=str(state.abs_path))
            return _make_fail("merge",
                              "merge 冲突, 已 git merge --abort; "
                              "手动解决后用 --resume-after-merge",
                              exit_code=r.exit_code, duration=dur)
        return _make_fail("merge", f"merge 失败: {redact(r.stderr)[:300]}",
                          exit_code=r.exit_code, duration=dur)
    return _make_pass("merge", f"merged {state.upstream_ref}",
                      exit_code=0, duration=dur)


def phase_install(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 3: pip install."""
    cfg = state.config
    if cfg.venv is None or cfg.pip_install_cmd is None:
        return _make_skip("install", "venv 或 pip_install 缺失, skip")
    pip_bin = state.abs_path / cfg.venv / "bin" / "pip"
    if not pip_bin.exists():
        return _make_skip("install", f"venv pip 不存在: {pip_bin}, skip")
    cmd = [str(pip_bin)] + list(cfg.pip_install_cmd)
    if dry_run:
        return _make_pass("install", f"[dry-run] {' '.join(cmd)}")
    t0 = time.time()
    r = run_cmd(cmd, cwd=str(state.abs_path))
    dur = time.time() - t0
    if r.exit_code != 0:
        return _make_fail("install", f"pip install 失败: {redact(r.stderr)[:300]}",
                          exit_code=r.exit_code, duration=dur)
    return _make_pass("install", "pip install OK", exit_code=0, duration=dur)


def phase_restart(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 4: restart + health_check (opt-in cmd 时)."""
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
        return _make_pass("restart", detail)
    t0 = time.time()
    r = run_cmd(restart_cmd, cwd=str(state.abs_path))
    dur = time.time() - t0
    if r.exit_code != 0:
        return _make_fail("restart",
                          f"systemctl restart 失败: {redact(r.stderr)[:300]}",
                          exit_code=r.exit_code, duration=dur)
    # health_check (V2.0: None = skip)
    if cfg.health_check is None:
        return _make_pass("restart", "restart OK, health_check SKIP (None)",
                          exit_code=0, duration=dur)
    # health_check is opt-in shell cmd
    time.sleep(5)
    hc = run_cmd(["sh", "-c", cfg.health_check], cwd=str(state.abs_path))
    dur2 = time.time() - t0
    if hc.exit_code != 0:
        return _make_fail("restart",
                          f"health check 失败: {redact(hc.stderr)[:300]}",
                          exit_code=hc.exit_code, duration=dur2)
    return _make_pass("restart", "restart + health_check OK",
                      exit_code=0, duration=dur2)


def phase_push(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 5: push origin <branch>. 永远不 --force."""
    cfg = state.config
    if cfg.skip_push:
        return _make_skip("push", "skip_push=true (opt-in)")
    if dry_run:
        return _make_pass("push", f"[dry-run] git push origin {cfg.branch}")
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
                      skip_restart: bool = False, resume_after_merge: bool = False,
                      do_push: bool = False, dry_run: bool = True,
                      force_dirty: bool = False,
                      fail_fast: bool = False) -> PipelineResult:
    """Process a single submodule through the 5-phase pipeline."""
    abs_path = (project_root / path).resolve()

    # discover
    cfg = discover_submodule(name, path, project_root)

    # opt-in override
    override = load_optin_override(abs_path)
    if override:
        cfg = merge_override(cfg, override)

    # dirty worktree check
    if dry_run or force_dirty:
        pass  # dry-run never mutates; force_dirty allows
    else:
        dirty = run_cmd(["git", "status", "--porcelain"], cwd=str(abs_path))
        if dirty.exit_code == 0 and dirty.stdout.strip():
            log_warn(f'submodule "{name}" 有 dirty worktree (--force-dirty 可放行)')
            return PipelineResult(
                name=name, config_source=cfg.config_source, phases=[],
                overall="fail",
                abort_reason="dirty_worktree (use --force-dirty to override)",
            )

    state = SubmoduleState(
        config=cfg, abs_path=abs_path, pre_head=None,
        behind=0, ahead=0, upstream_ref=f"upstream/{cfg.branch}",
    )

    # record pre_head for merge conflict recovery
    head_r = run_cmd(["git", "rev-parse", "HEAD"], cwd=str(abs_path))
    if head_r.exit_code == 0:
        state.pre_head = head_r.stdout.strip()

    phases: list[PhaseResult] = []
    aborted = False
    abort_reason: Optional[str] = None

    def _should_abort(phase_result: PhaseResult) -> bool:
        """Return True if this phase result should abort subsequent phases."""
        return phase_result.status == "fail"

    # Phase 1: fetch
    if resume_after_merge:
        phases.append(_make_skip("fetch", "resume_after_merge, skip"))
    else:
        pr = phase_fetch(state, dry_run=dry_run)
        phases.append(pr)
        if _should_abort(pr):
            aborted = True
            abort_reason = pr.detail

    # Phase 2: merge
    if not aborted and not skip_merge and not resume_after_merge:
        pr = phase_merge(state, dry_run=dry_run)
        phases.append(pr)
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
    if do_push and not aborted:
        if not cfg.skip_push:
            pr = phase_push(state, dry_run=dry_run)
            phases.append(pr)
            if _should_abort(pr):
                abort_reason = pr.detail
        else:
            phases.append(_make_skip("push", "skip_push=true"))
    else:
        reason = "no --push" if not do_push else ("aborted" if aborted else "")
        phases.append(_make_skip("push", reason))

    overall = "fail" if aborted else "pass"
    return PipelineResult(
        name=name, config_source=cfg.config_source,
        phases=phases, overall=overall, abort_reason=abort_reason,
    )


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
