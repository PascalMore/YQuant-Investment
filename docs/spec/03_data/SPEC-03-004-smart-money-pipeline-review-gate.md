# SPEC-03-004: Smart Money Pipeline Review Gate

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-15 |
| 最后更新 | 2026-07-29 |
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
- [ ] pending 确认后通过 `load_pending_confirmed.py` 补录入库闭环。
- [ ] pending 审计 JSON 标记 `resolved` 状态。

### 2.2 Out of Scope

- [ ] 人工确认 UI（Feishu 交互式确认或 Web UI）。
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
| F-008 | `apply_command` 生成 | pending 行存在时 | 返回值包含 `apply_command` 字段，值为标准 CLI 命令字符串 | 无 pending 时该字段为空或不存在 |
| F-009 | `--date` 批量补录模式 | `load_pending_confirmed.py --date 2026-06-15` | 加载指定日期下所有已确认的 pending CSV 并逐个补录 | 指定日期无 pending 文件时返回 `{loaded: 0}` |
| F-010 | resolved 标记 | 补录成功后 | pending JSON 中 `review_status` 更新为 `resolved`，记录 `resolved_at` 时间戳 | 补录失败时不标记 resolved |
|| F-011 | OCR 代码/名称联合修正 | `Wind代码=688008.SH, 资产名称=联讯仪器` | `Wind代码=688808.SH, 资产名称=联讯仪器, review_status=auto_corrected` | 完整契约见 §4.1；匹配条件：code 精确等于 688008.SH（exact match，不得 code-only/fuzzy-code 触发）、name 使用名称标准化结果（pipeline step 1）包含「联讯仪器」；修正后 review_status=auto_corrected 与 pipeline status（success/partial_success/pending_review）兼容；拒绝分支（见 §4.1.3）包括 688008.SH/澜起科技、688008.SH+不兼容名称、已正确 688808.SH |

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

### 4.1 OCR 代码/名称联合修正契约（F-011 详细规格）

#### 4.1.1 输入前置条件与匹配语义
- `Wind代码` 必须精确（exact string match）等于 `688008.SH`；不得使用子串匹配、前缀匹配或模糊规则（code-only / fuzzy-code 触发被禁止）。
- `资产名称` 在名称标准化（pipeline step 1：全半角转换、空格规范化、常见符号清理）**之后**的值必须包含「联讯仪器」。
- **两个条件必须同时满足**；不得仅凭 code 或仅凭 name 触发。
- 单行进规则引擎后至多触发一次该修正。

#### 4.1.2 输出字段与值
修正完成后记录以下变更：

| 字段 | 值 | 说明 |
|------|------|------|
| `Wind代码` | `688808.SH` | 修正后的 Wind 代码 |
| `资产名称` | `联讯仪器` | 修正后的标准化名称 |
| `review_status` | `auto_corrected` | 与已有 pipeline status（success/partial_success/pending_review）兼容；修正后行进入标准身份复核时同 matched 行处理（不因修正而再次 pending） |
| `review_reason` | `OCR joint correction: code 688008.SH + name 联讯仪器 → 688808.SH / 联讯仪器` | 人类可读的修正原因 |

#### 4.1.3 拒绝/不触发分支
以下输入组合**不触发**联合修正，行按既有标准身份复核流程处理：

| 输入代码 | 输入名称（标准化后） | 结果 |
|----------|---------------------|------|
| `688008.SH` | 澜起科技 | 不触发 → 标准复核 matched |
| `688008.SH` | 其他不兼容名称（非澜起科技/非联讯仪器） | 不触发 → 标准复核 pending_review |
| `688808.SH` | 联讯仪器 | 不触发（已是正确值）→ 标准复核 matched |
| `688008.SH` | （空 / null） | 不触发 → 标准复核 pending_review（或 missing_master） |
| 非 `688008.SH` 且 name 为联讯仪器 | 联讯仪器 | 不触发 → 按 name 标准复核行为 |

#### 4.1.4 审计记录
每次修正产生一条审计记录，以**以下精确顺序**写入 pipeline 返回值的 `review.audit_items[]` 数组：

| 顺序 | 字段 | 类型 | 示例值 | 说明 |
|------|------|------|--------|------|
| 1 | `original_code` | string | `"688008.SH"` | 修正前的 Wind 代码 |
| 2 | `target_code` | string | `"688808.SH"` | 修正后的 Wind 代码 |
| 3 | `original_name` | string | `"联讯仪器"` | OCR/解析输出的原始名称（标准化前） |
| 4 | `canonical_name` | string | `"联讯仪器"` | 修正后的标准化名称 |
| 5 | `correction_reason` | string | `"ocr_code_name_joint_correction"` | 修正原因编码 |
| 6 | `auto_correction_status` | string | `"auto_corrected"` | 修正状态；始终为 auto_corrected（如需人工确认分支由配置决定） |
| 7 | `corrected_at` | string | `"2026-07-29T12:00:00Z"` | ISO 8601 时间戳 |

**审计记录挂载位置：**
- audit 记录**始终**出现在 pipeline 返回值的 `review.audit_items[]` 数组中。
- 审计记录**同时**写入 pending JSON 文件（`pending.json.audit_items[]`）当且仅当：
  - 修正成功（`auto_correction_status` 为 `auto_corrected`），**且**
  - 该行所在输入批次中存在至少一条 pending 行（即 pipeline 最终状态为 `partial_success` 或 `pending_review`）。
- 如果整批次无 pending 行（全部 accepted），审计记录**仅**存在于 pipeline 返回值的 `review.audit_items[]`，不写入 pending JSON。

### 4.2 静态联合修正映射规范

联合修正规则从版本控制的 YAML（首选）或 JSON 文件读取映射条目，**不得硬编码**在 transformer 中。

**字段定义（按以下顺序）：**

| 顺序 | 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| 1 | `source_code` | string | 是 | 需要修正的原始 Wind 代码（用于 exact match） |
| 2 | `source_name_pattern` | string | 是 | 标准化名称中包含的子串模式 |
| 3 | `target_code` | string | 是 | 修正后的目标 Wind 代码 |
| 4 | `target_name` | string | 是 | 修正后的目标资产名称 |
| 5 | `reason` | string | 是 | 修正原因编码（如 `ocr_code_name_joint_correction`） |

**示例条目（YAML）：**
```yaml
- source_code: "688008.SH"
  source_name_pattern: "联讯仪器"
  target_code: "688808.SH"
  target_name: "联讯仪器"
  reason: "ocr_code_name_joint_correction"
```

**文件路径规范：** 映射文件存放于 `config/` 目录，具体文件名由 developer 在实现阶段确定（建议 `config/ocr_joint_corrections.yaml`）。

**配置缺失或异常时的行为（fail-closed）：**

| 场景 | 行为 |
|------|------|
| 文件不存在 | 跳过联合修正步骤，数据直接进入标准身份复核；不影响既有 pending/入库行为 |
| 文件格式错误 / 无法解析 | 同「文件不存在」，跳过联合修正；记录 warning 日志 |
| 文件为空（0 条目） | 同「文件不存在」，跳过联合修正 |
| 单一条目字段缺失或为空 | 跳过该条目，继续解析后续条目；单条目错误不影响其他条目 |
| 任何配置错误 | **不得**导致静默错误修正（不得以错误值修正代码或名称） |
| 配置错误导致 skip | **不得**导致 pipeline crash 或阻塞整批数据处理 |

任何情况下，配置错误均不得导致**静默错误修正**（即不得以错误的值改写代码或名称）。

**版本控制要求：**
- 映射文件受 Git 版本控制
- 变更需经过代码审查，reviewer 须校验修正模式的准确性和影响范围

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | 不兼容代码/名称不会被自动覆盖 | 单元测试 |
| A-002 | pending 行不进入正式 load 数据 | 单元测试 monkeypatch loader |
| A-003 | accepted 行在部分 pending 场景继续入库 | 单元测试 |
| A-004 | message pipeline 使用同样复核规则 | 单元测试 |
| A-005 | batch summary 汇总状态和 pending 行数正确 | 单元测试 |
| A-006 | 无 pending 的现有测试通过 | pytest 回归 |
| A-007 | pending 结果包含 `apply_command` 字段且格式正确 | 单元测试 |
| A-008 | `load_pending_confirmed` 正确过滤 confirmed 行并 upsert | 单元测试 monkeypatch loader |
| A-009 | `--date` 批量模式加载指定日期全部 pending 文件 | 单元测试 |
| A-010 | 补录成功后 pending JSON 标记为 `resolved` | 单元测试 |
| A-011 | 联合修正规则离线 fixture 矩阵全部通过 | 单元测试（无网络/Mongo） |

## 6. 测试要求

- 单元测试：
  - `a_share_name_corrector` 兼容/不兼容/缺主数据。
  - `asset_identity_review` accepted/pending split。
  - Image pipeline 部分入库，mock OCR/transformer/loader。
  - Message pipeline 部分入库。
  - `batch_report` 汇总。
  - 联合修正规则必须覆盖以下离线 fixture 矩阵（所有测试用例均无网络/Mongo 依赖）：

    | 编号 | 场景 | 输入 code | 输入 name（标准化后） | 期望 review_status | 是否修正 code | 是否修正 name | 是否产生审计记录 | 审计 target_code | 审计 canonical_name |
    |------|------|-----------|----------------------|--------------------|---------------|---------------|-----------------|-----------------|---------------------|
    | T1 | 修正命中 | `688008.SH` | 联讯仪器 | `auto_corrected` | ✅ → `688808.SH` | ✅ → `联讯仪器` | ✅ | `688808.SH` | 联讯仪器 |
    | T2 | 保护-真名 | `688008.SH` | 澜起科技 | `matched` | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A |
    | T3 | 保护-不兼容 | `688008.SH` | 某不兼容名称 | `pending_review` | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A |
    | T4 | 已正确 | `688808.SH` | 联讯仪器 | `matched` | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A |
    | T5 | code 不匹配 | `600519.SH` | 联讯仪器 | 按标准复核 | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A |
    | T6 | name 为空 | `688008.SH` |（空/null） | 按标准复核 | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A |
    | T7 | image/message 共享入口 | `688008.SH` | 联讯仪器 | `auto_corrected` | ✅ → `688808.SH` | ✅ → `联讯仪器` | ✅ | `688808.SH` | 联讯仪器（同一 fixture 数据分别在 Image pipeline 和 Message pipeline 的 mock 环境中各跑一次，均触发联合修正） |

  - 联合修正规则配置解析与异常处理测试（无网络/Mongo 依赖，纯 logic mock）：

    | 编号 | 场景 | 配置内容 | 期望行为 |
    |------|------|----------|----------|
    | C1 | 配置条目缺字段 | `{source_code: "688008.SH", target_code: "688808.SH", target_name: "联讯仪器", reason: "..."}`（缺 source_name_pattern） | 跳过该条目，记录 warning 日志；不修正该行，数据继续走标准流程 |
    | C2 | 配置文件为空（0 条目） | 空列表 `[]` | 跳过联合修正步骤，数据直接进入标准身份复核；不产生审计记录 |
    | C3 | 配置文件格式错误 | 无效 YAML/JSON 字符串 | 同 C2 行为（跳过修正），记录 warning；不阻塞 pipeline |
    | C4 | 单一条目 target_code 为空 | `{source_code: "688008.SH", source_name_pattern: "联讯仪器", target_code: "", target_name: "联讯仪器", reason: "..."}` | 跳过该条目，继续解析后续条目；不修正该行 |

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

- ~~人工确认补录 CLI/UI 的交互形态另开后续 SPEC~~ → **已解决**：采用 `load_pending_confirmed.py` CLI 补录，通过 `apply_command` 字段串联。Feishu/Web UI 确认入口未来另开 RFC。
- [ ] `load_pending_confirmed` 目前仅支持 position 和 trade，是否需要扩展到其他数据类型（如 NAV/basic_info）。
