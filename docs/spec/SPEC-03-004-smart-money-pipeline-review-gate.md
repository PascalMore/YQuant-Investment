# SPEC-03-004: Smart Money Pipeline Review Gate

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-15 |
| 最后更新 | 2026-06-15 |
| 来源 RFC | RFC-03-004 |
| 目标模块 | data-pipeline |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

## 1. 需求摘要

本 SPEC 定义 Smart Money Image/Message Pipeline 的证券身份复核行为。Pipeline 必须在正式入库前识别股票代码/名称的不确定性，高风险记录进入 pending 人工确认，低风险兼容记录可自动更正，正常记录继续入库。批量处理必须输出标准汇总，帮助用户判断一批图片中哪些已正确入库、哪些需要确认。

## 2. 范围

### 2.1 In Scope

- [x] Image portfolio/trade pipeline 的代码/名称复核。
- [x] Message portfolio/trade pipeline 的代码/名称复核。
- [x] A 股代码/名称主数据校验的保守自动更正。
- [x] pending CSV/JSON 审计产物。
- [x] 批次汇总函数与 watcher `--once/--scan-all` 汇总输出。
- [x] 单元测试覆盖核心行为。

### 2.2 Out of Scope

- [ ] 人工确认 UI。
- [ ] 自动把 pending 文件重新写库的交互流程。
- [ ] 生产 MongoDB schema 迁移。
- [ ] 历史数据修复。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 名称兼容自动更正 | `Wind代码=688019.SH, 资产名称=DR安集科` | `资产名称=安集科技, review_status=auto_corrected` | 仅当 normalized 名称相等或包含时触发 |
| F-002 | 名称不兼容 pending | `Wind代码=000333.SZ, 资产名称=贵州茅台` | 行进入 pending，正式入库过滤 | 不得覆盖为 `美的集团` |
| F-003 | 主数据缺失 pending | A 股代码可规范化但主数据无名称 | 行进入 pending | 避免静默接受未知 A 股身份 |
| F-004 | 部分入库 | 同一输入含 accepted 与 pending 行 | accepted 入库，pending 落文件，状态 `partial_success` | 全 pending 时状态 `pending_review` |
| F-005 | dry-run | `dry_run=True` | 不写 MongoDB，仍返回复核汇总 | pending 文件可不强制写库但应返回 blocked/pending 信息 |
| F-006 | 批次汇总 | 多个 pipeline result | 汇总总数、成功、部分成功、pending、失败、入库计数 | 失败项保留错误消息 |
| F-007 | 兼容原返回 | 原调用方读取 `rows/format/mongodb/excel_path` | 字段仍存在 | 新字段向后兼容 |

## 4. 数据与接口契约

- 数据实体：
  - `review`: `{accepted_rows, pending_rows, audit_count, pending_files}`
  - `pending`: `{csv, json, rows, issues}`
  - `batch_summary`: `{total, success, partial_success, pending_review, failed, pending_rows, mongodb}`
- 接口/函数：
  - `split_review_rows(df) -> (accepted_df, pending_df)`
  - `save_pending_review(...) -> dict`
  - `apply_asset_identity_review(df) -> pd.DataFrame`
  - `summarize_batch_results(results) -> dict`
  - `format_batch_summary(summary) -> str`
- 兼容性约束：
  - 不新增必需环境变量。
  - 不改变 MongoDB collection unique key。
  - 不改变现有无 pending 场景的入库数量。
- 幂等性/审计要求：
  - pending 文件名包含时间戳和输入类型，避免覆盖。
  - pending JSON 记录源文件、Excel 文件、日期、格式、原因和 audit 明细。

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | 不兼容代码/名称不会被自动覆盖 | 单元测试 |
| A-002 | pending 行不进入正式 load 数据 | 单元测试 monkeypatch loader |
| A-003 | accepted 行在部分 pending 场景继续入库 | 单元测试 |
| A-004 | message pipeline 使用同样复核规则 | 单元测试 |
| A-005 | batch summary 汇总状态和 pending 行数正确 | 单元测试 |
| A-006 | 无 pending 的现有测试通过 | pytest 回归 |

## 6. 测试要求

- 单元测试：
  - `a_share_name_corrector` 兼容/不兼容/缺主数据。
  - `asset_identity_review` accepted/pending split。
  - Image pipeline 部分入库，mock OCR/transformer/loader。
  - Message pipeline 部分入库。
  - `batch_report` 汇总。
- 集成测试：
  - 可使用 dry-run 对样例 DataFrame 跑通，不要求真实 OCR 或 MongoDB。
- 回归测试：
  - 现有 `test_codec_pipeline.py`。
  - 现有 stock info API 测试不受影响。
- 不可自动化验证项：
  - 人工确认后的最终业务判断由用户完成。

## 7. 实现约束

- 禁止事项：
  - 不得因为主数据存在就无条件覆盖 OCR 名称。
  - 不得把 pending 行写入正式 MongoDB。
  - 不得新增第三方依赖。
- 依赖限制：
  - 使用 pandas、标准库和现有 pymongo/openpyxl。
- 性能/安全/风控约束：
  - 单批文件数量通常很小，优先正确性和可审计性。
  - pending 文件不得包含密钥或数据库凭证。

## 8. 开放问题

- [ ] 人工确认补录 CLI/UI 的交互形态另开后续 SPEC。
