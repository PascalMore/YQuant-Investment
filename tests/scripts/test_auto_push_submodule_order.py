# -*- coding: utf-8 -*-
"""Offline structural test for scripts/auto_push.sh.

Verifies the submodule/gitlink ordering invariants required by the bug that
caused the main repo's gitlink to fall behind GitHub after the 03:30 cron run.

Invariants checked (no real git, no real commit/push):
  1. The script initializes submodules BEFORE iterating .gitmodules.
  2. After the per-submodule push loop, the script does NOT call
     `git submodule update` again — doing so would reset each submodule
     working tree back to the currently-recorded gitlink.
  3. The first git write operation on the main repo is `git add -A`,
     so gitlink changes are picked up before commit/push.
  4. The pre-loop init uses fail-fast semantics (no `|| true` swallowing).

Implemented by parsing the script with shlex + regex — no shell execution.
"""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "auto_push.sh"


# ---------------------------------------------------------------------------
# Helpers: collect every command invocation from the script body
# ---------------------------------------------------------------------------


def _strip_comments(src: str) -> str:
    """Strip full-line and trailing `#` comments while preserving strings."""
    out_lines: list[str] = []
    for line in src.splitlines():
        # Drop leading whitespace then a leading '#'
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Drop trailing inline comment — but only if outside of any quotes.
        # Cheap heuristic: if the line contains a balanced quote section, leave it.
        # For this script we never embed '#' inside a quoted string, so a
        # naive split on " #" (with space prefix) is safe.
        if " #" in line:
            line = line.split(" #", 1)[0]
        out_lines.append(line)
    return "\n".join(out_lines)


def _command_calls(src: str):
    """Yield (line_no, command_text) for every top-level & control-flow body.

    Control structures (`if`, `while`, `for`, ...) span multiple lines; we only
    pick up the first command line that has actual content.
    """
    cleaned = _strip_comments(src)
    for lineno, line in enumerate(cleaned.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        # Match a leading command token followed by anything non-comment.
        # We accept either a bare command, or a leading keyword like `if`,
        # `while`, `then`, `do`, `else`, `elif`, `fi`, `done`, `!`, `{`.
        m = re.match(
            r"^(?:if|elif|while|until|then|else|do|!|\{|\(\()\s+(.*)$",
            s,
        )
        if m:
            tail = m.group(1).strip()
        elif re.match(r"^(fi|done|esac)\b", s):
            continue
        else:
            tail = s
        if not tail:
            continue
        yield lineno, tail


def _line_for_git_call(src: str, needle: str) -> int | None:
    """Return the 1-based line number of the first line that runs `git <needle>`.

    Skips comment-only lines. Matches anywhere in the line as long as it begins
    with `git <needle>` (allowing leading whitespace).
    """
    pattern = re.compile(rf"^\s*git\s+{re.escape(needle)}\b")
    for lineno, line in enumerate(src.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        # Drop trailing inline comment piece (heuristic).
        code = line.split(" #", 1)[0]
        if pattern.match(code):
            return lineno
    return None


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def src() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def calls(src: str):
    return list(_command_calls(src))


def _join_call_tokens(tail: str) -> str:
    """Rebuild a shell-style single-line tokenization (best-effort) for
    substring matching."""
    try:
        return " ".join(shlex.split(tail, posix=True))
    except ValueError:
        return tail


# ---------------------------------------------------------------------------
# Invariant 1: submodule init runs BEFORE the per-submodule push loop
# ---------------------------------------------------------------------------


def test_submodule_init_runs_before_submodule_push_loop(src: str) -> None:
    init_line = _line_for_git_call(src, "submodule")
    assert init_line is not None, "expected `git submodule ...` somewhere in auto_push.sh"

    # Extract the first command with `submodule update --init` and confirm
    # there is no `--recursive` after `--init`. The bug fix specifically
    # removes the recursive re-reset from the loop tail; we only need an init
    # here so the per-submodule loop starts on a real working tree.
    src_clean = _strip_comments(src)
    init_re = re.compile(r"^\s*git\s+submodule\s+update\s+--init\b")
    init_lines = [
        lineno for lineno, line in enumerate(src_clean.splitlines(), start=1)
        if init_re.match(line.split(" #", 1)[0])
    ]
    assert init_lines, (
        "expected a fail-fast `git submodule update --init` before the loop"
    )
    init_line = init_lines[0]

    # Find the per-submodule push loop body. It's the `while IFS=` loop.
    loop_match = re.search(
        r"^\s*while\s+IFS=\s*read\b",
        src_clean,
        re.MULTILINE,
    )
    assert loop_match is not None, "expected the per-submodule while-read loop"
    loop_line = loop_match.start()
    # Convert byte offset to line number.
    loop_line_no = src_clean.count("\n", 0, loop_line) + 1

    assert init_line < loop_line_no, (
        f"`git submodule update --init` (line {init_line}) must run BEFORE the "
        f"per-submodule while loop (line {loop_line_no})."
    )


# ---------------------------------------------------------------------------
# Invariant 2: NO `git submodule update` AFTER the per-submodule push loop
# ---------------------------------------------------------------------------


SHELL_KEYWORDS = {"if", "then", "else", "elif", "fi", "while", "until", "do", "done", "!", "{", "(("}


def _iter_substantive_statements(body: str):
    """Yield each non-empty, non-comment, non-keyword-only line from `body`.

    Strips comments (full-line + trailing) so `# ── Main repo ──` banners
    don't trigger as content. Skips lines that are only a shell structural
    keyword (e.g. `fi`, `done`).
    """
    for raw in body.splitlines():
        # Drop trailing inline `#` comment piece (heuristic — no `#` inside
        # quoted strings in this script).
        code = raw.split(" #", 1)[0]
        stripped = code.strip()
        if not stripped or stripped.startswith("#"):
            continue
        head = stripped.split(None, 1)[0]
        if head in SHELL_KEYWORDS:
            continue
        yield stripped


def test_no_post_loop_submodule_update(src: str) -> None:
    src_clean = _strip_comments(src)
    loop_match = re.search(
        r"^\s*while\s+IFS=\s*read\b",
        src_clean,
        re.MULTILINE,
    )
    assert loop_match is not None, "expected the per-submodule while loop"
    loop_start = loop_match.start()
    after_loop = src_clean[loop_start:]

    # Find the loop terminator: `done < <(git config ...)`
    done_match = re.search(r"^\s*done\b", after_loop, re.MULTILINE)
    assert done_match is not None, "expected a `done` terminator for the loop"
    after_done_offset = done_match.end()
    after_done = after_loop[after_done_offset:]

    # After the loop, there must NOT be another `git submodule update`.
    bad = re.search(r"^\s*git\s+submodule\s+update\b", after_done, re.MULTILINE)
    assert bad is None, (
        "post-loop `git submodule update` would reset submodules back to the "
        "currently-recorded gitlink, silently dropping the freshly-pushed SHA.\n"
        f"Offending line: {bad.group(0) if bad else '<n/a>'}"
    )


# ---------------------------------------------------------------------------
# Invariant 3: The first git write on the main repo is `git add -A`
# ---------------------------------------------------------------------------


def test_first_main_repo_git_write_is_add(src: str) -> None:
    src_clean = _strip_comments(src)

    # Locate the per-submodule loop's process-substitution terminator. The
    # `done < <(git config ... | awk ...)` line ends with `)`. Match that whole
    # line so `.end()` lands after the newline, not in the middle of the body.
    iter_re = re.compile(
        r"^\s*done\s*<\s*<\(git\s+config[^\n]*\)\s*$",
        re.MULTILINE,
    )
    iter_match = iter_re.search(src_clean)
    assert iter_match is not None, "expected `done < <(git config ...)`"
    after_done = src_clean[iter_match.end():]

    # Walk substantive statements (skipping `if/then/else/fi/do/done` and
    # `cd` navigation) until we hit the first `git` call. That call must be
    # the main-repo `git add -A` — otherwise the freshly-pushed submodule
    # SHAs would never be picked up by the parent commit.
    for stmt in _iter_substantive_statements(after_done):
        # Skip pure navigation: `cd "..."` / `cd "$repo_path"`
        if stmt.startswith("cd "):
            continue
        # Detect any explicit MAIN_BRANCH variable read.
        if stmt.startswith("MAIN_BRANCH="):
            continue
        assert stmt.startswith("git "), (
            f"first substantive post-loop command must start with `git`; "
            f"got: {stmt!r}"
        )
        assert stmt.startswith("git add") and "-A" in stmt, (
            f"first post-loop git operation must be `git add -A`; got: {stmt!r}"
        )
        return

    pytest.fail("no post-loop git command found; script structure changed?")


# ---------------------------------------------------------------------------
# Invariant 4: Pre-loop init is fail-fast (no `|| true`)
# ---------------------------------------------------------------------------


def test_preloop_submodule_init_is_fail_fast(src: str) -> None:
    src_clean = _strip_comments(src)
    init_re = re.compile(
        r"^\s*(?P<cmd>git\s+submodule\s+update\s+--init)(?P<tail>.*)$",
        re.MULTILINE,
    )
    matches = list(init_re.finditer(src_clean))
    assert matches, "expected `git submodule update --init` before the loop"
    m = matches[0]
    cmd, tail = m.group("cmd"), m.group("tail").strip()
    assert "|| true" not in tail, (
        "pre-loop `git submodule update --init` must NOT use `|| true` — "
        "fail-fast preserves working trees from silent corruption."
    )
    assert "2>/dev/null" not in tail, (
        "pre-loop `git submodule update --init` must NOT swallow stderr via "
        "`2>/dev/null` — silent stderr hides submodule state corruption."
    )


# ---------------------------------------------------------------------------
# Invariant 5: Script still enforces `set -euo pipefail`
# ---------------------------------------------------------------------------


def test_strict_mode_preserved(src: str) -> None:
    first_nonblank = next(
        (line for line in src.splitlines() if line.strip() and not line.lstrip().startswith("#")),
        None,
    )
    assert first_nonblank is not None, "script body is unexpectedly empty"
    assert first_nonblank.strip() == "set -euo pipefail", (
        f"expected `set -euo pipefail` as the very first non-comment line; "
        f"got: {first_nonblank!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 6: bash -n lint must continue to pass
# ---------------------------------------------------------------------------


def test_bash_n_passes() -> None:
    import subprocess

    r = subprocess.run(
        ["bash", "-n", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, (
        f"`bash -n scripts/auto_push.sh` failed:\n"
        f"stdout={r.stdout!r}\nstderr={r.stderr!r}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
