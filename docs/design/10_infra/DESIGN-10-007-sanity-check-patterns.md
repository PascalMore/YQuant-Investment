# DESIGN-10-007：Sanity Check 标准模式 Skill

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-08 |
| 来源 RFC | RFC-10-007-sanity-check-patterns |
| 来源 SPEC | SPEC-10-007-sanity-check-patterns |
| 目标模块 | `skills/infra/sanity-check/` |
| Quick Flow | T1=`t_a4539961`; T2=`t_46c017a3`; T3=`t_649d0695`; T4=`t_bfcef8a4` |

## 1. 设计摘要

本 Design 将 RFC/SPEC-10-007 落为 T2 Developer 可直接执行的最小实现方案。T2 的目标不是修复历史业务代码，而是在 `skills/infra/sanity-check/` 新增一个可加载、可自测、可复制模板的 Hermes skill。

核心设计原则：

1. 标准库优先：模板代码默认不引入新依赖。
2. 明确边界：sanity check ≠ validation ≠ error handling。
3. Fail-fast 默认保守：数据写入、外部发送、危险 no-op 参数一律 loud fail。
4. 反例目录仅作教学与后续修复依据，不触发本次 T2 扩范围。

## 2. 现状证据与设计输入

### 2.1 P0 反例输入

T1 扫描确认以下 P0 反例应进入 `references/examples.md`：

| ID | 文件:行号 | 现状 | 风险 | 对应模板 |
|---|---|---|---|---|
| EX-P0-001 | `skills/data/data_interface/mongo_reader.py:67-85` | `collection_name` 默认为 `portfolio_position`，未知集合落到 `position_date` 查询 | 传错集合名时 silent wrong query | `mongo_connection_check`, `type_coercion_check` |
| EX-P0-002 | `skills/reports/daily-smartmoney-analysis/scripts/daily_export_report.py:494-508` | 群 chat id 缺失时 fallback Pascal 个人 chat id | 外部消息目标错误被掩盖 | `interface_arg_check` / env boundary |
| EX-P0-003 | `skills/data/data-pipeline/scripts/smart_money_watcher.py:145-151` | 路径无日期时 fallback 今天 | 审计日期错位 | `date_format_check`, `file_existence_check` |

P1 反例：

- `skills/reports/daily-market-analysis/scripts/main.py:191-192`：marker 读取异常后 `pass`，应 warn。
- `skills/reports/daily-market-analysis/scripts/main.py:253-255`：debug 分支引用未定义变量，显式参数应有 smoke test。

### 2.2 正例输入

`RFC/SPEC/DESIGN-10-006` 与 `scripts/upgrade/upgrade_hermes_agent.py` 已形成较成熟的 git / branch / manifest 前置检查模式。T2 可在 `templates.md` 的 `git_state_check` 中吸收其思想，但不要引用该脚本内部函数，避免 skill 与 upgrade 脚本耦合。

## 3. 精确文件清单

T2 Implement 只允许新增以下 5 个 skill 文件；不得修改历史业务代码。

1. `skills/infra/sanity-check/SKILL.md`
2. `skills/infra/sanity-check/references/templates.md`
3. `skills/infra/sanity-check/references/fail-fast-vs-warn.md`
4. `skills/infra/sanity-check/references/examples.md`
5. `skills/infra/sanity-check/scripts/self_test.py`

T1 已创建的文档文件：

1. `docs/rfc/10_infra/RFC-10-007-sanity-check-patterns.md`
2. `docs/spec/10_infra/SPEC-10-007-sanity-check-patterns.md`
3. `docs/design/10_infra/DESIGN-10-007-sanity-check-patterns.md`

T2 不应修改三层文档；若实现中发现 SPEC 不可执行，应 `kanban_block` 退回 Principal，而不是自行扩大范围。

## 4. 目录与内容设计

### 4.1 `SKILL.md`

结构：

```text
--- frontmatter ---
# Sanity Check
## When to use
## Definition
## Not validation / not error handling
## Decision tree
## Fail-fast vs warn
## Template index
## Real anti-pattern examples
## Verification
## Do not
```

关键内容：

- When to use：新增 CLI 参数、接入文件/目录、日期字段、MongoDB、git 操作、外部消息目标时加载。
- Decision tree：
  - CLI / 参数语义 → `interface_arg_check`
  - 文件读写 → `file_existence_check`
  - 字符串转数值/布尔/日期 → `type_coercion_check`
  - YQuant 日期字符串 → `date_format_check`
  - 升级 / auto-push / repo 操作 → `git_state_check`
  - MongoDB 边界 → `mongo_connection_check`
- Do not：不要 `try/except pass`，不要 fallback 今天，生产外发不要 fallback 私人 chat，未知 collection 不要 default 到持仓集合。

### 4.2 `references/templates.md`

必须包含 6 个一级或二级章节，章节标题与模板名一致：

1. `interface_arg_check`
2. `file_existence_check`
3. `type_coercion_check`
4. `date_format_check`
5. `git_state_check`
6. `mongo_connection_check`

每个章节必须包含：

- 触发条件。
- 默认决策：fail-fast 或 warn。
- 代码块：完整可复制 Python 示例。
- 错误消息示例。
- 真实反例引用。
- “适配注意”：如何在具体项目中改 allowed list / env name / branch name。

代码来源以 SPEC-10-007 §5 为准，T2 可以重排到 reference 文件中，但不得弱化以下语义：

- unknown option / dangerous no-op arg fail-fast；
- write path parent 不可写 fail-fast；
- type/date coercion 失败 fail-fast；
- unknown Mongo collection fail-fast；
- production write DB 不匹配 fail-fast。

### 4.3 `references/fail-fast-vs-warn.md`

必须包含：

```text
# Fail-fast vs Warn-and-Continue
## Golden rule
## Decision table
## P0 / P1 / P2 classification
## Error message format
## Examples
```

Golden rule：

```text
Silent wrong output is worse than absent output.
If the user cannot notice the mistake before data write / outbound send / audit boundary, fail-fast.
```

P0/P1/P2：

| 等级 | 定义 | 默认动作 |
|---|---|---|
| P0 | 生产数据、外部发送、交易/风控、安全边界可能被污染 | fail-fast |
| P1 | 调试、审计、可观测性、复盘质量受影响 | warn 或显式请求时 fail-fast |
| P2 | 风格、提示文案、非关键 best-effort | warn |

### 4.4 `references/examples.md`

必须包含：

```text
# Real Anti-pattern Examples
## P0 examples
## P1 examples
## How to use these examples
## Not a fix list
```

P0 examples 至少列入 DESIGN §2.1 的 3 条。每条格式：

```markdown
### EX-P0-001 — Unknown Mongo collection silently defaults to position_date
- Location: `skills/data/data_interface/mongo_reader.py:67-85`
- Pattern: unknown collection -> `{'position_date': date}`
- Why it is dangerous: ...
- Template: `mongo_connection_check`
- Fix direction: collection allowlist + explicit error
- Scope note: example only; do not fix in sanity-check skill implementation.
```

### 4.5 `scripts/self_test.py`

实现策略：

- 该脚本可以内联最小版模板函数，不必从 markdown 中抽取代码。
- 不依赖 pytest；使用 `assert` 和 helper `expect_error()`。
- 只验证核心行为，不连接真实 MongoDB。
- 成功时打印 `sanity-check self-test: PASS`。

伪代码：

```python
#!/usr/bin/env python3
from pathlib import Path
from decimal import Decimal
import tempfile

class SanityCheckError(ValueError):
    pass

# include minimal template functions here

def expect_error(fn, label):
    try:
        fn()
    except SanityCheckError:
        return
    raise AssertionError(f"expected SanityCheckError: {label}")


def main():
    expect_error(lambda: interface_arg_check([...]), "noop arg")
    expect_error(lambda: file_existence_check("/no/such/file", mode="read-file", purpose="input"), "missing file")
    expect_error(lambda: type_coercion_check("abc", field="amount", converter=Decimal, expected="decimal"), "bad decimal")
    expect_error(lambda: date_format_check("20260708", field="position_date"), "bad date")
    expect_error(lambda: mongo_connection_check(... unknown collection ...), "unknown collection")
    print("sanity-check self-test: PASS")

if __name__ == "__main__":
    main()
```

## 5. 实现顺序

T2 推荐顺序：

1. 创建目录：`skills/infra/sanity-check/{references,scripts}`。
2. 写 `SKILL.md`，先保证 Hermes skill metadata 可解析。
3. 写 `references/templates.md`，从 SPEC §5 搬运并整理 6 个模板。
4. 写 `references/fail-fast-vs-warn.md`。
5. 写 `references/examples.md`，录入 3 条 P0 + 2 条 P1。
6. 写 `scripts/self_test.py`。
7. 运行 `python3 skills/infra/sanity-check/scripts/self_test.py`。
8. 可选运行 `hermes -p yquantdeveloper chat --skills sanity-check -q '只回复 OK'` 验证 skill loader；如果环境不允许，至少用文件存在 + self_test 替代。

## 6. 验证计划

T2 自检：

```bash
cd /home/pascal/workspace/yquant-investment
python3 skills/infra/sanity-check/scripts/self_test.py
python3 - <<'PY'
from pathlib import Path
required = [
  'skills/infra/sanity-check/SKILL.md',
  'skills/infra/sanity-check/references/templates.md',
  'skills/infra/sanity-check/references/fail-fast-vs-warn.md',
  'skills/infra/sanity-check/references/examples.md',
  'skills/infra/sanity-check/scripts/self_test.py',
]
for p in required:
    assert Path(p).exists(), p
print('files: PASS')
PY
```

T3 Verify 必须：

- 重跑 self_test。
- 检查 `SKILL.md` frontmatter。
- grep/读取确认 6 个模板名均出现。
- 检查 `examples.md` 至少包含 `EX-P0-001` / `EX-P0-002` / `EX-P0-003`。
- 确认 `git diff --stat` 只包含允许文件，不含历史业务代码修改。

## 7. 回滚方案

因为 T2 只新增 isolated skill 文件，回滚方式简单：

```bash
rm -rf skills/infra/sanity-check
```

若 T2 意外修改历史业务代码，Reviewer / Closeout 应要求回滚越界 diff，只保留本 Design §3 文件清单内的新增文件。

## 8. 与 AI Coding Pipeline 的衔接

Quick Flow 链：

```text
T1 RFC/SPEC/Design  yquantprincipal  t_a4539961
T2 Implement        yquantdeveloper  t_46c017a3   parents=[T1]
T3 Verify           yquanttester     t_649d0695   parents=[T1,T2]
T4 Closeout         yquant           t_bfcef8a4   parents=[T1,T2,T3]
```

注意：如果当前 Kanban parent links 因 P-27 占位符问题不完整，orchestrator 需要在 Closeout 自审记录并补链；T2/T3 worker 不应自行修改 Kanban DB 状态。

## 9. T2 Handoff 要求

T2 完成时 summary / metadata 应包含：

```json
{
  "changed_files": [
    "skills/infra/sanity-check/SKILL.md",
    "skills/infra/sanity-check/references/templates.md",
    "skills/infra/sanity-check/references/fail-fast-vs-warn.md",
    "skills/infra/sanity-check/references/examples.md",
    "skills/infra/sanity-check/scripts/self_test.py"
  ],
  "tests": {
    "self_test": "python3 skills/infra/sanity-check/scripts/self_test.py"
  },
  "scope_guard": "historical business code not modified"
}
```

完成后状态选择：验收 PASS 直接 `kanban_complete`；不要因“后续可修历史反例”而 block。历史反例是非阻塞后续工作，进入 residual risks / follow-up 建议。

## 10. 验收标准映射

| 验收项 | 验证方式 |
|---|---|
| 三层文档存在 | `test -f docs/rfc/... && test -f docs/spec/... && test -f docs/design/...` |
| 6 个模板完整 | 读取 `templates.md`，确认 6 个模板名、代码块和错误消息格式 |
| Fail-fast vs warn 决策表 | 读取 `references/fail-fast-vs-warn.md` |
| 至少 3 条 P0 反例 | 读取 `references/examples.md`，确认 EX-P0-001/002/003 |
| self_test 通过 | `python3 skills/infra/sanity-check/scripts/self_test.py` exit 0 |
| 无越界修改 | `git diff --name-only` 只包含 Design §3 允许文件 + T1 文档 |

## 11. 残余风险

| 风险 | 等级 | 处理 |
|---|---|---|
| 本 skill 只提供模板，不强制历史代码迁移 | Low | 后续可按 examples 单独派修复任务 |
| optional Mongo ping 在无 pymongo 环境不可跑 | Low | 默认 self_test 不 require ping，真实边界再启用 |
| Worker 可能把 examples 当修复清单 | Medium | `examples.md` 与本 Design 明确 Not a fix list |
