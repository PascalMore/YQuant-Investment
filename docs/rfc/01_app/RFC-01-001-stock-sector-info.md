# RFC-01-001：stock_sector_info 股票行业分类映射表

## 元数据（Metadata）
| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant |
| 创建日期 | 2026-05-21 |
| 最后更新 | 2026-05-21 |
| 所属模块 | 01_app（应用层） |
| 依赖RFC | RFC-00-001-yqclaw-investment-global-architecture |
| 替代RFC | 无 |
| 适配AI工具 | OpenClaw、Claude Code、Codex |
| 标签 | #app #sector #industry-mapping #mongodb |

### 版本历史（Changelog）
| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-05-21 | 初始创建，定义 stock_sector_info 表结构 | YQuant |

## 1. 执行摘要

建立股票与多级别行业分类的映射表，支持申万（SW）、GICS、证监会（CSRC）等多种分类体系。为 Phase 4 深度分析的 Darwin 时刻检测、共识方向引擎和 Munger Checklist 提供行业归属数据。

## 2. 背景与动机

### 2.1 问题
- 现有 `stock_basic_info` 的 `industry` 字段是证监会分类，非申万分类
- 申万行业分类通过 `index_member_all` 接口获取，但未建立持久化表
- Phase 4 需要股票的行业归属（L1/L2/L3）用于行业聚合和达尔文时刻检测

### 2.2 目标
- 建立统一的多分类体系行业映射表
- 支持按股票代码或行业代码查询
- 复用 Tushare `index_member_all` 接口

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）
- [ ] 表结构支持多种分类体系（classify_system）
- [ ] 主键为 `full_symbol + classify_system` 复合唯一键
- [ ] 字段与 TradingAgents-CN 的 `standardize_basic_info` 保持一致（code/symbol/full_symbol/name）
- [ ] 支持申万（SW）L1/L2/L3 三级分类
- [ ] 通过 Tushare `index_member_all` 接口同步数据

### 3.2 非目标（Out of Scope）
- [ ] 不实现行业分类的计算逻辑（只做映射存储）
- [ ] 不实现多分类体系的自动切换逻辑

## 4. 整体设计

### 4.1 数据模型

**Collection：** `stock_sector_info`
**Database：** `tradingagents`
**主键：** `full_symbol + classify_system`（复合唯一键）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `_id` | ObjectId | 是 | MongoDB 主键（自动生成） |
| `full_symbol` | string | 是 | 完整股票代码，如 `600519.SH`，主键 |
| `code` | string | 是 | 本地股票代码，如 `600519` |
| `symbol` | string | 是 | 同 code，保持与 TradingAgents-CN 一致 |
| `name` | string | 是 | 股票名称 |
| `classify_system` | string | 是 | 分类体系，如 `SW`、`GICS`、`CSRC` |
| `l1_code` | string | 是 | 一级行业代码，如 `801050` |
| `l1_name` | string | 是 | 一级行业名称，如 `有色金属` |
| `l2_code` | string | 否 | 二级行业代码 |
| `l2_name` | string | 否 | 二级行业名称 |
| `l3_code` | string | 否 | 三级行业代码 |
| `l3_name` | string | 否 | 三级行业名称 |
| `datasource` | string | 是 | 数据来源，如 `tushare` |
| `update_at` | datetime | 是 | 更新时间 |

### 4.2 索引设计

```javascript
// 复合唯一索引（主键）
db.stock_sector_info.createIndex(
    { full_symbol: 1, classify_system: 1 },
    { unique: true, name: "uk_full_symbol_classify_system" }
)

// 查询索引
db.stock_sector_info.createIndex(
    { classify_system: 1, l1_code: 1 },
    { name: "idx_classify_l1" }
)

db.stock_sector_info.createIndex(
    { l2_code: 1 },
    { name: "idx_l2_code" }
)

db.stock_sector_info.createIndex(
    { l3_code: 1 },
    { name: "idx_l3_code" }
)

db.stock_sector_info.createIndex(
    { full_symbol: 1 },
    { name: "idx_full_symbol" }
)
```

### 4.3 classify_system 枚举值

| 值 | 含义 |
|---|---|
| `SW` | 申万行业分类（默认） |
| `GICS` | GICS 行业分类 |
| `CSRC` | 证监会行业分类 |
| `ZZ` | 中证行业分类 |

## 5. 数据来源

### 5.1 Tushare Pro 接口

```python
import tushare as ts

pro = ts.pro_api(token=TUSHARE_TOKEN)

# 获取单只股票的行业分类
df = pro.index_member_all(ts_code='600519.SH')
# 返回: l1_code, l1_name, l2_code, l2_name, l3_code, l3_name, ts_code, name, in_date, out_date, is_new

# 获取某一级行业下所有股票
df = pro.index_member_all(l1_code='801050.SI')

# 获取某二级行业下所有股票
df = pro.index_member_all(l2_code='801051.SI')
```

### 5.2 字段映射

| Tushare 返回字段 | stock_sector_info 字段 |
|---|---|
| `ts_code` | `full_symbol` |
| `name` | `name` |
| `l1_code` | `l1_code` |
| `l1_name` | `l1_name` |
| `l2_code` | `l2_code` |
| `l2_name` | `l2_name` |
| `l3_code` | `l3_code` |
| `l3_name` | `l3_name` |
| - | `code`（从 full_symbol 提取） |
| - | `symbol`（同 code） |
| - | `classify_system`（固定 `SW`） |
| - | `datasource`（固定 `tushare`） |

### 5.3 同步策略

| 场景 | 策略 |
|------|------|
| 全量同步 | 每日首次启动时全量拉取 `index_member_all(is_new='Y')`，upsert |
| 增量更新 | 监控 `is_new='N'` 的记录变化（行业变更） |
| 单股查询 | 支持按 `ts_code` 查询单只股票的行业归属 |

## 6. Python 实现

### 6.1 Service 类

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class SectorInfo:
    """股票行业分类映射"""
    code: str
    symbol: str
    full_symbol: str
    name: str
    classify_system: str
    l1_code: str
    l1_name: str
    l2_code: Optional[str]
    l2_name: Optional[str]
    l3_code: Optional[str]
    l3_name: Optional[str]
    datasource: str = "tushare"
    update_at: datetime = None


class StockSectorInfoService:
    """股票行业分类映射服务"""

    def __init__(self, mongo_client, tushare_token: str):
        self.mongo_client = mongo_client
        self.db = mongo_client['tradingagents']
        self.collection = self.db['stock_sector_info']
        self.tushare_token = tushare_token

    def sync_from_tushare(
        self,
        classify_system: str = "SW",
        force: bool = False
    ) -> dict:
        """从 Tushare 同步行业分类数据"""
        pass

    def get_sector_by_symbol(
        self,
        full_symbol: str,
        classify_system: str = "SW"
    ) -> Optional[SectorInfo]:
        """获取单只股票的行业分类"""
        pass

    def get_stocks_by_industry(
        self,
        l1_code: str = None,
        l2_code: str = None,
        l3_code: str = None,
        classify_system: str = "SW"
    ) -> list[SectorInfo]:
        """按行业获取股票列表"""
        pass
```

### 6.2 复用 Tushare 统一包装

参考 `TradingAgents-CN/tradingagents/dataflows/providers/china/tushare.py` 的实现风格，不重复造轮子。

## 7. 与 TradingAgents-CN 字段对照

| TradingAgents-CN standardize_basic_info | stock_sector_info |
|---|---|
| `code` | `code` |
| `symbol` | `symbol` |
| `full_symbol` | `full_symbol` |
| `name` | `name` |
| - | `classify_system`（新增） |
| `industry`（证监会） | `l1_name`（申万） |

## 8. 验收标准

- [ ] `full_symbol + classify_system` 唯一键约束生效
- [ ] 支持按 `full_symbol` 查询单只股票的行业分类
- [ ] 支持按 `l1_code/l2_code/l3_code` 查询行业内的股票列表
- [ ] 数据来自 Tushare `index_member_all` 接口
- [ ] `code/symbol/full_symbol/name` 与 `standardize_basic_info` 保持一致
- [ ] 单元测试覆盖核心方法

## 9. 版本记录（Changelog）
| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-05-21 | 初始创建 | YQuant |