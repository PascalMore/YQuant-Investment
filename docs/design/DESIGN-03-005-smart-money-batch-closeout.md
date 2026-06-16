# DESIGN-03-005: Smart Money Batch Closeout

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Published |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-16 |
| 最后更新 | 2026-06-16 |
| 来源 RFC | RFC-03-005 |
| 来源 SPEC | SPEC-03-005 |
| 目标模块 | data-pipeline |

## 1. 设计摘要

本设计在现有 Smart Money pipeline 的批次汇总之后增加 closeout 层。最小实现只修改 `batch_report.py` 和 `smart_money_watcher.py`：前者负责从 summary 构造结构化 closeout 和用户可读确认文本，后者负责在批量扫描结束时输出/返回 closeout。

本设计不新增依赖、不修改 MongoDB 历史数据、不调用外部聊天 API。聊天发送由 YQuant Orchestrator 获取格式化文本后执行。

## 2. 现状分析

### 2.1 已有能力

- `batch_report.py` 已提供：
  - `summarize_batch_results(results) -> dict`
  - `format_batch_summary(summary) -> str`
- `smart_money_watcher.py` 已在 `process_existing_files` 结束后：
  - 收集每个文件的 result；
  - 对异常项追加 `status=failed`；
  - 调用 `summarize_batch_results`；
  - 用 logger 输出 `format_batch_summary(summary)`。

### 2.2 缺口

- `format_batch_summary` 仍偏技术日志，不构成用户 closeout。
- summary 没有显式 `confirmation` 结构。
- 没有 `message_text` 字段供 Orchestrator 直接发送。
- pending/partial/failed 没有被统一转成用户必须回答的问题。
- `--once` 当前逐文件打印 result，缺少最后一段面向用户的汇总确认文本。

## 3. 最小实现范围

### 3.1 文件改动

| 文件 | 必须改动 | 禁止改动 |
|---|---|---|
| `skills/data/data-pipeline/scripts/batch_report.py` | 新增 closeout 构造与格式化；保留旧 summary 兼容 | 不引入新依赖 |
| `skills/data/data-pipeline/scripts/smart_money_watcher.py` | 批量结束输出/返回 closeout 文本 | 不调用聊天 API，不改 daemon 复杂逻辑 |

如测试文件已存在，允许新增或扩展 batch_report/watcher 相关测试；不要求修改 OCR、loader、transformer。

### 3.2 不做事项

- 不新增 MongoDB 集合。
- 不更新历史记录。
- 不修改 pending 文件格式。
- 不新增 Feishu/Telegram/OpenClaw message 调用。
- 不引入异步队列、cron 或持久化 batch state。

## 4. 详细设计

### 4.1 `batch_report.py`

保留现有函数：

```python
def summarize_batch_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    ...


def format_batch_summary(summary: dict[str, Any]) -> str:
    ...
```

新增函数：

```python
def build_batch_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    """Build user-actionable closeout from a batch summary."""


def format_batch_closeout(closeout: dict[str, Any]) -> str:
    """Format closeout text for Orchestrator chat delivery."""
```

建议让 `format_batch_summary(summary)` 委托新函数：

```python
def format_batch_summary(summary: dict[str, Any]) -> str:
    closeout = build_batch_closeout(summary)
    return format_batch_closeout(closeout)
```

这样旧调用方自动获得确认问题，同时避免维护两套文案。

### 4.2 closeout 构造逻辑

伪代码：

```python
def build_batch_closeout(summary):
    totals = {
        "files": summary.get("total", 0),
        "success": summary.get("success", 0),
        "partial_success": summary.get("partial_success", 0),
        "pending_review": summary.get("pending_review", 0),
        "failed": summary.get("failed", 0),
        "dry_run": summary.get("dry_run", 0),
        "accepted_rows": summary.get("accepted_rows", 0),
        "pending_rows": summary.get("pending_rows", 0),
    }
    needs_confirmation_items = [
        normalize_pending_item(item)
        for item in summary.get("items", [])
        if (item.get("pending_rows") or 0) > 0
        or item.get("status") in {"partial_success", "pending_review"}
    ]
    failed_items = [
        normalize_failed_item(item)
        for item in summary.get("items", [])
        if item.get("status") == "failed" or item.get("error")
    ]
    status, confirmation = classify_closeout(totals, needs_confirmation_items, failed_items)
    closeout = {...}
    closeout["message_text"] = format_batch_closeout(closeout)
    return closeout
```

注意避免 `build_batch_closeout` 与 `format_batch_closeout` 互相递归。可先构造不含 `message_text` 的 dict，再调用 formatter 填入。

### 4.3 状态分类

推荐私有 helper：

```python
def _classify_confirmation(totals, needs_confirmation_items, failed_items):
    if totals["files"] == 0:
        return "closed_empty", {...}
    if failed_items:
        return "closed_with_failures", {...}
    if needs_confirmation_items or totals["pending_rows"] > 0:
        return "closed_needs_confirmation", {...}
    if totals["dry_run"] > 0:
        return "closed_dry_run", {...}
    return "closed_clean", {...}
```

确认问题文案应由状态决定：

| 状态 | 确认问题 |
|---|---|
| `closed_clean` | “本批次已全部成功入库且无 pending/failed。请确认：是否将本批次标记为已复核完成？” |
| `closed_needs_confirmation` | “本批次仍有 N 行需要人工确认。请确认：是否按 pending 文件修正后补录，还是暂不入库并保留为待处理？” |
| `closed_with_failures` | “本批次有 N 个文件处理失败。请确认：是否重试失败文件，还是忽略并关闭本批次？” |
| `closed_dry_run` | “本批次为 dry-run，未执行正式入库。请确认：是否按该结果执行正式入库流程？” |
| `closed_empty` | “本批次未发现待处理文件，无需确认。” |

### 4.4 文本格式

`format_batch_closeout` 输出中文专业风格，保持简洁：

```text
Smart Money 批次处理 Closeout

状态：closed_needs_confirmation
文件：total=6, success=5, partial_success=1, pending_review=0, failed=0, dry_run=0
行数：accepted=22, pending=2
入库：portfolio_position=18, portfolio_trade=4

待确认：
- /path/a.png: pending_rows=2, csv=/path/a.csv

确认问题：本批次仍有 2 行需要人工确认。请确认：是否按 pending 文件修正后补录，还是暂不入库并保留为待处理？
```

长列表处理：

- 默认列出前 10 个 pending/failed 项。
- 超过 10 个时追加 `... 还有 N 项未显示`。
- 不丢弃结构化 `needs_confirmation_items/failed_items` 中的完整明细。

### 4.5 `smart_money_watcher.py`

当前：

```python
summary = summarize_batch_results(results)
logger.info("\n%s", format_batch_summary(summary))
return results
```

目标：

```python
summary = summarize_batch_results(results)
closeout = build_batch_closeout(summary)
logger.info("\n%s", closeout["message_text"])
return {
    "results": results,
    "summary": summary,
    "closeout": closeout,
}
```

如果为了兼容先不改变 `process_existing_files` 返回类型，则至少：

```python
summary = summarize_batch_results(results)
closeout = build_batch_closeout(summary)
logger.info("\n%s", closeout["message_text"])
print(closeout["message_text"])
return results
```

推荐升级返回 dict，并同步 `main()` 中 `--once/--scan-all` 的打印逻辑：

```python
batch = loop.run_until_complete(process_existing_files(processed_files))
for result in batch["results"]:
    print(f"✅ {result}")
print()
print(batch["closeout"]["message_text"])
```

这样 Orchestrator 和人工 CLI 都能看到同一 closeout。

## 5. 测试策略

### 5.1 单元测试

重点覆盖 `batch_report.py`：

- `test_build_batch_closeout_clean`
- `test_build_batch_closeout_pending_confirmation`
- `test_build_batch_closeout_failed`
- `test_build_batch_closeout_dry_run`
- `test_build_batch_closeout_empty`
- `test_format_batch_closeout_includes_confirmation_question`

每个测试直接构造 summary dict，不依赖真实 OCR/MongoDB。

### 5.2 watcher 测试

可用 monkeypatch：

- mock `scan_existing_files` 返回两个路径；
- mock `PortfolioPipeline.process_image/process_message` 返回固定 result；
- 验证 `process_existing_files` 返回或输出包含 `closeout`。

如当前测试体系尚未覆盖 watcher，可先把验收集中在 `batch_report.py`，并在 PR 描述中说明 watcher 采用人工 CLI 验证。

### 4.6 YQuant Feishu Handler 集成

在 YQuant 的飞书消息处理入口，图片处理后调用 `image_batch_state.add_image_result(result)` 累积结果。

当检测到用户消息包含触发词时，调用 `close_batch_now()` 获取 closeout，发送 `message_text` 到飞书。

本阶段采用显式结束语方案，不做自动时间窗口合并。图片仍然沿用原有单张处理主流程；“批次”只是在会话状态中累积多个单张处理结果，直到用户发送结束语。

#### 触发词检测
```python
BATCH_END_PHRASES = [
    "图片批次已上传",
    "就这些",
    "处理完了",
    "发完了",
    "没有了",
]

def is_batch_end(message: str) -> bool:
    return any(phrase in message for phrase in BATCH_END_PHRASES)
```

#### 会话处理伪代码
```python
# 每条图片消息处理后：
add_image_result(pipeline_result)

# 用户发送触发词时：
closeout = close_batch_now()
if closeout:
    await message_tool.send(closeout["message_text"])
```

#### 集成位置
YQuant Feishu Handler 消息处理循环（message loop）

#### 依赖模块
- `image_batch_state.close_batch_now()`
- `image_batch_state.add_image_result(result)`

#### 发送方式
OpenClaw message tool（`message_text` 字段内容）

#### 约束
- YQuant Handler 发送消息前需先调用 `add_image_result` 累积本次会话的所有图片结果
- 如果累积结果为空（用户只发触发词，没有发图片），`close_batch_now()` 返回 None，此时不发送消息
- 触发词检测大小写不敏感
- 不启用 30s timer 或“无新图片自动 closeout”；结束点由用户显式消息决定

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 返回类型改变影响调用方 | 同步 `main()`；必要时保留返回 list，只输出 closeout | 回退为仅 logger/print closeout |
| 文案过长 | 限制显示前 10 项，结构化字段保留完整数据 | 临时只显示统计和文件路径 |
| dry_run 旧 summary 无字段 | `summary.get("dry_run", 0)` 兼容 | 不影响旧数据 |
| Orchestrator 未发送消息 | data-pipeline 仍输出 `message_text`，由上层补发送 | 人工复制 stdout 文本 |

## 7. 交接给实现者

### 7.1 必须遵守

- 以 `SPEC-03-005` 为直接契约。
- 优先只改 `batch_report.py` 和 `smart_money_watcher.py`。
- 不新增外部依赖。
- 不触碰 MongoDB 历史数据。
- 不在 data-pipeline 层调用外部聊天 API。
- 保持 03-004 pending review 语义不变。

### 7.2 可自行判断

- closeout 文案的精简程度。
- 是否将 `format_batch_summary` 直接升级为 closeout 文本。
- `process_existing_files` 返回 list 还是 dict；若改为 dict，必须同步 `main()`。

### 7.3 退回 Principal 的情况

- 需要定义 Feishu 交互按钮或消息卡片。
- 需要持久化 batch closeout 到数据库。
- 需要实现 pending 确认后的自动补录。
- daemon 模式需要复杂的时间窗口合并与防打扰策略。
