# Sanity Check 模板

本文件提供 6 个可直接 copy-paste 的 Python 标准库模板。每个模板包含：触发条件、默认策略、完整 Python 实现、错误消息格式、真实反例引用、适配注意。

所有模板共享一个错误类型：

```python
class SanityCheckError(ValueError):
    pass
```

错误消息统一格式：

```text
[SanityCheck:<check_name>] <field> invalid.
expected: <期望>
actual: <实际>
next: <修复建议>
```

---

## interface_arg_check

**触发条件**：新增/修改 CLI 参数、argparse 选项、`store_true` flag，或需要拒绝未知 option 时。

**默认策略**：fail-fast。危险 no-op arg 比没有 arg 更危险——用户以为功能已启用，实际跑生产路径。

**完整 Python 实现**：

```python
from dataclasses import dataclass
from typing import Iterable, Mapping, Any


class SanityCheckError(ValueError):
    pass


@dataclass(frozen=True)
class ArgRule:
    name: str
    enabled: bool
    implemented: bool = True
    dangerous_if_noop: bool = True
    next_step: str = "remove the arg or implement its behavior"


def interface_arg_check(rules: Iterable[ArgRule]) -> None:
    """Check CLI args are implemented when enabled and dangerous-if-noop."""
    for rule in rules:
        if rule.enabled and not rule.implemented and rule.dangerous_if_noop:
            raise SanityCheckError(
                f"[SanityCheck:interface_arg_check] {rule.name} invalid.\n"
                f"expected: enabled arg has implemented behavior\n"
                f"actual: arg is enabled but not implemented\n"
                f"next: {rule.next_step}"
            )


def forbid_unknown_options(options: Mapping[str, Any], allowed: set[str]) -> None:
    """Fail-fast on unknown CLI options instead of silently ignoring them."""
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise SanityCheckError(
            f"[SanityCheck:interface_arg_check] options invalid.\n"
            f"expected: only {sorted(allowed)}\n"
            f"actual: unknown {unknown}\n"
            f"next: remove unknown options or add explicit implementation"
        )
```

**错误消息示例**：

```text
[SanityCheck:interface_arg_check] --debug invalid.
expected: enabled arg has implemented behavior
actual: arg is enabled but not implemented
next: remove the arg or implement its behavior
```

**真实反例引用**：`skills/reports/daily-market-analysis/scripts/main.py:253-255`，`--debug` 分支引用未定义变量；显式 debug 参数应有 smoke test。

**适配注意**：
- `ArgRule.next_step` 可按项目改成更具体的修复建议（如 "implement --debug branch or remove the flag from argparse"）。
- `forbid_unknown_options` 的 `allowed` 集合应来自项目实际的 argparse 定义，不要手写副本（容易漂移）。

---

## file_existence_check

**触发条件**：接入新的输入/输出文件或目录路径，需要区分读/写语义时。

**默认策略**：写入路径 fail-fast（parent 不可写即报错）；只读 optional path 可 warn。

**完整 Python 实现**：

```python
from pathlib import Path
import os


class SanityCheckError(ValueError):
    pass


def file_existence_check(path: Path | str, *, mode: str, purpose: str) -> None:
    """Check file/dir existence and readability/writability for a given purpose.

    mode must be one of: read-file, read-dir, write-file, write-dir.
    purpose is a human-readable label included in error messages.
    """
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
            f"expected: readable file\n"
            f"actual: {p}\n"
            f"next: provide an existing file path"
        )
    if mode == "read-dir" and (not p.exists() or not p.is_dir()):
        raise SanityCheckError(
            f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
            f"expected: readable directory\n"
            f"actual: {p}\n"
            f"next: provide an existing directory"
        )
    if mode == "write-file":
        parent = p.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            raise SanityCheckError(
                f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
                f"expected: writable parent directory\n"
                f"actual: {parent}\n"
                f"next: create parent or choose writable output path"
            )
    if mode == "write-dir":
        if p.exists() and not p.is_dir():
            raise SanityCheckError(
                f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
                f"expected: directory path\n"
                f"actual: file {p}\n"
                f"next: choose a directory path"
            )
        parent = p if p.exists() else p.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            raise SanityCheckError(
                f"[SanityCheck:file_existence_check] {purpose} invalid.\n"
                f"expected: writable directory parent\n"
                f"actual: {parent}\n"
                f"next: create parent or fix permissions"
            )
```

**错误消息示例**：

```text
[SanityCheck:file_existence_check] input csv invalid.
expected: readable file
actual: /data/source/2026-07-08/input.csv
next: provide an existing file path
```

**真实反例引用**：`skills/data/data-pipeline/scripts/smart_money_watcher.py:145-151`，路径中提取不到日期时应 fail-fast 或要求显式 date，而不是 fallback 今天。

**适配注意**：
- `purpose` 参数必填，不要传空字符串——它是错误消息中唯一能让用户快速定位的字段。
- 对于 "optional read path"，可以捕获异常后 warn；但写入路径不要 warn-only。

---

## type_coercion_check

**触发条件**：把 JSON/YAML/CSV/env 的字符串值显式转换成 int/float/Decimal/bool 时。

**默认策略**：fail-fast。silent default（`int(x)` 失败 fallback 0）比直接报错更危险。

**完整 Python 实现**：

```python
from decimal import Decimal, InvalidOperation
from typing import Callable, TypeVar, Any


T = TypeVar("T")


class SanityCheckError(ValueError):
    pass


def type_coercion_check(value: Any, *, field: str, converter: Callable[[Any], T], expected: str) -> T:
    """Explicitly coerce a value with loud failure; never silent default.

    converter: e.g. int, Decimal, to_bool_strict.
    expected: human-readable target type label for error messages.
    """
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
    """Safe Decimal coercion: stringify and strip first."""
    return Decimal(str(value).strip())


def to_bool_strict(value: Any) -> bool:
    """Strict bool: only accept true/false/1/0/yes/no (case-insensitive str) or actual bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "1", "yes"}:
        return True
    if isinstance(value, str) and value.lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"not a strict bool: {value!r}")
```

**错误消息示例**：

```text
[SanityCheck:type_coercion_check] amount invalid.
expected: decimal
actual: 'abc'
next: normalize input before business logic
```

**真实反例引用**：`skills/data/data_interface/mongo_reader.py:67-85`，`kwargs` 中 collection_name 缺失或未知时不应 silent default 到持仓集合。

**适配注意**：
- `to_bool_strict` 不接受空字符串或 `None`——这些在 bool 语境下是 ambiguous，应 fail-fast。
- 如果业务允许 `None`，用 `allow_none` 分支在调用前显式判断，不要让 converter 静默兜底。

---

## date_format_check

**触发条件**：处理 `position_date` / `trade_date` / `nav_date` 等 YQuant 业务日期字段。

**默认策略**：写入 MongoDB / 文件目录时 fail-fast；只读展示可 warn。

**完整 Python 实现**：

```python
from datetime import datetime


class SanityCheckError(ValueError):
    pass


def date_format_check(value: object, *, field: str, allow_none: bool = False) -> str | None:
    """Force YYYY-MM-DD string; reject datetime, YYYYMMDD, empty, silent-today.

    Returns the validated string (or None if allow_none and value is None).
    """
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
            f"expected: YYYY-MM-DD\n"
            f"actual: {value!r}\n"
            f"next: use e.g. 2026-07-08, not YYYYMMDD or datetime"
        ) from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise SanityCheckError(
            f"[SanityCheck:date_format_check] {field} invalid.\n"
            f"expected: canonical YYYY-MM-DD\n"
            f"actual: {value!r}\n"
            f"next: zero-pad month/day"
        )
    return value
```

**错误消息示例**：

```text
[SanityCheck:date_format_check] position_date invalid.
expected: YYYY-MM-DD
actual: '20260708'
next: use e.g. 2026-07-08, not YYYYMMDD or datetime
```

**真实反例引用**：`skills/data/data-pipeline/scripts/smart_money_watcher.py:53-55`、`:74-75`、`:112-113` 中 date 缺失 fallback 今天；如果输入路径来自历史数据，应要求显式 business date。

**适配注意**：
- `allow_none=True` 用于可选日期字段，调用方必须显式判断，不要在 converter 内部默认今天。
- 不要把 `datetime` 对象传进来——先 `.strftime("%Y-%m-%d")`，否则会被 isinstance 分支拦住。

---

## git_state_check

**触发条件**：升级脚本、auto-push、流水线编排等需要在执行前确认 branch / dirty / unpushed 状态的场景。

**默认策略**：升级/auto-push 类脚本 fail-fast；只读报告可 warn。

**完整 Python 实现**：

```python
from dataclasses import dataclass
from pathlib import Path
import subprocess


class SanityCheckError(ValueError):
    pass


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
    """Check git branch/dirty/unpushed satisfy preconditions for a mutating operation.

    allowed_branch: if set, fail-fast unless current branch matches.
    allow_dirty: if False, fail-fast on uncommitted changes.
    allow_unpushed: if False, fail-fast on commits not pushed to upstream.
    """
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
```

**错误消息示例**：

```text
[SanityCheck:git_state_check] branch invalid.
expected: main
actual: feature/xyz
next: checkout expected branch or pass explicit --branch
```

**真实正例引用**：`scripts/upgrade/upgrade_hermes_agent.py` V2 已围绕 branch / preserve-features / patch manifest 做安全升级前置检查。本模板吸收其思想，但不引用其内部函数（避免 skill 与 upgrade 脚本耦合）。

**适配注意**：
- `@{u}..HEAD` 在没有 upstream 的分支上会报错——可以在调用前先 `git rev-parse --abbrev-ref @{u}` 判断。
- `allow_dirty=True` 适合本地开发；`allow_dirty=False` 适合 CI / 升级 / auto-push。

---

## mongo_connection_check

**触发条件**：连接或写入 MongoDB，特别是 `tradingagents` 库的 collection。

**默认策略**：生产写入 fail-fast；本地 dry-run 可 warn。

**完整 Python 实现**：

```python
from dataclasses import dataclass


class SanityCheckError(ValueError):
    pass


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
    """Check MongoDB connection string, database, and collection before boundary crossing.

    connection_string: from env/secret store; never print it.
    require_ping: if True, attempt a real ping (optional pymongo import).
    """
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
    if require_ping:
        try:
            from pymongo import MongoClient  # optional dependency at runtime boundary
            client = MongoClient(connection_string, serverSelectionTimeoutMS=3000)
            client.admin.command("ping")
        except Exception as exc:
            raise SanityCheckError(
                "[SanityCheck:mongo_connection_check] ping invalid.\n"
                "expected: MongoDB ping succeeds\nactual: ping failed\n"
                "next: check network/credentials without printing secrets"
            ) from exc
```

**错误消息示例**：

```text
[SanityCheck:mongo_connection_check] collection invalid.
expected: one of ['portfolio_position', 'portfolio_trade', 'signal']
actual: position_date
next: add explicit collection mapping; do not default to portfolio_position
```

**真实反例引用**：`skills/data/data_interface/mongo_reader.py:67-85`，未知集合默认到 `position_date` 查询应改为 allowed collection fail-fast。

**适配注意**：
- `allowed_collections` 应来自项目实际的 collection 映射，不要手写容易漂移的副本。
- `connection_string` 永远不要打印到日志——错误消息只说 "empty" 或 "ping failed"。
- `require_ping=True` 会引入 optional pymongo 依赖；self_test 默认不启用 ping，真实边界再启用。
