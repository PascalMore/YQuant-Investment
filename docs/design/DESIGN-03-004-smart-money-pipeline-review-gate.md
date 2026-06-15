# DESIGN-03-004: Smart Money Pipeline Review Gate

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-15 |
| 最后更新 | 2026-06-15 |
| 来源 RFC | RFC-03-004 |
| 来源 SPEC | SPEC-03-004 |
| 目标模块 | data-pipeline |

## 1. 设计摘要

本设计在现有 data-pipeline 中新增共享的资产身份复核层。它不替换 OCR、Transformer、Validator 或 Loader，而是在入库前把 DataFrame 按复核状态拆分为 accepted/pending：accepted 继续走原有 transform/validate/load，pending 写入审计文件并进入批次汇总。

## 2. 现状分析

- 相关目录：
  - `skills/data/data-pipeline/scripts/`
  - `tests/`
- 相关文件：
  - `run_unified_image_pipeline.py`
  - `run_unified_message_pipeline.py`
  - `smart_money_watcher.py`
  - `transformers/a_share_name_corrector.py`
  - `transformers/portfolio_excel_transformer.py`
- 现有约束：
  - Image pipeline 已保存原图和 Excel。
  - A 股名称校正已有主数据 API。
  - 当前高风险 mismatch 会整张阻塞，不满足部分入库。
  - Message pipeline 尚未接入同样校验。
- 兼容性风险：
  - 过滤 pending 行时不能丢失 NAV/basic_info。
  - DataFrame `attrs` 在 copy/filter 后可能丢失，需要显式传 audit。
  - watcher 当前只记录单文件结果，需要新增批次汇总但不破坏实时 watch。

## 3. 方案设计

### 3.1 模块/文件改动

| 文件 | 改动 | 原因 |
|---|---|---|
| `transformers/a_share_name_corrector.py` | 统一状态：`matched/auto_corrected/pending_review/missing_master`；`correct_position_records` 改为保守逻辑 | 防止 normalized record 二次静默覆盖 |
| `transformers/asset_identity_review.py` | 新增 shared helper：拆分 accepted/pending、保存 pending CSV/JSON、构造 review summary | Image/Message 共用 |
| `run_unified_image_pipeline.py` | 接入 shared review；pending 不 raise；accepted 部分继续入库 | 满足部分入库 |
| `run_unified_message_pipeline.py` | 接入同一套 review | message pipeline 行为一致 |
| `batch_report.py` | 新增批次汇总和文本格式化 | 标准化批次汇报 |
| `smart_money_watcher.py` | `process_existing_files` 收集失败项并输出 batch summary | 批量可观测 |
| `tests/test_image_pipeline_asset_name_guard.py` | 扩展测试 | 覆盖新增行为 |

### 3.2 数据流/控制流

```text
raw input
  -> parse/OCR dataframe
  -> apply_asset_identity_review(df)
  -> split_review_rows(df)
       accepted_df -> transformer -> normalizer -> validator -> loader
       pending_df  -> review_pending/*.csv + *.json
  -> result(status, review, pending, mongodb)
```

批次汇总：

```text
list[pipeline_result]
  -> summarize_batch_results
  -> format_batch_summary
  -> log / caller response
```

### 3.3 接口与数据结构

- 新增：
  - `PENDING_REVIEW_STATUSES = {"pending_review", "missing_master"}`
  - `apply_asset_identity_review(df)`
  - `split_review_rows(df)`
  - `save_pending_review(...)`
  - `build_review_summary(...)`
  - `summarize_batch_results(results)`
  - `format_batch_summary(summary)`
- 修改：
  - pipeline result 新增 `status/review/pending`。
  - watcher batch result 可包含 `error`。
- 废弃：
  - 不再用 mismatch 直接 raise 阻塞整张图片。

### 3.4 UI/原型设计

无。pending 文件先作为人工审核输入。

## 4. 实现计划

- [x] Step 1: 补齐 RFC/SPEC/Design。
- [ ] Step 2: 增加 shared review helper 和 batch report。
- [ ] Step 3: 修改 Image pipeline 为部分入库。
- [ ] Step 4: 修改 Message pipeline 为同样语义。
- [ ] Step 5: 修改 watcher 批次汇总。
- [ ] Step 6: 扩展测试并跑 pytest。
- [ ] Step 7: Review gate。

## 5. 测试策略

- 单元测试：
  - 名称兼容自动修正。
  - 名称不兼容 pending。
  - pending split 与审计文件。
  - batch summary。
- 集成测试：
  - monkeypatch OCR/loader，验证部分入库不会写 pending 行。
  - monkeypatch message loader，验证 message pipeline 一致。
- 手工验证：
  - 检查 pending CSV/JSON 字段可读。
- 回归范围：
  - `tests/test_image_pipeline_asset_name_guard.py`
  - `skills/data/data-pipeline/scripts/test_codec_pipeline.py`

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| pending 误伤过多 | 汇总暴露 pending 明细，后续补别名库 | 回退到旧版本或放宽兼容规则 |
| 过滤行后空 DataFrame | 返回 `pending_review`，只保存审计文件 | 手工确认后补录 |
| batch summary 影响 watcher | 只在批量扫描路径输出，实时 watch 保持单文件处理 | 删除 batch_report 接入 |

## 7. 交接给实现者

- 必须遵守：
  - 以 `SPEC-03-004` 为直接契约。
  - 不新增外部依赖。
  - 不修改无关 hotel scraper 变更。
  - 不触碰真实 MongoDB 历史数据。
- 可自行判断：
  - pending 文件字段顺序。
  - batch summary 文案。
- 遇到以下情况退回 Principal：
  - 需要新增 MongoDB pending 集合。
  - 需要定义人工确认 UI/API。
  - 现有 transformer 无法在过滤行后保留产品 NAV。
