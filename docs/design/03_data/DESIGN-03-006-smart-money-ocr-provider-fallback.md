# DESIGN-03-006: Smart Money OCR Provider Fallback（MiniMax → Z.AI/GLM）

## 元数据

| 项 | 值 |
|---|---|
| 状态 | ✅ Implemented |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-25 |
| 最后更新 | 2026-06-25 (Closeout 完成) |
| 来源 RFC | RFC-03-006 |
| 来源 SPEC | SPEC-03-006 |
| 目标模块 | data-pipeline（OCR Provider 层） |
| 适配 Agent | YQuant-Developer-Engineer（Implement）、YQuant-Test-Engineer（Verify）、YQuant-Reviewer-Principal（Review） |

---

## 1. 设计摘要

本设计将 SPEC-03-006 定义的 OCR provider 抽象层落地为可执行的架构方案。核心思路：**在 Extractor 内部插入一个 `providers/` 子包**，把"调用哪个上游 OCR"从硬编码的 `mmx vision describe` 升级为可注册、可插拔、可 fallback 的 provider 链；`MiniMaxImageExtractor` 对外签名保持 `BaseExtractor.extract` 完全不变，下游 Transform / Validate / Loader / Review Gate / Batch Closeout 零改动。

设计的关键取舍：

1. **provider 注册表（dict）模式**（SPEC 决策 #5）：新增 provider 只需 `register_provider("qwen", QwenVisionProvider)`，Router 内部不硬编码 `if name == ...`。
2. **顺序 fallback、不做双向**（SPEC 决策 #6）：Router 按 `config.yaml` 的 `order` 列表依次尝试；Z.AI 失败直接上抛 RuntimeError，不回切 MiniMax。简单、可预测、延迟可控。
3. **Z.AI MCP client 选型 = Hermes MCP SDK（stdio transport）**（SPEC §12.2 移交项，本设计拍板）：复用已在 `config.yaml` 注册的 `@z_ai/mcp-server`，通过 MCP stdio 通道调用 "General Image Analysis tool"。详细理由见 §3.8。
4. **共享代码提取**：`VISION_PROMPT`、`_normalize_columns`、`_clean_data`、`_extract_json`、`_parse_date`、`_parse_percentage`、`_parse_number` 从 `MiniMaxImageExtractor` 迁到 `providers/` 子包，MiniMax 与 Z.AI provider 共用，避免 schema 漂移。
5. **审计字段透传不参与入库**：`provider_status` 作为只读审计字段向 pipeline result、batch summary、pending 文件透传，Transform / Validator / Loader 不感知。

---

## 2. 现状分析

### 2.1 相关目录与文件

- 核心目录：`skills/data/data-pipeline/scripts/`
  - `extractors/minimax_image_extractor.py`（当前 OCR 实现，531 行，硬编码 `mmx vision describe`）
  - `extractors/base.py`（`BaseExtractor` 抽象类）
  - `extractors/__init__.py`（导出 `MiniMaxImageExtractor` 等）
  - `transformers/asset_identity_review.py`（`save_pending_review` 所在文件）
  - `run_unified_image_pipeline.py`（统一 image pipeline 入口）
  - `run_image_pipeline.py`（portfolio-only image pipeline）
  - `run_trade_image_pipeline.py`（trade-only image pipeline）
  - `batch_report.py`（批次汇总与 closeout）
  - `test_load_pending_confirmed.py`、`test_codec_pipeline.py`（现有测试）
- 外部依赖：
  - `~/.hermes/profiles/yquant/config.yaml`（MCP servers 配置；`mmx` 与 `@z_ai/mcp-server` 已注册）
  - `~/.hermes/profiles/yquant/.env`（`Z_AI_API_KEY` 存放位置）

### 2.2 当前 OCR 调用路径（改造前）

```
MiniMaxImageExtractor.extract(image_path)
  └─ _run_vision_extraction(img_path)            # 硬编码 subprocess mmx vision describe
       ├─ 3 次指数退避重试（仅对 transient 错误）
       ├─ _is_retryable_failure(stdout, stderr)   # 关键字匹配
       ├─ _unwrap_mmx_response(output)            # 剥离 {"content": "..."} 外壳
       ├─ _extract_json(output)                   # markdown / 裸 JSON 提取
       ├─ _parse_vision_output(output)            # json.loads → DataFrame
       │    ├─ _normalize_columns(df)             # 字段别名 → 中文标准列名
       │    └─ _clean_data(df)                     # 日期/百分比/数值清洗
       └─ _write_vision_debug(status, ...)         # 写 pic_*_vision_*.json
```

重试 3 次耗尽后直接 `raise RuntimeError`，被 pipeline 顶层 catch → 整图 `failed`。没有 fallback。

### 2.3 现有约束

- `BaseExtractor.extract(source, **kwargs) -> list[dict]` 是所有 pipeline 入口的调用契约；`extract` 返回 `[{"df": DataFrame, "source_path": str}]`。
- `save_pending_review(*, pending_df, audit, source_root, folder_date, prefix, timestamp, fmt, source_path, excel_path) -> dict` 当前不接受 provider 信息。
- pipeline 入口 `run_unified_image_pipeline.py` 在 OCR 后立即读 `records[0]["df"]`，不读其他字段。
- `detect_format(df)` 依赖中文标准列名（`截止日期`、`资产名称`、`持仓比例` 等）判断 portfolio / trade 格式。
- 测试文件直接放在 `scripts/` 目录下（非 `scripts/tests/` 子目录）。

### 2.4 兼容性风险

- **schema 漂移**：Z.AI 输出列名/格式可能与 MiniMax 不同 → 用共享 `_normalize_columns` + `_clean_data` + Z.AI 专用别名映射收敛（SPEC §4.6）。
- **`provider_status` 透传中断**：如果 Extractor 委托 Router 后忘了把 `provider_status` 写回 record dict，审计链路会断 → 设计中明确 record dict 的 `to_record()` 序列化契约。
- **注册表全局状态污染**：测试间共享 `_REGISTRY` 可能互相干扰 → 测试必须 `unregister` 或用独立 module。
- **异步上下文**：现有 `_run_vision_extraction` 已是 async；MCP SDK client 可能有自己的 event loop 要求 → Router 与 provider 全部 async，统一用 `asyncio`。

---

## 3. 方案设计

### 3.1 目标目录结构（新增 `providers/` 子包）

```
skills/data/data-pipeline/scripts/
├── extractors/
│   ├── base.py                           # 不动
│   ├── minimax_image_extractor.py        # 重构：内部委托 Router
│   └── __init__.py                       # 不动
├── providers/                            # ★ 新增子包
│   ├── __init__.py                       # 包导出 + _bootstrap_registry()
│   ├── base.py                           # VisionProvider ABC、ProviderResult、ProviderError、FailureKind、FailureReason、AttemptRecord
│   ├── registry.py                       # _REGISTRY、register_provider、get_provider、list_providers
│   ├── router.py                         # VisionProviderRouter、RouterConfig
│   ├── prompts.py                        # VISION_PROMPT 常量（从 minimax_image_extractor 迁出）
│   ├── extract_json.py                   # extract_json()、_normalize_columns()、_clean_data()、_parse_date()、_parse_percentage()、_parse_number()、字段别名映射
│   ├── classify.py                       # classify_failure()、_sanitize_error()
│   ├── health_check.py                   # health_check_all()、check_minimax_cli()、check_zai_mcp()
│   ├── minimax_provider.py              # MiniMaxVisionProvider（封装现有 mmx 调用）
│   └── zai_provider.py                   # ZAIVisionProvider（封装 Z.AI MCP 调用）
├── tests/                                # ★ 新增（如尚不存在则创建）
│   └── test_ocr_provider_fallback.py     # 20 个单元测试 + 2 个集成测试
├── run_unified_image_pipeline.py         # 修改：透传 provider_status
├── run_image_pipeline.py                 # 修改：透传 provider_status
├── run_trade_image_pipeline.py           # 修改：透传 provider_status
├── transformers/
│   └── asset_identity_review.py          # 修改：save_pending_review 增加 provider_status kwarg
├── batch_report.py                       # 修改：items[] 允许携带 provider_status
└── ...
```

> **测试目录约定说明**：现有测试（`test_load_pending_confirmed.py`、`test_codec_pipeline.py`）直接放在 `scripts/` 下。SPEC §8.1 指定新测试路径为 `scripts/tests/test_ocr_provider_fallback.py`。本设计遵从 SPEC 路径，但建议 Developer 验证现有 `conftest.py` / `pytest` 配置是否从 `scripts/` 自动发现 `tests/` 子目录；若 pytest 未配置 `testpaths`，需确保 `tests/__init__.py` 存在或在 `conftest.py` 中加 `testpaths`。这是一次性配置事项，不影响接口设计。

### 3.2 模块结构图

```text
┌─────────────────────────────────────────────────────────────┐
│                    Pipeline 入口层                           │
│  run_unified_image_pipeline.py                              │
│  run_image_pipeline.py / run_trade_image_pipeline.py        │
│                                                             │
│  extractor = MiniMaxImageExtractor(output_dir, date_str)   │
│  records = await extractor.extract(image_path)             │
│      ↓ records[0] = {df, source_path, provider_status}     │
└──────────────────────────┬──────────────────────────────────┘
                           │ 委托（签名不变）
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              MiniMaxImageExtractor（重构后）                  │
│                                                             │
│  extract() 内部:                                            │
│    router = VisionProviderRouter(RouterConfig(...))         │
│    result = await router.describe(image_path)               │
│    return [result.to_record()]                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  VisionProviderRouter                        │
│                                                             │
│  按 RouterConfig.provider_order 顺序:                       │
│    [0] MiniMax → 成功 → 返回 ProviderResult(fallback=False) │
│    [1] Z.AI   → 成功 → 返回 ProviderResult(fallback=True)  │
│                                                             │
│  全部失败 → raise RuntimeError(双 provider 错误)             │
└──────┬───────────────────────────────┬──────────────────────┘
       │                               │
       ▼                               ▼
┌──────────────────┐          ┌──────────────────┐
│ MiniMaxVision    │          │  ZAIVision       │
│   Provider       │          │    Provider      │
│                  │          │                  │
│ subprocess.run(  │          │ MCP SDK client   │
│   mmx vision     │          │ (stdio transport)│
│   describe)      │          │                  │
│                  │          │ extract_json()   │
│ 3 次重试          │          │ + 别名映射        │
│ classify_failure │          │ classify_failure │
└────────┬─────────┘          └────────┬─────────┘
         │                             │
         ▼                             ▼
┌─────────────────────────────────────────────────────────────┐
│              共享层（providers/extract_json.py）              │
│                                                             │
│  extract_json(raw) → list[dict]                            │
│  _normalize_columns(df) → 标准中文列名                       │
│  _clean_data(df) → 日期/百分比/数值清洗                       │
│  _parse_date / _parse_percentage / _parse_number            │
└─────────────────────────────────────────────────────────────┘
         │                             │
         ▼                             ▼
┌─────────────────────────────────────────────────────────────┐
│              VisionProvider ABC + ProviderResult             │
│                                                             │
│  describe(image_path) -> ProviderResult                     │
│  health_check() -> bool                                     │
│                                                             │
│  ProviderResult: {df, source_path, provider_status}         │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 涉及文件清单

#### 3.3.1 新增

| 路径 | 用途 | 估计行数 |
|---|---|---|
| `scripts/providers/__init__.py` | 包导出 + `_bootstrap_registry()` 自动注册 minimax/zai | ~20 |
| `scripts/providers/base.py` | `VisionProvider` ABC、`ProviderResult`、`ProviderError`、`FailureKind`、`FailureReason`、`AttemptRecord` | ~120 |
| `scripts/providers/registry.py` | `_REGISTRY`、`register_provider`、`unregister_provider`、`get_provider`、`list_providers` | ~60 |
| `scripts/providers/router.py` | `VisionProviderRouter`、`RouterConfig` | ~130 |
| `scripts/providers/prompts.py` | `VISION_PROMPT` 常量 | ~20 |
| `scripts/providers/extract_json.py` | `extract_json()`、`_normalize_columns()`、`_clean_data()`、`_parse_date()`、`_parse_percentage()`、`_parse_number()`、`_ALIAS_MAP` | ~200 |
| `scripts/providers/classify.py` | `classify_failure()`、`_sanitize_error()`、`RETRYABLE_MARKERS`、`QUOTA_MARKERS`、`PARSE_MARKERS` | ~100 |
| `scripts/providers/health_check.py` | `health_check_all()`、`check_minimax_cli()`、`check_zai_mcp()` | ~60 |
| `scripts/providers/minimax_provider.py` | `MiniMaxVisionProvider`（封装现有 mmx 调用 + 3 次重试 + classify） | ~180 |
| `scripts/providers/zai_provider.py` | `ZAIVisionProvider`（MCP SDK client + extract_json + 别名映射） | ~160 |
| `scripts/tests/test_ocr_provider_fallback.py` | 20 单元测试 + 2 集成测试（SPEC §9） | ~500 |

#### 3.3.2 修改

| 路径 | 改动内容 | 估计改动行数 |
|---|---|---|
| `scripts/extractors/minimax_image_extractor.py` | 移除 `VISION_PROMPT` 及全部 `_run_vision_extraction` / `_is_retryable_failure` / `_write_vision_debug` / `_parse_vision_output` / `_unwrap_mmx_response` / `_extract_json` / `_normalize_columns` / `_clean_data` / `_parse_date` / `_parse_percentage` / `_parse_number`（迁到 providers/）；`extract()` 改为构造 Router 并委托；保留 `__init__`、`source_type`、`validate_source` 签名不变 | -350 / +60 |
| `scripts/run_unified_image_pipeline.py` | OCR 返回的 record dict 增加 `provider_status`；传给 `save_pending_review(provider_status=...)`；其余流程不变 | +10 |
| `scripts/run_image_pipeline.py` | 同上 | +10 |
| `scripts/run_trade_image_pipeline.py` | 同上 | +10 |
| `scripts/transformers/asset_identity_review.py` | `save_pending_review()` 增加 `provider_status: dict | None = None` kwarg；CSV 追加 `provider` 列；JSON 追加 `provider_status` 字段；向后兼容（无 provider_status 时不写新列） | +30 |
| `scripts/batch_report.py` | items[] 允许携带 `provider_status`（仅透传，不聚合）；`format_batch_closeout` 可选地打印一行 `provider=<name> fallback=<bool>` | +15 |
| `~/.hermes/profiles/yquant/config.yaml` | 新增 `ocr_providers` 段（SPEC §5.1） | +15 |
| `skills/data/data-pipeline/SKILL.md` | 新增"OCR Provider Fallback"段落引用本 DESIGN/SPEC | +20 |

#### 3.3.3 不改动（明确列出）

- `scripts/extractors/base.py`（`BaseExtractor` 接口不变）
- `scripts/extractors/__init__.py`（导出不变）
- `scripts/transformers/portfolio_excel_transformer.py`
- `scripts/transformers/trade_excel_transformer.py`
- `scripts/transformers/image_portfolio_normalizer.py`
- `scripts/transformers/trade_normalizer.py`
- `scripts/transformers/a_share_name_corrector.py`
- `scripts/validators/*.py`
- `scripts/loaders/mongodb_loader.py`
- `scripts/run_unified_message_pipeline.py`（消息路径不走 OCR）
- `scripts/run_message_pipeline.py`（同上）
- `scripts/load_pending_confirmed.py`（reader 端兼容策略属 SPEC-03-004 后续 patch）

### 3.4 调用时序图

#### 3.4.1 Happy Path（主 provider MiniMax 成功）

```text
Pipeline → Extractor → Router → MiniMaxProvider
                  Router 收到 result 后立即返回（fallback_used=False）；
                  ZAIProvider 完全不被实例化（UT-20 保证零开销）。
```

#### 3.4.2 Fallback Path（主失败 → 备成功）

```text
Router  try MiniMax → ProviderError(QUOTA_EXCEEDED, retryable=False)
       → 立即切备（不重试 quota）
       → get_provider("zai") + ZAIProvider.describe()
       → ProviderResult(name="zai", fallback_used=True,
                        attempts=[minimax_fail, zai_ok])
       → 返回 Extractor → 透传至 pipeline record dict
```

#### 3.4.3 Fallback 全失败 Path（主备皆败）

```text
Router  try minimax → ProviderError(QUOTA_EXCEEDED)
       → 切备
       try zai    → ProviderError(PARSE_ERROR)
       → 不做双向 fallback（决策 #6）
       → raise RuntimeError("[minimax] quota_exceeded: ... / [zai] parse_error: ...")
Pipeline 顶层 catch → 整图 status="failed"；attempts 总数=2
```

> 详细时序（含 process 名/箭头方向）与图示见 DESIGN 评审配套的 mermaid 版本（如需可在 Review 阶段补出）；本设计在 §3.6 数据流图中已包含所有关键组件与数据流向，时序图此处仅保留差异点描述，避免重复。
### 3.5 错误流图（按 SPEC FailureKind 枚举）

```text
                       ┌──────────────────────┐
                       │   mmx subprocess /   │
                       │   MCP SDK 调用       │
                       └──────────┬───────────┘
                                  │
                                  ▼
                       ┌──────────────────────┐
                       │  classify_failure()  │
                       └──────────┬───────────┘
                                  │
           ┌──────────┬───────────┼───────────┬──────────┐
           ▼          ▼           ▼           ▼          ▼
    ┌────────────┐┌──────────┐┌────────┐┌──────────┐┌─────────┐
    │CLI_NOT_FOUND││TIMEOUT   ││QUOTA_  ││NETWORK/  ││PARSE_   │
    │            ││          ││EXCEEDED││UNKNOWN   ││ERROR    │
    │retryable=F ││retry=T   ││retry=F ││NETWORK:T││retry=F  │
    │            ││          ││        ││UNKNOWN:F││         │
    └─────┬──────┘└────┬─────┘└───┬────┘└────┬─────┘└────┬────┘
          │            │          │          │           │
          ▼            ▼          ▼          ▼           ▼
    ┌─────────────────────────────────────────────────────────┐
    │            MiniMaxProvider 内部决策                       │
    │                                                         │
    │  retryable=True & attempts < 3 → 重试（指数退避）         │
    │  retryable=False OR 重试耗尽 → raise ProviderError       │
    └────────────────────────┬────────────────────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Router 接收     │
                    │  ProviderError   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ 有下一个 provider？│
                    └───┬──────────┬───┘
                       是          否
                        │          │
                        ▼          ▼
              ┌──────────────┐ ┌───────────────────┐
              │ 实例化并调用  │ │ raise RuntimeError │
              │ 下一个 provider│ │ (双 provider 错误) │
              └──────────────┘ └───────────────────┘
```

**各 FailureKind 的处理矩阵**（与 SPEC §7.1 对齐）：

| FailureKind | retryable | MiniMax 重试 | 触发 fallback | Z.AI 重试 |
|---|---|---|---|---|
| `QUOTA_EXCEEDED` | False | 否（立即切） | ✓ 立即 | 否 |
| `TIMEOUT` | True | ✓ 最多 3 次 | 重试全失败后切 | 否 |
| `NETWORK` | True | ✓ 最多 3 次 | 重试全失败后切 | 否 |
| `CLI_NOT_FOUND` | False | 否 | ✓ 立即 | — |
| `MCP_UNAVAILABLE` | False | — | — | 否（Z.AI 专用） |
| `PARSE_ERROR` | False | 否 | ✓ 立即 | 否 |
| `SCHEMA_MISMATCH` | False | 否 | ✓ 立即 | 否 |
| `UNKNOWN` | False | 否 | ✓ 立即 | 否 |

### 3.6 数据流与控制流

```text
图片输入 (image_path: Path)
  │
  ▼
[1] MiniMaxImageExtractor.extract(source)
  │   - source: str | list[str]
  │   - 遍历每张图，调用 Router
  │
  ▼
[2] VisionProviderRouter.describe(image_path)
  │   - 按 RouterConfig.provider_order 遍历
  │   - 实例化 provider: get_provider(name, output_dir, date_str)
  │
  ├──> [3a] MiniMaxVisionProvider.describe(image_path)
  │        │
  │        ├─ subprocess.run(["mmx", "vision", "describe", ...], timeout=120)
  │        ├─ 3 次指数退避重试（仅 retryable=True）
  │        ├─ classify_failure(stdout, stderr, returncode)
  │        ├─ _unwrap_mmx_response(output)
  │        ├─ extract_json(output)
  │        ├─ _normalize_columns(df) + _clean_data(df)
  │        └─ 返回 ProviderResult(name="minimax", fallback_used=False)
  │             或 raise ProviderError(classified)
  │
  ├──> [3b] ZAIVisionProvider.describe(image_path)   ← 仅在 [3a] 失败时
  │        │
  │        ├─ MCP SDK client → @z_ai/mcp-server (stdio)
  │        │   调用 "General Image Analysis tool"
  │        │   prompt = VISION_PROMPT
  │        ├─ 不重试（1 次失败即返回）
  │        ├─ classify_failure(exception=...)
  │        ├─ extract_json(raw_response) + 别名映射
  │        ├─ _normalize_columns(df) + _clean_data(df)
  │        └─ 返回 ProviderResult(name="zai", fallback_used=True)
  │             或 raise ProviderError(classified)
  │
  ▼
[4] Router 合并 ProviderResult
  │   - attempts = [provider[0]_record, provider[1]_record, ...]
  │   - fallback_used = (成功 provider 的 index > 0)
  │   - provider_status.name = 成功 provider 的 name
  │
  ▼
[5] Extractor 返回 [{df, source_path, provider_status}]
  │
  ▼
[6] Pipeline 下游（全部不变）
  │   - apply_asset_identity_review(df)       ← 只读 df
  │   - detect_format(df)                      ← 只读 df
  │   - split_review_rows(df)
  │   - save_pending_review(..., provider_status=...)  ← 新增 kwarg
  │   - PortfolioExcelTransformer / TradeExcelTransformer ← 只读 records[0]["df"]
  │   - validator / loader
  │   - batch_report（provider_status 仅透传）
  │
  ▼
输出: {status, image, excel_path, rows, format, review, pending, provider_status, ...}
```

### 3.7 接口形态

> 以下为 DESIGN 层的最终签名定稿。Developer 以此为准；签名直接取自 SPEC §4，本设计做了实现层补充（如 `__init__` 参数、工厂模式细节）。

> 完整的 dataclass/exception/enum 定义见 **SPEC §4.1-4.4**。以下仅列出本设计在实现层补充的关键形态。

**base.py**（SPEC §4.1-4.2 完整定义 + 本设计补充）：
- `VisionProvider` ABC 增加 `__init__(*, output_dir, date_str, **kwargs)`，统一所有 provider 的初始化参数。
- `ProviderResult.to_record() -> dict` 序列化为 `{df, source_path, provider_status}`，直接供 Extractor 返回。
- `AttemptRecord.to_dict()` 用于序列化到 `provider_status["attempts"]`。

**registry.py**（SPEC §4.3）：
- `_REGISTRY: dict[str, type[VisionProvider]]`、`register_provider` / `unregister_provider` / `get_provider` / `list_providers`。
- `providers/__init__.py` 的 `_bootstrap_registry()` 在 import 时自动注册 minimax + zai。

**router.py**（SPEC §4.4）：
- `RouterConfig.from_dict(d)` 从 config.yaml 的 `ocr_providers` 段构造；空 dict 时返回默认值 `order=["minimax","zai"]`。
- `VisionProviderRouter.__init__(config, *, factories=None)`：`factories` 参数供测试注入 mock。
- `describe(image_path) -> ProviderResult`：双 provider 失败时 `raise RuntimeError`。
- `health_check_all() -> dict[str, bool]`：不抛异常。

**minimax_provider.py**（SPEC F-003）：
- `MiniMaxVisionProvider.describe()` 封装 `subprocess.run(["mmx","vision","describe",...], timeout)` + 3 次指数退避重试 + `classify_failure` + `_unwrap_mmx_response` → `extract_json` → `_normalize_columns` → `_clean_data`。
- `health_check()`: `shutil.which("mmx")` 是否在 PATH。

**zai_provider.py**（SPEC F-004 + §4.6）：
- `ZAIVisionProvider.__init__` 中 `_mcp_client = None`（延迟初始化）。
- `describe()` 首次调用时初始化 MCP SDK client（§3.8）→ 调用 "General Image Analysis tool"（prompt=VISION_PROMPT）→ `extract_json` + `_ALIAS_MAP` 别名映射 → `_normalize_columns` → `_clean_data`。不重试（决策 #6）。
- `health_check()`: 检查 `Z_AI_API_KEY` 是否在 `os.environ`。

### 3.8 Z.AI MCP Client 选型（SPEC §12.2 移交项 — 本设计拍板）

SPEC §12.2 将 Z.AI MCP client 选型移交到 Design 阶段。本设计决策如下：

**选定方案：Hermes MCP SDK（stdio transport）**

| 维度 | stdio 子进程 | **Hermes MCP SDK (选定)** | HTTP REST |
|---|---|---|---|
| 与 MiniMax 一致性 | ✓（mmx 也是子进程） | ✗（SDK API 调用） | ✗ |
| 新增依赖 | 无 | `mcp` Python 包（SPEC §11.2 已允许） | `httpx` / `requests`（已有） |
| 配额/认证管理 | 需手动传 key | SDK 从 config 读取 | 需手动传 key |
| 工具发现 | 硬编码工具名 | SDK 可枚举工具 | 硬编码 endpoint |
| 错误处理 | 解析 stderr（脆弱） | SDK 有结构化错误 | HTTP status code |
| 与 Hermes 集成 | 需自建 wrapper | **原生集成** | 需自建 client |

**理由**：

1. SPEC §11.2 明确允许新增 "Hermes MCP 客户端" 依赖。
2. `@z_ai/mcp-server` 已在 `~/.hermes/profiles/yquant/config.yaml` 注册，MCP SDK 可直接复用该注册通道，无需手动管理连接参数。
3. MCP SDK 提供结构化错误（tool call 失败返回 JSON error 而非非零退出码），分类更准确。
4. 长期可扩展：未来新增 Qwen-VL / Doubao provider 如果也是 MCP server，可零成本接入。

**实现约束**：

- MCP client 在首次 `describe()` 调用时延迟初始化（不在 `__init__` 中连接），避免主 provider 成功时的零开销（UT-20 保证）。
- MCP 连接失败归类为 `MCP_UNAVAILABLE`（retryable=False），立即返回 ProviderError。
- **Spike 前置步骤**：Developer 在 Implement 阶段第一步必须做一次 spike，验证：
  1. `mcp` Python SDK 可成功 import；
  2. 通过 stdio 连接 `@z_ai/mcp-server` 成功；
  3. "General Image Analysis tool" 的确切工具名与调用参数 schema（用一张测试图片验证）。
  - Spike 失败则退回 stdio 子进程方案（如果存在 `zai` CLI wrapper），并 kanban_block 通知 Principal。

> ⚠️ 本设计**不读取** config.yaml 中的 MCP server 配置细节或 `.env` 中的 API key，遵守任务约束。Developer 在 spike 阶段按需读取。

### 3.9 配置项 Schema

#### 3.9.1 config.yaml 新增段（SPEC §5.1）

```yaml
# Smart Money OCR Provider Fallback 配置
# ⚠️ 仅 Orchestrator / Developer 修改；普通用户不应触碰。
ocr_providers:
  # provider 优先级顺序；首项为主，后续为 fallback 链。
  order:
    - minimax
    - zai
  primary_timeout_seconds: 120    # mmx 子进程超时
  fallback_timeout_seconds: 90    # Z.AI MCP 请求超时
  health_check_on_start: true     # 启动时检查 provider 可用性（仅日志）
  include_provider_status_in_debug: true  # 审计 JSON 是否携带 provider_status
```

#### 3.9.2 RouterConfig 加载流程

```text
config.yaml (ocr_providers 段)
  │
  ▼
RouterConfig.from_dict(yaml.safe_load(...).get("ocr_providers", {}))
  │
  ├─ provider_order: ["minimax", "zai"]
  ├─ primary_timeout_seconds: 120
  └─ fallback_timeout_seconds: 90
  │
  ▼
VisionProviderRouter(config)
  │
  └─ 按 provider_order 构造 factory 列表
     (默认用 registry；测试可注入 mock factory)
```

**默认值兜底**：如果 config.yaml 没有 `ocr_providers` 段（旧环境），`RouterConfig.from_dict({})` 返回默认值 `order=["minimax","zai"]`、timeout=120/90，保证零配置可用。

#### 3.9.3 错误分类与脱敏

`classify_failure()` 的标记集合（`RETRYABLE_MARKERS` / `QUOTA_MARKERS` / `PARSE_MARKERS`）与分类优先级（CLI_NOT_FOUND → TIMEOUT → QUOTA → NETWORK → PARSE → UNKNOWN）完整定义见 **SPEC §4.5**。`_sanitize_error()` 的脱敏规则（token 替换、home 路径替换、≤500 字符截断）见 **SPEC §7.3**。Developer 直接引用 SPEC 定义，不自行重新设计标记集合。

### 3.10 迁移路径（从当前硬编码 MiniMax 平滑切换）

本设计的核心原则是 **Extractor 对外签名零变化 + 下游零变化**，因此迁移是渐进的：

```text
阶段 0（当前）
  minimax_image_extractor.py
    └─ _run_vision_extraction() 硬编码 mmx
    └─ _is_retryable_failure() / _parse_vision_output() / ...
        ↓ 迁移
阶段 1（Implement Step 1-3）
  providers/ 子包建立
    ├─ VISION_PROMPT → providers/prompts.py
    ├─ _extract_json / _normalize_columns / _clean_data / _parse_* → providers/extract_json.py
    ├─ _is_retryable_failure → providers/classify.py (classify_failure)
    ├─ _run_vision_extraction → providers/minimax_provider.py (MiniMaxVisionProvider)
    └─ _write_vision_debug → 保留在 provider 内部
        ↓ 委托
阶段 2（Implement Step 4）
  minimax_image_extractor.py 重构
    └─ extract() 内部: router.describe(img) → result.to_record()
    └─ 对外: MiniMaxImageExtractor(output_dir, date_str).extract(source) 签名不变
    └─ 此时若 RouterConfig.order=["minimax"]（仅主），行为与改造前完全一致
        ↓ 启用 fallback
阶段 3（Implement Step 5-6）
  config.yaml 新增 ocr_providers.order=["minimax","zai"]
  providers/zai_provider.py 落地
  下游 save_pending_review(provider_status=...) 透传
```

**关键安全网**：
- 阶段 1 完成后，即使 Z.AI provider 还没实现，只要 `order=["minimax"]`，pipeline 行为与改造前完全一致。
- 阶段 2 完成后，跑一遍现有回归测试（`test_load_pending_confirmed.py`、`test_codec_pipeline.py`）确认零回归。
- 阶段 3 才真正启用 fallback；此时 Z.AI provider 已通过 spike 验证。

---

## 4. 实现计划

以下为 Implement 阶段的建议步骤顺序（Developer 执行）：

- [ ] **Step 0（Spike）**：验证 `mcp` Python SDK 可 import + stdio 连接 `@z_ai/mcp-server` 成功 + 确认 "General Image Analysis tool" 的确切工具名与参数 schema。Spike 失败则 kanban_block 通知 Principal。
- [ ] **Step 1**：创建 `providers/` 子包骨架：`base.py`（核心类型）、`registry.py`（注册表）、`prompts.py`（迁出 `VISION_PROMPT`）。
- [ ] **Step 2**：创建 `extract_json.py`（从 `minimax_image_extractor.py` 迁出 `_extract_json` / `_normalize_columns` / `_clean_data` / `_parse_date` / `_parse_percentage` / `_parse_number` + 新增 `_ALIAS_MAP`）。
- [ ] **Step 3**：创建 `classify.py`（`classify_failure` + `_sanitize_error` + 标记常量）。
- [ ] **Step 4**：创建 `minimax_provider.py`（`MiniMaxVisionProvider`：封装现有 mmx 调用 + 3 次重试 + classify + 共享 parse）。
- [ ] **Step 5**：创建 `zai_provider.py`（`ZAIVisionProvider`：MCP SDK client + `extract_json` + 别名映射）。
- [ ] **Step 6**：创建 `router.py`（`VisionProviderRouter` + `RouterConfig`）+ `health_check.py`。
- [ ] **Step 7**：重构 `minimax_image_extractor.py`（`extract()` 委托 Router，移除迁出代码）。
- [ ] **Step 8**：修改 `asset_identity_review.py`（`save_pending_review` 增加 `provider_status` kwarg + CSV/JSON 新字段）。
- [ ] **Step 9**：修改 `run_unified_image_pipeline.py` / `run_image_pipeline.py` / `run_trade_image_pipeline.py`（透传 `provider_status`）。
- [ ] **Step 10**：修改 `batch_report.py`（items[] 透传 `provider_status`）。
- [ ] **Step 11**：修改 `config.yaml`（新增 `ocr_providers` 段）+ `SKILL.md`（新增文档段落）。
- [ ] **Step 12**：编写 `tests/test_ocr_provider_fallback.py`（20 单元 + 2 集成）。
- [ ] **Step 13**：跑全量回归测试，确认零回归。

**推荐并行**：Step 1-3（骨架）可并行；Step 4-5（两个 provider）可并行；Step 8-10（下游透传）可并行。Step 7（Extractor 重构）必须在 Step 1-6 完成后。

---

## 5. 测试策略

### 5.1 单元测试（test_ocr_provider_fallback.py）

与 SPEC §9.1 的 20 个用例逐一对齐：

| 用例 | 描述 | 关键断言 | Mock 策略 |
|---|---|---|---|
| UT-01 | MiniMax 成功路径 | `fallback_used=False`, `name="minimax"`, `attempts` len=1 | mock `MiniMaxVisionProvider.describe` |
| UT-02 | quota 触发 fallback | `fallback_used=True`, `attempts` len=2, errors 含 minimax 摘要 | mock minimax raise QUOTA_EXCEEDED, zai 成功 |
| UT-03 | 超时 3 次后切 | minimax 3 次 attempt 都记录 | mock minimax 连续 TIMEOUT ×3, zai 成功 |
| UT-04 | 解析失败立即切 | minimax 只 1 次 attempt（不重试） | mock minimax raise PARSE_ERROR |
| UT-05 | 双 provider 都失败 | RuntimeError message 含双 provider 错误 | mock 双方均失败 |
| UT-06 | Z.AI markdown JSON 解析 | DataFrame 行数正确 | 喂 ```` ```json [...] ``` ```` 给 extract_json |
| UT-07 | Z.AI 字段别名映射 | 列标准化为中文 | 喂 `assetName/windCode/ratio` |
| UT-08 | Z.AI 夹杂前后文 | 仍能提取 | 喂「以下是提取结果：[...] 请审核」 |
| UT-09 | register 拒绝重复 | raise ValueError | 注册同 name 两次 |
| UT-10 | get_provider 未知名 | raise KeyError | 查 "qwen" |
| UT-11 | Router 不做双向 fallback | attempts 总数=2 | mock minimax 失败 → zai 失败 |
| UT-12 | health_check_all 不抛异常 | 返回 `{minimax:False, zai:True}` | mock minimax health 抛异常 |
| UT-13 | classify 各关键字命中 | kind + retryable 正确 | 喂 quota/timeout/parse/network/cli 各一例 |
| UT-14 | pending.csv 写 provider 列 | CSV 含 `provider` 列值="zai" | mock `save_pending_review` |
| UT-15 | pending.json 写 provider_status | JSON 含 `provider_status.name="zai"` | 同上 |
| UT-16 | pending.csv 向后兼容 | 无 provider_status 时不写 provider 列 | `provider_status=None` |
| UT-17 | 错误信息脱敏 | key 被替换为 `***` | 喂含 `sk-abc123` 的 stderr |
| UT-18 | debug JSON 扩展字段 | 含 `provider_status` 顶层字段 | 模拟 Router 失败 |
| UT-19 | config order 覆盖默认 | Router 第一个尝试 zai | 临时 yaml `order:[zai,minimax]` |
| UT-20 | 主成功路径零开销 | zai `__init__` 调用次数=0 | mock minimax 成功 |

### 5.2 集成测试

| 用例 | 描述 |
|---|---|
| IT-01 | dry-run 跑通 `run_unified_image_pipeline.py --dry-run`，mock 双 provider 不实际调用 mmx/MCP；断言返回 dict 含 `provider_status` |
| IT-02 | 构造测试图片，run pipeline 走通 minimax 路径（mock），断言 pending.csv/json 落盘格式正确 |

### 5.3 回归测试

- `test_load_pending_confirmed.py`：不修改即可通过（pending.csv 向后兼容）。
- `test_codec_pipeline.py`：不受影响（message pipeline 不走 OCR）。

### 5.4 不可自动化验证项

- Z.AI MCP 实际响应延迟与配额耗尽阈值：依赖真实 MCP 服务，生产环境观察。
- 两 provider 对同一图的识别一致率：留作后续 RFC（RFC-03-006 §8 方案 B）。

---

## 6. 风险、降级与回滚

| 风险 | 概率 | 影响 | 应对方案 | 降级 / 回滚 |
|---|---|---|---|---|
| Z.AI 输出 schema 与 MiniMax 差异大 → Transformer 失败 | 中 | 高 | 共享 `_normalize_columns` + `_clean_data` + 别名映射；provider 出口 schema 校验 | schema 校验失败 → 整图 fallback 失败语义 |
| `mcp` Python SDK 不可用或与 Z.AI server 不兼容 | 中 | 高 | Step 0 spike 前置验证；失败则退回 stdio 子进程方案 | kanban_block 通知 Principal；暂用 `order=["minimax"]` |
| Z.AI MCP 占用主对话 token 预算 | 中 | 中 | MCP 仅在 OCR 路径按需调用；延迟初始化；不在 `__init__` 连接 | UT-20 保证主成功时 zai 未实例化 |
| Z.AI 配额独立耗尽 | 低 | 中 | 双 provider 同时耗尽 → 回到现有失败语义 | 未来可加"配额预算计数器"（后续 RFC） |
| fallback 路径 pending 被误判为 MiniMax 误识 | 低 | 低 | pending.json + provider_status 记录实际 provider | 人工补录时显式提示 provider 来源 |
| 两 provider 对同一图识别不一致 → 重复入库 | 低 | 高 | OCR 阶段不写库；写入由 Transform/Loader 单点控制 | MongoDB unique key 兜底（已有） |
| 主备切换引入额外延迟（每图多 ~10s） | 中 | 中 | 仅主失败时切；正常路径零开销 | 未来可加超时预算 |
| mmx CLI 与 Z.AI MCP 配置状态不一致 | 中 | 中 | 启动 health_check 记录；不阻塞 | 仅双 provider 都不可用时失败 |
| 注册表全局状态在测试间污染 | 低 | 中 | 测试必须 `unregister` 或用独立 module | `register_provider` 默认拒绝重名 |
| `providers/extract_json.py` 迁出后行为微变 | 低 | 中 | 迁出后逐函数比对原 minimax_image_extractor 输出 | 回退到内联实现 |

### 回滚方案

**整体回滚**（fallback 方案上线后发现严重问题）：

1. 将 `config.yaml` 的 `ocr_providers.order` 改为 `["minimax"]`（仅主 provider）。
2. 此时 Router 只尝试 MiniMax，行为与改造前完全一致。
3. pipeline 入口代码已重构但对外签名不变，无需回退 Extractor 代码。

**单文件回滚**：

- `asset_identity_review.py` 的 `save_pending_review` 改动是向后兼容的（`provider_status=None` 时不写新列），无需回退。
- `run_unified_image_pipeline.py` 等的透传改动只增加字段、不删除字段，不影响旧消费者。

**降级方案（fallback 也失败时）**：

```text
两 provider 都失败
  → Router raise RuntimeError(双 provider 错误摘要)
  → Pipeline 顶层 catch → 整图 status="failed"
  → debug JSON 记录双方 provider_status.errors
  → batch_report 在 closeout 中标注 provider 双失败
  → 人工查看 debug JSON 决定是否手动重试或换日期
```

---

## 7. 交接给实现者

### 必须遵守

- 以 **SPEC-03-006** 为直接工作契约，本 DESIGN 为架构补充。
- 接口签名以 SPEC §4 + 本设计 §3.7 为准；不得自行更改公开签名。
- `MiniMaxImageExtractor.extract(source, **kwargs) -> list[dict]` 对外签名**不变**（SPEC 决策）。
- 所有 provider 必须实现 `VisionProvider` ABC 的 `describe()` + `health_check()`。
- MiniMax 最多 3 次重试（与现状一致）；Z.AI 不重试（决策 #6）。
- 错误信息必须经 `_sanitize_error()` 脱敏后才能写入 `provider_status.errors` / debug JSON。
- `Z_AI_API_KEY` 只从 `os.environ` 读取，禁止写入代码/配置/debug 文件/stdout。
- 不修改 Transform / Validate / Loader / Review Gate / Batch Closeout 的入参签名。
- 不新增除 `mcp`（MCP SDK）和 `pytest-asyncio`（如需）以外的第三方依赖。
- 不做反向 fallback（Z.AI → MiniMax，决策 #6）。
- 不暴露 `--provider-order` / `--ocr-fallback` CLI 参数给普通用户（决策 #1）。
- Z.AI MCP client 延迟初始化（不在 `__init__` 连接），保证主成功路径零开销（UT-20）。
- 共享代码（`VISION_PROMPT` / `_normalize_columns` / `_clean_data`）必须迁到 `providers/` 子包由双 provider 共用，禁止各自复制一份。

### 可自行判断

- `extract_json()` 内部的正则匹配策略（SPEC 给了模式，具体 regex 细节可微调）。
- debug JSON 中 `provider_status` 的嵌套结构（只要含 name/fallback_used/attempts/errors 四个键即可）。
- MCP client 的具体连接参数（从 config 读取的细节）。
- 测试中 mock 注入的具体方式（factory 参数 vs monkeypatch）。
- `_sanitize_error()` 的具体 token 匹配正则（只要覆盖 `sk-`/`AIza`/`Bearer` 即可）。
- pending.csv 中 `provider` 列的列位置（追加到末尾即可）。

### 遇到以下情况退回 Principal（kanban_block）

- `mcp` Python SDK 无法 import 或与 Z.AI server 不兼容（§3.8 spike 失败）。
- 需要修改 `BaseExtractor` 接口或 `MiniMaxImageExtractor` 公开签名。
- 需要新增除 `mcp` / `pytest-asyncio` 以外的第三方依赖。
- Z.AI "General Image Analysis tool" 的返回 schema 与预期差异巨大（需要独立的 prompt 或 post-processing 策略）。
- 发现 SPEC 与 RFC 存在实质不一致（如触发条件矩阵矛盾）。
- 需要修改 MongoDB schema 或新增集合。
- `extract_json.py` 迁出共享代码后发现 MiniMax 现有行为需要改变（如列映射规则需要调整）。

---

## 8. 设计层面的开放问题

以下问题在本设计阶段**不需要解决**，但记录在此供后续迭代参考：

| 编号 | 问题 | 当前处理 | 后续归属 |
|---|---|---|---|
| OQ-1 | 是否需要 Router 状态计数器（fallback 频率统计）？ | 先用 stderr 日志 + batch summary 透传，不持久化 | 后续 RFC |
| OQ-2 | Z.AI → MiniMax 双向 fallback？ | 不做（决策 #6，单向） | 后续 RFC |
| OQ-3 | 按图片类型智能路由（portfolio vs trade 走不同 provider）？ | 不做，纯顺序 fallback | 后续 RFC（RFC-03-006 §8 方案 B） |
| OQ-4 | provider 性能基准 / 成本对比？ | 不做 | 后续 RFC |
| OQ-5 | `--provider-override` CLI 参数（临时切换主备）？ | 不暴露（决策 #1） | 后续 RFC |
| OQ-6 | `minimax_image_extractor.py` 是否需要扩展 `**kwargs`？ | 默认不扩展；如 Implement 发现需要透传 `provider_status` 到 extract 返回值，用 record dict 字段而非 kwargs | Developer 可自行判断 |
| OQ-7 | MCP client 连接复用 vs 每次新建？ | 延迟初始化 + 复用（首次 describe 时创建，后续复用） | Developer 实现时决定 |

---

## 9. 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V0.1 | 2026-06-25 | 初始创建；从 SPEC-03-006 派生；确定 Z.AI MCP SDK 选型（§3.8）；模块结构图、调用时序图、错误流图、迁移路径、测试策略、回滚方案、实现者交接信息 |
