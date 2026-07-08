# SPEC-10-007：Sanity Check 标准模式 Skill

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-08 |
| 来源 RFC | RFC-10-007-sanity-check-patterns |
| 关联 Design | DESIGN-10-007-sanity-check-patterns |
| 目标模块 | 10_infra / 工程质量 skill |
| Quick Flow | T1=`t_a4539961`; T2=`t_46c017a3`; T3=`t_649d0695`; T4=`t_bfcef8a4` |

## 1. 需求摘要

本 SPEC 将 RFC-10-007 的 sanity check 标准模式落为可执行、可测试的 skill 契约。目标是在 `skills/quality/sanity-check/` 新增一个可复用 skill，沉淀 6 个常用模板、fail-fast vs warn 决策表和真实反例目录。

本 SPEC 的直接消费者是 T2 Developer。T2 不需要重新扫描仓库即可实现 skill；所有必须行为、文件路径、模板接口和验收标准均在本文件定义。

## 2. 范围

### 2.1 In Scope

- 新增 `skills/quality/sanity-check/SKILL.md`。
- 新增 `skills/quality/sanity-check/references/templates.md`，包含 6 个模板的完整 Python 示例。
- 新增 `skills/quality/sanity-check/references/fail-fast-vs-warn.md`，包含选择准则与决策表。
- 新增 `skills/quality/sanity-check/references/examples.md`，包含真实反例目录，至少 3 条 P0。
- 新增 `skills/quality/sanity-check/scripts/self_test.py`，对模板核心函数做标准库级 smoke test。
- 不新增第三方依赖。

### 2.2 Out of Scope

- 不修复 `mongo_reader.py`、`daily_export_report.py`、`smart_money_watcher.py` 等历史代码。
- 不引入 Pydantic、jsonschema、pre-commit、ruff 或 CI gate。
- 不连接真实 MongoDB 或发送真实 Telegram/Feishu/邮件消息。
- 不修改 AI Coding Pipeline skill、Hermes profile 配置、cron/systemd。

## 3. Skill 文件结构契约

T2 必须创建以下结构：

```text
skills/quality/sanity-check/
├── SKILL.md
├── references/
│   ├── templates.md
│   ├── fail-fast-vs-warn.md
│   └── examples.md
└── scripts/
    └── self_test.py
```

### 3.1 `SKILL.md` 契约

必须包含 YAML frontmatter：

```yaml
---
name: sanity-check
description: Standard fail-fast / warn sanity-check patterns for CLI args, files, type coercion, dates, git state, and MongoDB boundaries.
version: 1.0.0
platforms: [linux, macos, windows]
environments: [cli, repo, kanban]
metadata:
  hermes:
    tags: [quality, sanity-check, fail-fast, validation-boundary]
    related_skills: [yquant-ai-coding-pipeline, systematic-debugging, test-driven-development]
---
```

必须包含章节：

1. 触发条件：何时加载本 skill。
2. 一句话定义：sanity check 是业务逻辑前的最后一道合理性闸门。
3. 边界：不是 validation，不是 error handling。
4. 决策树：六个模板如何选择。
5. Fail-fast vs warn 摘要。
6. 模板索引：指向 `references/templates.md`。
7. 真实反例：指向 `references/examples.md`。
8. 验证：如何运行 `scripts/self_test.py`。
9. 禁止事项：不要吞错、不要 silent fallback、不要为 no-op 参数只补文档。

## 4. Fail-fast vs warn 决策契约

### 4.1 元规则

| 条件 | 决策 | 理由 |
|---|---|---|
| 可能导致数据写入错误位置、错误日期、错误集合 | fail-fast | 数据污染后难回滚 |
| 可能导致外部消息发错对象 | fail-fast | 隐私和审计风险 |
| 用户显式选择危险 flag，但实现无法保证语义 | fail-fast | no-op arg 比没有 arg 更危险 |
| 只读路径缺失，且有明确 fallback 数据源 | warn-and-continue | best-effort 可接受 |
| git dirty/unpushed 只影响审计，不改变当前只读检查 | warn | 可由操作者后续处理 |
| debug / preview 分支失败，不影响生产主路径 | warn 或 fail-fast，取决于该参数是否被用户显式请求 | 显式请求时应 fail-fast |

### 4.2 错误消息格式

所有 fail-fast 错误消息必须包含：

```text
[SanityCheck:<check_name>] <field> invalid.
expected: <期望>
actual: <实际>
next: <修复建议>
```

Warning 必须包含同样字段，但前缀为 `[SanityWarn:<check_name>]`。

## 5. 六个模板契约

### 5.1 `interface_arg_check`

用途：检查 CLI 参数合法性、互斥关系、危险 no-op arg、显式 flag 是否被实现消费。

默认策略：fail-fast。

必须提供代码：

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
```

真实反例引用：`skills/reports/daily-market-analysis/scripts/main.py:253-255`，`--debug` 分支引用未定义变量；显式 debug 参数应有 smoke test。

### 5.2 `file_existence_check`

用途：文件/目录存在性、类型、可读/可写检查。

默认策略：写入路径 fail-fast；只读 optional path 可 warn。

必须提供代码：

```python
from pathlib import Path
import os

class SanityCheckError(ValueError):
    pass


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
        raise SanityCheckError(f"[SanityCheck:file_existence_check] {purpose} invalid.\nexpected: readable file\nactual: {p}\nnext: provide an existing file path")
    if mode == "read-dir" and (not p.exists() or not p.is_dir()):
        raise SanityCheckError(f"[SanityCheck:file_existence_check] {purpose} invalid.\nexpected: readable directory\nactual: {p}\nnext: provide an existing directory")
    if mode == "write-file":
        parent = p.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            raise SanityCheckError(f"[SanityCheck:file_existence_check] {purpose} invalid.\nexpected: writable parent directory\nactual: {parent}\nnext: create parent or choose writable output path")
    if mode == "write-dir":
        if p.exists() and not p.is_dir():
            raise SanityCheckError(f"[SanityCheck:file_existence_check] {purpose} invalid.\nexpected: directory path\nactual: file {p}\nnext: choose a directory path")
        parent = p if p.exists() else p.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            raise SanityCheckError(f"[SanityCheck:file_existence_check] {purpose} invalid.\nexpected: writable directory parent\nactual: {parent}\nnext: create parent or fix permissions")
```

真实反例引用：`skills/data/data-pipeline/scripts/smart_money_watcher.py:145-151`，路径中提取不到日期时应 fail-fast 或要求显式 date，而不是 fallback 今天。

### 5.3 `type_coercion_check`

用途：显式执行字符串到 int/float/Decimal/bool/date 的转换；禁止 silent default。

默认策略：转换失败 fail-fast。

必须提供代码：

```python
from decimal import Decimal, InvalidOperation
from typing import Callable, TypeVar, Any

T = TypeVar("T")

class SanityCheckError(ValueError):
    pass


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
```

真实反例引用：`skills/data/data_interface/mongo_reader.py:67-85`，`kwargs` 中 collection_name 缺失或未知时不应 silent default 到持仓集合。

### 5.4 `date_format_check`

用途：强制检查 `YYYY-MM-DD` 字符串日期，避免 datetime 对象、`YYYYMMDD`、空值、默认今天混入业务写入。

默认策略：写入 MongoDB / 文件目录时 fail-fast；只读展示可 warn。

必须提供代码：

```python
from datetime import datetime

class SanityCheckError(ValueError):
    pass


def date_format_check(value: object, *, field: str, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise SanityCheckError(
            f"[SanityCheck:date_format_check] {field} invalid.\n"
            f"expected: str in YYYY-MM-DD\nactual: {type(value).__name__}: {value!r}\nnext: format date explicitly before calling this boundary"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SanityCheckError(
            f"[SanityCheck:date_format_check] {field} invalid.\n"
            f"expected: YYYY-MM-DD\nactual: {value!r}\nnext: use e.g. 2026-07-08, not YYYYMMDD or datetime"
        ) from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise SanityCheckError(
            f"[SanityCheck:date_format_check] {field} invalid.\n"
            f"expected: canonical YYYY-MM-DD\nactual: {value!r}\nnext: zero-pad month/day"
        )
    return value
```

真实反例引用：`skills/data/data-pipeline/scripts/smart_money_watcher.py:53-55`、`:74-75`、`:112-113` 中 date 缺失 fallback 今天；如果输入路径来自历史数据，应要求显式 business date。

### 5.5 `git_state_check`

用途：检查 branch、dirty tree、unpushed commits、remote 是否满足脚本安全前置条件。

默认策略：升级/自动 push 类脚本 fail-fast；只读报告可 warn。

必须提供代码：

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


def git_state_check(repo: Path | str, *, allowed_branch: str | None = None, allow_dirty: bool = False, allow_unpushed: bool = True) -> GitState:
    r = Path(repo)
    branch = _git(r, ["branch", "--show-current"])
    dirty = bool(_git(r, ["status", "--porcelain"]))
    unpushed_raw = _git(r, ["rev-list", "--count", "@{u}..HEAD"]) if branch else "0"
    unpushed = int(unpushed_raw or "0")
    if allowed_branch and branch != allowed_branch:
        raise SanityCheckError(f"[SanityCheck:git_state_check] branch invalid.\nexpected: {allowed_branch}\nactual: {branch}\nnext: checkout expected branch or pass explicit --branch")
    if dirty and not allow_dirty:
        raise SanityCheckError(f"[SanityCheck:git_state_check] working tree invalid.\nexpected: clean tree\nactual: dirty\nnext: commit/stash/revert before running mutating operation")
    if unpushed and not allow_unpushed:
        raise SanityCheckError(f"[SanityCheck:git_state_check] unpushed commits invalid.\nexpected: 0\nactual: {unpushed}\nnext: push or explicitly preserve feature branch")
    return GitState(branch=branch, dirty=dirty, unpushed=unpushed)
```

真实正例引用：`scripts/upgrade/upgrade_hermes_agent.py` V2 已围绕 branch / preserve-features / patch manifest 做安全升级前置检查。

### 5.6 `mongo_connection_check`

用途：生产 MongoDB 读写前确认 connection string、database、collection 选择、可选 ping。

默认策略：生产写入 fail-fast；本地 dry-run 可 warn。

必须提供代码：

```python
from dataclasses import dataclass
from typing import Iterable

class SanityCheckError(ValueError):
    pass

@dataclass(frozen=True)
class MongoBoundary:
    database: str
    collection: str
    allowed_collections: set[str]
    operation: str  # read | write | dry-run


def mongo_connection_check(boundary: MongoBoundary, *, connection_string: str | None, require_ping: bool = False) -> None:
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
            f"actual: {boundary.collection}\nnext: add explicit collection mapping; do not default to portfolio_position"
        )
    if boundary.operation == "write" and boundary.database != "tradingagents":
        raise SanityCheckError(
            f"[SanityCheck:mongo_connection_check] database invalid.\n"
            f"expected: tradingagents for YQuant production write\nactual: {boundary.database}\nnext: confirm target database explicitly"
        )
    if require_ping:
        try:
            from pymongo import MongoClient  # optional dependency at runtime boundary
            client = MongoClient(connection_string, serverSelectionTimeoutMS=3000)
            client.admin.command("ping")
        except Exception as exc:
            raise SanityCheckError(
                "[SanityCheck:mongo_connection_check] ping invalid.\n"
                "expected: MongoDB ping succeeds\nactual: ping failed\nnext: check network/credentials without printing secrets"
            ) from exc
```

真实反例引用：`skills/data/data_interface/mongo_reader.py:67-85`，未知集合默认到 `position_date` 查询应改为 allowed collection fail-fast。

## 6. 真实反例目录契约

`references/examples.md` 必须至少包含下表 3 条 P0，并可追加 P1/P2：

| ID | 优先级 | 文件:行号 | 代码片段 | 为什么是反例 | 修复方向 |
|---|---|---|---|---|---|
| EX-P0-001 | P0 | `skills/data/data_interface/mongo_reader.py:67-85` | unknown collection -> default `position_date` | 传错 collection 时 silent wrong query | collection allowlist + unknown fail-fast |
| EX-P0-002 | P0 | `skills/reports/daily-smartmoney-analysis/scripts/daily_export_report.py:494-508` | missing group chat -> Pascal personal chat fallback | 外部消息目标错误被掩盖 | 生产发送要求显式 target_chat_id；test mode 才允许 personal |
| EX-P0-003 | P0 | `skills/data/data-pipeline/scripts/smart_money_watcher.py:145-151` | path no date -> today | 历史/补录文件审计日期错位 | 从 path 取不到日期时 fail-fast 或要求 explicit date |
| EX-P1-001 | P1 | `skills/reports/daily-market-analysis/scripts/main.py:191-192` | marker mtime exception pass | 可观测性不足 | warn 并继续 |
| EX-P1-002 | P1 | `skills/reports/daily-market-analysis/scripts/main.py:253-255` | debug branch uses undefined `report` | 显式 debug 参数破损 | interface arg smoke test |

## 7. `self_test.py` 契约

`self_test.py` 必须：

- 仅使用 Python 标准库。
- 可直接运行：`python3 skills/quality/sanity-check/scripts/self_test.py`。
- 至少覆盖：
  - unknown interface arg fail-fast；
  - missing read file fail-fast；
  - bad Decimal coercion fail-fast；
  - bad date format fail-fast；
  - Mongo unknown collection fail-fast（不真实连接 DB）。
- 成功输出：`sanity-check self-test: PASS`。
- 失败时非零退出。

## 8. 验收标准

T2 完成后必须满足：

- [ ] 5 个 skill 文件存在：`SKILL.md`、3 个 references、`scripts/self_test.py`。
- [ ] `SKILL.md` frontmatter 可被 Hermes skill loader 解析。
- [ ] `templates.md` 包含本 SPEC 六个模板的完整代码，且模板名完全一致。
- [ ] `fail-fast-vs-warn.md` 包含 §4 决策表等价内容。
- [ ] `examples.md` 至少包含 3 条 P0 反例，带文件:行号。
- [ ] `python3 skills/quality/sanity-check/scripts/self_test.py` exit 0。
- [ ] 不修改历史业务代码，不新增依赖，不连接真实 MongoDB，不发送外部消息。

## 9. 残余风险

| 风险 | 等级 | 处理 |
|---|---|---|
| 反例目录可能让 T2 误修历史代码 | Medium | DESIGN 明确 T2 禁止修改历史业务代码 |
| Mongo 模板 optional pymongo 在某些 profile 不可用 | Low | self_test 不 require ping；真实使用时才 optional import |
| 模板代码复制后可能与项目风格不完全一致 | Low | Skill 标注“copy-paste baseline”，允许具体项目适配但不得弱化 fail-fast 语义 |
