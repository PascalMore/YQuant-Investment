# RFC-03-005: Smart Money Batch Closeout

## 元数据（Metadata）
| 项 | 值 |
|---|---|
| 状态 | Published |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-16 |
| 最后更新 | 2026-06-16 |
| 所属模块 | data |
| 依赖RFC | RFC-03-004 |
| 替代RFC | 无 |
| AI适配 | OpenClaw/Codex |
| 标签 | #数据管道 #批次汇总 #人工确认 #closeout #飞书 |

## 1. 执行摘要（Executive Summary）

Smart Money Image/Message Pipeline 已具备单文件处理、pending review 和批次 summary 的基础能力，但当前批量扫描结束后缺少强制 closeout：用户连续发送多张图片后，系统只完成入库和日志输出，没有主动把批次结果整理成聊天确认点。

本 RFC 定义“批次结束 closeout + 主动确认点汇报”闭环：每次批量处理结束必须生成标准 closeout，汇总总文件数、成功/失败/partial 状态、MongoDB 入库计数、pending/needs_confirmation 明细，并形成面向用户的明确确认问题。代码侧只负责生成结构化报告和格式化文本；聊天发送由 Orchestrator 使用该文本执行。

## 2. 背景与动机（Background & Motivation）

03-004 解决了高风险证券身份进入 pending、正常记录继续入库、批次结果可汇总的问题。但实际使用中仍出现运营缺口：

- 用户连续发送 6 张图片后，pipeline 完成处理但没有批量 closeout。
- 没有主动在聊天中报告“哪些已入库、哪些失败、哪些需要确认”。
- pending review 与 `needs_confirmation` 没有被提升为用户必须回答的问题。
- Orchestrator 缺少稳定的、可直接转发给用户的 closeout 文本契约。

量化数据管道的风险不只在“是否写库成功”，还在“用户是否知道当前批次是否完全可信”。因此批次处理必须以 closeout 作为闭环终点，而不是以最后一个文件处理完成作为隐式终点。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

- [x] 每次批量处理结束必须生成 batch closeout。
- [x] closeout 必须汇总：
  - 总文件数；
  - `success/partial_success/failed/pending_review/dry_run` 数量；
  - accepted rows、pending rows；
  - MongoDB 各集合入库计数；
  - 失败文件及错误；
  - pending/needs_confirmation 项及审计文件路径。
- [x] closeout 必须包含面向用户的明确确认问题，而不是只输出技术日志。
- [x] pending 或 partial 场景必须明确提示“哪些项目需要确认后才能视为完成”。
- [x] 无 pending/failed 场景也必须给出“本批次是否确认完成归档”的确认点。
- [x] Orchestrator 可直接使用格式化文本发送聊天消息，不需要理解内部 result 细节。

### 3.2 非目标（Out of Scope）

- [ ] 本次不实现交互式审核 UI。
- [ ] 本次不调用 Feishu、Telegram、企业微信或其他外部聊天 API。
- [ ] 本次不直接修改 MongoDB 历史数据。
- [ ] 本次不新增 MongoDB pending 集合或改变正式集合 schema。
- [ ] 本次不实现 pending 人工确认后的补录流程。
- [ ] 本次不改变 OCR、Transformer、Validator、Loader 的核心业务逻辑。

## 4. 业务边界（Business Boundary）

### 4.1 批次定义

批次指一次由 watcher 或 Orchestrator 触发的多文件处理窗口，典型来源包括：

- `smart_money_watcher.py --once <date>`；
- `smart_money_watcher.py --scan-all`；
- Orchestrator 对一组图片或消息文本的显式批量调用。

实时 daemon 模式下单个新增文件也可形成一个单文件批次，但本 RFC 的最低实现范围优先覆盖 `--once/--scan-all` 等明确有结束点的批量扫描路径。

#### 4.1.1 YQuant Feishu Handler 触发

在 YQuant 飞书会话中，用户发送图片后跟一句「图片批次已上传」或等效结束语。YQuant 检测到该关键词后：

1. 调用 `image_batch_state.close_batch_now()` 获取本批次 closeout dict
2. 通过 OpenClaw message tool 发送 `closeout["message_text"]` 给用户
3. 等待用户确认后处理 pending 项（如有）

触发关键词（`BATCH_END_PHRASES`）：

```
图片批次已上传 / 就这些 / 处理完了 / 发完了 / 没有了
```

closeout 发送后，用户可回复「确认归档」「重试失败文件」「处理 pending」等指令。

该会话批次不是新的图片处理管道，也不改变单张图片处理主流程。每张图片仍独立 OCR、标准化、校验和入库；批次层只负责累积每张图片返回的 result，并在显式结束语出现后做汇总 closeout。本阶段不采用 30s 无新图片自动关闭批次。

### 4.2 Closeout 的完成条件

批次 closeout 生成不等于业务完全完成。应区分：

- `closed_clean`: 全部文件成功，无 pending，无 failed，可建议用户确认归档。
- `closed_needs_confirmation`: 存在 pending/needs_confirmation/partial，需要用户确认后才能补录或关闭风险项。
- `closed_with_failures`: 存在 failed，需要用户决定重试、忽略或人工处理。
- `closed_dry_run`: dry-run 批次完成，仅用于验证，不代表正式入库完成。

### 4.3 确认点语义

closeout 必须给用户一个可回答的问题，例如：

- “本批次 6 个文件已处理完成，其中 5 个成功、1 个 partial，待确认 2 行。请确认：是否按 pending CSV 中的证券身份修正后补录，还是暂不入库？”
- “本批次 6 个文件全部成功入库，无 pending/failed。请确认：是否将本批次标记为已复核完成？”

确认问题必须出现在格式化文本末尾，便于 Orchestrator 直接发送给用户。

## 5. 整体设计（Overall Design）

### 5.1 核心设计哲学

批次处理必须以“可审计 closeout”结束。日志是给系统看的，closeout 是给用户和 Orchestrator 做决策的。

### 5.2 架构总览

```text
Image/Message files
  -> per-file pipeline result
  -> summarize_batch_results(results)
  -> build_batch_closeout(summary)
  -> format_batch_closeout(closeout)
  -> watcher stdout/log + return object
  -> Orchestrator sends formatted text to chat
```

### 5.3 模块分工

- `batch_report.py`: 汇总 per-file results，构造 batch closeout 结构，并格式化用户确认文本。
- `smart_money_watcher.py`: 在批量扫描结束后生成 closeout，并把格式化文本打印/记录/返回给调用者。
- Orchestrator: 获取 closeout 文本并调用 OpenClaw message tool 发送到当前聊天。

## 6. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| closeout 只写日志，Orchestrator 无法主动发送 | 中 | 高 | batch_report 输出明确 `message_text` 字段 | Orchestrator 可用 stdout 文本兜底 |
| pending/failed 口径不一致 | 中 | 中 | 统一由 `batch_report.py` 计算 confirmation status | 保留原 summary 字段供排查 |
| 单文件 daemon 模式频繁打扰用户 | 中 | 中 | 首阶段只强制批量扫描 closeout，daemon 后续单独设计节流 | daemon 保持原行为 |
| 文本过长影响聊天可读性 | 低 | 中 | 默认列出关键明细，长列表可截断并保留路径 | 提供完整 JSON/summary 供追溯 |

## 7. 验收标准（Acceptance Criteria）

- 批量扫描结束后可获得结构化 `batch_closeout`。
- 格式化 closeout 文本包含统计、入库计数、pending/failed 明细和明确确认问题。
- 存在 partial 或 pending 时，确认问题指向人工确认和后续补录决策。
- 无异常时，确认问题指向是否归档本批次。
- 实现不新增外部依赖，不触碰 MongoDB 历史数据，不调用外部聊天 API。

## 8. 落地计划（Implementation Plan）

1. Principal 创建 RFC/SPEC/Design。
2. Developer 最小修改 `batch_report.py`，补齐 closeout 结构与格式化函数。
3. Developer 最小修改 `smart_money_watcher.py`，批量结束时输出并返回 closeout。
4. Test Engineer 增加 batch closeout 单元测试和 watcher 批量路径验证。
5. Reviewer 独立审查 closeout 口径、兼容性和无外部 API 调用。
6. YQuant Feishu Handler 接入：在会话处理逻辑中检测批次结束关键词，调用 `image_batch_state.close_batch_now()` 并发送 `message_text`。

## 9. 开放问题（Open Questions）

- daemon 模式是否需要基于时间窗口或文件数量做合并 closeout，避免单文件频繁打扰。
- pending 确认后的补录入口是否后续扩展为专门 CLI 或 Feishu 交互命令。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-06-16 | 初始创建 | YQuant-Codex-Principal |
