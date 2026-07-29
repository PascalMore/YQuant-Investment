# DESIGN-03-004: Smart Money Pipeline Review Gate

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-15 |
| 最后更新 | 2026-07-29 |
| 来源 RFC | RFC-03-004 (V1.2, §5.4) |
| 来源 SPEC | SPEC-03-004 (V1.2, §4.1 F-011, §4.2) |
| 目标模块 | data-pipeline |

## 1. 设计摘要

本设计在现有 data-pipeline 中新增共享的资产身份复核层。它不替换 OCR、Transformer、Validator 或 Loader，而是在入库前把 DataFrame 按复核状态拆分为 accepted/pending：accepted 继续走原有 transform/validate/load，pending 写入审计文件并进入批次汇总。

**V1.2 新增范围**（由 RFC / SPEC V1.2 驱动）：在标准化步骤和主数据校验步骤之间插入可配置的 **OCR 代码/名称联合修正**（F-011），针对特定 OCR 误读模式（`688008.SH + 联讯仪器 → 688808.SH / 联讯仪器`）做窄范围修正。修正记录以 7 字段 SPEC 规范写入 `review.audit_items[]` 数组。

## 2. 现状分析

- 相关目录：
  - `skills/data/data-pipeline/scripts/`
  - `skills/data/data-pipeline/tests/`
  - `skills/data/data-pipeline/config/`（V1.2 新增：静态映射配置）
- 相关文件：
  - `run_unified_image_pipeline.py`
  - `run_unified_message_pipeline.py`
  - `smart_money_watcher.py`
  - `transformers/a_share_name_corrector.py`
  - `transformers/asset_identity_review.py`（V1.2 新增函数落脚点）
  - `batch_report.py`
  - `stock_name_corrections.py`（V1.2 不修改）
- 现有约束：
  - Image pipeline 已保存原图和 Excel。
  - A 股名称校正已有主数据 API。
  - 当前高风险 mismatch 会整张阻塞，不满足部分入库。
  - Message pipeline 尚未接入同样校验。
  - `apply_asset_identity_review(df)` 是集中式入口，已在 Image/Message 两个 pipeline 调用。
  - `stock_name_corrections.py` 中的 `688808.SH → 联讯仪器` 条目是**正确代码时**的静态名称校验；**F-011 处理的是错误代码场景**，两者不冲突。
- 兼容性风险：
  - 过滤 pending 行时不能丢失 NAV/basic_info。
  - DataFrame `attrs` 在 copy/filter 后可能丢失，需要显式传 audit。
  - watcher 当前只记录单文件结果，需要新增批次汇总但不破坏实时 watch。
  - **V1.2 新增**：联合修正后的代码/名称对必须正确进入标准身份复核，不能因修正后再次 pending。
  - **V1.2 新增**：`review.audit_items[]` 是 pipeline 结果新字段，不影响现有返回结构。

## 3. 方案设计

### 3.1 模块/文件改动

| 文件 | 改动 | 原因 |
|---|---|---|
| `transformers/a_share_name_corrector.py` | 不修改（见「不改文件清单」第 68 行——F-011 不侵入 A 股主数据语义） | — |
| `transformers/asset_identity_review.py` | **V1.2 核心改动**：新增 `apply_ocr_joint_corrections()` 函数（含配置加载、规则匹配、修正执行、审计记录生成）；修改 `apply_asset_identity_review()` 在标准化后/主数据前调用联合修正；新增 `OCR_JOINT_AUDIT_ATTR` 常量存储 7 字段审计；新增 `get_ocr_joint_audit(df)` 提取函数供 pipeline 出口使用 | F-011 实现主场 |
| `config/ocr_joint_corrections.yaml` | **V1.2 新增文件**：静态映射配置，初版含 `688008.SH + 联讯仪器 → 688808.SH / 联讯仪器` 条目 | 配置驱动、不硬编码 |
| `run_unified_image_pipeline.py` | **V1.2 新增**：在构造 `review` dict 后，从 `df.attrs.get(OCR_JOINT_AUDIT_ATTR, [])` 提取并追加到返回结果的 `review.audit_items` 字段；`save_pending_review()` 调用新增 `joint_audit` 参数（仅含 OCR 联合修正的 7 字段审计记录，不含高风险审计字段），使 pending JSON 在有 pending 行时包含 7 字段审计记录 | 保证 `review.audit_items[]` 始终出现在 pipeline 返回值中；pending JSON `audit_items[]` 仅含 joint_audit schema（SPEC §4.1.4），不与高风险审计混合 |
| `run_unified_message_pipeline.py` | **V1.2 新增**：同上逻辑 | message pipeline 行为一致 |
| `skills/data/data-pipeline/tests/test_ocr_joint_correction.py` | **V1.2 新增**：按 SPEC §6 离线 fixture 矩阵（T1-T6），每个用例断言 code/name/status/audit_items 四个维度；使用 `monkeypatch` 替代配置加载实现纯离线测试 | 覆盖已绑定语义、保护 澜起科技、拒绝不兼容、已正确、code 不匹配、name 为空 六场景 |
| `skills/data/data-pipeline/tests/test_asset_identity_review.py` | **V1.2 新增**：联合修正 + 标准复核串联测试（先修正再进入主数据校验，验证修正后行不会因同一行再次 pending） | 保证修正后行正确走 matched 路径 |
| 其他已有测试文件 | 不修改 | 保持向后兼容 |

#### 不改文件清单

- `docs/rfc/03_data/RFC-03-004-*.md` — RFC 已在父任务中冻结
- `docs/spec/03_data/SPEC-03-004-*.md` — SPEC 已在父任务中冻结
- `transformers/a_share_name_corrector.py` — 联合修正是独立逻辑，不侵入 A 股主数据校验
- `stock_name_corrections.py` — 联合修正使用独立 YAML 配置
- `batch_report.py` — 不涉及 F-011
- `smart_money_watcher.py` — 不涉及 F-011（已有 batch report 不变）
- `load_pending_confirmed.py` — 不涉及 F-011
- 任何 `docs/` 模板文件
- 任何 MongoDB/loader/validator 代码

### 3.2 数据流/控制流

```text
raw input
  -> parse/OCR dataframe
  -> standardize_df_asset_names(df)        [Step 1: 名称标准化]
  -> apply_ocr_joint_corrections(df)       [Step 1.5: V1.2 新增 — 联合修正]
  -> correct_stock_names(df)               [Step 2a: 静态代码名称校正]
  -> correct_dataframe_asset_names(df)     [Step 2b: A 股主数据校验]
  -> split_review_rows(df)
       accepted_df -> transformer -> normalizer -> validator -> loader
       pending_df  -> review_pending/*.csv + *.json (+ apply_command)
  -> result(status, review, pending, mongodb)
       review.audit_items[] : 联合修正 7 字段审计记录（无条件始终存在）
       pending.json.audit_items[] : 同上，仅当批次有 pending 行时写入
```

V1.2 新增的联合修正插入在 `standardize_df_asset_names()` **之后**、`correct_stock_names()` **之前**，确保：
- 修正后的代码/名称对以正确值进入标准身份复核。
- 真实的 `688008.SH / 澜起科技` 不受影响（名称条件不匹配）。
- 修正后 `review_status = auto_corrected` 行在后续复核中走 matched 路径。

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
  - **V1.2 新增**：`apply_ocr_joint_corrections(df, config_path=None) -> pd.DataFrame`
  - **V1.2 新增**：`OCR_JOINT_AUDIT_ATTR = "ocr_joint_audit"`（常量）
  - **V1.2 新增**：`_load_ocr_joint_corrections_config(config_path) -> list[dict]`（内部 helper）
- 修改：
  - **V1.2 修改**：`apply_asset_identity_review(df)` 内部串联调用 `apply_ocr_joint_corrections`
  - pipeline result 新增 `status/review/pending`。
  - **V1.2 新增**：pipeline result `review.audit_items` 字段（list[dict]，7 字段/条）
  - pipeline result 在有 pending 行时包含 `apply_command` 字段（标准 CLI 命令字符串）。
  - watcher batch result 可包含 `error`。
  - **V1.2 修改**：`save_pending_review()` 新增 `joint_audit: list[dict] | None = None` 参数，当有 pending 行且在 pending JSON 中写入 `audit_items` 字段

#### V1.2 新增：联合修正配置加载

```python
def _load_ocr_joint_corrections_config(
    config_path: str | Path | None = None,
) -> list[dict]:
    """Load OCR joint correction rules from YAML config file.

    Resolution order:
    1. If config_path is provided, use it directly.
    2. Otherwise resolve relative to <scripts>/config/ocr_joint_corrections.yaml.
    3. If file not found / parse error / empty → return [] (skip joint correction).
    """
```

**Config file path spec**：`config/ocr_joint_corrections.yaml`，相对于 `scripts/` 目录。绝对路径为 `skills/data/data-pipeline/scripts/config/ocr_joint_corrections.yaml`。

**Fail-closed behavior**（精确对应 SPEC-03-004 §4.2）：

| 场景 | 行为 |
|---|---|
| 文件不存在 | 返回 `[]`，跳过联合修正，data 直接进入标准复核；记录 `logger.warning` |
| 文件格式错误 / YAML 解析异常 | 同「文件不存在」，跳过联合修正；记录 `logger.warning` |
| 文件为空（0 条目） | 同「文件不存在」，跳过联合修正 |
| 单一条目字段缺失（缺少 `source_code`/`source_name_pattern`/`target_code`/`target_name`/`reason` 任一） | 跳过该条目，继续解析后续条目；记录 `logger.warning` |
| 任何配置错误 | **不得**导致静默错误修正（不得以错误值改写 code/name） |
| 配置错误导致 skip | **不得**导致 pipeline crash 或阻塞整批数据处理 |

#### V1.2 新增：联合修正函数

```python
def apply_ocr_joint_corrections(
    df: pd.DataFrame,
    config_path: str | Path | None = None,
) -> pd.DataFrame:
    """Apply OCR code/name joint correction rules.

    This function MUST be called AFTER standardize_df_asset_names() and
    BEFORE correct_stock_names() / correct_dataframe_asset_names().

    It reads correction rules from a static YAML/JSON config, matches rows
    where Wind_code AND asset_name both match a rule's source pattern, and
    performs the joint correction. Audit records (7-field SPEC schema) are
    stored in df.attrs["ocr_joint_audit"].

    The function is idempotent: a row that was already corrected by this rule
    (matched previously in the same pipeline run) is NOT corrected again.
    """
```

**匹配逻辑**（精确对应 SPEC-03-004 §4.1.1）：
1. `Wind代码` 精确等于 `source_code`（exact string match，禁用子串/前缀/fuzzy match）
2. 标准化后的 `资产名称` 包含 `source_name_pattern`（substring match after `standardize_asset_name()`）
3. 两个条件同时满足；单一条件不得触发
4. 单行至多触发一次该修正

**修正动作**（精确对应 SPEC-03-004 §4.1.2）：
- `Wind代码` = `target_code`
- `资产名称` = `target_name`
- `名称复核状态` = `auto_corrected`
- `名称复核原因` = 规则中的 `reason` 对应的人类可读字符串（如 `OCR joint correction: code 688008.SH + name 联讯仪器 → 688808.SH / 联讯仪器`）

#### V1.2 新增：审计数据模型

每次修正产生一条审计记录，**以以下精确顺序和组织**写入 `df.attrs[OCR_JOINT_AUDIT_ATTR]` 列表：

| 顺序 | 字段 | 类型 | 示例值 | 说明 |
|---|---|---|---|---|
| 1 | `original_code` | string | `"688008.SH"` | 修正前的 Wind 代码 |
| 2 | `target_code` | string | `"688808.SH"` | 修正后的 Wind 代码 |
| 3 | `original_name` | string | `"联讯仪器"` | OCR/解析输出的原始名称（标准化前，从输入 DataFrame 的原始值捕获） |
| 4 | `canonical_name` | string | `"联讯仪器"` | 修正后的标准化名称 |
| 5 | `correction_reason` | string | `"ocr_code_name_joint_correction"` | 修正原因编码；从配置 `reason` 字段读取 |
| 6 | `auto_correction_status` | string | `"auto_corrected"` | 修正状态；当前始终为 `auto_corrected` |
| 7 | `corrected_at` | string | `"2026-07-29T12:00:00Z"` | ISO 8601 时间戳，带时区 |

**挂载位置**：

- `review.audit_items[]` **始终包含**本次 pipeline 运行产生的全部联合修正审计记录（不论该批次是否有 pending 行）。
- `pending.json` 中的 `audit_items[]` **仅当**该输入批次存在至少一条 pending 行时写入（即 pipeline 最终状态为 `partial_success` 或 `pending_review`）。
- 7 字段审计记录**不写入** `df.attrs[AUDIT_ATTR]`（asset_name_audit），后者保留现有 schema 用于高风险管理。

**`save_pending_review()` 变更**：新增可选参数 `joint_audit: list[dict] | None = None`。当 `pending_df` 非空且 `joint_audit` 非空时，在 pending JSON payload 中追加 `audit_items: joint_audit` 字段。向后兼容：`joint_audit=None` 或空列表时不写该字段。

```python
# pending JSON 新增字段（当 joint_audit 非空且 pending 非空时）
{
    ...existing_fields...,
    "audit_items": [
        {
            "original_code": "688008.SH",
            "target_code": "688808.SH",
            "original_name": "联讯仪器",
            "canonical_name": "联讯仪器",
            "correction_reason": "ocr_code_name_joint_correction",
            "auto_correction_status": "auto_corrected",
            "corrected_at": "2026-07-29T12:00:00Z"
        }
    ]
}
```

#### V1.2 修改：`apply_asset_identity_review()` 串联

**Attrs 保留策略（V1.2 裁决确认）**：在 `apply_asset_identity_review()` 全过程中，两个 attrs key 各自独立保留，内容不交叉。规则如下：

| Attrs key | 写入阶段 | 后续操作 | 出口提取 |
|-----------|---------|---------|---------|
| `OCR_JOINT_AUDIT_ATTR` | Step 1.5 `apply_ocr_joint_corrections()` 写入 | Step 2a/2b **不读不改**；pandas `.copy()` 会丢弃 attrs，但当前 pipeline Step 1.5→2a→2b 均为原地列修改（无 `df.copy`），保留无需额外手段 | pipeline 出口通过 `df.attrs.get(OCR_JOINT_AUDIT_ATTR, [])` 提取 → `review.audit_items[]` |
| `AUDIT_ATTR` | Step 2a `correct_stock_names()` 追加 | Step 2b 继续追加 | 保持现有高风险管理 schema |
| **隔离保证** | 两个 key **从不合并**。任何代码或注释禁止以"向后兼容 summary counting"为由将 `OCR_JOINT_AUDIT_ATTR` 的值写入 `AUDIT_ATTR` | | |
| **统计替代** | 如需总审计条目数，分别取 `len(review.audit_items[])` + `len(df.attrs.get(AUDIT_ATTR, []))` 后求和，不在存储层合并 | | |

```python
def apply_asset_identity_review(df: pd.DataFrame) -> pd.DataFrame:
    """Run all asset identity review steps on a pipeline DataFrame."""
    reviewed = standardize_df_asset_names(df)              # Step 1: 名称标准化
    reviewed = apply_ocr_joint_corrections(reviewed)        # Step 1.5: V1.2 联合修正
    # OCR_JOINT_AUDIT_ATTR is set by apply_ocr_joint_corrections() above
    # It remains isolated in reviewed.attrs[OCR_JOINT_AUDIT_ATTR] throughout
    # Pipeline exit code reads OCR_JOINT_AUDIT_ATTR to populate review.audit_items[]
    reviewed = correct_stock_names(reviewed)                # Step 2a: 静态代码名称校正
    # AUDIT_ATTR accumulates results from correct_stock_names() (static_audit)
    reviewed = correct_dataframe_asset_names(reviewed)      # Step 2b: A 股主数据校验
    # AUDIT_ATTR accumulates both Step 2a and Step 2b audit results
    # KEY CONTRACT: OCR_JOINT_AUDIT_ATTR and AUDIT_ATTR are NEVER merged.
    #   OCR_JOINT_AUDIT_ATTR → review.audit_items[] (7-field SPEC schema, §3.3.2)
    #   AUDIT_ATTR          → existing high-risk audit schema (unchanged)
    return reviewed
```

#### V1.2 新增：pipeline 出口集成

在 `run_unified_image_pipeline.py` 和 `run_unified_message_pipeline.py` 中，在构建 `review` dict 后、返回结果前插入：

```python
# 在 build_review_summary(...) 调用之后
review["audit_items"] = df.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
```

在 `save_pending_review()` 调用处追加：

```python
pending = save_pending_review(
    ...existing args...,
    joint_audit=df.attrs.get(OCR_JOINT_AUDIT_ATTR, []),
)
```

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

- [x] Step 1: 补齐 RFC/SPEC/Design（V1.1 已更新 F-008/F-009/F-010；V1.2 已更新 F-011）。
- [x] Step 2: 增加 shared review helper 和 batch report（asset_identity_review.py, batch_report.py）。
- [x] Step 3: 修改 Image pipeline 为部分入库。
- [x] Step 4: 修改 Message pipeline 为同样语义。
- [x] Step 5: 修改 watcher 批次汇总。
- [x] Step 6a: 核心测试（asset_name_guard, pipeline 部分入库, batch summary）。
- [ ] Step 6b: **[V1.1 新增]** `save_pending_review` 返回 `apply_command` 字段（F-008）。
- [ ] Step 6c: **[V1.1 新增]** `load_pending_confirmed.py` 增加 `--date` 批量模式和 `--name-mapping` 参数（F-009）。
- [ ] Step 6d: **[V1.1 新增]** 补录后 pending JSON 标记 `resolved` + `resolved_at`（F-010）。
- [ ] Step 6e: **[V1.1 新增]** `batch_report.format_batch_closeout()` 追加补录命令提示。
- [ ] Step 6f: **[V1.1 新增]** 新增测试覆盖 F-008/F-009/F-010。
- [ ] **Step 6g: [V1.2 新增] 实现联合修正 F-011**：
  - 创建 `config/ocr_joint_corrections.yaml`，含首条映射。
  - `asset_identity_review.py`：新增 `_load_ocr_joint_corrections_config()`、`apply_ocr_joint_corrections()`、`get_ocr_joint_audit()`；修改 `apply_asset_identity_review()` 串联调用；修改 `save_pending_review()` 新增 `joint_audit` 参数。
  - `run_unified_image_pipeline.py`：新增 `review.audit_items` 提取逻辑；修改 `save_pending_review()` 调用传参。
  - `run_unified_message_pipeline.py`：同上。
  - 新增测试文件覆盖 T1-T7 离线 fixture 矩阵 + C1-C4 配置异常处理 + 串联测试。
- [ ] Step 7: Review gate（独立审查）。

## 5. 测试策略

- 单元测试：
  - 名称兼容自动修正。
  - 名称不兼容 pending。
  - pending split 与审计文件。
  - batch summary。
  - **[V1.1 新增]** `apply_command` 生成测试：验证 `save_pending_review()` 返回的 `apply_command` 字段格式正确、包含正确的 CSV 路径（F-008 / A-007）。
  - **[V1.1 新增]** `--date` 批量模式测试：给定日期目录下多个 pending CSV，验证全部被加载且写入 MongoDB（mock loader）（F-009 / A-009）。
  - **[V1.1 新增]** `--name-mapping` 参数测试：验证映射文件正确替换资产名称。
  - **[V1.1 新增]** resolved 标记测试：补录成功后 pending JSON `status` 更新为 `resolved` 且 `resolved_at` 写入；补录失败时不标记（F-010 / A-010）。
  - **[V1.1 新增]** `format_batch_closeout` 追加补录命令提示测试。
  - **V1.2 新增：联合修正离线 fixture 矩阵**（SPEC-03-004 §6 A-011）：

    | 编号 | 场景 | 输入 code | 输入 name（标准化后） | 期望 review_status | 是否修正 code | 是否修正 name | 是否产生审计记? | 审计 original_code | 审计 canonical_name | 断言序列 |
    |------|------|-----------|----------------------|--------------------|---------------|---------------|-----------------|-------------------|---------------------|----------|
    | T1 | 修正命中 | `688008.SH` | 联讯仪器 | `auto_corrected` | ✅ → `688808.SH` | ✅ → `联讯仪器` | ✅ | `688008.SH` | `联讯仪器` | code==688808.SH, name==联讯仪器, status==auto_corrected, audit.len()==1, audit[0].auto_correction_status==auto_corrected |
    | T2 | 保护-真名 | `688008.SH` | 澜起科技 | `matched`（标准复核后） | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A | code==688008.SH, name==澜起科技（不经联合修正，走标准复核） |
    | T3 | 保护-不兼容 | `688008.SH` | 某不兼容名称 | `pending_review`（标准复核后） | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A | code==688008.SH, name 不变→标准 pending |
    | T4 | 已正确 | `688808.SH` | 联讯仪器 | `matched`（标准复核后） | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A | code==688808.SH, name==联讯仪器（规则不触发） |
    | T5 | code 不匹配 | `600519.SH` | 联讯仪器 | 按标准复核 | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A | code!=688008.SH, 规则不触发 |
    | T6 | name 为空 | `688008.SH` |（空/null）| 按标准复核 | ❌ 不变 | ❌ 不变 | ❌ 不产生 | N/A | N/A | name 非 str→规则不触发 |
    | T7 | image/message 共享入口 | `688008.SH` | 联讯仪器 | `auto_corrected` | ✅ → `688808.SH` | ✅ → `联讯仪器` | ✅ | `688808.SH` | `联讯仪器` | 同一 fixture 数据分别在 Image pipeline 和 Message pipeline 的 mock 环境中各跑一次，均触发联合修正 |

  - **V1.2 新增：联合修正+标准复核串联测试**：修正命中行 → 修正后 code/name → 进入标准身份复核 → 验证最终 status 为 `matched`（不因同一行二次 pending）。mock `load_a_share_name_map` 返回 `{"688808.SH": "联讯仪器"}`。

  - **V1.2 新增：联合修正配置解析与异常处理测试**（SPEC-03-004 §6 C1-C4，纯 logic mock，无网络/Mongo 依赖）：

    | 编号 | 场景 | 配置内容 | 期望行为 |
    |------|------|----------|----------|
    | C1 | 配置条目缺字段 | `{source_code: "688008.SH", target_code: "688808.SH", target_name: "联讯仪器", reason: "..."}`（缺 `source_name_pattern`） | 跳过该条目，记录 warning 日志；不修正该行，数据继续走标准流程 |
    | C2 | 配置文件为空（0 条目） | 空列表 `[]` | 跳过联合修正步骤，数据直接进入标准身份复核；不产生审计记录 |
    | C3 | 配置文件格式错误 | 无效 YAML/JSON 字符串 | 同 C2 行为（跳过修正），记录 warning；不阻塞 pipeline |
    | C4 | 单一条目 target_code 为空 | `{source_code: "688008.SH", source_name_pattern: "联讯仪器", target_code: "", target_name: "联讯仪器", reason: "..."}` | 跳过该条目，继续解析后续条目；不修正该行 |

- 集成测试：
  - monkeypatch OCR/loader，验证部分入库不会写 pending 行。
  - monkeypatch message loader，验证 message pipeline 一致。
  - **[V1.1 新增]** 端到端闭环：pipeline 产出 pending → 模拟人工确认 → `load_pending_confirmed --date` → 验证 MongoDB 写入 + JSON resolved 标记。
  - **V1.2 新增**：dry-run 模式验证 image pipeline 返回结果中 `review.audit_items` 字段存在且格式正确。
- 手工验证：
  - 检查 pending CSV/JSON 字段可读。
  - **V1.2 新增**：检查 `config/ocr_joint_corrections.yaml` 条目可被正确加载（使用 `python3 -c "import yaml; print(yaml.safe_load(open('config/ocr_joint_corrections.yaml')))"`）。
- 回归范围：
  - `skills/data/data-pipeline/tests/test_a_share_name_corrector.py`
  - `skills/data/data-pipeline/tests/test_asset_identity_review.py`
  - `skills/data/data-pipeline/tests/test_run_unified_image_pipeline.py`
  - `skills/data/data-pipeline/tests/test_run_unified_message_pipeline.py`
  - `skills/data/data-pipeline/tests/test_batch_report.py`
  - `skills/data/data-pipeline/tests/test_image_batch_state.py`
  - `skills/data/data-pipeline/tests/test_smart_money_watcher.py`
  - `skills/data/data-pipeline/scripts/test_codec_pipeline.py`
  - `tests/test_load_pending_confirmed.py`（新增）
  - **V1.2 新增**：`skills/data/data-pipeline/tests/test_ocr_joint_correction.py`
- 建议 pytest 命令：

  ```bash
  # 联合修正专用测试（离线、无网络/Mongo）
  cd skills/data/data-pipeline && python3 -m pytest tests/test_ocr_joint_correction.py -v --tb=short

  # 全部 review gate 测试回归
  cd skills/data/data-pipeline && python3 -m pytest tests/test_a_share_name_corrector.py tests/test_asset_identity_review.py tests/test_ocr_joint_correction.py -v --tb=short

  # 禁止的网络/Mongo smoke（不得执行）
  # ❌ pytest test_ocr_joint_correction.py --network-access  ← 无此标志
  # ❌ 任何访问 stock_basic_info / MongoDB 的测试
  ```

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| pending 误伤过多 | 汇总暴露 pending 明细，后续补别名库 | 回退到旧版本或放宽兼容规则 |
| 过滤行后空 DataFrame | 返回 `pending_review`，只保存审计文件 | 手工确认后补录 |
| batch summary 影响 watcher | 只在批量扫描路径输出，实时 watch 保持单文件处理 | 删除 batch_report 接入 |
| **V1.2 新增**：联合修正规则误伤（扩大为其他误读模式） | 映射文件受版本控制，变更需代码审查 | 删除/禁用配置文件中对应条目即回退；代码不参与数据回填 |
| **V1.2 新增**：配置加载异常导致静默跳过 | fail-closed 走 `logger.warning`；data 走标准复核路径 | 纯降级，数据不受损；修正配置后重跑 |
| **V1.2 新增**：未来出现类似误读模式但配置未及时更新 | 映射文件是版本控制文件，更新后走标准部署流程 | 配置变更不影响已有数据 |

### 回滚方式

- **移除或禁用映射条目**：在 `config/ocr_joint_corrections.yaml` 中删除对应条目或整个文件。代码在文件不存在/空时自动跳过联合修正（fail-closed）。
- **代码回滚**：`git revert` 联合修正在 `asset_identity_review.py` / pipeline entry points 的改动。配置文件的版本控制允许与代码同步回滚。
- **数据不受影响**：修正操作只影响新进入 pipeline 的数据，已入库的 MongoDB 数据不回填。

## 7. 交接给实现者

- 必须遵守：
  - 以 `SPEC-03-004`（V1.2）为直接契约。
  - 不新增外部依赖（仅使用 yaml 标准库/已安装 PyYAML、pandas、datetime、pathlib）。
  - 不修改无关 hotel scraper 变更。
  - 不触碰真实 MongoDB 历史数据。
  - **`apply_command` 格式约束**：必须为可直接复制执行的 CLI 字符串，格式为 `python3 load_pending_confirmed.py --csv <path>`（单文件）或 `python3 load_pending_confirmed.py --date <YYYY-MM-DD>`（批量）。路径使用相对 scripts 目录的路径。
  - **`--date` 批量模式约束**：扫描 `review_pending/` 目录下匹配指定日期的 pending CSV 文件，逐个加载。无匹配文件时返回 `{loaded: 0, errors: []}`。
  - **resolved 标记约束**：仅在 upsert 成功后更新 pending JSON；upsert 失败或部分失败时不标记 resolved。`resolved_at` 使用 ISO 8601 带时区格式。
  - **`--name-mapping` 约束**：JSON 文件格式为 `{"原始名称": "正确名称"}`，在写入 MongoDB 前替换 `asset_name` 字段。
  - **V1.2 新增：联合修正约束**：
    - 配置加载 fail-closed：文件不存在/格式错误/解析失败时跳过，不 crash pipeline。
    - `apply_ocr_joint_corrections()` 必须在 `standardize_df_asset_names()` 之后、`correct_stock_names()` 之前调用。
    - 7 字段审计记录必须严格遵循 SPEC-03-004 §4.1.4 的顺序和字段名。
    - `review.audit_items[]` 必须始终存在（空数组也返回），不能因无命中就不存在。
    - `save_pending_review()` 的 `joint_audit` 参数向后兼容：不传或 None 时不写入 `audit_items` 到 pending JSON。
    - 修正后 `名称复核原因` 字符串格式：`OCR joint correction: code {source_code} + name {source_name_pattern} → {target_code} / {target_name}`。
  - **V1.2 新增：配置格式验证**：`_load_ocr_joint_corrections_config()` 对每条目校验 `source_code`/`source_name_pattern`/`target_code`/`target_name`/`reason` 五个字段均存在且非空；缺失任意字段则跳过该条目并 warning。
  - **V1.2 新增：累积治理原则**（RFC-03-004 §5.4 规定，设计层面需同步到实现）：映射列表随用户确认识别的 OCR 误读模式逐步增长。新规则必须经用户确认→代码审查→显式配置；条目达 50 条时评估升级策略；每年审查一次映射有效性。实现者不需要实现治理流程本身（运营流程），但需要确保 `config/ocr_joint_corrections.yaml` 的版本控制、代码审查和 fail-closed 行为支持上述治理。
- 可自行判断：
  - pending 文件字段顺序。
  - batch summary / closeout 文案措辞。
  - `--date` 模式下文件匹配模式（glob pattern）。
  - `config/ocr_joint_corrections.yaml` 的 YAML 格式细节（注释，缩进）。
  - 联合修正审计记录中 `original_name` 的值：使用标准化前/后的原始值（建议：从输入 DataFrame 在 `standardize_df_asset_names()` 之前备份 `资产名称` 列，或直接从输入参数捕获）。实现者选择一种方式，但必须在设计文档中说明。
  - `standardize_asset_name()` 的调用时机：联合修正的 name 匹配是在 **标准化后**（SPEC §4.1.1 规定），所以 `source_name_pattern` 匹配时 name 已是标准化后的值；但 `original_name` 审计字段应当记录 OCR 原始值（标准化前）。
- 遇到以下情况退回 Principal：
  - 需要新增 MongoDB pending 集合。
  - 需要定义人工确认 UI/API。
  - 现有 transformer 无法在过滤行后保留产品 NAV。
  - `apply_command` 需要支持除 `load_pending_confirmed.py` 以外的其他补录工具。
  - 联合修正需要扩展为无条件 code 替换（超出 F-011 窄范围）。
  - 需要修改 `stock_basic_info` 或 A 股主数据 API。

### 配置文件初版内容

```yaml
# skills/data/data-pipeline/scripts/config/ocr_joint_corrections.yaml
# OCR 代码/名称联合修正映射
# 当 OCR/解析输出的 Wind 代码和资产名称同时匹配 source 值时，联合修正为 target 值
# 变更前必须经过代码审查
- source_code: "688008.SH"
  source_name_pattern: "联讯仪器"
  target_code: "688808.SH"
  target_name: "联讯仪器"
  reason: "ocr_code_name_joint_correction"
```

## 8. 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-06-15 | 初始设计：review gate 核心架构 |
| V1.1 | 2026-06-17 | 新增 F-008（apply_command）、F-009（--date 批量模式）、F-010（resolved 标记）的详细设计；更新模块改动表、数据流、接口契约、实现计划和测试策略 |
| V1.2 | 2026-07-29 | **本任务（T2 Design）最终一致化**：新增 F-011（OCR 代码/名称联合修正）完整设计，含 `apply_ocr_joint_corrections()` 函数、`config/ocr_joint_corrections.yaml` 配置规范、7 字段审计数据模型（`review.audit_items[]`）、T1-T7 离线 fixture 矩阵（含新增 T7 image/message 共享入口）、C1-C4 配置异常处理测试表、pipeline 入口最小改动、回滚方案/版本控制要求、RFC §5.4 累积治理原则引用。与父任务 T1 RFC/SPEC V1.2 逐项一致。 |
