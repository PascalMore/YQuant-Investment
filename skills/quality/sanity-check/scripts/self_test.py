#!/usr/bin/env python3
"""Sanity-check skill self-test.

Runs with stdlib only (pathlib, subprocess, tempfile, decimal, datetime).
Does not connect to real MongoDB; does not send external messages.

Usage:
    python3 skills/quality/sanity-check/scripts/self_test.py

Success prints "sanity-check self-test: PASS" and exits 0.
Failure raises AssertionError / SanityCheckError and exits non-zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, TypeVar
import os
import subprocess
import tempfile


# ---------------------------------------------------------------------------
# Shared error type
# ---------------------------------------------------------------------------

class SanityCheckError(ValueError):
    """All fail-fast sanity checks raise this."""


# ---------------------------------------------------------------------------
# Minimal inline template implementations (kept in sync with templates.md)
# ---------------------------------------------------------------------------

T = TypeVar("T")


# --- interface_arg_check ---

@dataclass(frozen=True)
class ArgRule:
    name: str
    enabled: bool
    implemented: bool = True
    dangerous_if_noop: bool = True
    next_step: str = "remove the arg or implement its behavior"


def interface_arg_check(rules: Iterable[ArgRule]) -> None:
    for rule in rules:
        if rule.enabled and not rule.implemented and rule.dangerous_if_noop:
            raise SanityCheckError(
                f"[SanityCheck:interface_arg_check] {rule.name} invalid.\n"
                f"expected: enabled arg has implemented behavior\n"
                f"actual: arg is enabled but not implemented\n"
                f"next: {rule.next_step}"
            )


def forbid_unknown_options(options: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise SanityCheckError(
            f"[SanityCheck:interface_arg_check] options invalid.\n"
            f"expected: only {sorted(allowed)}\n"
            f"actual: unknown {unknown}\n"
            f"next: remove unknown options or add explicit implementation"
        )


# --- file_existence_check ---

def file_existence_check(path: Path | str, *, mode: str, purpose: str) -> None:
    p = Path(path)
    if mode not in {"read-file", "read-dir", "write-file", "write-dir"}:
        raise SanityCheckError(
            f"[SanityCheck:file_existence_check] mode invalid.\n"
            f"expected: read-file/read-dir/write-file/write-dir\n"
            f"actual: {mode}\n"
            f"next: choose an explicit file access mode for {purpose}"
        )
    if mode == "read-file" and (not p.exists() or not p.is_file()):
        raise SanityCheckError(
            f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
            f"expected: readable file\nactual: {p}\n"
            f"next: provide an existing file path"
        )
    if mode == "read-dir" and (not p.exists() or not p.is_dir()):
        raise SanityCheckError(
            f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
            f"expected: readable directory\nactual: {p}\n"
            f"next: provide an existing directory"
        )
    if mode == "write-file":
        parent = p.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            raise SanityCheckError(
                f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
                f"expected: writable parent directory\nactual: {parent}\n"
                f"next: create parent or choose writable output path"
            )
    if mode == "write-dir":
        if p.exists() and not p.is_dir():
            raise SanityCheckError(
                f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
                f"expected: directory path\nactual: file {p}\n"
                f"next: choose a directory path"
            )
        parent = p if p.exists() else p.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            raise SanityCheckError(
                f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
                f"expected: writable directory parent\nactual: {parent}\n"
                f"next: create parent or fix permissions"
            )


# --- type_coercion_check ---

def type_coercion_check(value: Any, *, field: str, converter: Callable[[Any], T], expected: str) -> T:
    if value is None:
        raise SanityCheckError(
            f"[SanityCheck:type_coercion_check] {field} invalid.\n"
            f"expected: {expected}\nactual: None\nnext: pass an explicit value"
        )
    try:
        return converter(value)
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise SanityCheckError(
            f"[SanityCheck:type_coercion_check] {field} invalid.\n"
            f"expected: {expected}\nactual: {value!r}\nnext: normalize input before business logic"
        ) from exc


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value).strip())


def to_bool_strict(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "1", "yes"}:
        return True
    if isinstance(value, str) and value.lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"not a strict bool: {value!r}")


# --- date_format_check ---

def date_format_check(value: object, *, field: str, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise SanityCheckError(
            f"[SanityCheck:date_format_check] {field} invalid.\n"
            f"expected: str in YYYY-MM-DD\n"
            f"actual: {type(value).__name__}: {value!r}\n"
            f"next: format date explicitly before calling this boundary"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SanityCheckError(
            f"[SanityCheck:date_format_check] {field} invalid.\n"
            f"expected: YYYY-MM-DD\nactual: {value!r}\n"
            f"next: use e.g. 2026-07-08, not YYYYMMDD or datetime"
        ) from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise SanityCheckError(
            f"[SanityCheck:date_format_check] {field} invalid.\n"
            f"expected: canonical YYYY-MM-DD\nactual: {value!r}\n"
            f"next: zero-pad month/day"
        )
    return value


# --- git_state_check (structural check only; real git ops tested against temp repo) ---

@dataclass(frozen=True)
class GitState:
    branch: str
    dirty: bool
    unpushed: int


def _git(repo: Path, args: list[str]) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _git_quiet(repo: Path, args: list[str]) -> str:
    """Run a git command, returning stdout; stderr suppressed for expected soft-failures."""
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def _unpushed_count(repo: Path, branch: str) -> int:
    """Count commits not pushed to upstream; return 0 if no upstream configured."""
    if not branch:
        return 0
    try:
        raw = _git_quiet(repo, ["rev-list", "--count", "@{u}..HEAD"])
        return int(raw or "0")
    except subprocess.CalledProcessError:
        # No upstream configured for this branch.
        return 0


def git_state_check(
    repo: Path | str,
    *,
    allowed_branch: str | None = None,
    allow_dirty: bool = False,
    allow_unpushed: bool = True,
) -> GitState:
    r = Path(repo)
    branch = _git(r, ["branch", "--show-current"])
    dirty = bool(_git(r, ["status", "--porcelain"]))
    unpushed = _unpushed_count(r, branch)
    if allowed_branch and branch != allowed_branch:
        raise SanityCheckError(
            f"[SanityCheck:git_state_check] branch invalid.\n"
            f"expected: {allowed_branch}\nactual: {branch}\n"
            f"next: checkout expected branch or pass explicit --branch"
        )
    if dirty and not allow_dirty:
        raise SanityCheckError(
            f"[SanityCheck:git_state_check] working tree invalid.\n"
            f"expected: clean tree\nactual: dirty\n"
            f"next: commit/stash/revert before running mutating operation"
        )
    if unpushed and not allow_unpushed:
        raise SanityCheckError(
            f"[SanityCheck:git_state_check] unpushed commits invalid.\n"
            f"expected: 0\nactual: {unpushed}\n"
            f"next: push or explicitly preserve feature branch"
        )
    return GitState(branch=branch, dirty=dirty, unpushed=unpushed)


# --- mongo_connection_check (no real DB connection; require_ping not exercised here) ---

@dataclass(frozen=True)
class MongoBoundary:
    database: str
    collection: str
    allowed_collections: set[str]
    operation: str  # read | write | dry-run


def mongo_connection_check(
    boundary: MongoBoundary,
    *,
    connection_string: str | None,
    require_ping: bool = False,
) -> None:
    if not connection_string:
        raise SanityCheckError(
            "[SanityCheck:mongo_connection_check] connection_string invalid.\n"
            "expected: non-empty MongoDB connection string from env/secret store\n"
            "actual: empty\nnext: configure env without printing secrets"
        )
    if boundary.collection not in boundary.allowed_collections:
        raise SanityCheckError(
            f"[SanityCheck:mongo_connection_check] collection invalid.\n"
            f"expected: one of {sorted(boundary.allowed_collections)}\n"
            f"actual: {boundary.collection}\n"
            f"next: add explicit collection mapping; do not default to portfolio_position"
        )
    if boundary.operation == "write" and boundary.database != "tradingagents":
        raise SanityCheckError(
            f"[SanityCheck:mongo_connection_check] database invalid.\n"
            f"expected: tradingagents for YQuant production write\n"
            f"actual: {boundary.database}\n"
            f"next: confirm target database explicitly"
        )
    # require_ping path intentionally not exercised in self_test (no real DB).


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def expect_error(fn: Callable[[], Any], label: str) -> None:
    """Assert that fn raises SanityCheckError."""
    try:
        fn()
    except SanityCheckError:
        return
    raise AssertionError(f"expected SanityCheckError: {label}")


def expect_ok(fn: Callable[[], Any], label: str) -> None:
    """Assert that fn returns without raising."""
    try:
        fn()
    except SanityCheckError as exc:
        raise AssertionError(f"unexpected SanityCheckError for {label}: {exc}") from exc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_interface_arg_check() -> None:
    # dangerous no-op arg must fail-fast
    expect_error(
        lambda: interface_arg_check([
            ArgRule(name="--debug", enabled=True, implemented=False, dangerous_if_noop=True),
        ]),
        "dangerous no-op arg",
    )
    # implemented arg is OK
    expect_ok(
        lambda: interface_arg_check([
            ArgRule(name="--verbose", enabled=True, implemented=True),
        ]),
        "implemented arg",
    )
    # unknown option fail-fast
    expect_error(
        lambda: forbid_unknown_options({"--foo": 1, "--bar": 2}, allowed={"--bar"}),
        "unknown option",
    )
    # all-known options OK
    expect_ok(
        lambda: forbid_unknown_options({"--bar": 2}, allowed={"--bar"}),
        "all known options",
    )


def test_file_existence_check() -> None:
    # missing read file fail-fast
    expect_error(
        lambda: file_existence_check("/no/such/file_xyz", mode="read-file", purpose="input"),
        "missing read file",
    )
    # existing file OK
    with tempfile.NamedTemporaryFile() as tmp:
        expect_ok(
            lambda: file_existence_check(tmp.name, mode="read-file", purpose="tmp input"),
            "existing tmp file",
        )
    # invalid mode fail-fast
    expect_error(
        lambda: file_existence_check("/tmp", mode="execute", purpose="bad mode"),
        "invalid mode",
    )
    # existing dir OK for read-dir
    expect_ok(
        lambda: file_existence_check("/tmp", mode="read-dir", purpose="tmp dir"),
        "existing tmp dir",
    )


def test_type_coercion_check() -> None:
    # bad decimal fail-fast
    expect_error(
        lambda: type_coercion_check("abc", field="amount", converter=to_decimal, expected="decimal"),
        "bad decimal coercion",
    )
    # None value fail-fast
    expect_error(
        lambda: type_coercion_check(None, field="amount", converter=to_decimal, expected="decimal"),
        "None coercion",
    )
    # good decimal OK
    result = type_coercion_check("123.45", field="amount", converter=to_decimal, expected="decimal")
    assert result == Decimal("123.45"), f"decimal coercion returned {result!r}"
    # strict bool converter sanity (direct calls do not raise SanityCheckError)
    assert to_bool_strict("yes") is True
    assert to_bool_strict("0") is False
    # ambiguous bool must fail-fast when used through type_coercion_check
    expect_error(
        lambda: type_coercion_check("maybe", field="flag", converter=to_bool_strict, expected="strict bool"),
        "ambiguous bool via type_coercion_check",
    )


def test_date_format_check() -> None:
    # YYYYMMDD fail-fast
    expect_error(
        lambda: date_format_check("20260708", field="position_date"),
        "YYYYMMDD instead of YYYY-MM-DD",
    )
    # datetime object fail-fast
    expect_error(
        lambda: date_format_check(datetime(2026, 7, 8), field="position_date"),
        "datetime object instead of str",
    )
    # non-canonical format fail-fast
    expect_error(
        lambda: date_format_check("2026-7-8", field="position_date"),
        "non-zero-padded date",
    )
    # good date OK
    result = date_format_check("2026-07-08", field="position_date")
    assert result == "2026-07-08"
    # allow_none
    assert date_format_check(None, field="optional_date", allow_none=True) is None


def test_git_state_check() -> None:
    # Use a temp git repo so we exercise real git without touching the project repo.
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        (repo / "a.txt").write_text("hello")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)

        # clean tree on main: should pass with allowed_branch=main
        state = git_state_check(repo, allowed_branch="main", allow_dirty=False)
        assert state.branch == "main", f"branch={state.branch}"
        assert state.dirty is False, f"dirty={state.dirty}"

        # make it dirty
        (repo / "a.txt").write_text("changed")
        # dirty + allow_dirty=False must fail-fast
        expect_error(
            lambda: git_state_check(repo, allowed_branch="main", allow_dirty=False),
            "dirty tree not allowed",
        )
        # dirty + allow_dirty=True should pass
        expect_ok(
            lambda: git_state_check(repo, allow_dirty=True),
            "dirty tree allowed",
        )
        # wrong branch fail-fast
        expect_error(
            lambda: git_state_check(repo, allowed_branch="release", allow_dirty=True),
            "wrong branch",
        )


def test_mongo_connection_check() -> None:
    allowed = {"portfolio_position", "portfolio_trade", "signal"}
    # unknown collection fail-fast
    expect_error(
        lambda: mongo_connection_check(
            MongoBoundary(
                database="tradingagents",
                collection="position_date",  # typo, not in allowlist
                allowed_collections=allowed,
                operation="write",
            ),
            connection_string="mongodb://localhost:27017",
        ),
        "unknown collection",
    )
    # empty connection_string fail-fast
    expect_error(
        lambda: mongo_connection_check(
            MongoBoundary(
                database="tradingagents",
                collection="portfolio_position",
                allowed_collections=allowed,
                operation="write",
            ),
            connection_string=None,
        ),
        "empty connection_string",
    )
    # wrong database for write fail-fast
    expect_error(
        lambda: mongo_connection_check(
            MongoBoundary(
                database="test_db",
                collection="portfolio_position",
                allowed_collections=allowed,
                operation="write",
            ),
            connection_string="mongodb://localhost:27017",
        ),
        "wrong database for write",
    )
    # valid write boundary OK
    expect_ok(
        lambda: mongo_connection_check(
            MongoBoundary(
                database="tradingagents",
                collection="portfolio_position",
                allowed_collections=allowed,
                operation="write",
            ),
            connection_string="mongodb://localhost:27017",
        ),
        "valid write boundary",
    )
    # read on non-tradingagents DB is OK (only write enforces tradingagents)
    expect_ok(
        lambda: mongo_connection_check(
            MongoBoundary(
                database="other_db",
                collection="portfolio_position",
                allowed_collections=allowed,
                operation="read",
            ),
            connection_string="mongodb://localhost:27017",
        ),
        "read on non-tradingagents",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    tests = [
        ("interface_arg_check", test_interface_arg_check),
        ("file_existence_check", test_file_existence_check),
        ("type_coercion_check", test_type_coercion_check),
        ("date_format_check", test_date_format_check),
        ("git_state_check", test_git_state_check),
        ("mongo_connection_check", test_mongo_connection_check),
    ]
    for name, fn in tests:
        fn()
        print(f"  ok: {name}")
    print("sanity-check self-test: PASS")


if __name__ == "__main__":
    main()
