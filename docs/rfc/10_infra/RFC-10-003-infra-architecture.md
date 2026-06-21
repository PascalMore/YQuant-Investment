# RFC-10-003：skills/infra 基础工具架构标准
## 元数据（Metadata）
| 项 | 值|
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant |
| 创建日期 | 2026-05-18 |
| 最后更新 | 2026-05-18 |
| 版本号 | V0.1 |
| 所属模块 | 10_infra（基础设施） |
| 依赖RFC | RFC-00-001-yquant-investment-global-architecture |
| 替代RFC | 无 |
| 适配AI工具 | OpenClaw、Claude Code |
| 标签 | #infra #架构 #日志 #工具 #复用 |

### 版本历史（Changelog）
| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-05-18 | 初始创建，定义 skills/infra 目录架构和工具规范 | YQuant |

## 1. 执行摘要
本文档定义 `skills/infra/` 目录的标准化架构，包括统一日志工具（`logger.py`）、日期处理工具（`date_utils.py`）的接口规范和使用标准。确保基础设施代码可复用、跨项目统一。

## 2. 背景与动机
### 2.1 问题
- 各子项目独立实现日志工具，格式不统一
- 日志输出路径分散，难以集中管理
- 日期处理逻辑重复（交易日判断、日期格式等）

### 2.2 目标
- 统一日志输出路径和格式规范
- 提供通用日期处理工具
- 基础设施代码可跨项目复用

## 3. 目标与非目标
### 3.1 必须目标（Must-Have）
- [ ] 统一日志工具（输出到 `logs/{submodule}/{module}_{YYYYMMDD}.log`）
- [ ] 日期处理工具（交易日判断、日期获取）
- [ ] 日志格式符合 YQuant 规范

### 3.2 非目标（Out of Scope）
- [ ] 业务相关工具（放对应子项目）
- [ ] 数据库连接管理（放 skills/data）
- [ ] 配置管理（放对应子项目的 config/）

## 4. 整体设计
### 4.1 核心设计哲学
**通用优先**：infra/ 只放非业务相关的通用基础工具，不依赖任何业务模块。

### 4.2 架构总览
```
skills/infra/
├── __init__.py
├── logger.py       # 统一日志工具
└── date_utils.py   # 日期处理工具
```

### 4.3 日志输出规范
```
logs/
├── research/
│   ├── argus/
│   │   └── argus_20260518.log
│   └── smart_money/
│       └── smart_money_20260518.log
├── portfolio/
├── strategy/
└── trading/
```

## 5. 详细设计

### 5.1 logger.py 接口规范
```python
import logging
from pathlib import Path
from datetime import datetime

def get_logger(
    module: str,
    submodule: str = None,
    level: int = logging.INFO
) -> logging.Logger:
    """
    获取统一日志器
    
    Args:
        module: 模块名（如 'argus'、'portfolio'）
        submodule: 子模块路径（如 'research/argus'、'data/smart_money'）
        level: 日志级别，默认 INFO
    
    输出路径：logs/{submodule}/{module}_{YYYYMMDD}.log
    默认输出：logs/{module}/{module}_{YYYYMMDD}.log
    
    Returns:
        logging.Logger: 配置好的日志器
    
    Example:
        logger = get_logger('argus', 'research/argus')
        logger.info('Signal generated')
    """
    pass

def get_log_file_path(module: str, submodule: str = None) -> Path:
    """
    获取日志文件路径
    
    Args:
        module: 模块名
        submodule: 子模块路径
    
    Returns:
        Path: 日志文件完整路径
    """
    pass
```

### 5.2 date_utils.py 接口规范
```python
from datetime import date, datetime
from typing import List

def get_trading_dates(start: str, end: str) -> List[str]:
    """
    获取指定日期范围内的交易日列表
    
    Args:
        start: 开始日期（YYYY-MM-DD）
        end: 结束日期（YYYY-MM-DD）
    
    Returns:
        List[str]: 交易日列表，格式 YYYY-MM-DD
    """
    pass

def is_trading_day(d: str) -> bool:
    """
    判断是否为交易日
    
    Args:
        d: 日期（YYYY-MM-DD）
    
    Returns:
        bool: 是否为交易日
    """
    pass

def get_latest_trading_day(d: str) -> str:
    """
    获取指定日期最近的交易日（包含当天）
    
    Args:
        d: 日期（YYYY-MM-DD）
    
    Returns:
        str: 最近交易日（YYYY-MM-DD）
    """
    pass

def get_next_trading_day(d: str) -> str:
    """
    获取指定日期的下一个交易日
    
    Args:
        d: 日期（YYYY-MM-DD）
    
    Returns:
        str: 下一个交易日（YYYY-MM-DD）
    """
    pass

def parse_date(d: str) -> date:
    """
    解析日期字符串为 date 对象
    
    Args:
        d: 日期字符串（支持 YYYY-MM-DD、YYYYMMDD 等）
    
    Returns:
        date: date 对象
    """
    pass

def format_date(d: date, fmt: str = '%Y-%m-%d') -> str:
    """
    格式化日期为字符串
    
    Args:
        d: date 对象
        fmt: 格式，默认 '%Y-%m-%d'
    
    Returns:
        str: 格式化后的日期字符串
    """
    pass
```

## 6. 日志格式规范
```python
# 日志格式
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
# 时间格式
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 示例输出
# 2026-05-18 10:30:45 [INFO] argus.core.credibility - Credibility score: 0.85
# 2026-05-18 10:30:45 [WARNING] argus.core.signal_generator - Low confidence: 0.32
```

## 7. 验收标准
- [ ] get_logger() 输出到正确路径 `logs/{submodule}/{module}_{YYYYMMDD}.log`
- [ ] 日志格式符合规范
- [ ] date_utils.py 所有函数可独立测试
- [ ] 可被 skills/research/argus/ 等子项目调用
- [ ] 不依赖任何业务模块

## 8. 参考资料
- RFC-00-001-yquant-investment-global-architecture
- Python logging 模块官方文档