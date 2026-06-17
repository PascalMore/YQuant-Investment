# DESIGN-03-004: Smart Money Pipeline Review Gate

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-15 |
| 最后更新 | 2026-06-17 |
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
| `transformers/asset_identity_review.py` | 新增 shared helper：拆分 accepted/pending、保存 pending CSV/JSON、构造 review summary；`save_pending_review()` 返回值新增 `apply_command` 字段（F-008） | Image/Message 共用；闭环补录命令自动生成 |
| `run_unified_image_pipeline.py` | 接入 shared review；pending 不 raise；accepted 部分继续入库 | 满足部分入库 |
| `run_unified_message_pipeline.py` | 接入同一套 review | message pipeline 行为一致 |
| `batch_report.py` | 新增批次汇总和文本格式化；`format_batch_closeout()` 在 pending 明细后追加补录命令提示 | 标准化批次汇报；引导用户完成闭环 |
| `load_pending_confirmed.py` | 新增 `--date` 批量模式（F-009）、`--name-mapping` 参数、resolved 标记逻辑（F-010） | 支持批量补录与 pending 状态闭环 |
| `smart_money_watcher.py` | `process_existing_files` 收集失败项并输出 batch summary | 批量可观测 |
| `tests/test_image_pipeline_asset_name_guard.py` | 扩展测试 | 覆盖新增行为 |
| `tests/test_load_pending_confirmed.py` | 新增测试文件 | 覆盖 --date 批量模式、resolved 标记、apply_command 生成 |

### 3.2 数据流/控制流

```text
raw input
  -> parse/OCR dataframe
  -> apply_asset_identity_review(df)
  -> split_review_rows(df)
       accepted_df -> transformer -> normalizer -> validator -> loader
       pending_df  -> review_pending/*.csv + *.json (+ apply_command)
  -> result(status, review, pending, mongodb)
```

Pending 闭环（本次新增）：

```text
pending CSV/JSON 落盘
  -> 人工确认（编辑 CSV 中名称复核状态为 confirmed / 修正资产名称）
  -> load_pending_confirmed.py --csv <file>  （单文件模式）
  load_pending_confirmed.py --date 2026-06-15  （批量模式，F-009）
  -> MongoDB upsert（与正式 load 同集合、同 schema）
  -> pending JSON 标记 review_status=resolved, resolved_at=<ISO>（F-010）
```

批次汇总：

```text
list[pipeline_result]
  -> summarize_batch_results
  -> format_batch_summary
  -> format_batch_closeout（含 pending 明细 + 补录命令提示）
  -> log / caller response
```

### 3.3 接口与数据结构

- 新增：
  - `PENDING_REVIEW_STATUSES = {"pending_review", "missing_master"}`
  - `apply_asset_identity_review(df)`
  - `split_review_rows(df)`
  - `save_pending_review(...) -> dict`（返回值新增 `apply_command: str`，F-008）
  - `build_review_summary(...)`
  - `summarize_batch_results(results)`
  - `format_batch_summary(summary)`
  - `format_batch_closeout(closeout)`（pending 明细后追加补录命令提示）
- 修改：
  - pipeline result 新增 `status/review/pending`。
  - pipeline result 在有 pending 行时包含 `apply_command` 字段（标准 CLI 命令字符串）。
  - watcher batch result 可包含 `error`。
- `load_pending_confirmed.py` CLI 接口（本次新增 F-009）：

  ```bash
  # 单文件模式（已有）
  python3 load_pending_confirmed.py --csv <pending_csv_path> [--dry-run]

  # 批量模式（新增）
  python3 load_pending_confirmed.py --date 2026-06-15 [--dry-run] [--name-mapping <json_file>]
  ```

  | 参数 | 说明 |
  |---|---|
  | `--csv <path>` | 单文件模式：加载指定 pending CSV |
  | `--date <YYYY-MM-DD>` | 批量模式：加载指定日期下所有 pending CSV（F-009） |
  | `--name-mapping <json>` | 可选：名称映射 JSON 文件，用于批量替换资产名称 |
  | `--dry-run` | 只展示将要写入的记录，不实际写 MongoDB |

- pending JSON 新增字段（F-010）：

  | 字段 | 说明 |
  |---|---|
  | `status` | 生命周期标记：`pending_review` → `resolved` |
  | `resolved_at` | 补录成功后写入 ISO 时间戳；补录失败时不写入 |

- 废弃：
  - 不再用 mismatch 直接 raise 阻塞整张图片。

### 3.4 UI/原型设计

无。pending 文件先作为人工审核输入。

## 4. 实现计划

- [x] Step 1: 补齐 RFC/SPEC/Design（V1.1 已更新 F-008/F-009/F-010）。
- [x] Step 2: 增加 shared review helper 和 batch report（asset_identity_review.py, batch_report.py）。
- [x] Step 3: 修改 Image pipeline 为部分入库。
- [x] Step 4: 修改 Message pipeline 为同样语义。
- [x] Step 5: 修改 watcher 批次汇总。
- [x] Step 6a: 核心测试（asset_name_guard, pipeline 部分入库, batch summary）。
- [ ] Step 6b: **[本次新增]** `save_pending_review` 返回 `apply_command` 字段（F-008）。
- [ ] Step 6c: **[本次新增]** `load_pending_confirmed.py` 增加 `--date` 批量模式和 `--name-mapping` 参数（F-009）。
- [ ] Step 6d: **[本次新增]** 补录后 pending JSON 标记 `resolved` + `resolved_at`（F-010）。
- [ ] Step 6e: **[本次新增]** `batch_report.format_batch_closeout()` 追加补录命令提示。
- [ ] Step 6f: **[本次新增]** 新增测试覆盖 F-008/F-009/F-010。
- [ ] Step 7: Review gate（独立审查）。

## 5. 测试策略

- 单元测试：
  - 名称兼容自动修正。
  - 名称不兼容 pending。
  - pending split 与审计文件。
  - batch summary。
  - **[新增]** `apply_command` 生成测试：验证 `save_pending_review()` 返回的 `apply_command` 字段格式正确、包含正确的 CSV 路径（F-008 / A-007）。
  - **[新增]** `--date` 批量模式测试：给定日期目录下多个 pending CSV，验证全部被加载且写入 MongoDB（mock loader）（F-009 / A-009）。
  - **[新增]** `--name-mapping` 参数测试：验证映射文件正确替换资产名称。
  - **[新增]** resolved 标记测试：补录成功后 pending JSON `status` 更新为 `resolved` 且 `resolved_at` 写入；补录失败时不标记（F-010 / A-010）。
  - **[新增]** `format_batch_closeout` 追加补录命令提示测试。
- 集成测试：
  - monkeypatch OCR/loader，验证部分入库不会写 pending 行。
  - monkeypatch message loader，验证 message pipeline 一致。
  - **[新增]** 端到端闭环：pipeline 产出 pending → 模拟人工确认 → `load_pending_confirmed --date` → 验证 MongoDB 写入 + JSON resolved 标记。
- 手工验证：
  - 检查 pending CSV/JSON 字段可读。
- 回归范围：
  - `tests/test_image_pipeline_asset_name_guard.py`
  - `skills/data/data-pipeline/scripts/test_codec_pipeline.py`
  - `tests/test_load_pending_confirmed.py`（新增）

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| pending 误伤过多 | 汇总暴露 pending 明细，后续补别名库 | 回退到旧版本或放宽兼容规则 |
| 过滤行后空 DataFrame | 返回 `pending_review`，只保存审计文件 | 手工确认后补录 |
| batch summary 影响 watcher | 只在批量扫描路径输出，实时 watch 保持单文件处理 | 删除 batch_report 接入 |

## 7. 交接给实现者

- 必须遵守：
  - 以 `SPEC-03-004`（V1.1）为直接契约。
  - 不新增外部依赖。
  - 不修改无关 hotel scraper 变更。
  - 不触碰真实 MongoDB 历史数据。
  - **`apply_command` 格式约束**：必须为可直接复制执行的 CLI 字符串，格式为 `python3 load_pending_confirmed.py --csv <path>`（单文件）或 `python3 load_pending_confirmed.py --date <YYYY-MM-DD>`（批量）。路径使用相对 scripts 目录的路径。
  - **`--date` 批量模式约束**：扫描 `review_pending/` 目录下匹配指定日期的 pending CSV 文件，逐个加载。无匹配文件时返回 `{loaded: 0, errors: []}`。
  - **resolved 标记约束**：仅在 upsert 成功后更新 pending JSON；upsert 失败或部分失败时不标记 resolved。`resolved_at` 使用 ISO 8601 带时区格式。
  - **`--name-mapping` 约束**：JSON 文件格式为 `{"原始名称": "正确名称"}`，在写入 MongoDB 前替换 `asset_name` 字段。
- 可自行判断：
  - pending 文件字段顺序。
  - batch summary / closeout 文案措辞。
  - `--date` 模式下文件匹配模式（glob pattern）。
- 遇到以下情况退回 Principal：
  - 需要新增 MongoDB pending 集合。
  - 需要定义人工确认 UI/API。
  - 现有 transformer 无法在过滤行后保留产品 NAV。
  - `apply_command` 需要支持除 `load_pending_confirmed.py` 以外的其他补录工具。

## 8. 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-06-15 | 初始设计：review gate 核心架构 |
| V1.1 | 2026-06-17 | 新增 F-008（apply_command）、F-009（--date 批量模式）、F-010（resolved 标记）的详细设计；更新模块改动表、数据流、接口契约、实现计划和测试策略 |
