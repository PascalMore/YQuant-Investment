# RFC-03-003：skills/data 数据架构标准
## 元数据（Metadata）
| 项 | 值|
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant |
| 创建日期 | 2026-05-18 |
| 最后更新 | 2026-05-18 |
| 版本号 | V0.1 |
| 所属模块 | 03_data（数据层） |
| 依赖RFC | RFC-00-001-yquant-investment-global-architecture |
| 替代RFC | 无 |
| 适配AI工具 | OpenClaw、Claude Code |
| 标签 | #data #架构 #接口 #复用 |

### 版本历史（Changelog）
| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-05-18 | 初始创建，定义 skills/data 目录架构和接口规范 | YQuant |

## 1. 执行摘要
本文档定义 `skills/data/` 目录的标准化架构，包括标准数据接口（`data_interface/`）、业务数据实现（`portfolio/`）的目录结构、接口契约和复用原则。确保数据层代码可复用、可测试、业务逻辑隔离。

## 2. 背景与动机
### 2.1 问题
- 各子项目（argus、daily_stock_analysis 等）独立实现数据读写，代码重复
- 数据接口不统一，子项目间无法相互调用
- 业务逻辑渗透到数据层，难以复用和测试

### 2.2 目标
- 建立标准数据接口（IReader/IWriter）
- 业务数据实现与接口分离
- 数据层代码可跨项目复用

## 3. 目标与非目标
### 3.1 必须目标（Must-Have）
- [ ] 定义 IReader/IWriter 标准接口
- [ ] 实现 portfolio 数据接口
- [ ] 业务逻辑不进入 data 层
- [ ] 接口实现可独立测试

### 3.2 非目标（Out of Scope）
- [ ] 业务逻辑实现（放子项目）
- [ ] 数据库连接管理细节（由接口实现类处理）
- [ ] 数据缓存机制

## 4. 整体设计
### 4.1 核心设计哲学
**接口驱动 + 实现分离**：定义标准接口契约，具体实现按业务分类下沉到对应目录。data 层只做数据读写，不含业务逻辑。

### 4.2 架构总览
```
skills/data/
├── data_interface/              # 标准接口定义（抽象层）
│   ├── __init__.py
│   ├── base_reader.py          # IReader 接口定义
│   ├── base_writer.py          # IWriter 接口定义
│   ├── mongo_reader.py         # 通用 MongoDB 读取实现
│   └── mongo_writer.py         # 通用 MongoDB 写入实现
└── portfolio/                   # portfolio 业务数据实现
    ├── __init__.py
    ├── transformer.py          # 数据转换（raw→processed、化名映射）
    └── config.py               # portfolio 配置（集合名等）
```

### 4.3 模块分工
| 模块 | 职责 | 边界 |
|------|------|------|
| data_interface/ | 定义标准接口契约（IReader/IWriter） | 不含业务逻辑 |
| data_interface/mongo_reader.py | 通用 MongoDB 读取 | 只读，支持按日期/产品过滤 |
| data_interface/mongo_writer.py | 通用 MongoDB 写入 | 只写，支持 upsert |
| portfolio/ | portfolio 数据处理 | 含数据转换、化名映射 |

## 5. 详细设计
### 5.1 标准接口定义

#### IReader 接口
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class IReader(ABC):
    """标准数据读取接口"""
    
    @abstractmethod
    def read(self, date: str, **kwargs) -> List[Dict]:
        """按日期读取数据
        
        Args:
            date: 日期（YYYY-MM-DD）
            **kwargs: 可选过滤参数（如 product_code）
        
        Returns:
            List[Dict]: 数据列表
        """
        pass
    
    @abstractmethod
    def read_by_product(self, product_code: str, date: str) -> List[Dict]:
        """按产品读取数据
        
        Args:
            product_code: 产品代码
            date: 日期（YYYY-MM-DD）
        
        Returns:
            List[Dict]: 数据列表
        """
        pass
```

#### IWriter 接口
```python
from abc import ABC, abstractmethod
from typing import List, Dict

class IWriter(ABC):
    """标准数据写入接口"""
    
    @abstractmethod
    def write(self, data: List[Dict], **kwargs) -> int:
        """写入数据
        
        Args:
            data: 数据列表
            **kwargs: 可选参数（如 collection_name）
        
        Returns:
            int: 写入条数
        """
        pass
    
    @abstractmethod
    def upsert(self, data: List[Dict], **kwargs) -> int:
        """upsert数据（按唯一键更新或插入）
        
        Args:
            data: 数据列表
            **kwargs: 可选参数（如 collection_name, unique_keys）
        
        Returns:
            int: 操作条数
        """
        pass
```

### 5.2 mongo_reader.py 实现规范
```python
class MongoReader(IReader):
    """通用 MongoDB 读取实现"""
    
    def __init__(self, connection_string: str = None, database: str = 'tradingagents'):
        # 从 .env 或参数读取连接字符串
        pass
    
    def read(self, date: str, **kwargs) -> List[Dict]:
        # 支持 collection_name, product_code 等过滤
        pass
    
    def read_by_product(self, product_code: str, date: str) -> List[Dict]:
        pass
    
    def _build_query(self, date: str, **kwargs) -> Dict:
        # 构建 MongoDB 查询条件
        pass
```

### 5.3 mongo_writer.py 实现规范
```python
class MongoWriter(IWriter):
    """通用 MongoDB 写入实现"""
    
    def __init__(self, connection_string: str = None, database: str = 'tradingagents'):
        pass
    
    def write(self, data: List[Dict], **kwargs) -> int:
        # 支持 collection_name 配置
        pass
    
    def upsert(self, data: List[Dict], **kwargs) -> int:
        # 支持 unique_keys 配置，按唯一键upsert
        pass
```

### 5.4 portfolio/config.py 配置
```python
# MongoDB portfolio 集合配置
PORTFOLIO_COLLECTIONS = {
    'basic_info': 'portfolio_basic_info',
    'nav': 'portfolio_nav',
    'position': 'portfolio_position',
    'trade': 'portfolio_trade',
}

# Argus 输出集合（08_research）
ARGUS_COLLECTIONS = {
    'signal': '08_research_argus_signal',
    'stock_pool': '08_research_argus_stock_pool',
    'credibility': '08_research_argus_credibility',
}
```

### 5.5 portfolio/transformer.py 职责
- 接收 portfolio_position / portfolio_trade 原始数据
- 持仓比例变化计算
- 交易方向标准化（BUY/SELL/HOLD）
- 化名映射（JS→景顺、ZO→中欧...）
- **不含业务逻辑**：只做数据转换

## 6. 复用原则
1. **接口优先**：新增数据接口必须先定义接口，再实现
2. **业务隔离**：data 层不含业务逻辑，业务逻辑放子项目
3. **可测试**：接口实现类可独立测试，不依赖业务逻辑
4. **配置外置**：集合名、连接字符串等配置外置到 config.py 或 .env

## 7. 验收标准
- [ ] IReader/IWriter 接口定义完整
- [ ] MongoReader/MongoWriter 实现可独立运行
- [ ] portfolio/transformer.py 不含业务逻辑
- [ ] 单元测试覆盖核心方法
- [ ] 可被 skills/research/argus/ 等子项目调用

## 8. 参考资料
- RFC-00-001-yquant-investment-global-architecture
- skills/data/data-pipeline/scripts/loaders/mongodb_loader.py