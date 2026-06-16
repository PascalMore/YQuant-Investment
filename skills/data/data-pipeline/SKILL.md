---
name: data-pipeline
description: YQuant 数据管道框架。所有外部数据（API采集、文件导入、图片解析、消息提取）统一经由本管道处理，完成 Extract → Transform → Validate → Load 全流程。
---

# Data Pipeline

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
├── SKILL.md                     ← 本文件
├── scripts/
│   ├── pipeline.py              ← 管道引擎（核心编排）
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py              ← Extractor 基类
│   │   ├── image_parser.py      ← 图片解析（Vision 模型）
│   │   ├── api_extractor.py     ← API 拉取（Tushare/AKShare）
│   │   ├── file_extractor.py   ← 文件导入（CSV/Excel）
│   │   └── message_extractor.py ← 聊天消息解析
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
└── references/
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
| `ApiExtractor` | 待实现 | 从 Tushare/AKShare API 拉取 |
| `FileExtractor` | 待实现 | 从 CSV/Excel 导入 |
| `MessageExtractor` | 待实现 | 从聊天消息解析结构化数据 |

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
|------|-------------|----------|
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

## 开发进度

- [ ] SKILL.md（本文档）
- [ ] 基类定义（base.py 各层）
- [ ] MongoDBLoader
- [ ] NaNNormalizer
- [ ] SchemaValidator
- [ ] ImageParserExtractor
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
