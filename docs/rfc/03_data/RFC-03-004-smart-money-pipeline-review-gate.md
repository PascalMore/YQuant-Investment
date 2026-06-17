# RFC-03-004: Smart Money Pipeline Review Gate

## 元数据（Metadata）
| 项 | 值 |
|---|---|
| 状态 | 已采纳 |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-15 |
| 最后更新 | 2026-06-17 |
| 所属模块 | data |
| 依赖RFC | RFC-03-003 |
| 替代RFC | 无 |
| AI适配 | OpenClaw/Codex |
| 标签 | #数据管道 #OCR #人工复核 #审计 #批次汇总 |

## 1. 执行摘要（Executive Summary）

Smart Money 图片和消息入库需要从“静默修正并整张失败”升级为“低风险自动修正、高风险 pending 人工确认、正常记录继续入库”。本 RFC 定义股票代码/名称身份校验、pending 审计产物和批次汇总的业务边界。

## 2. 背景与动机（Background & Motivation）

当前 Image/Message Data Pipeline 依赖 OCR 或文本解析生成 `Wind代码` 与 `资产名称`。已有港股名称更正和 A 股代码/名称校对，但存在两个风险：

- 如果 OCR 把股票代码识别错，按错误代码查主数据再覆盖名称，会放大错误。
- 高风险修正当前缺少人工确认状态，容易在入库后才发现数据污染。

另一个运营缺口是批次级可观测性不足：一批截图通常包含多个产品和交易表，但目前只返回单张图片处理结果，缺少标准化的成功、失败、pending 汇总。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

- [x] 对股票代码/名称冲突采用保守校验：只有名称兼容时才自动更正。
- [x] 对不确定或高风险记录标记为 `pending_review`，并生成可人工确认的审计文件。
- [x] 同一输入内无问题记录继续入库，不被 pending 记录阻塞。
- [x] Image 与 Message portfolio/trade 路径共享同一套身份复核语义。
- [x] 批次处理输出标准汇总：总文件数、成功数、部分成功数、失败数、pending 文件数和 pending 明细。
- [ ] pending 记录经人工确认后，通过标准接口（`load_pending_confirmed`）补录入库，并将审计状态标记为 `resolved`。

### 3.2 非目标（Out of Scope）

- [ ] 本次不实现完整前端审核 UI。
- [ ] 本次不直接修改历史 MongoDB 数据。
- [ ] 本次不新增外部依赖或更换 OCR 模型。
- [ ] 本次不改变真实交易或组合决策逻辑。
- [ ] 本次不实现 Feishu 交互式确认或 Web UI 确认入口（未来可扩展）。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

把“证券身份不确定性”作为数据治理状态，而不是异常；正常数据走直通路径，高风险数据进入人工复核路径。

### 4.2 架构总览

```text
Image/Message input
  -> Extract/Parse
  -> Name standardization
  -> Asset identity review
       -> accepted rows -> Transform -> Validate -> MongoDB
       -> pending rows  -> pending CSV/JSON + batch report
  -> standardized result
```

### 4.3 模块分工

- `a_share_name_corrector`: 提供 A 股主数据校验、兼容名称自动更正和复核状态列。
- `asset_identity_review`: 统一拆分 accepted/pending 行，保存 pending 审计产物，构造标准结果。
- `run_unified_image_pipeline.py`: 在图片 OCR 后执行身份复核，支持部分入库。
- `run_unified_message_pipeline.py`: 在文本解析后执行同样的身份复核，支持部分入库。
- `batch_report`: 对多文件处理结果生成标准化批次汇总。
- `smart_money_watcher.py`: 在批量扫描时输出批次汇总。

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

- 触发条件：收到图片、消息文本，或 watcher 批量扫描文件。
- 核心处理逻辑：
  1. 标准化资产名称中的空格、全半角和常见符号。
  2. 对 A 股 `Wind代码` 查询 `stock_basic_info` 主数据。
  3. 名称完全一致或强兼容时允许自动更正。
  4. 名称不兼容或主数据缺失时标记 pending，不写入正式集合。
  5. accepted 行继续 transform/validate/load。
  6. pending 行写入 `review_pending` 目录，等待人工确认。
  7. 人工确认后，编辑 pending CSV 中 `名称复核状态` 为 `confirmed`（或修正 `Wind代码`/`资产名称`），执行 `load_pending_confirmed.py` 补录入库。
  8. 补录完成后，pending JSON 中 `review_status` 更新为 `resolved`，记录 `resolved_at` 时间戳。
- 正常分支：无 pending 时保持原有入库行为。
- 异常降级分支：存在 pending 时返回 `partial_success`，记录已入库行数和待确认行数；全 pending 时返回 `pending_review`，不写库但保存审计文件。
- 补录分支：人工确认 pending CSV 后通过 `load_pending_confirmed` 写入正式集合，审计文件标记为 `resolved`。

### 5.2 数据模型（Data Model）

| 字段 | 类型 | 说明 | 约束 |
|---|---|---|---|
| `review_status` | string | 标准复核状态 | `matched/auto_corrected/pending_review/missing_master` |
| `review_reason` | string | 复核原因 | pending 时非空 |
| `pending_csv` | string | 待确认 CSV 路径 | pending 时非空 |
| `pending_json` | string | 待确认元数据路径 | pending 时非空 |
| `accepted_rows` | int | 继续入库行数 | >= 0 |
| `pending_rows` | int | 待确认行数 | >= 0 |
| `status` | string | pipeline 结果状态 | `success/partial_success/pending_review/failed/dry_run` |

正式 MongoDB 集合不新增必填字段；pending 文件是审计与人工确认中间态。

### 5.3 接口契约（API Contract）

Pipeline `run_pipeline(...) -> dict` 返回值新增以下兼容字段：

- `status`: 处理状态。
- `review`: 身份复核汇总。
- `pending`: pending 审计文件路径与明细。
- `batch_summary`: 仅批量处理时输出。
- `apply_command`: 当存在 pending 行时，返回标准补录命令字符串（如 `python3 load_pending_confirmed.py <pending_csv_path>`），方便用户直接执行。

既有 `rows/format/mongodb/excel_path` 字段保留。

补录接口 `load_pending_confirmed.py` 契约：

- 输入：pending CSV 文件路径（用户确认后，`名称复核状态` 列已更新为 `confirmed` 或修正后的值）。
- 行为：读取 CSV，过滤掉仍为 pending 的行，将 confirmed 行 upsert 到 `portfolio_position` 或 `portfolio_trade`。
- 输出：`{loaded: int, errors: list}`。
- 批量模式：`--date <YYYY-MM-DD>` 参数可加载指定日期下所有 resolved 的 pending 文件。

## 6. AI实装规范（AI Implementation Rules）

### 6.1 必须执行

- 只在 accepted 行上执行正式入库。
- pending 行必须保留原始 OCR/消息字段、主数据名称、原因和源文件路径。
- 代码必须有针对兼容自动修正、不兼容 pending、部分入库、批次汇总的测试。
- 不得吞掉 validation error；非身份复核错误仍按原有失败语义处理。

### 6.2 先询问再执行

- 新增生产数据库集合。
- 对历史数据做批量修复。
- 引入新的 OCR/LLM 服务或第三方依赖。

### 6.3 绝对禁止

- 在代码/名称不兼容时用主数据名称覆盖 OCR 名称。
- 因单行 pending 阻塞同一图片内其他正常行入库。
- 把 pending 数据写入 `portfolio_position` 或 `portfolio_trade` 正式集合。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 名称兼容规则过严导致 pending 增多 | 中 | 中 | 先保证数据正确性，pending 汇总暴露人工成本 | 后续基于确认样本扩展别名库 |
| 主数据缺失误判 | 中 | 中 | `missing_master` 进入 pending，避免自动覆盖 | 人工确认后补主数据或补录 |
| 批次汇总和 Feishu 回复口径不一致 | 低 | 中 | 批次汇总统一由 `batch_report` 生成 | 单图结果仍可独立查看 |
| 部分入库破坏 NAV/position 一致性 | 低 | 中 | NAV/basic_info 可入库，position 仅过滤 pending 行 | 汇总明确 pending 行数 |

## 8. 备选方案（Alternatives Considered）

- 整张图片 pending：实现简单，但正常数据被异常行阻塞，运营效率差。
- 自动 fuzzy code correction：可能修复更多 OCR 错误，但错误放大风险高，本阶段不采用。
- 直接新增 MongoDB pending 集合：利于系统化审核，但涉及生产 schema，本阶段先用文件审计。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

- 名称兼容时自动更正并可入库。
- 名称不兼容时进入 pending，不覆盖名称。
- 同一输入有 accepted 和 pending 行时，accepted 行完成入库，pending 行生成审计文件。
- 批量处理能输出总数、成功、部分成功、pending、失败统计。

### 9.2 非功能验收

- 无新增第三方依赖。
- 对原有无 pending 的 pipeline 兼容。
- pending 文件可被人工打开和追溯源文件。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

1. 补齐 RFC/SPEC/Design。
2. 实现共享身份复核和 pending 审计工具。
3. 接入 Image/Message pipeline。
4. 接入 watcher 批次汇总。
5. 增加单元测试并执行验证。
6. 独立 review 后 closeout。

### 10.2 任务清单

- Principal: 文档与设计门禁。
- Developer: 最小范围实现。
- Test Engineer: 单元与回归验证。
- Reviewer: diff 与行为一致性审查。

## 11. 开放问题（Open Questions）

- ~~人工确认后的补录入口是否需要后续升级为 Feishu 交互式确认或 Web UI~~ → **已解决**：当前通过 `load_pending_confirmed.py` CLI 补录，pending 审计 JSON 记录 `apply_command` 字段。未来如需 Feishu/Web UI 确认入口，另开 RFC。
- 港股/美股是否需要接入更完整的证券主数据，而不仅是静态名称映射。

## 12. 参考资料（References）

- `skills/data/data-pipeline/SKILL.md`
- `skills/data/data-pipeline/docs/IMAGE_PORTFOLIO_DATA_PIPELINE.md`
- `docs/rfc/03_data/RFC-03-003-data-architecture.md`

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-06-15 | 初始创建 | YQuant-Codex-Principal |
| V1.1 | 2026-06-17 | 将人工确认补录闭环从 Out of Scope 移入正式 Scope；新增 `apply_command` 接口契约；补充补录业务流程；标记开放问题已解决 | YQuant-Codex-Principal |
