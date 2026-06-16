# SPEC-03-005: Smart Money Batch Closeout

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Published |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-16 |
| 最后更新 | 2026-06-16 |
| 来源 RFC | RFC-03-005 |
| 目标模块 | data-pipeline |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

## 1. 需求摘要

本 SPEC 定义 Smart Money Image/Message Pipeline 的批次 closeout 输出契约。批量处理结束后，系统必须生成一个结构化 `batch_closeout` 和一段可直接发送给用户的 `message_text`，用于主动汇报本批次处理结果并提出明确确认问题。

本 SPEC 不要求代码直接发送聊天消息；发送动作由 Orchestrator 使用 `message_text` 执行。

## 2. 范围

### 2.1 In Scope

- [x] `batch_report.py` 的批次 closeout 结构化输出。
- [x] `batch_report.py` 的用户可读 closeout 文本格式化。
- [x] `smart_money_watcher.py --once/--scan-all` 批量结束后的 closeout 输出与返回。
- [x] pending、partial、failed、dry-run、全成功场景的确认点生成。
- [x] 单元测试覆盖 batch closeout 统计和确认问题。
- [x] YQuant Feishu Handler 检测「图片批次已上传」等触发词，调用 `close_batch_now()` 并发送 `message_text`。

### 2.2 Out of Scope

- [ ] Feishu/Telegram/企业微信 API 调用。
- [ ] OpenClaw `message` tool 调用。
- [ ] MongoDB 历史数据修改。
- [ ] pending 人工确认后的补录 CLI/UI。
- [ ] watcher daemon 模式的批次窗口、节流和合并推送。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 汇总批次 closeout | `list[pipeline_result]` | `batch_closeout` | 空列表也返回 closeout，状态为 `closed_clean` 或 `closed_empty` |
| F-002 | 识别待确认项 | result 含 `pending_rows > 0` 或 `pending` | `needs_confirmation_items` | `partial_success/pending_review` 必须进入确认列表 |
| F-003 | 识别失败项 | result `status=failed` 或含 `error` | `failed_items` | 错误消息保留但不抛出 |
| F-004 | 汇总入库计数 | result `mongodb` dict | `mongodb_counts` | 仅累加 int 值，非 int 忽略 |
| F-005 | 生成确认状态 | summary + issues | `confirmation.status` | 见 4.3 |
| F-006 | 生成确认问题 | closeout | `confirmation.question` | 必须是面向用户的明确问题 |
| F-007 | 格式化聊天文本 | `batch_closeout` | `message_text` | 不包含外部 API 调用 |
| F-008 | watcher 批量输出 | `--once/--scan-all` | stdout/log/return 中包含 closeout | 不破坏现有逐文件打印 |
| F-009 | YQuant 检测批次结束触发词 | 用户发送包含触发词的消息 | 识别为批次结束信号 |
| F-010 | 调用 `close_batch_now()` | 批次结束信号触发 | 返回 closeout dict，含 `message_text` |
| F-011 | 发送 `message_text` 到飞书 | 收到 closeout dict | 通过 OpenClaw message tool 发送 |
| F-012 | 确认后处理 | 用户回复确认 | 记录确认状态，处理 pending 项（如有） |

YQuant 会话中的图片批次必须采用显式结束语触发。每张图片继续按现有单图主流程处理；批次状态只累积单图 result，不引入自动 timer、不等待“无新图片 30s”。

## 4. 数据与接口契约

### 4.1 既有 summary 兼容

`summarize_batch_results(results) -> dict` 保持兼容，至少包含：

```python
{
    "total": int,
    "success": int,
    "partial_success": int,
    "pending_review": int,
    "failed": int,
    "dry_run": int,              # 可新增，缺省为 0
    "accepted_rows": int,
    "pending_rows": int,
    "mongodb": dict[str, int],
    "items": list[dict],
}
```

`items[]` 建议字段：

```python
{
    "source": str | None,
    "type": "image" | "message" | None,
    "format": str | None,
    "status": str,
    "rows": int | None,
    "accepted_rows": int | None,
    "pending_rows": int | None,
    "pending_files": {"csv": str, "json": str},
    "error": str | None,
}
```

### 4.2 新增 closeout 函数

必须新增或等价提供以下函数：

```python
def build_batch_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    """Build structured batch closeout from batch summary."""


def format_batch_closeout(closeout: dict[str, Any]) -> str:
    """Format closeout as user-facing text with an explicit confirmation question."""
```

允许保留 `format_batch_summary(summary)`，但它应：

- 继续兼容旧调用；
- 或内部委托到 `build_batch_closeout` + `format_batch_closeout`；
- 不再只输出技术 summary 而缺少确认问题。

### 4.3 `batch_closeout` 字段契约

```python
{
    "kind": "smart_money_batch_closeout",
    "status": "closed_clean" | "closed_needs_confirmation" | "closed_with_failures" | "closed_dry_run" | "closed_empty",
    "totals": {
        "files": int,
        "success": int,
        "partial_success": int,
        "pending_review": int,
        "failed": int,
        "dry_run": int,
        "accepted_rows": int,
        "pending_rows": int,
    },
    "mongodb_counts": dict[str, int],
    "needs_confirmation_items": [
        {
            "source": str | None,
            "status": str,
            "pending_rows": int,
            "pending_files": {"csv": str | None, "json": str | None},
            "reason": str | None,
        }
    ],
    "failed_items": [
        {
            "source": str | None,
            "status": "failed",
            "error": str | None,
        }
    ],
    "confirmation": {
        "required": bool,
        "reason": "pending_review" | "failed" | "clean_closeout" | "dry_run" | "empty_batch",
        "question": str,
        "expected_user_action": "confirm_archive" | "confirm_pending_resolution" | "retry_or_ignore_failures" | "acknowledge_dry_run" | "none",
    },
    "message_text": str,
}
```

### 4.4 状态判定规则

| 条件 | `status` | `confirmation.required` | `expected_user_action` |
|---|---|---:|---|
| `total == 0` | `closed_empty` | false | `none` |
| `dry_run > 0` 且无 failed/pending | `closed_dry_run` | true | `acknowledge_dry_run` |
| `failed > 0` | `closed_with_failures` | true | `retry_or_ignore_failures` |
| `pending_rows > 0` 或 `partial_success > 0` 或 `pending_review > 0` | `closed_needs_confirmation` | true | `confirm_pending_resolution` |
| 无 failed/pending/partial | `closed_clean` | true | `confirm_archive` |

如多个条件同时满足，优先级为：

1. `closed_empty`
2. `closed_with_failures`
3. `closed_needs_confirmation`
4. `closed_dry_run`
5. `closed_clean`

### 4.5 `message_text` 格式要求

格式化文本必须包含：

- 标题：`Smart Money 批次处理 Closeout`
- 批次状态；
- 文件统计；
- 入库计数；
- pending/needs_confirmation 明细；
- failed 明细；
- 明确确认问题。

示例：

```text
Smart Money 批次处理 Closeout

状态：closed_needs_confirmation
文件：total=6, success=5, partial_success=1, pending_review=0, failed=0
入库：portfolio_position=18, portfolio_trade=4
行数：accepted=22, pending=2

待确认：
- /path/a.png: pending_rows=2, csv=/path/review_pending/a.csv

确认问题：本批次仍有 2 行需要人工确认。请确认：是否按 pending CSV 修正后补录，还是暂不入库并保留为待处理？
```

## 5. watcher 契约

`smart_money_watcher.py` 的批量路径必须满足：

- `process_existing_files(...)` 在处理完扫描列表后构造 summary 和 closeout。
- stdout 或 logger 输出 `format_batch_closeout(closeout)`。
- 返回值应保持兼容；允许从 `list[dict]` 升级为包含结果和 closeout 的 dict，但若改签名必须同步调用点。
- `--once` 和 `--scan-all` 结束时用户能看到 closeout 文本。

推荐返回结构：

```python
{
    "results": list[dict],
    "summary": dict[str, Any],
    "closeout": dict[str, Any],
}
```

若为降低改动保持返回 `results`，则至少需把 closeout 写入日志和 stdout，供 Orchestrator 捕获。

## 6. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | 全成功批次生成 `closed_clean`，且有归档确认问题 | 单元测试 |
| A-002 | partial/pending 批次生成 `closed_needs_confirmation` | 单元测试 |
| A-003 | failed 批次生成 `closed_with_failures`，失败明细保留 | 单元测试 |
| A-004 | MongoDB 入库计数正确累加 | 单元测试 |
| A-005 | `message_text` 包含标题、统计、入库、明细、确认问题 | 单元测试 |
| A-006 | watcher `--once/--scan-all` 批量结束输出 closeout | 集成或 monkeypatch 测试 |
| A-007 | 实现不调用外部聊天 API | 代码审查 |

## 7. 实现约束

- 禁止新增第三方依赖。
- 禁止触碰 MongoDB 历史数据。
- 禁止在 data-pipeline 层调用外部聊天 API。
- 禁止改变单文件 pipeline 的核心入库语义。
- 优先修改：
  - `skills/data/data-pipeline/scripts/batch_report.py`
  - `skills/data/data-pipeline/scripts/smart_money_watcher.py`
- 如需修改其他文件，必须说明原因并保持最小范围。

## 8. 测试要求

- 新增或扩展 `batch_report` 单元测试：
  - clean closeout；
  - needs confirmation；
  - failures；
  - dry-run；
  - empty batch；
  - message text 包含确认问题。
- watcher 测试可通过 monkeypatch pipeline 结果，避免真实 OCR/MongoDB。

## 9. 开放问题

- daemon 模式是否在后续增加时间窗口 closeout，例如 5 分钟无新文件后汇总推送。
