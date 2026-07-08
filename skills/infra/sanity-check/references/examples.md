# Real Anti-pattern Examples

本目录收录 YQuant 项目中真实存在的 sanity check 反模式，作为教学和后续修复依据。

**重要：本目录不是 T2 修复清单。** sanity-check skill 只提供模板，不强制历史代码迁移。历史反例的修复应作为独立 follow-up 任务，按优先级单独派工。

---

## P0 examples

### EX-P0-001 — Unknown Mongo collection silently defaults to position_date

- **Location**: `skills/data/data_interface/mongo_reader.py:67-85`
- **Pattern**: unknown collection name → fallback 查询 `{'position_date': date}`
- **Why it is dangerous**: 调用者传错集合名时不会 loud fail，而是可能按持仓日期字段查询错误集合，造成空结果或错结果被当作真实数据。这是典型的 silent wrong output——用户要到查询返回空或错数据后才可能发现，此时可能已经污染了下游报告或决策。
- **Template**: `mongo_connection_check`（主），`type_coercion_check`（次——collection_name 的来源应显式校验）
- **Fix direction**: collection allowlist + unknown collection fail-fast；`MongoBoundary.allowed_collections` 应来自项目实际映射，不要 default 到持仓集合。
- **Scope note**: example only; do not fix in sanity-check skill implementation.

### EX-P0-002 — Missing group chat id falls back to Pascal personal chat

- **Location**: `skills/reports/daily-smartmoney-analysis/scripts/daily_export_report.py:494-508`
- **Pattern**: 群 chat id 缺失时 fallback 到 Pascal 个人 chat id 发送报告
- **Why it is dangerous**: 外部消息 recipient 缺失属于环境配置错误；静默改发个人账号会掩盖群推送失败（运维以为群已收到，实际没有），也可能扩大敏感报告的泄露面（个人账号可能被更多人访问或审计不严）。
- **Template**: `interface_arg_check`（recipient 参数应显式校验），或 env boundary sanity check
- **Fix direction**: 生产发送要求显式 `target_chat_id`；只有 test mode（显式 flag）才允许 fallback 到 personal chat，且必须 warn。
- **Scope note**: example only; do not fix in sanity-check skill implementation.

### EX-P0-003 — Path with no date silently falls back to today

- **Location**: `skills/data/data-pipeline/scripts/smart_money_watcher.py:145-151`
- **Pattern**: 从文件路径提取不到日期时 fallback 到 `datetime.now()`
- **Why it is dangerous**: 历史补录文件（OCR 图片、消息文本）的审计日期应由路径或显式参数决定。静默 fallback 今天会导致 OCR/解析结果写入今天目录，审计日期错位，后续复盘或回补时找不到正确时间线。
- **Template**: `date_format_check`（主），`file_existence_check`（次——路径应显式校验）
- **Fix direction**: 从 path 取不到日期时 fail-fast 或要求调用方传 explicit date；不要用 `kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))`。
- **Scope note**: example only; do not fix in sanity-check skill implementation.

---

## P1 examples

### EX-P1-001 — Marker mtime read exception swallowed by pass

- **Location**: `skills/reports/daily-market-analysis/scripts/main.py:191-192`
- **Pattern**: 读取 marker 文件 mtime 时 `try: ... except: pass`
- **Why it is a problem**: 错误被吞掉，可观测性不足。如果 marker 文件权限错误或路径漂移，运维无法及时察觉，复盘时才发现数据更新时间戳缺失。
- **Template**: 应改为 warn（`[SanityWarn:...]`），保留 best-effort 但留下痕迹。
- **Fix direction**: `except OSError as exc: warn(...)`，不要 `pass`。
- **Scope note**: example only; do not fix in sanity-check skill implementation.

### EX-P1-002 — Debug branch references undefined variable

- **Location**: `skills/reports/daily-market-analysis/scripts/main.py:253-255`
- **Pattern**: `--debug` 分支引用 `report` 变量，但该变量在分支上下文未定义
- **Why it is a problem**: 显式 debug 参数被消费了（argparse 有定义），但实现层破损。用户以为 debug 生效，实际会在边缘路径崩溃或 no-op。这是 interface arg 缺 smoke test 的典型症状。
- **Template**: `interface_arg_check`（ArgRule implemented 检查）
- **Fix direction**: 给 debug 参数加最小 smoke test，确保 implemented=True 时分支真的能跑通。
- **Scope note**: example only; do not fix in sanity-check skill implementation.

---

## How to use these examples

1. **教学**：worker 加载 sanity-check skill 时，通过 examples 理解每个模板要防什么。
2. **自检**：新写代码前，快速对照 examples 看是否在重蹈覆辙。
3. **修复优先级参考**：如果未来派独立修复任务，P0 优先于 P1。

## Not a fix list

这些反例在 T2 Implement 阶段**不修复**。原因：

- T2 的 scope 是创建 skill 模板，不是重构历史代码。
- 历史代码修复涉及业务逻辑验证，应作为独立 follow-up 任务，经 RFC/SPEC 流程。
- 批量修复会增加回归风险，应逐个评估。

如果你（worker）发现自己在本 skill 实现过程中"顺手"修改了 `mongo_reader.py` / `daily_export_report.py` / `smart_money_watcher.py` 等历史文件，立即停止——这超出 T2 scope。正确做法是把发现记入 comment，留给 orchestrator 决定是否派 follow-up。
