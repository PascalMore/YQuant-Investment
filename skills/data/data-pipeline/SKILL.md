---
name: data-pipeline
description: YQuant 数据管道框架。所有外部数据（API采集、文件导入、图片解析、消息提取）统一经由本管道处理，完成 Extract → Transform → Validate → Load 全流程。
---
# Data Pipeline

> **📌 Image Pipeline 实战笔记**：`references/image-pipeline-workflow.md` 记录 Smart Money 图片入库的完整实操流程、3 个日期概念辨析、孤儿 CSV 现象、NAV 字段名坑（`aum` 不是 `scale`）、`--date` 已删除等本会话踩过的坑。新会话涉及图片入库前先看这个文件。
>
> **📌 Agent 反模式清单（2026-06-26 用户明确反馈）**：`references/agent-overengineering-anti-patterns.md` 记录 9 条「agent 不要 over-engineer」反模式 — 收到图片后**只归档 + 跑 pipeline**，不要 vision 读图、不要 md5 去重、不要 sanity check、不要替用户决定并发/配额/降级、不要替用户猜 product_code 命名。新会话涉及图片入库前必看。
>
> **📌 图片入库多批推送实战（2026-06-27）**：`references/image-pipeline-multi-batch-2026-06-27.md` 记录用户分多批（9:46 + 10:02 + 10:10）推同一批持仓截图时，agent 如何区分"归档 vs 已跑 pipeline"、MongoDB 业务日期字段实际是字符串而非 datetime、OCR 输出全角括号 `市值（本币）` 导致 loader KeyError 的临时修复。
>
> **📌 6/26 早上失败复盘（Z_AI_API_KEY 缺失）**：`references/image-failure-postmortem.md` 记录早上 6 张并发跑 2 张失败的真正根因（profile .env 不注入裸跑子进程）+ 修复方案 + 验证步骤。看到 `Z_AI_API_KEY environment variable is required` 时**先看这个文件**，**不要直接套用 line 774 那个 pitfall**（那是另一回事）。
>
> **🔍 Z.AI MCP 工具清单（v0.1.2 实测）**：`references/zai-mcp-tools.md` — `@z_ai/mcp-server` 实际暴露 8 个 tool（`extract_text_from_screenshot` / `analyze_image` / `ui_to_artifact` 等），provider 选 tool 的优先级，**为什么以前 zai fallback 静默失败**（heuristic 选错 tool → 缺 required 参数）。图片 pipeline 的 JSON 提取优先 `analyze_image`，纯 OCR `extract_text_from_screenshot` 只作兜底。
>
> **🧯 Z.AI MCP fallback 生产修复（2026-06-26 晚间）**：`references/zai-mcp-fallback-runtime-2026-06-26.md` — MiniMax quota 耗尽后 ZAI fallback 的三连坑：`env:` 被轻量 YAML parser 拍平成顶层导致 MCP 子进程拿不到 `Z_AI_API_KEY`（已在代码里兼容）；tool 优先级改 `analyze_image` 优先（`extract_text_from_screenshot` 返回纯 OCR 文本无法满足 JSON 契约）。
>
> **🌐 Z.AI / GLM endpoint 规范（2026-06-26 实测）**：`references/zai-glm-endpoints.md` — `glm-5.2` Coding Plan 必须用 OpenAI Chat Completion endpoint `https://open.bigmodel.cn/api/coding/paas/v4`；Anthropic Messages endpoint `https://open.bigmodel.cn/api/anthropic` 只适合 Anthropic-compatible/custom provider；普通 `/api/paas/v4` 的 1113 不代表 Coding Plan 没额度。
>
> **🛠 env 加载诊断脚本**：`scripts/verify_env_loaded.sh` — 跑一次就能验证 pipeline 入口 + provider 入口的 self-load 是否都生效。`unset && .venv/bin/python` 模拟裸跑场景。

## 核心定位

data-pipeline 是 YQuant 的**统一数据摄入框架**，负责将各种来源的原始数据转化为结构化、已校验的存储数据。

所有数据流均走同一套管道，只是 **Extractor（采集节点）** 不同：
- `ApiExtractor` — 从 Tushare / AKShare 等 API 拉取
- `ImageParser` — 从图片（飞书/Telegram截图）中提取
- `FileExtractor` — 从 CSV / Excel 导入
- `MessageExtractor` — 从聊天消息中解析

## 架构

```
数据输入（图片/API/文件/消息）
        ↓
  ┌─────────────┐
  │  Extractor  │  ← 采集节点（按来源切换）
  └─────────────┘
        ↓
  ┌─────────────┐
  │ Transformer │  ← 数据清洗、字段映射、类型转换
  └─────────────┘
        ↓
  ┌─────────────┐
  │  Validator  │  ← Schema 校验、必填检查、范围校验
  └─────────────┘
        ↓
  ┌─────────────┐
  │   Loader    │  ← 写入 MongoDB / 文件 / 推送通知
  └─────────────┘
        ↓
  ┌─────────────┐
  │   Codec     │  ← 序列化传输编码（JSON↔Base64，可选 zlib 压缩）
  └─────────────┘
        ↓
  存储 / 跨系统传输
```

## 目录结构

```
data-pipeline/
├── SKILL.md                     ← 本文档
├── scripts/
│   ├── pipeline.py              ← 管道引擎（核心编排）
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py              ← Extractor 基类
│   │   ├── image_parser.py      ← 图片解析（Vision 模型）
│   │   ├── api_extractor.py     ← API 拉取（Tushare/AKShare）
│   │   ├── file_extractor.py   ← 文件导入（CSV / Excel）
│   │   └── message_extractor.py ← 聊天消息解析
│   ├── providers/               ← ★ Vision OCR provider 子包（SPEC-03-006）
│   │   ├── __init__.py          ← 包导出 + bootstrap_registry()
│   │   ├── base.py              ← VisionProvider ABC、ProviderResult、FailureKind
│   │   ├── registry.py          ← _REGISTRY、register/get_provider
│   │   ├── router.py            ← VisionProviderRouter、RouterConfig
│   │   ├── minimax_provider.py  ← MiniMaxVisionProvider（mmx vision describe）
│   │   ├── zai_provider.py      ← ZAIVisionProvider（Z.AI MCP 图像分析）
│   │   ├── prompts.py           ← VISION_PROMPT 常量
│   │   ├── extract_json.py      ← extract_json、normalize_columns、clean_data
│   │   ├── classify.py          ← classify_failure、sanitize_error
│   │   └── health_check.py      ← check_minimax_cli、check_zai_mcp
│   ├── transformers/
│   │   ├── __init__.py
│   │   ├── base.py             ← Transformer 基类
│   │   ├── field_mapper.py    ← 字段映射
│   │   └── normalizer.py       ← NaN/None 规范化
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── base.py            ← Validator 基类
│   │   └── schema_validator.py ← Schema 校验
│   ├── loaders/
│   │   ├── __init__.py
│   │   ├── base.py             ← Loader 基类
│   │   └── mongodb_loader.py   ← MongoDB 写入
│   └── serializers/
│       ├── __init__.py
│       └── base64_codec.py     ← JSON↔Base64 序列化（Transport 层）
│
│ ★ 常用运维脚本（agent 直接复用，不要重写）：
│   ├── check_data_completeness.py   ← 数据完整性检查（2026-06-27 新增）
│   ├── audit_pending_unmigrated.py  ← pending CSV 孤儿审计
│   ├── query_portfolio.py           ← 按 product_code 查询持仓
│   ├── load_pending_confirmed.py    ← pending 行入库（用户确认后）
│   └── stock_name_corrections.py    ← OCR 名称 → 主数据名静态映射
└── references/
    ├── image-pipeline-workflow.md       ← 图片入库实操笔记
    ├── agent-overengineering-anti-patterns.md ← Agent 反模式清单
    ├── image-failure-postmortem.md      ← 2026-06-26 失败复盘
    ├── zai-mcp-tools.md                 ← Z.AI MCP tool 列表
    ├── zai-mcp-fallback-runtime-2026-06-26.md ← 2026-06-26 晚间 fallback 三连坑修复
    ├── zai-glm-endpoints.md             ← Z.AI / GLM endpoint 规范
    ├── provider-fallback.md             ← Vision provider fallback RFC/SPEC
    └── provider-fallback-ops.md         ← Fallback 运维实战
    └── schemas/                ← 各数据类型 Schema 定义
        ├── financial.yaml       ← 财务数据 Schema
        ├── price.yaml           ← 行情数据 Schema
        └── manual_input.yaml    ← 手工输入数据 Schema
```

## Extractor 基类定义

```python
# scripts/extractors/base.py
from abc import ABC, abstractmethod
from typing import Any

class BaseExtractor(ABC):
    """数据采集节点基类"""
    
    @property
    @abstractmethod
    def source_type(self) -> str:
        """数据来源标识，如 'tushare', 'image', 'csv'"""
        pass
    
    @abstractmethod
    async def extract(self, source: Any, **kwargs) -> list[dict]:
        """
        执行采集
        - source: 数据来源（图片路径/URL、API 参数、文件路径等）
        - 返回: 结构化数据列表，每条为 dict
        """
        pass
    
    @abstractmethod
    async def validate_source(self, source: Any) -> bool:
        """校验数据来源是否有效"""
        pass
```

## Transformer 基类定义

```python
# scripts/transformers/base.py
from abc import ABC, abstractmethod

class BaseTransformer(ABC):
    """数据清洗转换节点基类"""
    
    @abstractmethod
    async def transform(self, records: list[dict]) -> list[dict]:
        """对 records 进行清洗转换"""
        pass
```

## Validator 基类定义

```python
# scripts/validators/base.py
from abc import ABC, abstractmethod
from typing import Optional

class ValidationResult:
    def __init__(self):
        self.valid: bool = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

class BaseValidator(ABC):
    """数据校验节点基类"""
    
    @abstractmethod
    async def validate(self, records: list[dict]) -> ValidationResult:
        pass
```

## Loader 基类定义

```python
# scripts/loaders/base.py
from abc import ABC, abstractmethod

class BaseLoader(ABC):
    """数据加载节点基类"""
    
    @property
    @abstractmethod
    def target_type(self) -> str:
        pass
    
    @abstractmethod
    async def load(self, records: list[dict]) -> dict:
        """
        执行加载
        - 返回: {"inserted": N, "updated": M, "skipped": K, "errors": [...]}
        """
        pass
```

## Pipeline 引擎

```python
# scripts/pipeline.py
class DataPipeline:
    """
    统一数据管道引擎
    将 Extractor → Transformer → Validator → Loader 串联
    """
    def __init__(
        self,
        extractor: BaseExtractor,
        transformer: BaseTransformer,
        validator: BaseValidator,
        loader: BaseLoader
    ):
        self.extractor = extractor
        self.transformer = transformer
        self.validator = validator
        self.loader = loader
    
    async def run(self, source: Any) -> dict:
        # 1. Extract
        raw_records = await self.extractor.extract(source)
        
        # 2. Transform
        clean_records = await self.transformer.transform(raw_records)
        
        # 3. Validate
        result = await self.validator.validate(clean_records)
        if not result.valid:
            raise ValueError(f"Validation failed: {result.errors}")
        
        # 4. Load
        load_result = await self.loader.load(clean_records)
        
        return load_result
```

## 使用示例

```python
from pipeline import DataPipeline
from extractors.minimax_image_extractor import MiniMaxImageExtractor
from transformers.normalizer import NaNNormalizer
from validators.schema_validator import SchemaValidator
from loaders.mongodb_loader import MongoDBLoader

pipeline = DataPipeline(
    extractor=MiniMaxImageExtractor(),
    transformer=NaNNormalizer(),
    validator=SchemaValidator(schema_name="manual_input"),
    loader=MongoDBLoader(db_name="tradingagents", collection="manual_input_data")
)

# 图片输入 → 全自动管道处理
result = await pipeline.run(source="/path/to/screenshot.png")
# result: {"inserted": 1, "updated": 0, "skipped": 0, "errors": []}
```

## 已有 Extractor

| Extractor | 状态 | 说明 |
|-----------|------|------|
| `MiniMaxImageExtractor` | ✅ 已完成 | 从图片解析结构化数据（MiniMax CLI Vision） |
| `ApiExtractor` | 待实现 | 从 Tushare / AKShare API 拉取 |
| `FileExtractor` | 待实现 | 从 CSV / Excel 导入 |
| `MessageExtractor` | 待实现 | 从聊天消息中解析 |

## 已有 Codec

| Codec | 状态 | 说明 |
|-------|------|------|
| `Base64Codec` | ✅ 已完成 | JSON↔Base64，支持嵌套结构聚合 + zlib level=9 压缩 |

### Base64Codec 使用

```python
from serializers.base64_codec import Base64Codec, encode_json, decode_base64

# 嵌套结构 + zlib 压缩（默认，推荐，用于传输/存储）
codec = Base64Codec(
    compress=True,             # zlib level=9 压缩
    data_layout="nested",     # 按 group_key 分组聚合
    group_key="产品名称",     # 分组字段
    position_fields=[        # positions 内保留的字段
        "Wind代码", "资产名称", "持仓比例", "数量", "市值(本币)"
    ]
)
b64 = codec.encode(records)   # list[dict] → Base64
data = codec.decode(b64)       # Base64 → nested dict

# 扁平结构 + 无压缩（调试场景）
codec_flat = Base64Codec(compress=False, data_layout="flat")

# 便捷函数（单行调用，默认嵌套+压缩）
b64_str = encode_json(records, compress=True,
                      group_key="产品名称",
                      position_fields=["Wind代码","资产名称","持仓比例","数量","市值(本币)"])
data = decode_base64(b64_str)
```

### 嵌套结构说明

| 模式 | Base64 长度 | 适用场景 |
|------|-------------|---------|
| **nested + gzip** | ~5,700 chars | ✅ **生产/传输**（默认） |
| flat + plain | ~89,000 chars | 调试/可读性要求高 |

嵌套结构将每行重复的产品级字段提取到外层，只在 positions 数组内保留持仓字段，zlib 压缩前就消除了大量冗余文本。

### 定位说明

JSON↔Base64 不属于传统 ETL 的 Extract/Transform/Load 步骤，而是 **Transport / Serialization 层**：


```
数据输入 → Extract → Transform → [Codec: JSON↔Base64] → Load → 存储/传输
                                              ↑
                                   用于跨边界传输
                          （HTTP Header / JSON 字段 / 文件存储 / 消息队列）
```

## 读取（只读查询）：核对持仓 / 交易 / 产品元数据

除了入库（write）路径外，`PortfolioMongoLoader` 也是核对库内数据最快的入口。
**只读查询也应该走它**，不要手动拼 MongoClient 连接串（凭证从 `skills/.env` 加载的逻辑只在 loader 内部）。

### 关键方法（容易猜错）

- ✅ `loader._get_client()` — 返回 `MongoClient`
- ✅ `loader._db()` — 返回 `Database`（内部走 `_get_client()` 懒加载）
- ❌ `loader._client()` — **不存在**，调用会返回 `None`，然后 `None(...)` 报 `TypeError: 'NoneType' object is not callable`

第一次用的时候大概率会写成 `loader._client()`（因为属性名带下划线），调试半天。

### 一行式核对脚本

```bash
PYTHONPATH=skills/data/data-pipeline/scripts:/home/pascal/workspace/yquant-investment \
  /home/pascal/workspace/yquant-investment/.venv/bin/python - <<'PY'
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
print(db["portfolio_position"].count_documents({"product_code": "SM002"}))
PY
```

更完整的可复用模板见 `scripts/query_portfolio.py`（支持产品代码 + 日期范围 + 自动 sanity check）。

### 业务日期字段（集合 → 业务日期字段名）

| 集合 | 业务日期字段 |
|------|------------|
| `portfolio_basic_info` | 无（按 `product_code` 唯一） |
| `portfolio_nav` | `nav_date` |
| `portfolio_position` | `position_date` |
| `portfolio_trade` | `trade_date` |

复合唯一键：

- `portfolio_position`: `(position_date, product_code, asset_wind_code)`
- `portfolio_trade`: `(trade_date, product_code, asset_wind_code, direction)`

### Pitfall: `product_code` vs `product_name` 是两个字段

用户口语里可能说"ZO-002"或"那个中欧产品"，但 MongoDB 查询必须用 `product_code`（如 `SM004`）。混淆后会得到"无数据"假象。

| 字段 | 含义 | 取值示例 |
|------|------|---------|
| `product_code` | 系统内唯一标识，查询用这个 | `SM001 / SM002 / SM003 / SM004 / SM012 / CCT-001` |
| `product_name` | 业务展示名/对外名 | `ZO-001 / ZO-002 / ZO-003 / ZO-004 / ZO-012 / CCT-001` |

诊断步骤：
1. 用户报"查不到 XX" → 先看 `portfolio_basic_info`，里面有完整 product_code ↔ product_name 映射
2. 在不知道 product_code 的情况下，可以用 `product_name` 反查：

```python
db["portfolio_basic_info"].find_one({"product_name": "ZO-002"})
# → {"product_code": "SM004", "product_name": "ZO-002", ...}
```

3. 或者列全表自检：

```bash
python scripts/query_portfolio.py --list-products
```

`portfolio_position.distinct("product_code")` 当前：`SM001 / SM002 / SM003 / SM004 / SM012 / CCT-001`。
`portfolio_basic_info.distinct("product_name")` 对应：`ZO-001 / ZO-002 / ZO-003 / ZO-004 / ZO-012 / CCT-001`。

> 当 `query_portfolio.py --product SM004 --sanity` 返回 `candidates: []` 且 `all_distinct` 包含 `SM004`，说明用户可能用了产品名（如 `zo-002`），不是系统真的没数据。

### Pitfall: 找不到 product_code 时的诊断流程

当用户报"查不到 XX"时，按以下顺序确认（避免误判是 query 写错还是真的没数据）：

1. **大小写/分隔符扫描** — 跑几个常见变体（`sm002 / SM002 / Sm002 / sm_002`），有时产品代码在入库时被规范化
2. **正则扫描** — `re.compile("^sm.*002$", re.IGNORECASE)` 看有没有近义编码
3. **`distinct("product_code")`** — 直接列出库里所有产品，避免被记忆中的代码误导
4. **sanity check** — `count_documents({"product_code": X})` 全表累计，看是真的没数据还是范围写错
5. **同库其他集合** — 查 `portfolio_basic_info`，如果元数据不存在说明这个产品根本没建过档

只有 1–5 步全为空，才能下结论"该 product_code 在 tradingagents 库里不存在"。

### 已知产品代码清单（截至 2026-06）

`portfolio_position.distinct("product_code")` 当前：`SM001 / SM002 / SM003 / SM004 / SM012 / CCT-001`。

如果用户提到不在这个清单里的产品代码，先用上面 1–5 步确认，再回问确认（避免用户记错/笔误）。

## 📊 数据完整性检查（用户问"XX 区间数据齐不齐"时用）

**触发场景**：用户问「检查 2025-07-07~09 portfolio_position/nav/trade 完整性」「portfolio 缺哪些日期」「trading day 覆盖率」等。

**复用脚本**：`scripts/check_data_completeness.py`（2026-06-27 新增）。

```bash
# 默认扫所有已知产品 × position/nav/trade 三个集合
.venv/bin/python skills/data/data-pipeline/scripts/check_data_completeness.py \
  --start 2025-07-07 --end 2025-07-09

# 指定产品
.venv/bin/python scripts/check_data_completeness.py \
  --start 2025-07-07 --end 2025-07-09 --products SM001,SM002

# JSON 输出（供下游程序消费）
.venv/bin/python scripts/check_data_completeness.py \
  --start 2025-07-07 --end 2025-07-09 --json
```

**脚本内部已修复的坑**（详见 P6a）：
- 用 `$in` 字符串数组而非 `$gte` datetime 对象（避免 `bson.errors.InvalidDocument`）
- 用 `holding_ratio / shares / market_value` 而非错误的 `position_ratio / quantity / market_value_local`
- 自动剔除周末（`date.weekday() >= 5`）

**输出**：
- 矩阵：product × trading_day 行数（自动剔除周末）
- Gap 分析：position / nav 在交易日缺数据的明确清单
- trade 不算 gap（trade 是稀疏的，**不是每个产品每天都有交易** — 用户 2026-06-27 明确反馈）

**报告模板**（用户问"数据完整性"时）：

```
## 📊 YYYY-MM-DD ~ YYYY-MM-DD 数据完整性报告

**日历核对**：X/X=周一 ✅ ... X/X=周末 ❌

### portfolio_position（持仓快照）
| 产品 | X/X | X/X | X/X | sum |
...

### portfolio_nav（净值）
| 产品 | ...

### portfolio_trade（成交明细 — 注意稀疏）

### 结论
- 真实缺失：product X 在 X/X 缺持仓（业务数据未传）
- trade 0 行 = 这天确实没交易（正常）
```

**反例（agent 本会话 2026-06-27）**：
- 没检查 `date.weekday()` 就说"7/8~7/9 是周末" — 实际是周二/三，**导致误判真实缺失**
- 用 `datetime.date(2025,7,1)` 直接做 MongoDB 查询 → `bson.errors.InvalidDocument`
- 用 `position_ratio / market_value_local` 字段名 → KeyError

### 设计原则 — 接口层强制安全 > 文档层提醒安全（2026-06-26 用户明确原则）

> 用户的工程原则：「**能否就不传呀，因为传错比不传更危险**」。

**对新增/修改 argparse 参数的影响**：
- 任何「可能传错」的参数都比「保留」更危险 → 默认应删除
- argparse 接受但内部不读的字段 = **dead field = 设计债**，迟早被误用
- 默认安全做法：参数化先做"实地调研"（grep 全链路引用 + 看 prompt / provider / loader 哪步真用它）→ 没用就删
- 保留 dead field + 写 pitfall 不如直接删 — 让老调用方 argparse error 比静默接受错值更安全

**对 SKILL.md 文档的影响**：
- 当某段说「不要传 X」「X 是 no-op」→ **优先做接口级修复**（删 X），不是反复强调文档
- 文档警告是兜底，不是首选
- "Pitfall — X 参数是 no-op" 这种段是"未做接口修复时的临时护栏"；做完整治后该段改写为"X 已删除"的事实陈述

**实战案例**（2026-06-26）：
- `run_unified_image_pipeline.py` 的 `--date` 原本是 dead field（argparse 接、内部链路不读）
- 三轮对话：发现 dead field → 用户要求删除 → 完整 4 阶段清理（接口 + provider 内部 + 调用方 + 文档）
- 改完后 argparse 直接报错「unrecognized arguments: --date 2025-07-16」 → 强制让误用浮出水面

**对其他模块的推广**：每次修改 pipeline / config / 业务入口前，先 grep 是否有「argparse 接受但内部不读」的 dead field。同样的改造已落地的：`run_unified_image_pipeline.py` / `run_image_pipeline.py` / `run_trade_image_pipeline.py`。未动的（按业务合理保留 `--date`）：`run_unified_message_pipeline.py` / `run_message_pipeline.py` / `run_trade_message_pipeline.py`（消息入口无 OCR，`--date` 是截止日期 hint，不是 dead field）。

## YQuant 会话入口：用户发图 → 归档 → 跑 pipeline

用户在 YQuant 会话中发送图片时，**不要**直接从截图解析出结构化数据入库。正确流程：

### 1. 归档图片（agent 第一步）

收到用户图片后立即保存到归档目录（**先不要做任何 OCR/解析**）：

```bash
# 归档目录命名：使用系统当前日期（user 发送图片的"今天"）
ARCHIVE_DATE=$(date +%Y-%m-%d)
IMAGE_DIR="/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image"
mkdir -p "$IMAGE_DIR"

# 命名用时间戳，**不要加 _unknown 后缀**（2026-06-26 用户纠正：多此一举）
DST="$IMAGE_DIR/portfolio_${ARCHIVE_DATE}_$(date +%H%M%S).jpg"
cp <用户截图本地路径> "$DST"
```

**关键 Pitfall — 三个日期概念不要混淆**（2026-06-25 用户真实纠正过）：

| 日期 | 含义 | 用途 |
|------|------|------|
| **归档日期** (archive_date) | 用户**发送图片的当天** | 目录命名 `skills/data/source/smart-money/{archive_date}/image/` |
| **业务日期** (business_date) | 图片**内容显示的日期** | 由 OCR 自己从 `截止日期` 列读取，写入 MongoDB 的 `trade_date` / `position_date` / `nav_date` 字段 |
| **系统日期** (system_date) | pipeline **实际跑的时刻** | pipeline 内部归档目录会再用一次系统日期（可能和 archive_date 跨日） |

**为什么归档日期 ≠ 业务日期**：用户可能 6/25 晚上发来 6/24 的日报，归档到 25（当天）；入库 `position_date` 走 OCR 识别的 6/24。**2026-06-26 改造后**：`run_unified_image_pipeline.py` 已删除 `--date` 参数，agent 不要再传日期，OCR 读完图自动入库。**这是 SKILL.md 里没说清的盲点**——之前容易误把业务日期当归档目录用。

### 2. 跑 pipeline（agent 第二步）

**不要传 `--date` 参数**。`run_unified_image_pipeline.py` 已删除 `--date`（2026-06-26 改造），传了 argparse 会直接报错。正确命令：

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image "$DST"
```

**注意**：pipeline 内部**会再次用系统当前日期建归档目录**（如 `2026-06-26/`），和 agent 第一步的归档目录（`2026-06-25/`）**可能不同**。这是预期行为——目录日期使用系统接收日期（SKILL.md 原文），不是 bug。

### 3. 禁止行为（用户已明确纠正过）

❌ **不要**从截图直接解析出结构化数据再写入 MongoDB。即使 OCR 后是同一份数据，也**必须**走 pipeline 流程，触发 `stock_basic_info` 名称复核、`missing_master` 状态标记等标准流程。

❌ **不要**用 `execute_code` 工具跑 pipeline 验证查询——它用 Hermes venv，**没有 pymongo / openpyxl**。验证 MongoDB 入库用 `.venv/bin/python -c` + `PortfolioMongoLoader` 模板（见下方"运行验证"）。

❌ **不要**在归档前 md5 去重 / 归档后 MongoDB sanity check（重发就让 pipeline 跑，MongoDB unique key 自然 upsert）。详见 `references/agent-overengineering-anti-patterns.md`。

❌ **不要**在归档命名里猜 product_code（用时间戳即可，**不要**加 `_unknown` 后缀 — 用户 2026-06-26 明确反馈「为什么是 xxxx_unknown.jpg」）。详见 `references/agent-overengineering-anti-patterns.md`。

### 4. 运行验证（pipeline 跑完后）

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment:/home/pascal/workspace/yquant-investment/skills/data/data-pipeline/scripts \
  .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
print(db['portfolio_trade'].count_documents({'trade_date': '<业务日期>'}))
# 进一步聚合 by product_code
pipeline = [
    {'\$match': {'trade_date': '<业务日期>'}},
    {'\$group': {'_id': '\$product_code', 'count': {'\$sum': 1}}}
]
for d in db['portfolio_trade'].aggregate(pipeline):
    print(f'  {d[\"_id\"]}: {d[\"count\"]} 条')
"
```

## 开发进度

- [x] SKILL.md（本文档）
- [x] 基类定义（base.py 各层）
- [x] MongoDBLoader（PortfolioMongoLoader）
- [x] NaNNormalizer（normalize_all）
- [x] SchemaValidator
- [x] ImageParserExtractor（MiniMax Vision OCR）
- [x] 消息 Portfolio Pipeline（run_message_pipeline.py）
- [ ] ApiExtractor（Tushare / AKShare）
- [ ] FileExtractor（CSV / Excel）
- [ ] MessageExtractor（聊天消息解析）
- [ ] 飞书消息接入
- [ ] Telegram 消息接入

## Message Portfolio Pipeline（消息直接输入）

用户提供 TSV/CSV 文本，无需 OCR，直接解析 → Excel → normalize → MongoDB。

### 入口脚本

```bash
python scripts/run_message_pipeline.py -i "raw text..." -d 2026-05-03
python scripts/run_message_pipeline.py -f /path/to/data.txt -d 2026-05-03 --dry-run
```

### Python API

```python
import asyncio
from scripts.run_message_pipeline import run_pipeline

result = asyncio.run(run_pipeline(
    raw_text="截止日期\t产品名称\t...",
    date_str="2026-05-03",
    source_root=Path("skills/data/source/smart-money"),
    dry_run=False,
))
```

### 流程

- Step 1: 文本解析 → Excel → `source/smart-money/{date}/portfolio_{YYYYMMDD}.xlsx`
- Step 2: Excel → `PaddleOCRExcelTransformer` → `normalize_all()` → basic_info / nav / position
- Step 3: validate + MongoDB（复用现有模块）

### Extractor

`extractors/MessagePortfolioExtractor` 读取已保存的 Excel：

```python
from extractors import MessagePortfolioExtractor
ext = MessagePortfolioExtractor()
records = await ext.extract("2026-05-03")  # 传入日期字符串
# → [{"df": DataFrame, "source_path": "..."}]
```

## Image Portfolio / Trade Pipeline（图片 OCR 输入）

图片 pipeline 使用 MiniMax Vision OCR，将截图解析为 DataFrame，再自动识别为 portfolio 或 trade 格式，后续统一进入 Transform → Validate → MongoDB。

### OCR Provider Fallback（MiniMax → Z.AI/GLM）

图片 OCR 现在走 `VisionProviderRouter`，主 provider 失败时自动降级到 Z.AI/GLM Vision MCP。设计目标：让 MiniMax 配额耗尽 / 临时不可用时，pipeline 不再整图 `failed`，而是落到备用 provider 继续走通。

**配置位置**：`~/.hermes/profiles/yquant/config.yaml` → `ocr_providers` 段。

```yaml
ocr_providers:
  order: [minimax, zai]   # 主 provider + fallback 链（单向，决策 #6）
  primary_timeout_seconds: 120
  fallback_timeout_seconds: 240   # glm-4.6v OCR 复杂表格 ~100s，90s 不够
  health_check_on_start: true
  include_provider_status_in_debug: true
```

> ⚠️ **Timeout tuning（2026-06-26 实测）**：Router 内部用 `asyncio.wait_for(timeout=fallback_timeout_seconds + 30)`。glm-4.6v 处理复杂表格截图 OCR 需要 ~100-105s。原默认 90s（有效超时 120s）会被 SIGTERM 杀掉。调到 240s（有效超时 270s）后稳定通过。

**不暴露原则**（决策 #1）：普通用户不能通过 CLI 切换 provider 顺序。`run_unified_image_pipeline.py` 不新增 `--provider-order` / `--ocr-fallback` 之类参数。需要临时改主备顺序，编辑 `config.yaml` 即可。

**审计字段**：`MiniMaxImageExtractor.extract()` 返回的每条 record 现在多带一个 `provider_status` dict，含 `name` / `fallback_used` / `attempts` / `errors` 四个键。下游消费者（`save_pending_review` / `batch_report`）仅透传，不参与入库决策：
- `pending.csv` 多一列 `provider`（值=`minimax` 或 `zai`）；旧调用方不传 `provider_status` 时**不写**新列（向后兼容）。
- `pending.json` payload 多一个 `provider_status` 字段。
- `batch_report` closeout 文本在末尾多一段「OCR provider 来源」短行（不打印完整 `provider_status` 全文）。

**回滚**：将 `ocr_providers.order` 改为 `[minimax]`（仅主），Router 只跑 MiniMax，行为与改造前完全一致；无需回退 Extractor 代码。

**参考资料**：
- RFC：`docs/rfc/03_data/RFC-03-006-smart-money-ocr-provider-fallback.md`
- SPEC：`docs/spec/03_data/SPEC-03-006-smart-money-ocr-provider-fallback.md`
- Design：`docs/design/03_data/DESIGN-03-006-smart-money-ocr-provider-fallback.md`

### 批量图片并行处理模式

当用户一次发送多张图片时（≥3张），正确做法是**每张图独立提交后台任务**，而不是在一个 for 循环里批量后台执行：

```bash
# ❌ 错误：6张图写在一个后台命令里，输出截断，无法追踪
# （同时：传 --date 也会 argparse error；--date 已删除）
for img in $IMAGES; do
  run_unified_image_pipeline.py --image $img --date $DATE &
done
wait   # 输出可能被截断

# ✅ 正确：每张图独立后台任务，独立 session_id，可分别追踪
for img in $IMAGES; do
  terminal(background=true, notify_on_complete=true,
    command="cd /home/pascal/workspace/yquant-investment && PYTHONPATH=/home/pascal/workspace/yquant-investment .venv/bin/python skills/data/data-pipeline/scripts/run_unified_image_pipeline.py --image $img")
done
# 等全部 notify 后再汇总
```

**YQuant 项目 venv 查找顺序**（优先级从高到低）：

1. **模块自身 venv**（如 `skills/xxx/.venv`）
2. **项目根目录 `.venv`** — fallback，统一环境（需手动创建）

> ⚠️ 不再经过 `TradingAgents-CN` 作为中转。每个 skill 的 venv 只管理自己。

**入口脚本**（**2026-06-26 改造后**：`--date` 已删除，argparse 会拒绝 `--date`，agent 不要传）：

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image /path/to/image.jpg
```

> 注意：根目录 `.venv` 需要 `PYTHONPATH` 才能解析项目内部 `skills.xxx` 导入。`TradingAgents-CN` venv 因架构差异不经过根目录 fallback。

关键目录语义：

- `skills/data/source/smart-money/{system_date}/image/`：归档原始图片、OCR raw JSON、生成的 Excel。
- `skills/data/source/smart-money/{system_date}/review_pending/`：需要人工确认的 Wind code / asset name 异常 CSV 与 JSON。
- 归档目录**永远用系统接收日期**（`folder_date = datetime.now()`），与 `--date` 无关。业务日期 `position_date` / `nav_date` 由 OCR 自己从图内 `截止日期` 列识别（2026-06-26 改造后 `run_unified_image_pipeline.py` 已删除 `--date` 参数）。

MiniMax raw/debug JSON 文件命名为 `pic_{timestamp}_vision_raw.json`、`pic_{timestamp}_vision_retry.json` 或 `pic_{timestamp}_vision_error.json`，只作为 OCR 审计与问题复盘材料，不作为后续入库入口。

**原因**：同一个 shell 命令内的多个后台子进程（`&`）共享一个输出流，Hermes 的 `process` 工具只能追踪通过 `terminal(background=true)` 创建的独立任务，不识别 shell 内嵌的后台子进程。输出截断时只能重新运行。

**后台任务无输出 ≠ 卡死**（2026-06-26 实战）：`run_unified_image_pipeline.py` 在非 TTY 后台进程里 stdout 可能被缓冲；OCR provider 等待期间 `process.poll/log` 可能连续数分钟显示空输出，但 Python 子进程 RSS/socket 仍在变化。不要因 0 输出立刻 kill 或重跑。先 `process.poll` 看进程仍 running；必要时用 `ps -eo pid,etimes,rss,args | grep run_unified_image_pipeline` 确认子进程仍活；等到 provider timeout/retry 自然完成。只有进程退出非 0 或超过预期 timeout 后，才按“两阶段失败处理”汇报临时方案。

**会话累积模式**：如果用户分多次发送图片，每次新图片到来时继续独立后台提交，所有 pending 记录跨所有图片累积，等用户发送「就这些」等触发词后一次性展示所有 pending 汇总。

**批次 closeout 后 pending 汇总命令**：
```python
# 汇总所有 pending 文件中的待确认记录
from pathlib import Path
import pandas as pd

pending_files = sorted(Path(f"skills/data/source/smart-money/{date}/review_pending").glob("*_pending.csv"))
for pf in pending_files:
    df = pd.read_csv(pf)
    pending = df[df["名称复核状态"] == "pending_review"]
    if len(pending):
        print(f"\n=== {pf.name} ({len(pending)} pending) ===")
        print(pending[["产品代码","Wind代码","资产名称","持仓比例","数量","市值(本币)","名称复核状态","主数据名称","名称复核原因"]].to_string(index=False))
```

**关键 Pitfall**：不要在单个终端命令里用 `&` 批量后台执行多张图片。每张图必须作为独立的 `terminal(background=true)` 任务提交。

## ⚠️ Python 环境与工具链注意事项

### Python 环境

**venv 查找顺序**：模块自身 `venv/` → 项目根目录 `.venv/`。项目根目录 venv 已安装 pandas / openpyxl / pymongo / python-dotenv，可直接使用。

```bash
# ✅ 正确 — 根目录 .venv + PYTHONPATH（2026-06-26 改造后：不传 --date，OCR 自己识别业务日期）
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py --image ...

# ❌ 错误 — 系统默认 python3 没有 pandas
python3 skills/data/data-pipeline/scripts/run_unified_image_pipeline.py
# → ModuleNotFoundError: No module named 'pandas'
```

Hermes `execute_code` 工具使用自己的 venv（无 pandas），**禁止**用于执行 pipeline。

### Hermes 工具阻塞与 Python 执行路径

- **`execute_code`** 工具使用 Hermes Agent 自己的 venv（无 pandas / openpyxl / pymongo），**禁止**用于执行 pipeline 和验证 MongoDB 入库
- 完整 Python path 命令（如 `.venv/bin/python ...`）**不触发** Hermes 安全审批，可直接执行
- 脚本通过 `-e`/`-c` 参数注入代码时会触发审批，**不要**依赖这种方式
- 若 pipeline 执行被安全策略拦截，切换 `terminal(background=true)` + `notify_on_complete=true` 提交后台任务

### Pitfall — 用户发图入库的 3 个日期概念（2026-06-25 用户纠正过）

agent 收到用户发图时，**3 个日期必须分别明确**：

1. **归档日期** = 用户**发送图片的当天**（`date +%Y-%m-%d`）→ 目录命名
2. **业务日期** = 图片内容显示的日期（OCR 自己从图内 `截止日期` 列识别；写入 MongoDB 的 `trade_date` / `position_date`）
3. **系统日期** = pipeline **实际跑的时刻**（pipeline 内部归档会再用一次，可能和 #1 跨日）

> 2026-06-26 改造后：`run_unified_image_pipeline.py` 不再接受 `--date` 参数。业务日期完全由 OCR 自己识别。归档目录 `folder_date` 永远用系统日期。

**用户已明确纠正**：发图给 agent 时，**归档日期不是图片日期**。agent 第一次保存图片到 `source/smart-money/{X}/image/` 时，`X` 是**归档日期**（=今天），不是图片显示的日期（=业务日期）。

**禁止行为**：从用户截图直接解析出结构化数据再写库。**必须**走 pipeline——触发 `stock_basic_info` 名称复核、`missing_master` 状态标记等标准审计流程。

### 行为规范 — 发图后 agent 不要 over-engineer（2026-06-26 用户明确要求）

收到图片时**只做 4 件事**，不要在前置或中间塞任何额外步骤：

1. **归档**到 `skills/data/source/smart-money/{archive_date}/image/`
2. **不读图** — 不用 `vision_analyze` / `mcp_Z_AI_Vision_MCP_*` / `mcp_MiniMax_Token_Plan_MCP_understand_image` 给用户描述图片内容（OCR 是 pipeline 的活，不是 agent 的）
3. **不做去重 / sanity check**：
   - 不要 `md5sum` 检查 image cache（重发就让 pipeline 跑多次，MongoDB unique key 自然 upsert）
   - 不要 `db.portfolio_position.distinct('position_date')` 之类的预检
   - 不要 `audit_pending_unmigrated.py` 预跑
   - 不要 `check_pending_pipeline_runs.py` 预跑（这是个诊断工具，**用户问"哪些没跑"时**才用，不在入库前置流程里）
4. **不干预 pipeline**：
   - 不替用户决定并发数 / 配额 / 降级（用 profile 默认）
   - 不替用户猜 product_code 写文件名（命名用 `portfolio_{date}_{HHMMSS}.jpg` 时间戳即可，**不要**加 `_unknown` 后缀 — 用户 2026-06-26 明确反馈「为什么是 xxxx_unknown.jpg」多此一举）
   - 不替用户预估配额消耗

**唯一可问用户的场景**：当 OCR 识别出的 `截止日期` 与预期明显不符（可通过 `provider_status` 或 pending CSV 反查），或同一批图混了多业务日期 — 这时才需要用户确认。其余一律直接跑。

完整 9 条反模式清单见 `references/agent-overengineering-anti-patterns.md`。

**5. **不要传 `--date` 参数**。`run_unified_image_pipeline.py` 已删除 `--date`（2026-06-26 改造），传了 argparse 直接报错。业务日期由 OCR 自己从图内 `截止日期` 列识别，入库字段 `position_date` / `nav_date` 与 agent 无关。详见下方「Pitfall — `--date` 参数已从 `run_unified_image_pipeline.py` 接口删除」段。**

### 行为规范 — 归档文件命名约定（2026-06-26 用户明确要求）

归档时**用时间戳命名，不加 `_unknown` 后缀**：

```bash
cp $USER_IMAGE skills/data/source/smart-money/{archive_date}/image/portfolio_{YYYY-MM-DD}_{HHMMSS}.jpg
```

**反例（不这样做）**：
- 加 `_unknown` 后缀（user 反馈「为什么是 xxxx_unknown.jpg」，多此一举）
- 在文件名里猜 product_code（OCR 才有真值）
- 给每张图编业务语义名（portfolio_xxx / trade_xxx，pipeline 自己识别格式）

**原因**：归档文件名只用于**追溯**和**人类快速定位**。Pipeline 自己识别 portfolio/trade 格式、自动检测 product_code（从图内表头），不依赖文件名。命名简洁、可排序、不臆断就够了。

多张并发归档：用 `${TS}` 自增避免冲突（`cp ... portfolio_${TS}.jpg; TS=$((TS+1))`）。

### 行为规范 — pipeline 出问题时主动排查（2026-06-26 用户明确要求）

pipeline 失败 / partial_success / pending 异常 / provider 全挂时，agent **不只汇报失败**，要主动分析：

**正确流程（两阶段，不要合并）**：

1. **阶段 1：临时处理（等用户确认后再做）**
   - 失败的图要不要重跑？顺序还是并发？要不要跳过？要不要手动入库？
   - agent **先停手**，给临时方案选项，等用户决定
   - 用户确认后再执行（执行后必验证）

2. **阶段 2：复盘分析 + 长期修复方案（等用户确认后再做）**
   - 临时处理完后，回头分析根因（不只是「这次为什么失败」，而是「pipeline 哪里有缺陷 / 哪里可以优化」）
   - 给出长期修复方案（修改哪个文件 / 哪一行 / 改成什么 / 风险）
   - agent **先停手**，等用户决定是否执行

**反例（不这样做）**：
- 把临时处理和长期方案合并成一个汇报，等于强迫用户一次性决定两件事
- 看到失败立刻自己改代码 / 改配置 / 重跑（跳过阶段 1 等确认）
- 临时处理完不进入阶段 2，只说「好了」就结束
- 把失败归咎于外部不可控（配额、网络），不排查代码

**典型排查路径**：
- ZAI MCP 启动报 `Z_AI_API_KEY environment variable is required` → 实际根因**通常不是 env 继承 bug**，是**裸跑 Python 进程（terminal background task / cron）没从 profile .env 自动加载**。SKILL.md line 774 那个 fix 是另一回事（PATH/HOME 缺失）。**正解**：在 pipeline 入口和 zai_provider `__init__` self-load `.env`。详见 `references/image-failure-postmortem.md`。
- 并发 npx 失败 → 先看是否 minimax 本身就 partial 失败（`unknown` 空错），再追 zai fallback 链
- 单图 OCR 内容错误 → 检查 prompt / 字段映射 / normalize
- MongoDB unique key 冲突 → 检查 `(position_date, product_code, asset_wind_code)` 是否与已有行冲突

**诊断原则**：看到错误先复现 + 跑「裸 env 状态探测」**再下结论**，不要直接套用既有 pitfall 段。下结论前必跑：
```python
# 模拟「裸跑」场景
unset Z_AI_API_KEY && PYTHONPATH=skills/data/data-pipeline/scripts .venv/bin/python -c "
import os
print('Z_AI_API_KEY:', 'SET' if os.environ.get('Z_AI_API_KEY') else 'MISSING')
from providers.zai_provider import ZAIVisionProvider
ZAIVisionProvider()  # 触发 self-load
print('after instance:', 'SET' if os.environ.get('Z_AI_API_KEY') else 'MISSING')
"
```

### Pitfall — `providers.health_check` 函数是 coroutine（2026-06-26 实战）

`check_minimax_cli()` 和 `check_zai_mcp()` 都是 async 函数。直接 `print(check_minimax_cli())` 会得到 `<coroutine ...>` + RuntimeWarning，不是 True/False。

**正确用法**：

```python
import asyncio
from providers.health_check import check_minimax_cli, check_zai_mcp

async def main():
    print(await check_minimax_cli())  # True / False
    print(await check_zai_mcp())

asyncio.run(main())
```

### Pitfall — ZAI fallback 链路从未真正工作过（2026-06-26 修复）

`zai_provider._pick_image_tool` 之前用启发式（`name 包含 "image"`），从 `@z_ai/mcp-server` v0.1.2 暴露的 8 个 tool 里**第一个匹配**到的是 `ui_to_artifact`（要求必填 `output_type`，provider 没传 → MCP server 报 missing required argument）。Fallback 每次都失败，只是 minimax 主路径一直通所以没人发现。

-**2026-06-26 晚间二次修复**：后续实测发现 `extract_text_from_screenshot` 虽然参数最少，但它是纯 OCR 工具，可能返回普通文本而不是 pipeline prompt 要求的 JSON 数组，导致 `parse_error: no JSON array in zai output`。图片入库 pipeline 需要优先使用能遵循 JSON 输出 prompt 的 `analyze_image`。

**当前正确优先级**（`zai_provider.py`）：`analyze_image` → `extract_text_from_screenshot` → 启发式 fallback。


### Pitfall — `.env` 不会被自动注入到 terminal background 进程（2026-06-26 修复）

profile 的 `~/.hermes/profiles/yquant/.env` 里设了 `Z_AI_API_KEY`，但 `terminal(background=true)` 启的 `.venv/bin/python` 子进程 `os.environ` 拿不到 — Hermes gateway 只给**它自己启动的**子进程注入 env，不传给外部 shell 启的进程。结果：zai MCP server 启动时 `Z_AI_API_KEY environment variable is required`。

**修复**（已在 `run_unified_image_pipeline.py` 入口 + `zai_provider.py` `__init__` self-load `.env`）：用 `python-dotenv` 的 `load_dotenv(path, override=False)`，幂等不覆盖已设值。Hermes 启的进程因 `Z_AI_API_KEY` 已设直接 skip；裸跑进程会加载 .env。

**症状 → 排查**：
- 失败日志里有 `Z_AI_API_KEY environment variable is required`
- **不是** SKILL.md line 774 那个 PATH/HOME 继承 bug（已修）
- **是** .env 没加载，参考本条修复

### Pitfall — OCR 把 `市值(本币)` 输出成全角括号 `市值（本币）`（2026-06-27 实测）

`load_pending_confirmed.py` 按精确列名读 CSV，遇到全角括号 `市值（本币）` 报 `KeyError: '市值(本币)'`，结果 `loaded=0` 静默失败。

**症状**：`Result: format=portfolio, loaded=0, nav_loaded=0, records=0  ERROR: Row 0: '市值(本币)'`

**正确处理（不要直接放弃）**：
1. 用 `sed -i 's/市值（全币）/市值(本币)/g' <pending.csv>` 把全角括号改回半角
2. 重新跑 `load_pending_confirmed.py --confirm-all`
3. 验证 MongoDB 实际入库

**反例（不要做）**：
- 跳过这一行 pending，CSV 永久滞留
- 改 loader 代码加 `re.sub` 兼容两种括号 → 治标不治本，OCR 噪声下次还会以其他字符复现

CSV 是审计文件，`sed` 改字段名要记录在案（注明修改时间 + 原因）。这是临时方案；长期应写 `stock_name_corrections.py` 永久映射，避免每天走手工 sed。

### Pitfall — "已归档" ≠ "已跑过 pipeline"（2026-06-27 实测）

`source/smart-money/{date}/image/` 目录里的 portfolio_*.jpg 文件，**只表示归档动作完成**，不表示 pipeline 已经处理过。当用户分多批推送同一批图（早上 9:46 + 中午 10:02 + 晚上 10:10），image_cache unique hash 可能是同一批 18 张的不同子集，但 pipeline 实际只跑了第一轮的子集。

**正确区分三件事**：
1. **image_cache 里** — 飞书推送的所有图（含重复推送的副本）
2. **归档目录里** — agent 第一步 cp 过去的图（按 unique hash 去重）
3. **pipeline 跑过的图** — 在归档目录里留下了对应的 `trade_*.xlsx` / `portfolio_*.xlsx` 和可能的 `*_vision_raw.json`

**判断"哪些图还没跑过 pipeline"的标准做法**：
```bash
# 已跑过 pipeline 的图 = 留下了同名 xlsx 的图
ls skills/data/source/smart-money/2026-06-27/image/portfolio_*.xlsx 2>/dev/null \
  | sed 's/portfolio_/portfolio_/; s/\.xlsx$/.jpg/' | sort -u > /tmp/ran.txt

# 归档目录里所有图
ls skills/data/source/smart-money/2026-06-27/image/portfolio_*.jpg | sort -u > /tmp/archived.txt

# 还没跑过的 = 差集
comm -23 /tmp/archived.txt /tmp/ran.txt
```

**反例（不要做）**：
- 仅凭 "归档目录里有" 就回复用户"已经处理过"
- 仅凭 image_cache unique hash 数 == 归档目录 unique hash 数 就说"全部入库了"
- 跳过启动 pipeline 步骤 → 用户数据没真入库

### Pitfall — 三批推送图是同一批的子集（2026-06-27 实测）

飞书可能把同一批持仓截图分多次推送（比如 9:46 推 18 张 + 10:02 推 9 张 + 10:10 推 9 张），image_cache 总文件数看着多但 unique hash 可能就是同一批的 18 张的拆分。

**正确诊断**：
```bash
# 列出 image_cache 按时间戳分组的图
for f in /home/pascal/.hermes/profiles/yquant/image_cache/img_*.jpg; do
  TS=$(stat -c '%y' "$f" | cut -c12-19)  # HH:MM:SS
  H=$(md5sum "$f" | awk '{print $1}')
  echo "$H $TS"
done | sort -k2,2

# 看几个时间簇 → 每个簇可能是同一批的部分
```

**然后**：
- 按 hash 求并集 = 实际独立图
- 按时间簇求差集 = 哪些 hash 是用户"新推"的（不在上一批里）

**反例（不要做）**：
- 直接按 image_cache 总数判断"9 张新图"——可能是同批重复推送
- 不对比 hash 直接说"都归档过 = 都跑过 pipeline"

### Pitfall — MongoDB 业务日期字段实际存字符串不是 datetime（2026-06-27 实测）

`portfolio_position.position_date` / `portfolio_nav.nav_date` / `portfolio_trade.trade_date` 在 MongoDB 里**实际类型是 `str`**（如 `'2025-07-07'`），不是 BSON datetime。

**症状 1**：用 `datetime.date(2025,7,7)` 做 `\$gte` / `\$lte` 查询报 `bson.errors.InvalidDocument: cannot encode object: datetime.date(2025, 7, 7)`
**症状 2**：用 `datetime.datetime(2025,7,7)` 做范围查询 → 返回 0 行（datetime > str）
**症状 3**：从查询结果读 `.day` → AttributeError: 'str' object has no attribute 'day'

**正确做法**：
```python
# ✅ 用 $in + 字符串列表
DATES = [f'2025-07-{d:02d}' for d in range(1,16)]
db['portfolio_position'].find({'position_date': {'$in': DATES}}, ...)

# ✅ 取日期部分用字符串切片
for r in cursor:
    day = int(r['position_date'][-2:])  # '2025-07-07' → 7
```

**反例（不要做）**：
- 看到查询返回 0 行就以为"数据缺失" — 可能是 datetime/str 类型不匹配
- 用 `datetime.date` 直接做 MongoDB 查询参数 — 报 InvalidDocument
- 用 `'2025-07-0' in str(d) and int(str(d)[-2:]) <= 11` 这种字符串截位 — 月份位错位（`'2025-07-07'[-2:]='07'` 而不是 `'7'`），正确做法用 `r['position_date'].day`

**诊断流程**：先 `find_one()` 一行 → `print(type(r['position_date']), r['position_date'])` → 确认实际类型再写查询。

### Pitfall — `_unknown` 文件名后缀是 agent 画蛇添足（2026-06-26 用户纠正）

agent 曾经自作主张把归档图片命名为 `portfolio_{ts}_unknown.jpg`，理由是「避免猜测 product_code」。用户反馈「为什么是 xxxx_unknown.jpg」— 这是越权，pipeline 自己识别格式和 product_code，文件名只需可排序可追溯。

**正确命名**：`portfolio_{YYYY-MM-DD}_{HHMMSS}.jpg`。多张并发归档用 `${TS}` 自增避免冲突。详见上文「行为规范 — 归档文件命名约定」段。

### Pitfall — Agent 不要用通用 vision 工具替 OCR（2026-06-26 用户纠正）

用户发图后，agent 曾用 `vision_analyze` / `mcp_Z_AI_Vision_MCP_analyze_image` 直接读图给用户描述 — 既浪费 vision 配额，又绕开 pipeline 的标准 OCR → normalize → validate → MongoDB 流程。

**正确做法**：agent 不读图，立即归档 + 启 pipeline。读图是 pipeline 的活。详见「行为规范 — 发图后 agent 不要 over-engineer」段。

### Pitfall — `--date` 参数已从 `run_unified_image_pipeline.py` 接口删除（2026-06-26 改造）

`run_unified_image_pipeline.py` **不再接受 `--date` 参数**。改造前它是个 no-op 死字段（`argparse` 接收、`MiniMaxImageExtractor.__init__` 存下、provider 链路全程不读），agent 传错日期静默无效。改造后直接 argparse 报错（`unrecognized arguments: --date ...`），杜绝误传。

**接口层变化**：
- `argparse.add_argument("--date", ...)` 已删除
- `run_unified_image_pipeline.run_pipeline()` 的 `date_str` 参数已删除
- 内部透传链全清：`MiniMaxImageExtractor.__init__` / `VisionProvider` / `VisionProviderRouter` / `MiniMaxVisionProvider` / `ZAIVisionProvider` 都不再有 `date_str` 字段
- `smart_money_watcher.process_image()` 调用处同步删除 `date_str=date_str` 参数

**业务日期的最终来源**（与 `--date` 无关）：

| 字段 | 来源 |
|---|---|
| `portfolio_position.position_date` | OCR 解析的 `截止日期` 列（`normalize_position` 用 `day.get("date")`） |
| `portfolio_nav.nav_date` | 同上（`normalize_nav` 用 `day.get("date")`） |
| `portfolio_trade.trade_date` | OCR 解析的 `日期` / `截止日期` 列 |
| 归档目录 `source/smart-money/{date}/image/` | `folder_date = datetime.now()`，**永远用系统日期** |

**用户明确原则**（2026-06-26 反馈）："能否就不传呀，因为传错比不传更危险"。这条原则写进 skill 是为了让新会话**不要**再"贴 SKILL.md 历史示例 → 顺手加 `--date`"。

**正确做法（2026-06-26 new default）**：

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image "$DST"        # 唯一必传参数
```

**反例（不这样做）**：
- 按旧版 SKILL.md 示例抄 `--date <业务日期>` → argparse error，pipeline 起不来
- 担心 OCR 识别错日期，agent 凭印象传 `--date` 兜底 → 接口已删，argparse 报错，且传错比不传更危险
- 同一批图混了多业务日期，agent 强写一个日期 → 历史已证明此路是错的

**OCR 识别错的日期**（少见但可能发生）通过 `audit_pending_unmigrated.py` 或 `update_position_date` 工具修正，**不要**在 agent 层用 `--date` 替 OCR 兜底。

### P6. pending 行入库用 `--name-mapping` 而不是先改 CSV（2026-06-26 实战）

场景：OCR 读到「广晟有色」，主数据是「中稀有色」（公司改名），想用主数据名入库。

**正确做法 — 用 `--name-mapping` 在命令行覆盖**：

```bash
.venv/bin/python skills/data/data-pipeline/scripts/load_pending_confirmed.py \
  --csv "...pending.csv" \
  --name-mapping '{"600259.SH": "中稀有色"}' \
  --confirm-all
```

**反例**：手动编辑 CSV 改 asset_name 字段再 `confirm-all` — 丢失 OCR 原始痕迹，且需要重跑 audit。

**长期方案（阶段 2 用）**：把确认过的映射加入 `scripts/stock_name_corrections.py`，下次 OCR 识别直接修正，避免再卡 `pending_review`。已知映射：`600259.SH → 中稀有色`（公司改名：原"广晟有色"，主数据已更名为"中稀有色"）。改完后用 `audit_pending_unmigrated.py` 或新跑的图片验证：pending 行应消失。

### P6d. pipeline 产出 xlsx 的命名格式与 agent 归档 jpg 不一致（2026-06-27 实测）

- agent 归档命名：`portfolio_{YYYY-MM-DD}_{HHMMSS}.jpg`（带连字符的日期）
- pipeline 产出 xlsx 命名：`portfolio_{YYYYMMDD}_{HHMMSS}.xlsx`（无连字符的紧凑日期）

两者都来自系统当前时间，但格式不一样。验证"图是否跑过 pipeline"**不要**做简单字符串替换（`portfolio_` ↔ `.xlsx`），因为日期格式不同（连字符 vs 无连字符）。正确做法：直接对比 `image/*.xlsx` 与 `image/*.jpg` 的 `PortfolioMongoLoader` 入库记录，或跑 `check_pending_pipeline_runs.py`。

**反例（agent 本会话 2026-06-27）**：glob `portfolio_2026-06-27_20*.xlsx` 期望看到 18 个 xlsx（每个归档 jpg 对应一个），实际只看到 13 个 → 误判 5 张没跑过 pipeline，实际是 glob 模式错了。

**正确 glob**：
```bash
# 归档 jpg
ls skills/data/source/smart-money/2026-06-27/image/portfolio_2026-06-27_20*.jpg

# pipeline 产出 xlsx（不同格式！）
ls skills/data/source/smart-money/2026-06-27/image/portfolio_20260627_20*.xlsx

# 注意：同一天的 xlsx 与 jpg 时间戳前缀 2026-06-27 vs 20260627 不一致
```

**诊断步骤**：
1. `ls skills/data/source/smart-money/$(date +%Y-%m-%d)/image/` 列出所有文件
2. 按扩展名分组（jpg vs xlsx vs json）
3. 找 jpg 中没有对应 xlsx 的（去掉扩展名前缀后比较，但要先剥离日期格式差异）
4. 用 MongoDB 入库时间戳交叉验证（更可靠）

### P6a. MongoDB 字段名 / 类型 — 不要凭印象写查询（2026-06-27 实战三次踩坑）

**集合实际字段（实测，不是文档说的）：**

| 集合 | 业务日期字段名 | 类型 | **常见错误拼写** |
|---|---|---|---|
| `portfolio_position` | `position_date` | **string**（不是 datetime）| `position_ratio / quantity / market_value_local` |
| `portfolio_nav` | `nav_date` | **string** | `scale / share` |
| `portfolio_trade` | `trade_date` | **string** | `quantity / wind_code` |

**`portfolio_position` 实际字段**：`asset_name / asset_wind_code / holding_ratio / shares / market_value / position_date / product_code / updated_at / source_image`。

**`portfolio_nav` 实际字段**（详见 P1）：`nav_date / product_code / nav / aum / share / updated_at`。

**两个坑一次说清：**

1. **类型坑**：`position_date` 是 `'2025-07-15'` 字符串，**不是** `datetime.datetime`。MongoDB `find({'position_date': {'$gte': datetime.date(2025,7,15)}})` 会抛 `bson.errors.InvalidDocument: cannot encode object: datetime.date(...)`。**正确**：
   ```python
   db['portfolio_position'].find({'position_date': {'$in': ['2025-07-15', '2025-07-16']}})
   # 或字符串范围（注意字典序和日期序一致时可用）：
   db['portfolio_position'].find({'position_date': {'$gte': '2025-07-15', '$lte': '2025-07-20'}})
   ```

2. **字段名坑**：`portfolio_position` 实际是 `holding_ratio / shares / market_value`，**不是** SKILL.md 早期暗示的 `position_ratio / quantity / market_value_local`。第一次用新集合时先 `find_one({...})` 然后 `print(sorted(r.keys()))` 看实际字段名，再写查询 — 不要凭记忆写。

**反例（agent 本会话三次踩坑）**：
```python
# ❌ datetime 编码错误
db['portfolio_position'].find({'position_date': {'$gte': date(2025,7,1)}})
# ❌ 字段名错误返回 KeyError
r['position_ratio']  # → KeyError: 'position_ratio'
r['market_value_local']  # → KeyError
# ❌ SKILL 早段提到的字段不存在
nav_record['share']  # SM001 早期记录没这个字段
```

**一次走通的查询模板**（业务日期 × 集合 × 6 产品矩阵）见 `scripts/check_data_completeness.py`。

### P6b. `smart_money_watcher` 已经在跑 — 不要重复启动 pipeline（2026-06-27 实战）

**症状**：飞书收到图片后，`smart_money_watcher` 守护进程自动触发 `run_unified_image_pipeline.py`。如果 agent 又手动 `terminal(background=true)` 启 pipeline，**同一张图会被处理两次**，MongoDB unique key 自然 upsert 但**会触发不必要的 OCR 成本**（MiniMax 配额）。

**agent 自检流程**（收到图片后、决定是否启 pipeline 之前）：

```bash
# 1. 看 image_cache 是否有未归档的新图
ls -la /home/pascal/.hermes/profiles/yquant/image_cache/img_*.jpg | tail -20

# 2. 看今天归档目录的 xlsx 是否已经生成（pipeline 跑过的痕迹）
ls /home/pascal/workspace/yquant-investment/skills/data/source/smart-money/$(date +%Y-%m-%d)/image/*.xlsx 2>/dev/null | wc -l
# 如果 xlsx 数 > 0，且 unique hash 数 ≈ archive 数 → watcher 已经处理过

# 3. 看今天 review_pending 是否有新文件
ls /home/pascal/workspace/yquant-investment/skills/data/source/smart-money/$(date +%Y-%m-%d)/review_pending/*.csv 2>/dev/null | wc -l
```

**判定规则**：
- `xlsx 数 ≥ 图片 unique hash 数` → watcher 全跑完了，**不要**再启 pipeline
- `xlsx 数 < 图片 unique hash 数` → watcher 没跑完（或部分失败），启剩余张
- `xlsx 数 = 0 且 review_pending 也没新增` → watcher 没启动，可能是 watcher 进程挂了，**先排查 watcher** 不要直接启

**反例（agent 本会话行为）**：用户发 18 张图 → 我启 10 个后台 pipeline → 实际 watcher 已经全部跑完 → 我的 10 个 pipeline 是冗余 OCR 浪费。

**正确做法（最小动作）**：
1. 归档图（必做）
2. 自检 xlsx/review_pending 状态（30 秒）
3. 如果 watcher 没跑完 → 启剩余张；如果跑完 → **只汇报结果，不要再启**

### P6c. image_cache 状态歧义 — 飞书会保留旧图（2026-06-27 实战）

**症状**：`/home/pascal/.hermes/profiles/yquant/image_cache/` 里有 72 张图，**其中多数是前几天/几小时前的旧图残留**。新发的 18 张图只是其中一部分（按 mtime 在 09:46~09:47 区间）。如果 agent 用 `ls -1 *.jpg | wc -l` 当"今天用户发了多少张"的依据，**会得到错的数量**（72 而不是 18）。

**正确做法**：
1. 用 `ls -la --time-style=full-iso` 看 mtime，按 mtime 区间筛选"用户最新发的图"
2. 按 mtime 排序后 `tail -N`，N 由用户在消息里说的张数决定（或 `ls` 当前会话推送间隔内）
3. **如果不确定张数，先问用户再启 pipeline** — OCR 成本按张算，多跑一张浪费一次

**反例（agent 本会话）**：用户说"新发了 18 张图"，我用 `ls img_*.jpg | wc -l` 得到 72，归档了 60 张（去重后），远超用户实际推送量。

### 图片 Vision 策略（关键 Pitfall — 两层问题）

图片处理涉及**两个独立环节**，每个环节都有坑：

#### 环节 1：Gateway 自动路由（入站图片 → agent 看到什么）

Hermes gateway 收到图片时，`_decide_image_input_mode()` 决定两种路由：

- **native**：图片作为 `image_url` 附在用户 turn 上，agent 直接"看到"像素。
- **text**：先调 `vision_analyze` 把图片转成文字描述，拼到消息前面，agent 只看到文字摘要。

**决策逻辑**（`agent/image_routing.py`）：
1. `agent.image_input_mode` 显式设置 → 遵从
2. `auxiliary.vision.provider` 显式设置（非 auto/空）→ text
3. `_lookup_supports_vision(provider, model)` 查 models.dev → True 则 native
4. 否则 → text

**⚠️ Pitfall：`custom:` 前缀的 provider 无法查 models.dev。**
`PROVIDER_TO_MODELS_DEV` 只映射内置 provider 名（`minimax`、`zai` 等），
不包含 `custom:minimax`。因此当 primary model 用 `custom:` provider 时，
`_lookup_supports_vision` 返回 `None` → 走 text 路径 → **每张图都额外调一次 vision_analyze**。

**修复**：在 config.yaml 里显式声明 `supports_vision`：

```yaml
model:
  default: MiniMax-M3
  provider: custom:minimax
  supports_vision: true    # ← 绕过 models.dev 查找，直接 native
```

设为 `true` 后，MiniMax-M3 原生视觉生效，图片作为像素直接传给模型，
**省掉一次 vision_analyze 调用**，且 agent 拿到的是原图而非 lossy 文字摘要。

#### 环节 2：Agent 手动调 Vision 工具（对话中临时看图）

当 agent 需要在对话中主动分析图片时（非 gateway 自动路由）：

**优先 MiniMax MCP，vision_analyze 作兜底：**

```python
# Step 1: 直接用 MiniMax MCP
mcp_MiniMax_Token_Plan_MCP_understand_image(
    image_source="/path/to/img.jpg",
    prompt="识别图片中所有文字、数字、表格内容..."
)

# Step 2: 如果 MiniMax 也失败，再降级到 vision_analyze
# vision_analyze(...)  # Hermes 内置 Vision — 兜底选项
```

**理由**：MiniMax MCP 的 structured JSON 输出更完整（含 `structuredContent.tables`），
更适合持仓截图、交易记录等结构化数据。`vision_analyze` 在图片分析场景中容易
产生 `Duplicate tool output` 或截断输出。

#### 双重分析问题

如果不设 `supports_vision: true`，同一张图会被分析**两次**：
1. Gateway 自动调 `vision_analyze`（text 路径预分析）
2. Pipeline 正式 OCR 调 MiniMax CLI（`run_unified_image_pipeline.py`）

两次调用走不同端点、不同额度，第二次才是正式入库。设 `supports_vision: true`
后环节 1 消失，agent 直接看到原图，自主决定是否调 pipeline。

**静态名称更名文件路径：** `skills/data/data-pipeline/scripts/stock_name_corrections.py`。该文件用于 OCR 识别后的 Wind code → 标准名称映射，修改后对新图片立即生效，无需重启任何服务。

**Vision Provider Fallback（zai MCP）**

`MiniMaxImageExtractor` 当前没有 fallback——MiniMax 套餐一旦耗尽，pipeline 立即失败。Fallback 走 agent 层：zai 提供的 `@z_ai/mcp-server`（GLM Coding Plan 套餐专属视觉 MCP，共享 5h prompt 池子，**不**按 token 付费）。

- 配置方法、环境变量、启用开关、协议约定：`references/provider-fallback.md`
- **运维实战笔记（2026-06-26 首次生产 fallback 测试）**：`references/provider-fallback-ops.md` — 含 2 个 Bug 修复记录（env 继承 + 超时调优）、Z_AI_VISION_MODEL 配置、诊断命令
- MCP server 完整配置片段（可直接 merge 到 config.yaml）：`templates/mcp-servers-zai-vision.yaml`
- ⚠️ 关键变量名区分：`Z_AI_API_KEY`（zai MCP 用）≠ `GLM_API_KEY`（zai pay-as-you-go API 用）。两者在 Z.AI 后台是独立条目。

**Z.AI Vision MCP env 配置（2026-06-26 实测补充）**：

```yaml
mcp_servers:
  "Z.AI Vision MCP":
    command: npx
    args: ["-y", "@z_ai/mcp-server"]
    env:
      Z_AI_API_KEY: ${Z_AI_API_KEY}
      Z_AI_MODE: ZHIPU
      Z_AI_VISION_MODEL: glm-4v-flash   # 可选：覆盖默认 glm-4.6v，flash 版更快
    connect_timeout: 120
    timeout: 120
```

> `Z_AI_VISION_MODEL` 是 `@z_ai/mcp-server` 的 env 变量（见源码 `build/core/environment.js` L108），默认 `glm-4.6v`。设置 `glm-4v-flash` 可加速简单图片，但 `analyze_image` 在 `glm-4v-flash` 上会触发 `max_tokens parameter is illegal（范围[1,1024]）`，导致 `analyze_image` JSON 表格抽取失败（仍可跑 `extract_text_from_screenshot` 纯 OCR）。当前默认 `glm-4v-flash` 在 tool 优先级为 `analyze_image` 优先时无法走通 JSON 抽取；遇到 `max_tokens` 报错可临时改 `glm-5v-turbo`。
>
> `glm-5.2` 不是这个 MCP server 的 vision model；它用于 Hermes `zai` provider 的 chat/compression/fallback。`glm-5.2` Coding Plan endpoint 需要显式使用 OpenAI Chat Completion URL `https://open.bigmodel.cn/api/coding/paas/v4`，不要误用 Anthropic Messages URL `https://open.bigmodel.cn/api/anthropic` 或普通 `/api/paas/v4`。详见 `references/zai-glm-endpoints.md`。

**关键 Pitfall — ZAI MCP 子进程拿不到 `Z_AI_API_KEY`（2026-06-26 晚间修复，commit `e78ccd8`）**：

`zai_provider.py` 的 `ZAIMCPClient._load_server_params()` 构建 `StdioServerParameters` 时，**原代码只读 `spec.get("env")`**，但 `_parse_mcp_servers()` 的轻量 YAML 解析器**不保留嵌套 mapping 上下文**——config.yaml 的 `env:` 块被拍平到 server spec 顶层，`spec.get("env")` 返回 `None`/`{}`。结果 npx 子进程没有任何 env vars 启动，z.ai MCP server 报 `Z_AI_API_KEY environment variable is required` + `McpError: Connection closed`。

**修复**（commit `e78ccd8`，`zai_provider.py` `_load_server_params`）：

```python
# ✅ 修复后 — 两层防御
env = spec.get("env") or {}
if not isinstance(env, dict):
    env = {}
# Compatibility: 轻量 YAML parser 把 env: 块拍平到顶层
if not env:
    env = {k: v for k, v in spec.items() if isinstance(k, str) and k.isupper()}
# Resolve ${VAR} + merge 父进程 os.environ（PATH/HOME 继承）
resolved = _resolve_env(env, os.environ)
merged = dict(os.environ)
merged.update(resolved)
return StdioServerParameters(command=command, args=args, env=merged)
```

**关键区分**（与 `.env` self-load 的关系）：
- 本 Bug 1：父进程 `os.environ` 有 `Z_AI_API_KEY`，但 zai provider 构造的 MCP 子进程 env 里没有（YAML 拍平 + 缺失 fallback merge）。
- `.env` self-load：父进程 `os.environ` **就没有** `Z_AI_API_KEY`（Hermes gateway 没注入到 `terminal(background=true)` 启的子进程）。

两个 Bug 都能报相同错误文本，但根因不同，修复点也不同。排查时先 `env | grep Z_AI_API_KEY` 看父进程有没有，再判断是哪个。

**关键 Pitfall — Fallback 超时不够（2026-06-26 实测）**：

Router 用 `asyncio.wait_for(provider.describe(), timeout=fallback_timeout_seconds + 30)`。原配置 `fallback_timeout_seconds=90`（有效超时 120s），但 glm-4.6v 复杂表格 OCR 需要 ~103s。首次实测时 MCP server 正常启动、API 请求发出，但 120s 后被 SIGTERM 杀掉。调到 `240`（有效超时 270s）后稳定通过。

**Z.AI MCP tool 优先级（2026-06-26 修复，晚间二次校准）**：

`_pick_image_tool` 之前用纯启发式（name 含 "image"）会选到 `ui_to_artifact`，需要 `output_type` 参数 provider 没法填，导致 fallback 必然失败。首次修复曾把 `extract_text_from_screenshot` 放在第一位，但生产验证发现它返回纯 OCR 文本，不能稳定满足 pipeline 的 JSON 数组契约。

当前正确白名单：

1. `analyze_image`（优先；遵循 prompt，能返回 JSON 数组/代码块，适合表格结构化）
2. `extract_text_from_screenshot`（纯 OCR 兜底，可能触发 `no JSON array in zai output`）
3. 启发式回退

详见 `references/zai-mcp-tools.md` 和 `references/zai-mcp-fallback-runtime-2026-06-26.md`。


**不要**为图片入库写自定义脚本或手动连接 MongoDB。正确做法只需一条命令：

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image /path/to/image.jpg
```

待确认行补录命令（同样需要根目录 venv）：

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/load_pending_confirmed.py \
  --csv "skills/data/source/smart-money/{date}/review_pending/{filename}_pending.csv" \
  --confirm-all
```

该 pipeline 自动完成：MiniMax OCR → 格式自动检测（portfolio/trade）→ Transform → Validate → MongoDB 入库。

**不要写自定义 Python 脚本插入 MongoDB 记录**。正确做法：
1. 运行 `run_unified_image_pipeline.py` 入库主体数据
2. 待确认行由 `load_pending_confirmed.py --confirm-all` 统一处理

**不要用 sed 批量修改 CSV 状态**再多次调用脚本。正确做法：
- 单次确认：`--confirm-all` 一行命令完成
- 分步确认：先不加 `--confirm-all` 入库自动通过部分，再加 `--confirm-all` 入库确认部分

**不要**绕过 pipeline 自己解析图片。用户说"图片数据入库" → 加载 `data-pipeline` skill → 调用 `run_unified_image_pipeline.py`。

手动连接 MongoDB 的典型错误：凭证从 `skills/.env` 读取时 `os.getenv('MONGODB_PASSWORD')` 在非项目目录运行返回 `None`。正确做法是 pipeline 内部已实现的 `PortfolioMongoLoader`，它通过 `.env` 文件加载凭证，**不需要**也不应该手动拼接连接字符串。

## Smart Money Batch Closeout（YQuant 会话集成）


当用户在飞书会话中发送图片批次后跟「图片批次已上传」等触发词时，YQuant 需要：
1. 累积每张图片的处理结果
2. 检测触发词后调用批次 closeout
3. 发送 closeout 文本给用户

### 触发词

```python
BATCH_END_PHRASES = [
    "图片批次已上传",
    "就这些",
    "处理完了",
    "发完了",
    "没有了",
]


def is_batch_end(message: str) -> bool:
    """检测用户消息是否为批次结束信号。"""
    return any(phrase in message for phrase in BATCH_END_PHRASES)
```

### 模块使用

所有函数在 `scripts/image_batch_state.py`：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from image_batch_state import add_image_result, close_batch_now, check_and_send_pending_closeout
```

### YQuant 会话流程

```python
# 1. 每张图片处理后，累积结果
pipeline_result = await run_unified_image_pipeline(...)
add_image_result(pipeline_result)

# 2. 用户发送触发词 → 调用 close_batch_now() 并发送
if is_batch_end(user_message):
    closeout = close_batch_now()
    if closeout:
        await message(closeout["message_text"])
    else:
        await message("当前没有待处理的图片批次。")
```


### closeout 结构

`close_batch_now()` 返回：

```python
{
    "kind": "smart_money_batch_closeout",
    "status": "closed_clean" | "closed_needs_confirmation" | "closed_with_failures" | "closed_dry_run" | "closed_empty",
    "totals": {"files": N, "success": N, ...},
    "mongodb_counts": {"position": N, "trade": N},
    "needs_confirmation_items": [...],
    "failed_items": [...],
    "confirmation": {"required": bool, "question": str, "expected_user_action": str},
    "message_text": "Smart Money 批次处理 Closeout\n\n状态：closed_clean\n..."
}
```


### 状态判定优先级

| 条件 | status |
|------|--------|
| 0 个文件 | `closed_empty` |
| 有 failed | `closed_with_failures` |
| 有 pending_rows / partial / pending_review | `closed_needs_confirmation` |
| 有 dry_run | `closed_dry_run` |
| 全部成功 | `closed_clean` |


### 状态文件

运行时状态文件写在 `WORKSPACE/.openclaw/`：
- `image_batch_results.json` — 累积中的图片结果

正常情况下用户无感，仅用于 YQuant 重启后的状态恢复。本方案不使用 30s timer；批次结束完全由用户发送「图片批次已上传」等触发词决定。

## 待确认项补录工作流

批次处理后若有 `closed_needs_confirmation` 状态：

1. YQuant 展示 closeout 报告，说明哪些行待确认（记录 `pending_csv` 路径）
2. 用户确认（如"联讯仪器、惠科股份 已确认"）
3. **一行命令完成补录**：

```bash
python3 skills/data/data-pipeline/scripts/load_pending_confirmed.py \
  --csv "skills/data/source/smart-money/{date}/review_pending/{filename}_pending.csv" \
  --confirm-all
```

`--confirm-all` 会放行所有状态（包括 `pending_review`、`missing_master`），将 CSV 中 Wind 代码非空的行全部入库。

### Pitfall — Pending CSV ≠ 未入库（2026-06-26 用户纠正过）

**当用户问"还有 pending 要入库吗？"时，**不要**只扫 CSV 状态就回答。CSV 是审计文件，不是真理源。历史 pending CSV 经常是孤儿（pipeline 早期版本可能直接入库但 CSV 状态没回填）。

**正确流程**：跨 CSV + MongoDB 双源核对。详见 `scripts/audit_pending_unmigrated.py`：

```bash
.venv/bin/python skills/data/data-pipeline/scripts/audit_pending_unmigrated.py
```

**实战发现（2026-06-26 实测）**：44 行 legacy pending CSV 中 **42 行（95.5%）已在 MongoDB**，仅 2 行真正未入库。盲目 `confirm-all` 全部 30 个 CSV 风险大，必须先核对。

### 安全设计

| 状态 | 默认行为 | `--confirm-all` 行为 |
|------|---------|---------------------|
| `pending_review` | ❌ 拦截 | ✅ 入库 |
| `missing_master` | ❌ 拦截 | ✅ 入库 |
| `resolved` / `confirmed` | ✅ 自动入库 | ✅ 入库 |
| 空或其他 | ✅ 自动入库 | ✅ 自动入库 |

**两次调用场景**（可选）：如果用户只确认了部分行，可以分步操作：
```bash
# Step 1: 先入自动通过的行
python3 load_pending_confirmed.py --csv pending.csv

# Step 2: 用户确认后，再入剩余行
python3 load_pending_confirmed.py --csv pending.csv --confirm-all
```

### Pitfall — NAV 字段名是 `aum` 不是 `scale`（2026-06-26 误报）

```python
# ❌ 错误 — 字段名猜错，永远返回默认值 0
rec = db['portfolio_nav'].find_one({'product_code': 'SM001'})
print(rec.get('scale', 0))  # → 0（字段不存在，误报"scale 为 0"）

# ✅ 正确 — 实际字段是 aum
print(rec.get('aum'))  # → 226570340
```

**教训**：第一次用时先 `find_one({...})` 然后打印 `rec.keys()` 看实际字段。`portfolio_nav` 的实际字段是 `nav_date / product_code / nav / aum / share / updated_at`。
