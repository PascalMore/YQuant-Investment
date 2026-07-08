#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Agent 自动升级脚本 (RFC-10-005 / SPEC-10-005 / DESIGN-10-005)

Pascal fork 的 Hermes Agent 源码升级编排器。默认从 upstream/main 升级本地
checkout (/home/pascal/workspace/hermes-agent)，在本地安装与验证成功后才
push 到 Pascal fork 的 origin/main。

核心策略：
  - Git: ff 优先；本地有自有 commit 时采用 A+ merge（保护后 merge upstream）。
  - 备份: manifest + zip 工作树 + git stash + pre_head 四重锚点。
  - 安装: uv editable install -> pip editable install。
  - Gateway restart: detached helper，避免同步自杀。
  - dry-run: 完整计划模式，不修改任何状态。

标准库实现，不引入第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

__version__ = "1.0.0"

DEFAULT_REPO = "/home/pascal/workspace/hermes-agent"
DEFAULT_HERMES_BIN = "/home/pascal/.local/bin/hermes"
DEFAULT_BACKUP_DIR = "/tmp"
DEFAULT_VERSION_REF = "upstream/main"
MANIFEST_SCHEMA_VERSION = "1"
GATEWAY_HEALTH_TIMEOUT = 90  # seconds


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpgradeConfig:
    repo: Path
    version_ref: str
    backup_dir: Path
    dry_run: bool
    restart: bool
    push: bool
    rollback_manifest: Optional[Path]
    yes: bool
    verbose: bool
    hermes_bin: Path = Path(DEFAULT_HERMES_BIN)
    # V2 增量字段（DESIGN-10-006 §3.2 / SPEC-10-006 §4.2）：
    # 默认值与 V1.0 行为完全等价。
    branch: str = "main"
    preserve_features: bool = False
    patches_manifest: Optional[Path] = None


@dataclass
class CommandResult:
    cmd: list
    cwd: Optional[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class RepoState:
    repo: Path
    branch: str
    pre_head: str
    origin_url: str
    upstream_url: str
    install_method: str
    dirty_files: list
    local_only_commits: list
    origin_main_sha: Optional[str]


@dataclass
class GitPlan:
    target_ref: str
    target_sha: str
    merge_mode: str  # already-up-to-date | ff-only | merge
    local_commits_need_protection: bool
    diverged: bool = False


# ---------------------------------------------------------------------------
# V2 patch manifest 数据结构（DESIGN-10-006 §3.2 / SPEC-10-006 §4.4）
# ---------------------------------------------------------------------------


# V2 默认 schema_version；V1 schema_version=1 仍可读。
PATCH_MANIFEST_SCHEMA_VERSION_CURRENT = 2


@dataclass(frozen=True)
class PatchEntry:
    id: str
    title: str
    commit: str
    branch: str
    upstream_pr: Optional[str]
    upstream_merged: bool
    file_globs: list
    notes: str = ""


@dataclass
class PatchesManifest:
    schema_version: int
    patches: list  # list[PatchEntry]


@dataclass
class PatchStatus:
    id: str
    upstream_merged_manifest: bool
    upstream_contains_commit: bool
    upstream_contains_patch_id: bool
    status: str  # merged | possibly-merged | pending | unknown
    reason: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class UpgradeError(Exception):
    """升级流程中预期失败，携带 stage / next_steps 上下文。"""

    def __init__(self, stage: str, message: str, next_steps: Optional[list] = None,
                 exit_code: int = 1):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.next_steps = next_steps or []
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log(msg: str, *, verbose: bool = False, force: bool = False) -> None:
    if verbose or force:
        print(msg, flush=True)


def log_info(msg: str, cfg: Optional[UpgradeConfig] = None) -> None:
    v = cfg.verbose if cfg else False
    print(f"[INFO] {msg}", flush=True)


def log_warn(msg: str) -> None:
    print(f"[WARN] {msg}", flush=True, file=sys.stderr)


def log_ok(msg: str) -> None:
    print(f"[OK]   {msg}", flush=True)


def log_err(msg: str) -> None:
    print(f"[ERR]  {msg}", flush=True, file=sys.stderr)


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# token-like / secret-like patterns to redact from logged output.
_SECRET_PATTERNS = [
    re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,})"),
    re.compile(r"(glpat-[A-Za-z0-9_-]{15,})"),
    re.compile(r"(xox[bpoa]-[A-Za-z0-9-]{10,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(token[=:]\s*)([A-Za-z0-9_\-/+=]{16,})", re.IGNORECASE),
    re.compile(r"(api[_-]?key[=:]\s*)([A-Za-z0-9_\-/+=]{16,})", re.IGNORECASE),
    re.compile(r"(password[=:]\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END[^-]+-----)"),
    # long hex / base64 blobs that look like tokens (>=32 chars)
    re.compile(r"\b([A-Za-z0-9+/=_-]{40,})\b"),
]

_ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _redact_env_value(value: str) -> str:
    """If a value looks like an .env secret value, mask it."""
    if any(s in value.lower() for s in ("token", "key", "secret", "password")):
        if len(value) > 3:
            return value[:2] + "***REDACTED***"
    return value


def redact(text: str) -> str:
    """对输出做保守脱敏：token-like、.env 值、私钥块。"""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        def _sub(m: re.Match) -> str:
            groups = m.groups()
            if len(groups) >= 2:
                # token=VALUE style: keep prefix, mask value
                return f"{groups[0]}***REDACTED***"
            return "***REDACTED***"
        out = pat.sub(_sub, out)
    return out


def redact_command(cmd: list) -> list:
    """对命令参数列表做脱敏（主要针对可能出现的 token 参数）。"""
    return [redact(str(c)) for c in cmd]


# ---------------------------------------------------------------------------
# Command wrapper
# ---------------------------------------------------------------------------


def run_cmd(cmd: list, *, cwd: Optional[str] = None, check: bool = False,
            capture: bool = True, env: Optional[dict] = None,
            manifest: Optional[list] = None,
            verbose: bool = False, timeout: Optional[int] = None) -> CommandResult:
    """统一执行外部命令。禁止 shell=True。记录 cmd/cwd/exit_code/stdout/stderr 摘要。

    若 manifest 列表提供，追加一条脱敏后的命令摘要。
    """
    cmd_str_parts = redact_command(cmd)
    cwd_display = str(cwd) if cwd else os.getcwd()
    log(f"$ {' '.join(cmd_str_parts)}  (cwd={cwd_display})", verbose=verbose)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        result = CommandResult(cmd=list(cmd), cwd=cwd, exit_code=127,
                               stdout="", stderr=str(exc))
        _record_command(manifest, result, verbose)
        if check:
            raise UpgradeError("command", f"命令不存在: {exc}") from exc
        return result
    except subprocess.TimeoutExpired as exc:
        result = CommandResult(cmd=list(cmd), cwd=cwd, exit_code=124,
                               stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                               stderr=f"timeout after {timeout}s")
        _record_command(manifest, result, verbose)
        if check:
            raise UpgradeError("command", f"命令超时: {exc}") from exc
        return result

    result = CommandResult(
        cmd=list(cmd), cwd=cwd, exit_code=proc.returncode,
        stdout=proc.stdout or "", stderr=proc.stderr or "",
    )
    _record_command(manifest, result, verbose)

    if check and proc.returncode != 0:
        raise UpgradeError(
            "command",
            f"命令失败 (exit={proc.returncode}): {' '.join(cmd_str_parts)}",
            next_steps=[f"stderr: {redact(result.stderr)[:500]}"],
        )
    return result


def _record_command(manifest: Optional[list], result: CommandResult, verbose: bool) -> None:
    if manifest is None:
        return
    tail = 600
    entry = {
        "cmd": redact_command(result.cmd),
        "cwd": result.cwd,
        "exit_code": result.exit_code,
        "stdout_tail": redact(result.stdout)[-tail:] if result.stdout else "",
        "stderr_tail": redact(result.stderr)[-tail:] if result.stderr else "",
    }
    manifest.append(entry)
    if verbose and (result.stdout or result.stderr):
        if result.stdout:
            log(f"  stdout: {redact(result.stdout)[:300]}", verbose=True)
        if result.stderr:
            log(f"  stderr: {redact(result.stderr)[:300]}", verbose=True)


# ---------------------------------------------------------------------------
# V2 patch manifest 读取与核对（DESIGN-10-006 §3.6-§3.7 / SPEC-10-006 §5.3）
# ---------------------------------------------------------------------------


def _load_yaml_subset(path: Path) -> dict:
    """读取 YAML，优先用 optional PyYAML，不可用时用受控 stdlib fallback。

    fallback 只支持 Pascal fork 私有 patch manifest 的最小子集：
      - 顶层 schema_version (int / 数字字符串)
      - 顶层 patches (list)
      - 每个 patch 的 id/title/commit/branch/upstream_pr/upstream_merged/file_globs/notes
    解析失败返回空 dict，由调用方以 warning 处理。
    """
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore  # optional, no new dependency
        try:
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                return {}
            return data
        except Exception:
            pass  # fallback below
    except Exception:
        pass
    # stdlib fallback —— 只解析本 manifest 实际使用的子集。
    return _parse_simple_patches_yaml(text)


def _parse_simple_patches_yaml(text: str) -> dict:
    """受限 YAML 子集 parser，只支持本项目 manifest 中出现的结构。

    限制：
      - 2 层嵌套：顶层 key + patches list 项（每个 item 是 mapping）
      - list item 下允许 1 层子列表（file_globs 等）
      - 字符串值支持双引号/无引号；空值 = null
      - 不支持 multiline / anchors / 3 层及以上嵌套
    解析失败返回空 dict。
    """
    out: dict = {}

    def _strip_val(v: str):
        v = v.strip()
        if not v:
            return None
        if (v.startswith('"') and v.endswith('"')) or (
            v.startswith("'") and v.endswith("'")
        ):
            return v[1:-1]
        if v.lower() in ("true", "yes"):
            return True
        if v.lower() in ("false", "no"):
            return False
        if v.lower() in ("null", "~"):
            return None
        return v

    # 状态机：
    #   "top"           —— 顶层；等待 top-level key
    #   ("list", key,
    #     indent,        —— 当前 list 项 "key:" 的缩进（决定子列表起点缩进）
    #     items)         —— 已收集的 list 项（dict 列表）
    # 在 list 状态下：
    #   - 同缩进的 "- key: value" → 新 list item（新 dict，先写入第一个 key）
    #   - 同缩进的 "- value" → 父级 key 的子列表元素（需先找到父 key）
    #   - 父缩进的 "key: value" → 写入当前最后一个 dict item
    #   - 父缩进的 "key:" (空值) → 准备进入子列表，下一个 "- value" 归属这个 key
    state = "top"
    list_key = None
    list_indent = 0
    items: list = []
    cur_item: Optional[dict] = None
    cur_child_key: Optional[str] = None
    cur_child_indent = 0

    def _flush_list():
        nonlocal list_key, list_indent, items, cur_item, cur_child_key, cur_child_indent
        if list_key is not None:
            out[list_key] = items
        list_key = None
        list_indent = 0
        items = []
        cur_item = None
        cur_child_key = None
        cur_child_indent = 0

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
                    # 可能进入 list（由下一行是否 "- " 决定）
                    out[key] = None
                    state = "expect_list"
                    list_key = key
                    list_indent = 0
                    items = []
                    cur_item = None
                    cur_child_key = None
                else:
                    out[key] = _strip_val(val)
        elif state == "expect_list":
            # 紧跟 "key:" 的下一行；如果是 "- "，进入 list
            if stripped.startswith("- "):
                state = "in_list"
                # 新 list item
                item_inline = stripped[2:].strip()
                cur_item = {}
                if ":" in item_inline:
                    k, _, v = item_inline.partition(":")
                    cur_item[k.strip()] = _strip_val(v)
                # else: 形如 "- value" 的 list item 顶层 entry（manifest 不支持）
                list_indent = indent
                cur_child_key = None
                cur_child_indent = 0
                items.append(cur_item)
            elif indent == 0 and ":" in stripped:
                # list 没起来；回到 top
                _flush_list()
                state = "top"
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    out[key] = None
                    state = "expect_list"
                else:
                    out[key] = _strip_val(val)
        elif state == "in_list":
            if indent == 0:
                # 新顶层 key —— 收尾当前 list
                _flush_list()
                state = "top"
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    out[key] = None
                    state = "expect_list"
                else:
                    out[key] = _strip_val(val)
            elif stripped.startswith("- "):
                # 子列表元素 vs 新 list item，靠 indent 判断
                # 新 list item 的 indent == list_indent；子列表元素 indent > list_indent
                if indent == list_indent and cur_child_key is None:
                    # 同 indent 再次 "- "，说明上一项已结束；新 list item
                    item_inline = stripped[2:].strip()
                    cur_item = {}
                    if ":" in item_inline:
                        k, _, v = item_inline.partition(":")
                        cur_item[k.strip()] = _strip_val(v)
                    cur_child_key = None
                    cur_child_indent = 0
                    items.append(cur_item)
                elif cur_item is not None and cur_child_key is not None:
                    # 子列表元素：归属 cur_child_key 列表
                    value = stripped[2:].strip()
                    existing = cur_item.get(cur_child_key)
                    if isinstance(existing, list):
                        existing.append(_strip_val(value))
                    elif existing is None:
                        cur_item[cur_child_key] = [_strip_val(value)]
                    else:
                        # 已有非 list 值，合并成 list
                        cur_item[cur_child_key] = [existing, _strip_val(value)]
                else:
                    # 既没有当前 item 也没有 child key —— 忽略
                    continue
            elif ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    # 空值：进入子列表模式
                    cur_child_key = key
                    cur_child_indent = indent
                    if cur_item is not None:
                        cur_item[key] = None
                else:
                    # 写入当前 item
                    if cur_item is not None:
                        cur_item[key] = _strip_val(val)
                        cur_child_key = None

    _flush_list()

    if "patches" in out and not isinstance(out["patches"], list):
        out["patches"] = []
    if "patches" not in out:
        out["patches"] = []
    return out


def load_patches_manifest(path: Path):
    """从 path 读取 patches manifest。

    返回 PatchesManifest；解析失败抛 ValueError，由调用方用 safe wrapper 处理。
    """
    raw = _load_yaml_subset(path)
    if not raw:
        raise ValueError("patches manifest 解析为空或失败")
    schema_raw = raw.get("schema_version", 1)
    try:
        schema = int(schema_raw)
    except (TypeError, ValueError):
        schema = 1
    entries = []
    for item in (raw.get("patches") or []):
        if not isinstance(item, dict):
            continue
        globs = item.get("file_globs") or []
        if isinstance(globs, str):
            globs = [globs]
        elif not isinstance(globs, list):
            globs = []
        try:
            entry = PatchEntry(
                id=str(item.get("id") or "").strip(),
                title=str(item.get("title") or "").strip(),
                commit=str(item.get("commit") or "").strip(),
                branch=str(item.get("branch") or "").strip(),
                upstream_pr=item.get("upstream_pr"),
                upstream_merged=bool(item.get("upstream_merged")),
                file_globs=[str(g) for g in globs],
                notes=str(item.get("notes") or ""),
            )
        except Exception as exc:
            # field-level failure → skip this entry with warning
            log_warn(f"patches manifest: 跳过非法条目 ({exc})")
            continue
        if not entry.id:
            continue
        entries.append(entry)
    return PatchesManifest(schema_version=schema, patches=entries)


def load_patches_manifest_safe(path):
    """safe wrapper：缺失/解析失败返回 None + warning。"""
    if path is None:
        return None
    if not path.exists():
        log_warn(f"patches manifest 不存在，跳过核对: {path}")
        return None
    try:
        return load_patches_manifest(path)
    except Exception as exc:
        log_warn(f"patches manifest 解析失败，跳过核对 ({exc.__class__.__name__}: {exc})")
        return None


def verify_patches_against_upstream(repo: Path, manifest_obj, upstream_ref: str,
                                    *, cmd_manifest=None, verbose: bool = False):
    """对每个 patch 做 best-effort upstream 包含性核对。

    判定规则（SPEC-10-006 §4.4）：
      - manifest 已标 upstream_merged → status='merged'
      - commit 在 upstream 可达 → status='merged'
      - 其他情况 best-effort（pending/unknown）

    本函数不修改 manifest 文件；只读取。失败不抛异常。
    """
    cmd_log = cmd_manifest if cmd_manifest is not None else []
    results = []
    for p in manifest_obj.patches:
        merged_manifest = bool(p.upstream_merged)
        contains_commit = False
        # commit reachability 检查 — 命令失败时当作 unknown
        if p.commit:
            r = git(
                ["merge-base", "--is-ancestor", p.commit, upstream_ref],
                repo=repo, manifest=cmd_log, verbose=verbose,
            )
            contains_commit = (r.exit_code == 0)

        if merged_manifest:
            status = "merged"
            reason = "manifest 已标 upstream_merged=true（脚本不复核）"
        elif contains_commit:
            status = "merged"
            reason = f"commit {p.commit} 在 {upstream_ref} 可达"
        else:
            # patch-id / file diff 留为后续增强；T2 先输出 pending。
            status = "pending"
            reason = (
                f"commit {p.commit} 未在 {upstream_ref} 可达；"
                "patch-id/file-diff 核对为后续增强，当前不判定"
            )

        # best-effort: 若 file_globs 在当前 repo 不存在任何一项，给 status 加 weak hint
        # 但不替换主 status，避免虚报 merged。
        if p.file_globs:
            missing = []
            for glob in p.file_globs:
                rr = git(
                    ["ls-files", "--error-unmatch", "--", glob],
                    repo=repo, manifest=cmd_log, verbose=verbose,
                )
                if rr.exit_code != 0:
                    missing.append(glob)
            if missing and not merged_manifest and not contains_commit:
                # 在不破坏主 status 的前提下，附 file_globs 缺失信息进 reason
                reason += f"；file_globs 不可读: {missing}"

        results.append(PatchStatus(
            id=p.id,
            upstream_merged_manifest=merged_manifest,
            upstream_contains_commit=contains_commit,
            upstream_contains_patch_id=False,
            status=status,
            reason=reason,
        ))
    return results


def print_patch_statuses(statuses) -> None:
    """输出补丁核对报告（stdout）。"""
    if not statuses:
        print("[patches] 无条目可核对")
        return
    for s in statuses:
        mark = "✓" if s.status == "merged" else (
            "~" if s.status == "possibly-merged" else "?"
        )
        print(f"  [{mark}] {s.id}: {s.status} — {s.reason}")


def run_patch_manifest_check_if_requested(config: UpgradeConfig, manifest: dict,
                                          upstream_ref: str) -> None:
    """如果 config.patches_manifest 提供，则做核对并把结果写入 manifest['patch_statuses']。

    不修改 patches manifest 文件本身（SPEC-10-006 §5.3-#5）。
    """
    pm = load_patches_manifest_safe(config.patches_manifest)
    if not pm:
        manifest["patch_statuses"] = []
        manifest["patches_check_status"] = "skipped"
        return
    statuses = verify_patches_against_upstream(
        config.repo, pm, upstream_ref,
        cmd_manifest=manifest.setdefault("commands", []),
        verbose=config.verbose,
    )
    # 序列化为 dict；不依赖 dataclasses.asdict 以减少依赖。
    manifest["patch_statuses"] = [
        {
            "id": s.id,
            "upstream_merged_manifest": s.upstream_merged_manifest,
            "upstream_contains_commit": s.upstream_contains_commit,
            "upstream_contains_patch_id": s.upstream_contains_patch_id,
            "status": s.status,
            "reason": s.reason,
        }
        for s in statuses
    ]
    manifest["patches_check_status"] = "ok"
    print_patch_statuses(statuses)


def preserve_feature_branch_if_requested(config: UpgradeConfig, state: RepoState,
                                        manifest: dict) -> None:
    """S0.5（仅在 --preserve-features 启用时执行）。

    行为契约（DESIGN-10-006 §3.5 / SPEC-10-006 §5.2）：
      - detached HEAD → warning + 跳过
      - origin 缺失 → warning + 跳过
      - dry-run → 输出计划，但不实际 push
      - real-run → `git push -u origin <branch>`；失败 warning + next steps，不做 destructive 操作

    不得 force push。当前 branch = main 时也允许执行（Pascal 自己决定是否重复 push）。
    """
    if not config.preserve_features:
        return
    branch = state.branch or ""
    if not branch:
        log_warn("--preserve-features: detached HEAD，跳过 feature branch push。")
        manifest["preserve_features_status"] = "skipped-detached-head"
        manifest["preserve_features_branch"] = None
        return

    # 检查 origin remote 是否存在（best-effort）
    r_remote = git(["remote", "get-url", "origin"], repo=config.repo,
                   manifest=manifest.setdefault("commands", []),
                   verbose=config.verbose)
    if r_remote.exit_code != 0:
        log_warn("--preserve-features: 缺少 origin remote，跳过 feature push。")
        manifest["preserve_features_status"] = "skipped-missing-origin"
        manifest["preserve_features_branch"] = branch
        return

    manifest["preserve_features_branch"] = branch

    if config.dry_run:
        print(f"  [S0.5 dry-run] 将执行: git -C {config.repo} push -u origin {branch}")
        manifest["preserve_features_status"] = "planned-dry-run"
        return

    log_info(f"--preserve-features: push 当前 branch '{branch}' 到 origin ...",
             config)
    r = git(["push", "-u", "origin", branch], repo=config.repo,
            manifest=manifest.setdefault("commands", []),
            verbose=config.verbose, timeout=120)
    if r.exit_code == 0:
        manifest["preserve_features_status"] = "ok"
        log_ok(f"feature branch '{branch}' 已 push 到 origin。")
    else:
        # 不做 destructive 操作；记录 next steps
        log_warn(f"--preserve-features: git push -u origin {branch} 失败，继续但请人工确认。")
        manifest["preserve_features_status"] = "warn-push-failed"
        manifest["preserve_features_error"] = redact(r.stderr)[:300]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def git(cmd: list, *, repo: Path, manifest: Optional[list] = None,
        check: bool = False, verbose: bool = False,
        env: Optional[dict] = None, timeout: Optional[int] = None) -> CommandResult:
    full = ["git", "-C", str(repo)] + cmd
    return run_cmd(full, cwd=str(repo), check=check, manifest=manifest,
                   env=env, verbose=verbose, timeout=timeout)


def git_out(cmd: list, *, repo: Path, manifest: Optional[list] = None,
            verbose: bool = False, timeout: Optional[int] = None) -> str:
    """Run git and return stripped stdout. Raises UpgradeError on failure."""
    r = git(cmd, repo=repo, manifest=manifest, verbose=verbose, timeout=timeout)
    if r.exit_code != 0:
        raise UpgradeError(
            "git",
            f"git {' '.join(cmd)} 失败 (exit={r.exit_code})",
            next_steps=[redact(r.stderr)[:300]] if r.stderr else [],
        )
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# Timestamp / path helpers
# ---------------------------------------------------------------------------


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def manifest_path(backup_dir: Path) -> Path:
    return Path(backup_dir) / f"hermes-upgrade-{_timestamp()}.json"


def backup_zip_path(backup_dir: Path) -> Path:
    return Path(backup_dir) / f"hermes-backup-{_timestamp()}.zip"


def restart_log_path(backup_dir: Path) -> Path:
    return Path(backup_dir) / f"hermes-upgrade-restart-{_timestamp()}.log"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def init_manifest(config: UpgradeConfig) -> dict:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": _utc_now_iso(),
        "repo": str(config.repo),
        "pre_branch": None,
        "pre_head": None,
        "origin_url": None,
        "upstream_url": None,
        "target_ref": config.version_ref,
        "target_sha": None,
        "backup_zip": None,
        "backup_size_bytes": None,
        "stash_ref": None,
        "dirty_files": [],
        "local_only_commits": [],
        "merge_mode": None,
        "post_head": None,
        "install_status": "pending",
        "verify_status": "pending",
        "restart_status": "pending",
        "push_status": "pending",
        "restart_log": None,
        "commands": [],
        "errors": [],
    }


def write_manifest(manifest: dict, path: Optional[Path]) -> None:
    """原子写入 manifest 到 path（先写临时文件，再 replace）。path 为 None 时不写。"""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise UpgradeError(
            "rollback",
            f"manifest schema_version 不匹配: {data.get('schema_version')} != {MANIFEST_SCHEMA_VERSION}",
        )
    return data


def add_manifest_error(manifest: dict, stage: str, code: str, message: str,
                       next_steps: Optional[list] = None) -> None:
    manifest.setdefault("errors", []).append({
        "stage": stage,
        "code": code,
        "message": message,
        "next_steps": next_steps or [],
    })


# ---------------------------------------------------------------------------
# Repo inspection
# ---------------------------------------------------------------------------


def detect_install_method(repo: Path, manifest: Optional[list] = None,
                          verbose: bool = False) -> str:
    """读取 .install_method；fallback 检测 .git。"""
    im_file = repo / ".install_method"
    if im_file.exists():
        try:
            val = im_file.read_text(encoding="utf-8").strip()
            if val:
                return val
        except OSError:
            pass
    if (repo / ".git").exists():
        return "git"
    return "unknown"


def inspect_repo(config: UpgradeConfig, manifest: dict) -> RepoState:
    """S0 inspect: 校验 git repo、remotes、branch、install_method、HEAD、dirty、local-only。"""
    repo = config.repo
    cmd_log = manifest.setdefault("commands", [])
    if not (repo / ".git").exists() and not repo.is_dir():
        raise UpgradeError("inspect", f"repo 不存在或非 git repo: {repo}",
                           exit_code=1)
    if not (repo / ".git").exists():
        raise UpgradeError("inspect", f"repo 不是 git 仓库: {repo}", exit_code=1)

    branch = git_out(["branch", "--show-current"], repo=repo, manifest=cmd_log,
                     verbose=config.verbose)
    # V2 §3.4：允许通过 config.branch 覆盖默认 main-only 检查。
    allowed_branch = config.branch
    if branch != allowed_branch:
        raise UpgradeError(
            "inspect",
            f"当前分支为 '{branch}'，本次允许分支为 '{allowed_branch}'。",
            next_steps=[
                f"如需在当前分支执行检查: --branch {branch}",
                f"如需默认升级，先 git -C {repo} checkout {allowed_branch}",
            ],
        )

    pre_head = git_out(["rev-parse", "HEAD"], repo=repo, manifest=cmd_log,
                       verbose=config.verbose)

    # remotes
    origin_url = ""
    upstream_url = ""
    r = git(["remote", "get-url", "origin"], repo=repo, manifest=cmd_log,
            verbose=config.verbose)
    if r.exit_code != 0:
        raise UpgradeError("inspect", "缺少 origin remote",
                           next_steps=[f"git -C {repo} remote add origin <fork-url>"])
    origin_url = r.stdout.strip()
    r = git(["remote", "get-url", "upstream"], repo=repo, manifest=cmd_log,
            verbose=config.verbose)
    if r.exit_code != 0:
        raise UpgradeError("inspect", "缺少 upstream remote",
                           next_steps=[f"git -C {repo} remote add upstream <official-url>"])
    upstream_url = r.stdout.strip()

    # dirty tree
    r = git(["status", "--porcelain=v1"], repo=repo, manifest=cmd_log,
            verbose=config.verbose)
    if r.exit_code != 0:
        raise UpgradeError("inspect", "无法读取 git status", exit_code=1)
    dirty_files = [line[3:].strip() for line in r.stdout.splitlines() if line.strip()]

    # origin/main sha (may be None if not fetched yet)
    r = git(["rev-parse", "--verify", "-q", "origin/main"], repo=repo,
            manifest=cmd_log, verbose=config.verbose)
    origin_main_sha = r.stdout.strip() if r.exit_code == 0 and r.stdout.strip() else None

    install_method = detect_install_method(repo, manifest=cmd_log, verbose=config.verbose)
    if install_method not in ("git",):
        raise UpgradeError(
            "inspect",
            f"install_method='{install_method}'，本脚本只支持 git 源码安装。",
            next_steps=["确保目标 repo 是 git checkout 安装。"],
        )

    # local-only commits vs upstream/main (best-effort, may be empty if not fetched)
    local_only = []
    r = git(["rev-list", "--count", "upstream/main..HEAD"], repo=repo,
            manifest=cmd_log, verbose=config.verbose)
    if r.exit_code == 0:
        try:
            n = int(r.stdout.strip())
        except ValueError:
            n = 0
        if n > 0:
            r2 = git(["log", "--oneline", "-n", "50", "upstream/main..HEAD"],
                     repo=repo, manifest=cmd_log, verbose=config.verbose)
            local_only = [line.strip() for line in r2.stdout.splitlines() if line.strip()]

    state = RepoState(
        repo=repo, branch=branch, pre_head=pre_head,
        origin_url=origin_url, upstream_url=upstream_url,
        install_method=install_method, dirty_files=dirty_files,
        local_only_commits=local_only, origin_main_sha=origin_main_sha,
    )

    # update manifest
    manifest["pre_branch"] = branch
    manifest["pre_head"] = pre_head
    manifest["origin_url"] = origin_url
    manifest["upstream_url"] = upstream_url
    manifest["install_method"] = install_method
    manifest["dirty_files"] = dirty_files
    manifest["local_only_commits"] = local_only
    return state


# ---------------------------------------------------------------------------
# Zip backup
# ---------------------------------------------------------------------------

ZIP_EXCLUDE_DIRS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "node_modules", "venv", ".venv", "dist", "build", ".eggs",
}
ZIP_EXCLUDE_PATTERNS = [
    re.compile(r"(^|/)\.git/objects/"),
    re.compile(r"(^|/)\.git/refs/"),
    re.compile(r"(^|/)\.git/logs/"),
    re.compile(r"(^|/)\.git/.*\.lock$"),
    re.compile(r"(^|/)venv/"),
    re.compile(r"(^|/)\.venv/"),
    re.compile(r"(^|/)node_modules/"),
    re.compile(r"(^|/)__pycache__/"),
    re.compile(r"\.pyc$"),
    re.compile(r"(^|/)\.pytest_cache/"),
    re.compile(r"(^|/)\.ruff_cache/"),
    re.compile(r"(^|/)\.mypy_cache/"),
    re.compile(r"(^|/)web/node_modules/"),
    re.compile(r"(^|/)apps/[^/]+/node_modules/"),
    re.compile(r"(^|/)apps/[^/]+/dist/"),
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)auth\.json$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"\.token$"),
    re.compile(r"(^|/)\.DS_Store$"),
    re.compile(r"(^|/)Thumbs\.db$"),
]


def _should_exclude_zip(rel: str) -> bool:
    for pat in ZIP_EXCLUDE_PATTERNS:
        if pat.search(rel):
            return True
    return False


def create_zip_backup(repo: Path, zip_path: Path, manifest: dict,
                      verbose: bool = False) -> Path:
    """按 include/exclude 规则创建 zip。zip 路径成员使用相对路径。"""
    repo = repo.resolve()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(repo):
            # prune excluded dirs in-place
            dirs[:] = [d for d in dirs if d not in ZIP_EXCLUDE_DIRS
                       and d != ".git"]
            # keep .install_method and top-level config even though .git pruned
            for fname in files:
                fpath = Path(root) / fname
                try:
                    rel = fpath.resolve().relative_to(repo).as_posix()
                except ValueError:
                    continue
                if _should_exclude_zip(rel):
                    continue
                # confirm still within repo after resolve
                try:
                    if not str(fpath.resolve()).startswith(str(repo)):
                        continue
                except OSError:
                    continue
                # skip symlinks (avoid escaping repo)
                if fpath.is_symlink():
                    continue
                try:
                    zf.write(fpath, arcname=rel)
                    count += 1
                    total += fpath.stat().st_size
                except (OSError, PermissionError) as exc:
                    # SPEC F-004: 备份失败必须停止。普通文件读/写失败不能
                    # 静默跳过 — 若要跳过必须显式列入 ZIP_EXCLUDE_PATTERNS。
                    add_manifest_error(manifest, "backup", "zip_write_failed",
                                       f"无法写入 zip 成员 {rel}: {exc}",
                                       next_steps=[f"chmod +r {fpath}",
                                                   "或将路径加入 ZIP_EXCLUDE_PATTERNS 后重跑。"])
                    raise UpgradeError(
                        "backup",
                        f"备份失败: 无法写入 {rel} ({exc.__class__.__name__}: {exc})",
                        next_steps=[
                            f"修复文件权限后重跑，例如: chmod -R u+r {fpath}",
                            "或把该路径显式加入 ZIP_EXCLUDE_PATTERNS 后重跑。",
                        ],
                    )
    manifest["backup_zip"] = str(zip_path)
    try:
        manifest["backup_size_bytes"] = zip_path.stat().st_size
    except OSError:
        manifest["backup_size_bytes"] = None
    log_info(f"zip 备份完成: {zip_path} ({count} files, {manifest['backup_size_bytes']} bytes)",
             _cfg_for(verbose))
    return zip_path


def _cfg_for(verbose: bool) -> UpgradeConfig:
    """Build a minimal config for logging helpers (verbose only)."""
    return UpgradeConfig(repo=Path("."), version_ref="", backup_dir=Path("/tmp"),
                         dry_run=False, restart=False, push=False,
                         rollback_manifest=None, yes=False, verbose=verbose)


def safe_unzip(zip_path: Path, dest: Path) -> list:
    """解压 zip 到 dest，做 zip-slip 校验，拒绝绝对路径/..//symlink 成员。"""
    dest = dest.resolve()
    restored = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts:
                raise UpgradeError("rollback",
                                   f"zip-slip 检测失败: 非法成员路径 {name}")
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest)):
                raise UpgradeError("rollback",
                                   f"zip-slip 检测失败: 成员逃逸 repo {name}")
            # skip symlink attributes (external_attr unix mode symlink)
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            restored.append(name)
    return restored


# ---------------------------------------------------------------------------
# Stash dirty tree
# ---------------------------------------------------------------------------


def stash_dirty_tree(state: RepoState, manifest: dict, config: UpgradeConfig) -> Optional[str]:
    """S2 stash: dirty tree 时执行 git stash push --include-untracked，记录 stash ref。"""
    if not state.dirty_files:
        log_info("工作树干净，无需 stash。", config)
        return None
    msg = f"hermes-auto-upgrade-{_timestamp()}"
    r = git(["stash", "push", "--include-untracked", "-m", msg],
            repo=config.repo, manifest=manifest.setdefault("commands", []),
            verbose=config.verbose)
    if r.exit_code != 0:
        add_manifest_error(manifest, "stash", "stash_failed",
                           f"git stash 失败 (exit={r.exit_code}): {redact(r.stderr)[:300]}")
        raise UpgradeError("stash", "git stash 失败",
                           next_steps=[f"手动处理 dirty tree: git -C {config.repo} status",
                                       "处理后重跑升级脚本。"])
    # 获取 stash ref
    r2 = git(["rev-parse", "--verify", "-q", "refs/stash"], repo=config.repo,
             manifest=manifest.setdefault("commands", []), verbose=config.verbose)
    stash_ref = r2.stdout.strip() if r2.exit_code == 0 and r2.stdout.strip() else None
    manifest["stash_ref"] = stash_ref
    log_info(f"已 stash {len(state.dirty_files)} 个 dirty 文件 -> {stash_ref}", config)
    return stash_ref


# ---------------------------------------------------------------------------
# Fetch & resolve
# ---------------------------------------------------------------------------


def fetch_remotes(config: UpgradeConfig, manifest: dict, target_ref: str) -> None:
    """S3 fetch: scoped fetch origin main + upstream tags; scoped by target ref remote."""
    cmd_log = manifest.setdefault("commands", [])
    # determine if target_ref is remote-scoped (e.g. upstream/main)
    remote_for_ref = None
    if "/" in target_ref:
        candidate_remote = target_ref.split("/", 1)[0]
        r = git(["remote"], repo=config.repo, manifest=cmd_log, verbose=config.verbose)
        remotes = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        if candidate_remote in remotes:
            remote_for_ref = candidate_remote

    # fetch origin main
    r = git(["fetch", "origin", "main"], repo=config.repo, manifest=cmd_log,
            verbose=config.verbose, timeout=300)
    if r.exit_code != 0:
        add_manifest_error(manifest, "fetch", "fetch_origin_failed",
                           f"fetch origin main 失败: {redact(r.stderr)[:300]}")
        raise UpgradeError("fetch", "fetch origin main 失败",
                           next_steps=["检查网络/SSH 认证。"])

    # fetch upstream --tags (and ref if scoped)
    fetch_up_cmd = ["fetch", "upstream", "--tags"]
    if remote_for_ref == "upstream":
        fetch_up_cmd = ["fetch", "upstream", target_ref.split("/", 1)[1], "--tags"]
    r = git(fetch_up_cmd, repo=config.repo, manifest=cmd_log,
            verbose=config.verbose, timeout=300)
    if r.exit_code != 0:
        add_manifest_error(manifest, "fetch", "fetch_upstream_failed",
                           f"fetch upstream 失败: {redact(r.stderr)[:300]}")
        raise UpgradeError("fetch", "fetch upstream 失败",
                           next_steps=["检查网络/SSH 认证。"])


def resolve_target_ref(config: UpgradeConfig, manifest: dict, target_ref: str) -> str:
    """将 --version / upstream/main 解析为 commit SHA。"""
    cmd_log = manifest.setdefault("commands", [])
    r = git(["rev-parse", "--verify", f"{target_ref}^{{commit}}"], repo=config.repo,
            manifest=cmd_log, verbose=config.verbose)
    if r.exit_code != 0:
        add_manifest_error(manifest, "resolve", "invalid_ref",
                           f"无效 git ref: {target_ref}")
        raise UpgradeError("resolve", f"无效 git ref: {target_ref}",
                           next_steps=[f"确认 ref 存在: git -C {config.repo} rev-parse --verify {target_ref}"])
    sha = r.stdout.strip()
    manifest["target_sha"] = sha
    return sha


def _is_ancestor(repo: Path, a: str, b: str, manifest: list, verbose: bool) -> bool:
    """Return True if a is ancestor of b."""
    r = git(["merge-base", "--is-ancestor", a, b], repo=repo, manifest=manifest,
            verbose=verbose)
    return r.exit_code == 0


def _has_merge_base(repo: Path, a: str, b: str, manifest: list, verbose: bool) -> bool:
    r = git(["merge-base", a, b], repo=repo, manifest=manifest, verbose=verbose)
    return r.exit_code == 0 and r.stdout.strip() != ""


def classify_git_relation(config: UpgradeConfig, state: RepoState, target_sha: str,
                          manifest: dict) -> GitPlan:
    """S4 classify: already-up-to-date / ff-only / merge / unrelated。"""
    cmd_log = manifest.setdefault("commands", [])
    head = state.pre_head

    if head == target_sha:
        return GitPlan(target_ref=config.version_ref, target_sha=target_sha,
                       merge_mode="already-up-to-date",
                       local_commits_need_protection=False)

    # head ancestor of target?
    if _is_ancestor(config.repo, head, target_sha, cmd_log, config.verbose):
        return GitPlan(target_ref=config.version_ref, target_sha=target_sha,
                       merge_mode="ff-only", local_commits_need_protection=False)

    # target ancestor of head? (local ahead, already has target)
    if _is_ancestor(config.repo, target_sha, head, cmd_log, config.verbose):
        return GitPlan(target_ref=config.version_ref, target_sha=target_sha,
                       merge_mode="already-up-to-date",
                       local_commits_need_protection=False)

    # diverged — need merge; only if merge-base exists
    if _has_merge_base(config.repo, head, target_sha, cmd_log, config.verbose):
        need_protect = bool(state.local_only_commits) or not _is_ancestor(
            config.repo, state.origin_main_sha or head, head, cmd_log, config.verbose)
        return GitPlan(target_ref=config.version_ref, target_sha=target_sha,
                       merge_mode="merge", local_commits_need_protection=need_protect,
                       diverged=True)

    add_manifest_error(manifest, "classify", "unrelated",
                       f"HEAD 与 target 无共同祖先 (unrelated histories)")
    raise UpgradeError("classify", "HEAD 与 target 无共同祖先，无法安全 merge。",
                       next_steps=["人工检查仓库历史。"])


# ---------------------------------------------------------------------------
# Protect local commits & apply merge
# ---------------------------------------------------------------------------


def protect_local_commits(config: UpgradeConfig, state: RepoState,
                          plan: GitPlan, manifest: dict) -> None:
    """S5 protect: 本地领先 commit 已在 origin 可达；否则先 push origin main 保护。"""
    if not plan.local_commits_need_protection:
        return
    cmd_log = manifest.setdefault("commands", [])
    # check if HEAD reachable from origin/main
    if state.origin_main_sha and _is_ancestor(config.repo, state.pre_head, state.pre_head,
                                              cmd_log, config.verbose):
        # Verify HEAD already in origin
        r = git(["merge-base", "--is-ancestor", state.pre_head, "origin/main"],
                repo=config.repo, manifest=cmd_log, verbose=config.verbose)
        if r.exit_code == 0:
            log_info("本地 commit 已在 origin/main 可达，无需额外保护 push。", config)
            return

    log_info("本地存在未保护的 commit，执行保护性 push origin main...", config)
    r = git(["push", "origin", "main"], repo=config.repo, manifest=cmd_log,
            verbose=config.verbose, timeout=120)
    if r.exit_code != 0:
        add_manifest_error(manifest, "protect", "push_failed",
                           f"保护性 push origin main 失败: {redact(r.stderr)[:300]}")
        raise UpgradeError("protect", "保护性 push origin main 失败",
                           next_steps=[f"手动 push: git -C {config.repo} push origin main",
                                       "检查 SSH/HTTPS 认证与 fork 权限。"])
    log_ok("本地 commit 已保护至 origin。", )


def apply_merge(config: UpgradeConfig, plan: GitPlan, manifest: dict) -> None:
    """S6 merge: ff-only / no-edit merge；冲突 abort。"""
    cmd_log = manifest.setdefault("commands", [])
    target = plan.target_sha
    if plan.merge_mode == "ff-only":
        r = git(["merge", "--ff-only", target], repo=config.repo,
                manifest=cmd_log, verbose=config.verbose)
        if r.exit_code != 0:
            add_manifest_error(manifest, "merge", "ff_failed",
                               f"ff-only merge 失败: {redact(r.stderr)[:300]}")
            raise UpgradeError("merge", "ff-only merge 失败")
        manifest["merge_mode"] = "ff-only"
    elif plan.merge_mode == "merge":
        r = git(["merge", "--no-edit", target], repo=config.repo,
                manifest=cmd_log, verbose=config.verbose)
        if r.exit_code != 0:
            # check for conflict
            r_conf = git(["diff", "--name-only", "--diff-filter=U"], repo=config.repo,
                         manifest=cmd_log, verbose=config.verbose)
            conflicted = [x.strip() for x in r_conf.stdout.splitlines() if x.strip()]
            # abort
            git(["merge", "--abort"], repo=config.repo, manifest=cmd_log,
                verbose=config.verbose)
            manifest["merge_mode"] = "abort-conflict"
            add_manifest_error(manifest, "merge", "conflict",
                               f"merge 冲突，已 abort。冲突文件: {conflicted}",
                               next_steps=["人工 resolve 后重跑，或使用 --rollback <manifest>"])
            raise UpgradeError("merge",
                               f"merge 冲突，已 git merge --abort。冲突文件: {conflicted}",
                               next_steps=[f"人工 resolve: git -C {config.repo} status",
                                           f"回滚: python3 {__file__} --rollback {manifest.get('_manifest_path', '<manifest>')}"])
        manifest["merge_mode"] = "merge"
    else:
        # already-up-to-date: nothing to merge
        manifest["merge_mode"] = "already-up-to-date"

    post = git_out(["rev-parse", "HEAD"], repo=config.repo, manifest=cmd_log,
                   verbose=config.verbose)
    manifest["post_head"] = post
    log_info(f"merge 完成 ({manifest['merge_mode']}), post_head={post[:12]}", config)


# ---------------------------------------------------------------------------
# Install & verify
# ---------------------------------------------------------------------------


def _find_uv() -> Optional[str]:
    return shutil.which("uv")


def install_editable(config: UpgradeConfig, manifest: dict) -> None:
    """S7 install: 清 pycache -> uv editable -> pip editable。"""
    cmd_log = manifest.setdefault("commands", [])
    repo = config.repo

    # clean pycache
    for root, dirs, _files in os.walk(repo):
        for d in list(dirs):
            if d == "__pycache__":
                p = Path(root) / d
                shutil.rmtree(p, ignore_errors=True)
    # clean .pyc top-level best-effort
    run_cmd(["find", str(repo), "-name", "__pycache__", "-type", "d", "-prune",
             "-exec", "rm", "-rf", "{}", "+"],
            cwd=str(repo), manifest=cmd_log, verbose=config.verbose)

    venv_python = repo / "venv" / "bin" / "python"
    target_python = str(venv_python) if venv_python.exists() else sys.executable
    env = os.environ.copy()
    if (repo / "venv").exists():
        env["VIRTUAL_ENV"] = str(repo / "venv")

    uv = _find_uv()
    installed = False
    if uv:
        r = run_cmd([uv, "pip", "install", "-e", ".[all]"], cwd=str(repo),
                    env=env, manifest=cmd_log, verbose=config.verbose, timeout=600)
        if r.exit_code == 0:
            installed = True
            log_info("uv editable install 成功。", config)
        else:
            log_warn(f"uv install 失败 (exit={r.exit_code})，fallback 到 pip。")
    if not installed:
        r = run_cmd([target_python, "-m", "pip", "install", "-e", ".[all]"],
                    cwd=str(repo), env=env, manifest=cmd_log,
                    verbose=config.verbose, timeout=600)
        if r.exit_code == 0:
            installed = True
            log_info("pip editable install (.[all]) 成功。", config)
        else:
            log_warn(f"pip install .[all] 失败，尝试 base install -e .")
            r = run_cmd([target_python, "-m", "pip", "install", "-e", "."],
                        cwd=str(repo), env=env, manifest=cmd_log,
                        verbose=config.verbose, timeout=600)
            if r.exit_code == 0:
                installed = True
                log_warn("pip base install (-e .) 成功，但 optional extras 未完整安装。", )
            else:
                add_manifest_error(manifest, "install", "install_failed",
                                   f"所有安装方式均失败。pip stderr: {redact(r.stderr)[:300]}")
                manifest["install_status"] = "failed"
                raise UpgradeError("install", "安装失败，所有方式均失败。",
                                   next_steps=["检查 pyproject.toml 与依赖。",
                                               f"建议 rollback: python3 {os.path.basename(__file__)} --rollback <manifest>"])

    manifest["install_status"] = "ok"


def verify_cli(config: UpgradeConfig, manifest: dict) -> str:
    r = run_cmd([str(config.hermes_bin), "--version"], manifest=manifest.setdefault("commands", []),
                verbose=config.verbose, timeout=60)
    if r.exit_code != 0 or not r.stdout.strip():
        add_manifest_error(manifest, "verify", "cli_failed",
                           f"hermes --version 失败 (exit={r.exit_code})")
        manifest["verify_status"] = "failed"
        raise UpgradeError("verify", "hermes --version 验证失败",
                           next_steps=[f"建议 rollback: python3 {os.path.basename(__file__)} --rollback <manifest>"])
    version = r.stdout.strip()
    log_ok(f"hermes --version: {version}")
    return version


def verify_import(config: UpgradeConfig, manifest: dict) -> None:
    venv_python = config.repo / "venv" / "bin" / "python"
    target_python = str(venv_python) if venv_python.exists() else sys.executable
    r = run_cmd([target_python, "-c", "import hermes_cli; import hermes_cli.main"],
                cwd=str(config.repo), manifest=manifest.setdefault("commands", []),
                verbose=config.verbose, timeout=60)
    if r.exit_code != 0:
        add_manifest_error(manifest, "verify", "import_failed",
                           f"hermes_cli import 失败: {redact(r.stderr)[:300]}")
        manifest["verify_status"] = "failed"
        raise UpgradeError("verify", "hermes_cli import 验证失败",
                           next_steps=[f"建议 rollback: python3 {os.path.basename(__file__)} --rollback <manifest>"])
    log_ok("hermes_cli import 验证通过。")


def verify_gateway_pre(config: UpgradeConfig, manifest: dict) -> str:
    """Pre-restart gateway status check. Returns status string."""
    r = run_cmd([str(config.hermes_bin), "gateway", "status"],
                manifest=manifest.setdefault("commands", []),
                verbose=config.verbose, timeout=60)
    status = "unknown"
    if r.exit_code == 0:
        out = (r.stdout + r.stderr).lower()
        if "running" in out or "healthy" in out or "ok" in out or "up" in out:
            status = "healthy"
        elif "stopped" in out or "down" in out or "not running" in out:
            status = "stopped"
    manifest["pre_gateway_status"] = status
    return status


def verify_gateway_post(config: UpgradeConfig, manifest: dict) -> str:
    """Post-restart gateway health check."""
    r = run_cmd([str(config.hermes_bin), "gateway", "status"],
                manifest=manifest.setdefault("commands", []),
                verbose=config.verbose, timeout=60)
    status = "unknown"
    if r.exit_code == 0:
        out = (r.stdout + r.stderr).lower()
        if "running" in out or "healthy" in out or "ok" in out or "up" in out:
            status = "healthy"
    return status


def set_verify_ok(manifest: dict) -> None:
    manifest["verify_status"] = "ok"


# ---------------------------------------------------------------------------
# Detached restart
# ---------------------------------------------------------------------------


def schedule_detached_restart(config: UpgradeConfig, manifest: dict) -> None:
    """S8 detached restart: setsid/nohup + hermes gateway restart，poll health 90s。

    安全要点（SPEC §4.7 / DESIGN §5）：禁止 `bash -lc "<拼字符串>"` 把 hermes_bin
    或 restart_log 直接拼进 shell 命令 — `--backup-dir` 含空格/分号/`$()` 等元字符
    时会被 shell 解释。我们改用一个临时 helper 脚本以 argv 形式调用 hermes，
    然后用 setsid+nohup 启动 helper，argv 本身不接受 shell 解释。
    """
    cmd_log = manifest.setdefault("commands", [])
    rlog = restart_log_path(config.backup_dir)
    manifest["restart_log"] = str(rlog)

    # 写入临时 helper 脚本。脚本本身不接受参数 — 我们以 argv 形式把 hermes_bin
    # 和 rlog 传给 helper（$1/$2），再由 helper 用 `"$@"` 透传给 hermes：
    # 这样 hermes_bin / rlog 中的 shell 元字符（空格、分号、`$()` 等）
    # 不会被 bash 解释，shell 注入面被消除。
    helper_script = config.backup_dir / f"hermes-restart-helper-{_timestamp()}.sh"
    helper_body = (
        "#!/usr/bin/env bash\n"
        "set -u\n"
        'exec "$1" gateway restart >> "$2" 2>&1\n'
    )
    try:
        helper_script.parent.mkdir(parents=True, exist_ok=True)
        helper_script.write_text(helper_body, encoding="utf-8")
        helper_script.chmod(0o755)
    except OSError as exc:
        add_manifest_error(manifest, "restart", "helper_write_failed",
                           f"无法写入 restart helper: {exc}",
                           next_steps=[f"检查 --backup-dir 权限: {config.backup_dir}"])
        raise UpgradeError("restart", f"无法写入 restart helper: {exc}",
                           next_steps=[f"手动重启: {config.hermes_bin} gateway restart"])
    manifest["restart_helper"] = str(helper_script)

    log_info(f"调度 detached gateway restart (helper={helper_script}, log={rlog})...",
             config)
    try:
        subprocess.Popen(
            # argv 形式：helper 不再被 bash -lc 解释；hermes_bin/rlog 也以 argv
            # 传入，绕过 shell 元字符注入。
            ["setsid", "nohup", str(helper_script),
             str(config.hermes_bin), str(rlog)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        add_manifest_error(manifest, "restart", "spawn_failed",
                           f"无法启动 detached restart helper: {exc}")
        manifest["restart_status"] = "failed"
        raise UpgradeError("restart", f"无法启动 detached restart: {exc}",
                           next_steps=[f"手动重启: {config.hermes_bin} gateway restart"])

    # poll health
    deadline = time.time() + GATEWAY_HEALTH_TIMEOUT
    healthy = False
    while time.time() < deadline:
        time.sleep(5)
        status = verify_gateway_post(config, manifest)
        if status == "healthy":
            healthy = True
            break

    if healthy:
        manifest["restart_status"] = "ok"
        log_ok("gateway restart 后健康检查通过。")
    else:
        manifest["restart_status"] = "failed"
        add_manifest_error(manifest, "restart", "health_timeout",
                           f"gateway restart 后 {GATEWAY_HEALTH_TIMEOUT}s 未恢复健康。",
                           next_steps=[f"查看日志: cat {rlog}",
                                       f"手动重启: {config.hermes_bin} gateway restart"])
        raise UpgradeError("restart",
                           f"gateway restart 后健康检查超时 ({GATEWAY_HEALTH_TIMEOUT}s)",
                           next_steps=[f"查看日志: cat {rlog}"])


# ---------------------------------------------------------------------------
# Push origin
# ---------------------------------------------------------------------------


def push_origin_if_enabled(config: UpgradeConfig, manifest: dict) -> None:
    """S9 push: 所有验证成功后 git push origin main。"""
    cmd_log = manifest.setdefault("commands", [])
    if not config.push:
        manifest["push_status"] = "skipped"
        log_info("push 已跳过 (--no-push)。手动推送: "
                 f"git -C {config.repo} push origin main", config)
        return
    r = git(["push", "origin", "main"], repo=config.repo, manifest=cmd_log,
            verbose=config.verbose, timeout=180)
    if r.exit_code != 0:
        manifest["push_status"] = "failed"
        add_manifest_error(manifest, "push", "push_failed",
                           f"push origin main 失败: {redact(r.stderr)[:300]}",
                           next_steps=[f"手动推送: git -C {config.repo} push origin main",
                                       "本地升级已成功，仅 fork 未同步。"])
        raise UpgradeError("push", "push origin main 失败（本地升级已成功，仅 fork 未同步）",
                           next_steps=[f"手动推送: git -C {config.repo} push origin main"])
    manifest["push_status"] = "ok"
    log_ok("已 push origin main。")


# ---------------------------------------------------------------------------
# Dry-run plan printing
# ---------------------------------------------------------------------------


def print_dry_run(config: UpgradeConfig, state: RepoState, *,
                  patch_statuses=None) -> int:
    """输出完整 dry-run 计划，不执行任何修改。

    V2 增量（DESIGN-10-006 §3.9 / SPEC-10-006 §5.4）：
      - 当前 branch 与 --branch 是否匹配
      - --preserve-features / --patches-manifest 计划信息
    """
    sep = "=" * 60
    print(sep)
    print("DRY-RUN 模式：以下为计划，不会修改 repo/venv/gateway/origin、patch manifest。")
    print(sep)
    print(f"  repo:           {state.repo}")
    print(f"  branch:         {state.branch}")
    print(f"  branch allowed: {config.branch}  "
          f"({'match' if state.branch == config.branch else 'MISMATCH'})")
    print(f"  pre_head:       {state.pre_head}")
    print(f"  origin_url:     {redact(state.origin_url)}")
    print(f"  upstream_url:   {redact(state.upstream_url)}")
    print(f"  install_method: {state.install_method}")
    print(f"  origin/main:    {state.origin_main_sha or '(未解析)'}")
    print(f"  target_ref:     {config.version_ref}")
    print(f"  dirty files:    {len(state.dirty_files)}")
    for f in state.dirty_files[:20]:
        print(f"    - {f}")
    if len(state.dirty_files) > 20:
        print(f"    ... ({len(state.dirty_files) - 20} more)")
    print(f"  local-only commits: {len(state.local_only_commits)}")
    for c in state.local_only_commits[:10]:
        print(f"    - {c}")
    # V2 信息
    print(f"  preserve_features: {'enabled' if config.preserve_features else 'disabled'}")
    if config.preserve_features:
        print(f"  S0.5 计划: git push -u origin {state.branch or '<detached>'}  (dry-run only)")
    if config.patches_manifest is not None:
        print(f"  patches_manifest:   {config.patches_manifest}")
        if patch_statuses is None:
            print("    -> 未在本调用中提供 patch_statuses；运行 upgrade 后可见")
        else:
            for ps in patch_statuses:
                mark = "✓" if ps.get("status") == "merged" else (
                    "~" if ps.get("status") == "possibly-merged" else "?"
                )
                print(f"    [{mark}] {ps.get('id')}: {ps.get('status')} — {ps.get('reason')}")
    else:
        print("  patches_manifest:   disabled")

    # attempt to resolve target if already locally available (no network fetch)
    target_sha = None
    r = git(["rev-parse", "--verify", "-q", f"{config.version_ref}^{{commit}}"],
            repo=config.repo, verbose=config.verbose)
    if r.exit_code == 0 and r.stdout.strip():
        target_sha = r.stdout.strip()

    print()
    print("  [计划步骤]")
    print(f"  0.5 (若 --preserve-features) git push -u origin {state.branch or '<detached>'}  (dry-run only; not executed)")
    print(f"  1. 创建 zip 备份     -> {backup_zip_path(config.backup_dir)}")
    print(f"  2. 写入 manifest     -> {manifest_path(config.backup_dir)}")
    if state.dirty_files:
        print("  3. git stash push --include-untracked  (dirty tree)")
    else:
        print("  3. (跳过 stash: 工作树干净)")
    print(f"  4. git fetch origin main + fetch upstream --tags")
    if target_sha:
        print(f"  5. resolve target   -> {target_sha}")
        head = state.pre_head
        if head == target_sha:
            print(f"     => merge_mode: already-up-to-date")
        elif _is_ancestor(config.repo, head, target_sha, [], config.verbose):
            print(f"     => merge_mode: ff-only  (git merge --ff-only {target_sha})")
        else:
            print(f"     => merge_mode: merge    (本地有自有 commit，A+ 策略)")
    else:
        print(f"  5. resolve target   -> (需 fetch 后解析; ref={config.version_ref})")
        print(f"     => merge_mode: unknown-before-fetch")
    if config.patches_manifest is not None:
        print(f"  6.5 (若 --patches-manifest) patch manifest check -> best-effort upstream containment report")
    print(f"  6. install          -> uv pip install -e '.[all]' (fallback pip)")
    print(f"  7. verify           -> hermes --version / import / gateway status")
    if config.restart:
        rlog = restart_log_path(config.backup_dir)
        print(f"  8. detached restart -> {config.hermes_bin} gateway restart (log={rlog})")
    else:
        print(f"  8. restart          -> SKIPPED (--no-restart)")
    if config.push:
        print(f"  9. push origin      -> git push origin main")
    else:
        print(f"  9. push origin      -> SKIPPED (--no-push)")

    print()
    print("  声明: dry-run 未修改 repo、venv、gateway、origin、patch manifest。")
    print(sep)
    return 0


# ---------------------------------------------------------------------------
# Upgrade main flow
# ---------------------------------------------------------------------------


def upgrade(config: UpgradeConfig) -> int:
    mpath = manifest_path(config.backup_dir)
    manifest = init_manifest(config)
    manifest["_manifest_path"] = str(mpath)

    try:
        # S0 inspect
        log_info("S0 检查 repo 状态...", config)
        state = inspect_repo(config, manifest)
        log_info(f"repo OK: {state.branch} @ {state.pre_head[:12]}, "
                 f"dirty={len(state.dirty_files)}, local_only={len(state.local_only_commits)}",
                 config)

        # S0.5 preserve_feature_branch (V2 增量 — 仅 --preserve-features 启用时执行)
        preserve_feature_branch_if_requested(config, state, manifest)
        # 注意：dry-run 不写 manifest（保持 V1.0 no-mutation 契约）。
        if not config.dry_run:
            write_manifest(manifest, mpath)

        # dry-run short-circuit
        if config.dry_run:
            return print_dry_run(config, state)

        # S1 backup
        log_info("S1 创建 zip 备份...", config)
        zpath = backup_zip_path(config.backup_dir)
        create_zip_backup(config.repo, zpath, manifest, verbose=config.verbose)
        write_manifest(manifest, mpath)

        # S2 stash
        log_info("S2 stash dirty tree (如有)...", config)
        stash_dirty_tree(state, manifest, config)
        write_manifest(manifest, mpath)

        # S3 fetch
        log_info("S3 fetch remotes...", config)
        fetch_remotes(config, manifest, config.version_ref)

        # resolve target
        log_info("解析 target ref...", config)
        target_sha = resolve_target_ref(config, manifest, config.version_ref)
        write_manifest(manifest, mpath)

        # re-inspect local-only after fetch
        state.origin_main_sha = git_out(["rev-parse", "--verify", "-q", "origin/main"],
                                        repo=config.repo, manifest=manifest.setdefault("commands", []),
                                        verbose=config.verbose) or None
        r = git(["rev-list", "--count", f"{target_sha}..HEAD"], repo=config.repo,
                manifest=manifest.setdefault("commands", []), verbose=config.verbose)
        try:
            n = int(r.stdout.strip()) if r.exit_code == 0 else 0
        except ValueError:
            n = 0
        if n > 0:
            r2 = git(["log", "--oneline", "-n", "50", f"{target_sha}..HEAD"], repo=config.repo,
                     manifest=manifest.setdefault("commands", []), verbose=config.verbose)
            state.local_only_commits = [x.strip() for x in r2.stdout.splitlines() if x.strip()]
            manifest["local_only_commits"] = state.local_only_commits

        # S4 classify
        log_info("S4 判定 git 关系...", config)
        plan = classify_git_relation(config, state, target_sha, manifest)
        log_info(f"merge_mode={plan.merge_mode}, "
                 f"need_protect={plan.local_commits_need_protection}", config)

        # S5 protect
        if plan.merge_mode != "already-up-to-date":
            protect_local_commits(config, state, plan, manifest)

        # S6 merge
        if plan.merge_mode != "already-up-to-date":
            log_info("S6 执行 merge...", config)
            apply_merge(config, plan, manifest)
        else:
            manifest["merge_mode"] = "already-up-to-date"
        write_manifest(manifest, mpath)

        # S6.5 patch manifest check (V2 增量 — 仅在 --patches-manifest 提供时执行)
        if config.patches_manifest is not None:
            log_info("S6.5 patch manifest upstream check...", config)
            run_patch_manifest_check_if_requested(
                config, manifest, config.version_ref)
        else:
            manifest["patch_statuses"] = []
            manifest["patches_check_status"] = "disabled"
        write_manifest(manifest, mpath)

        # S7 install + verify
        log_info("S7 安装依赖...", config)
        install_editable(config, manifest)
        write_manifest(manifest, mpath)

        log_info("验证 CLI/import/gateway...", config)
        version = verify_cli(config, manifest)
        verify_import(config, manifest)
        verify_gateway_pre(config, manifest)
        set_verify_ok(manifest)
        write_manifest(manifest, mpath)

        # S8 restart
        if config.restart:
            log_info("S8 detached gateway restart...", config)
            schedule_detached_restart(config, manifest)
        else:
            manifest["restart_status"] = "skipped"
            log_info("gateway restart 已跳过 (--no-restart)。", config)
            log_info(f"手动重启: {config.hermes_bin} gateway restart", config)
        write_manifest(manifest, mpath)

        # S9 push
        log_info("S9 push origin (如启用)...", config)
        push_origin_if_enabled(config, manifest)
        write_manifest(manifest, mpath)

        # summary
        log_ok("=" * 60)
        log_ok(f"升级完成。manifest: {mpath}")
        log_ok(f"  pre_head={manifest['pre_head'][:12]} -> post_head={manifest.get('post_head','')[:12] or '(n/a)'}")
        log_ok(f"  merge_mode={manifest['merge_mode']}, install={manifest['install_status']}, "
               f"verify={manifest['verify_status']}, restart={manifest['restart_status']}, "
               f"push={manifest['push_status']}")
        log_ok("=" * 60)
        return 0

    except UpgradeError as exc:
        add_manifest_error(manifest, exc.stage, exc.stage, str(exc), exc.next_steps)
        manifest["_manifest_path"] = str(mpath)
        write_manifest(manifest, mpath)
        log_err(f"[{exc.stage}] {exc}")
        if exc.next_steps:
            log("后续步骤:", force=True)
            for s in exc.next_steps:
                log(f"  - {s}", force=True)
        log_err(f"manifest: {mpath}")
        log_err(f"回滚: python3 {os.path.basename(__file__)} --rollback {mpath}")
        return exc.exit_code


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback_from_manifest(config: UpgradeConfig) -> int:
    if config.rollback_manifest is None:
        log_err("rollback 模式需要 --rollback <manifest>")
        return 2
    mpath = config.rollback_manifest
    if not mpath.exists():
        log_err(f"manifest 不存在: {mpath}")
        return 1

    manifest = load_manifest(mpath)
    repo = Path(manifest["repo"])
    pre_head = manifest.get("pre_head")
    backup_zip = manifest.get("backup_zip")
    stash_ref = manifest.get("stash_ref")
    post_head = manifest.get("post_head")
    dirty_files = manifest.get("dirty_files", [])

    sep = "=" * 60
    print(sep)
    print("ROLLBACK 计划 / 执行")
    print(sep)
    print(f"  manifest:        {mpath}")
    print(f"  repo:            {repo}")
    print(f"  pre_head:        {pre_head}")
    print(f"  post_head:       {post_head}")
    print(f"  backup_zip:      {backup_zip}")
    print(f"  stash_ref:       {stash_ref}")
    print(f"  dirty_files:     {len(dirty_files)}")

    if not pre_head:
        log_err("manifest 缺少 pre_head，无法回滚。")
        return 1

    if not (repo / ".git").exists():
        log_err(f"repo 不是 git 仓库: {repo}")
        return 1

    # dry-run short-circuit: must run BEFORE any stash/reset/unzip so that
    # dry-run never mutates the repo (SPEC §4.7 / DESIGN §5 rollback 契约).
    # Only inspect git status here so we can report current dirty state in plan.
    if config.dry_run:
        r = git(["status", "--porcelain=v1"], repo=repo, verbose=config.verbose)
        current_dirty = [line[3:].strip() for line in r.stdout.splitlines() if line.strip()]
        print()
        print("  [DRY-RUN] 将执行以下步骤（不实际执行）:")
        if current_dirty:
            print(f"    0. 真实执行时若 repo 仍 dirty ({len(current_dirty)} 个文件)，"
                  "会先 git stash push --include-untracked")
        print(f"    1. git -C {repo} merge --abort  (清理可能残留 merge 状态)")
        print(f"    2. git -C {repo} reset --hard {pre_head}")
        if backup_zip:
            print(f"    3. 解压 {backup_zip} 恢复工作树文件")
        if stash_ref:
            print(f"    4. 输出 stash apply 命令（不自动 apply）: "
                  f"git -C {repo} stash apply {stash_ref}")
        print(f"    5. 最小验证: hermes --version")
        print("  声明: dry-run 未修改 repo、stash、HEAD。")
        print(sep)
        return 0

    # check current dirty tree (only reachable in real-execute path)
    r = git(["status", "--porcelain=v1"], repo=repo, verbose=config.verbose)
    current_dirty = [line[3:].strip() for line in r.stdout.splitlines() if line.strip()]
    if current_dirty:
        msg = (f"当前 repo 有未记录的 dirty 文件 ({len(current_dirty)})。"
               f"回滚前需要先安全 stash。")
        print(f"  [WARN] {msg}")
        if not config.yes:
            print("  当前为非交互环境且未传 --yes，拒绝执行真实回滚。")
            print("  如需继续，请添加 --yes。")
            return 1
        safe_stash_name = f"hermes-auto-upgrade-rollback-{_timestamp()}"
        r2 = git(["stash", "push", "--include-untracked", "-m", safe_stash_name],
                 repo=repo, verbose=config.verbose)
        if r2.exit_code != 0:
            log_err("安全 stash 当前 dirty tree 失败，拒绝继续 hard reset。")
            return 1
        r3 = git(["rev-parse", "--verify", "-q", "refs/stash"], repo=repo,
                 verbose=config.verbose)
        print(f"  [INFO] 当前 dirty 已安全 stash 为: {r3.stdout.strip() or safe_stash_name}")

    # confirm
    if not config.yes:
        print()
        print("  即将执行 git reset --hard，这是不可逆操作。")
        print("  当前为非交互环境，请添加 --yes 确认。")
        return 1

    # 1. merge --abort (allow failure)
    git(["merge", "--abort"], repo=repo, verbose=config.verbose)

    # 2. hard reset
    print(f"  [EXEC] git -C {repo} reset --hard {pre_head}")
    r = git(["reset", "--hard", pre_head], repo=repo, verbose=config.verbose)
    if r.exit_code != 0:
        log_err(f"git reset --hard {pre_head} 失败: {redact(r.stderr)[:300]}")
        log_err(f"人工恢复: git -C {repo} reset --hard {pre_head}")
        return 1

    # 3. unzip restore
    if backup_zip and Path(backup_zip).exists():
        print(f"  [EXEC] 解压 {backup_zip} 恢复工作树...")
        try:
            restored = safe_unzip(Path(backup_zip), repo)
            print(f"  [INFO] 恢复 {len(restored)} 个文件。")
        except UpgradeError as exc:
            log_err(f"zip 解压失败: {exc}")
            log_err(f"人工解压: unzip -o {backup_zip} -d {repo}")
            return 1
    else:
        print("  [INFO] 无 backup_zip 或文件不存在，跳过 zip 恢复。")

    # 4. stash apply (manual command only)
    if stash_ref:
        print(f"  [INFO] dirty tree stash 未自动恢复。如需恢复，手动执行:")
        print(f"         git -C {repo} stash apply {stash_ref}")

    # 5. minimal verify
    r = run_cmd([str(config.hermes_bin), "--version"], verbose=config.verbose, timeout=60)
    if r.exit_code == 0:
        log_ok(f"hermes --version: {r.stdout.strip()}")
    else:
        log_warn("hermes --version 仍失败，可能需要重新安装。")
        print(f"  人工检查: {config.hermes_bin} --version")
        print(f"  重新安装: cd {repo} && uv pip install -e '.[all]'")

    print(sep)
    log_ok(f"回滚完成。repo HEAD 已恢复至 {pre_head[:12]}。")
    print(sep)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="upgrade_hermes_agent.py",
        description="Hermes Agent 自动升级脚本（RFC-10-005 / DESIGN-10-006 / SPEC-10-006）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  干跑（不修改任何状态）:\n"
            "    python3 upgrade_hermes_agent.py --dry-run --no-restart --no-push\n"
            "  升级到 upstream/main（不重启 gateway、不推送 fork）:\n"
            "    python3 upgrade_hermes_agent.py --no-restart --no-push\n"
            "  指定版本:\n"
            "    python3 upgrade_hermes_agent.py --version v2026.6.19 --no-restart --no-push\n"
            "  在非 main 分支（如 fix/feishu-table-card）执行检查:\n"
            "    python3 upgrade_hermes_agent.py --dry-run --branch fix/feishu-table-card --no-restart --no-push\n"
            "  保护 feature branch + patch manifest check:\n"
            "    python3 upgrade_hermes_agent.py --dry-run --preserve-features --patches-manifest data/hermes_patches.yaml --no-restart --no-push\n"
            "  回滚:\n"
            "    python3 upgrade_hermes_agent.py --rollback /tmp/hermes-upgrade-*.json --yes\n"
        ),
    )
    p.add_argument("--repo", type=Path, default=Path(DEFAULT_REPO),
                   help=f"Hermes Agent 源码 repo 路径 (默认: {DEFAULT_REPO})")
    p.add_argument("--version", type=str, default=DEFAULT_VERSION_REF,
                   help=f"目标 git ref: tag/branch/remote ref/SHA (默认: {DEFAULT_VERSION_REF})")
    p.add_argument("--branch", type=str, default="main",
                   help="V2: 允许执行 inspect/upgrade 的当前 git 分支 (默认: main)")
    p.add_argument("--preserve-features", action="store_true",
                   help="V2: 升级前 best-effort push 当前 feature branch 到 origin 以保护本地 commit")
    p.add_argument("--patches-manifest", type=Path, default=None,
                   help="V2: Pascal fork 私有 patch 清单路径，例如 data/hermes_patches.yaml")
    p.add_argument("--dry-run", action="store_true",
                   help="只输出计划，不修改 repo/venv/gateway/origin")
    p.add_argument("--no-restart", action="store_true",
                   help="跳过 gateway restart，输出手动重启命令")
    p.add_argument("--no-push", action="store_true",
                   help="跳过 push origin，输出手动推送命令")
    p.add_argument("--backup-dir", type=Path, default=Path(DEFAULT_BACKUP_DIR),
                   help=f"manifest/zip/restart log 输出目录 (默认: {DEFAULT_BACKUP_DIR})")
    p.add_argument("--rollback", type=Path, default=None, metavar="MANIFEST",
                   help="进入回滚模式，从 manifest 恢复 repo")
    p.add_argument("--yes", action="store_true",
                   help="非交互确认；不得绕过 conflict/verify/push 顺序保护")
    p.add_argument("--verbose", action="store_true",
                   help="输出更详细的命令日志")
    return p


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def config_from_args(args: argparse.Namespace) -> UpgradeConfig:
    return UpgradeConfig(
        repo=args.repo,
        version_ref=args.version,
        backup_dir=args.backup_dir,
        dry_run=args.dry_run,
        restart=not args.no_restart,
        push=not args.no_push,
        rollback_manifest=args.rollback,
        yes=args.yes,
        verbose=args.verbose,
        branch=getattr(args, "branch", "main"),
        preserve_features=getattr(args, "preserve_features", False),
        patches_manifest=getattr(args, "patches_manifest", None),
    )


def validate_args(args: argparse.Namespace) -> Optional[int]:
    """参数冲突校验。返回非 None 表示应立即退出该 exit code。"""
    if args.rollback is not None:
        conflicts = []
        if args.version is not None and args.version != DEFAULT_VERSION_REF:
            conflicts.append("--version")
        if args.no_restart:
            conflicts.append("--no-restart")
        if args.no_push:
            conflicts.append("--no-push")
        if getattr(args, "preserve_features", False):
            conflicts.append("--preserve-features")
        if getattr(args, "patches_manifest", None) is not None:
            conflicts.append("--patches-manifest")
        branch_val = getattr(args, "branch", "main")
        if branch_val != "main":
            conflicts.append("--branch (non-default)")
        if conflicts:
            log_err(f"--rollback 模式不接受以下参数: {', '.join(conflicts)}")
            log_err("rollback 模式只接受: --repo, --backup-dir, --dry-run, --yes, --verbose")
            return 2
    return None


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    code = validate_args(args)
    if code is not None:
        return code
    config = config_from_args(args)
    try:
        if config.rollback_manifest is not None:
            return rollback_from_manifest(config)
        return upgrade(config)
    except KeyboardInterrupt:
        log_err("中断。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
