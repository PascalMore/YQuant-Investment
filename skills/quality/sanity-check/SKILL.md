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

# Sanity Check

## 何时加载本 skill

当当前任务属于以下任一场景时，优先加载本 skill：

- 新增或修改 CLI 参数、argparse 选项、`store_true` flag。
- 接入新的输入/输出文件或目录路径。
- 把字符串、env、JSON/YAML 值转换成 int/float/Decimal/bool/date。
- 处理 `YYYY-MM-DD` 业务日期字段（`position_date` / `trade_date` / `nav_date` 等）。
- 执行 git 分支 / dirty / unpushed 相关的脚本前置检查（升级、auto-push、流水线编排）。
- 连接或写入 MongoDB，特别是 `tradingagents` 库的 collection。
- 设计外部消息目标（Telegram/飞书/企业微信群），recipient 缺失属于环境配置错误。

## 一句话定义

Sanity check 是：在数据流入业务逻辑之前，对输入和环境的最后一道合理性闸门。

它不是 validation（业务规则判断），也不是 error handling（运行时异常恢复）。它的职责是尽早阻止"显然不合理、会静默污染后续状态、用户难以察觉"的输入或环境进入主流程。

## 边界：不是 validation / 不是 error handling

| 类型 | 问题 | 示例 | 所属层 |
|---|---|---|---|
| Sanity check | 输入形态或环境是否足以安全进入主逻辑 | 日期必须是 `YYYY-MM-DD` 字符串；输出路径 parent 可写；目标 collection 属于允许列表 | 本 skill |
| Validation | 业务对象是否满足业务规则 | 持仓比例在 0~1；策略信号 zone 只能从 CANDIDATE/CORE/EXIT 中选 | 业务 SPEC / schema |
| Error handling | 已进入主逻辑后的异常如何恢复 | Tushare 429 后重试；OCR 超时后走备用 provider | 运行时设计 |

如果不确定，问自己："如果这条输入/环境不对，业务逻辑会得到错结果还是直接报错？"——前者是 sanity check 的职责。

## 决策树：六个模板选哪个

```
输入到达业务逻辑边界
   │
   ├─ CLI 参数 / flag / option 语义?
   │    └─ interface_arg_check
   │
   ├─ 文件 / 目录读写路径?
   │    └─ file_existence_check
   │
   ├─ 字符串 → 数值 / 布尔 / 枚举 的显式转换?
   │    └─ type_coercion_check
   │
   ├─ YQuant 业务日期字符串 (YYYY-MM-DD)?
   │    └─ date_format_check
   │
   ├─ 升级 / auto-push / repo 操作前置条件?
   │    └─ git_state_check
   │
   └─ MongoDB 连接 / database / collection 边界?
        └─ mongo_connection_check
```

一条输入可能需要多个模板（例如 unknown Mongo collection 同时涉及 `mongo_connection_check` 和 `type_coercion_check`）。先用决策树定位主模板，再叠加次模板。

## Fail-fast vs warn（摘要）

详细决策表见 `references/fail-fast-vs-warn.md`。黄金法则：

> Silent wrong output is worse than absent output.
> If the user cannot notice the mistake before data write / outbound send / audit boundary, fail-fast.

| 等级 | 定义 | 默认动作 |
|---|---|---|
| P0 | 生产数据、外部发送、交易/风控、安全边界可能被污染 | fail-fast |
| P1 | 调试、审计、可观测性、复盘质量受影响 | warn 或显式请求时 fail-fast |
| P2 | 风格、提示文案、非关键 best-effort | warn |

## 模板索引

六个模板的完整 Python 实现、触发条件、错误消息格式、fail-fast vs warn 建议、真实反例引用，见 `references/templates.md`：

| 模板 | 用途 | 默认策略 |
|---|---|---|
| `interface_arg_check` | CLI 参数合法性、危险 no-op arg | fail-fast |
| `file_existence_check` | 文件/目录存在性、可读/可写 | 写入 fail-fast；只读可 warn |
| `type_coercion_check` | 字符串→数值/布尔/日期 | fail-fast |
| `date_format_check` | `YYYY-MM-DD` vs datetime / `YYYYMMDD` | 写入 fail-fast；只读可 warn |
| `git_state_check` | branch / dirty / unpushed | 升级类 fail-fast；只读可 warn |
| `mongo_connection_check` | connection + database + collection | 生产写入 fail-fast；dry-run 可 warn |

## 真实反例

`references/examples.md` 收录至少 3 条 P0 + 2 条 P1 真实反例，带文件:行号、风险说明和修复方向。

**重要：反例目录不是修复清单。** 本 skill 只提供模板，不强制历史代码迁移。历史反例的修复应作为独立 follow-up 任务。

## 验证

```bash
python3 skills/quality/sanity-check/scripts/self_test.py
```

成功时打印 `sanity-check self-test: PASS`，exit 0。失败时非零退出。

self_test 只验证模板核心函数的行为，不连接真实 MongoDB，不发送外部消息。

## 禁止事项（Do not）

以下写法是 sanity check 的反面，本 skill 提供的模板禁止弱化这些语义：

1. **不要 `try/except pass`（吞错）**——错误吞掉后，后续状态不可解释。
2. **不要 silent fallback 今天**——`date = kwargs.get('trade_date', datetime.now().strftime('%Y-%m-%d'))` 会造成审计日期错位。
3. **生产外发不要 fallback 私人 chat**——recipient 缺失属于环境配置错误，应 fail-fast。
4. **未知 collection 不要 default 到持仓集合**——应 collection allowlist + unknown fail-fast。
5. **不要为 no-op 参数只补文档**——危险 no-op arg 应删除或实现行为，而不是只在 README 提醒。
6. **不要 silent coercion**——`int(x)` 失败后 fallback 0 比直接报错更危险。

如果你发现自己在写以上模式，停下来，回到决策树选一个模板。
