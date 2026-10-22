---
name: risk
description: "YQuant 风险管控模块：用于 VaR/CVaR、压力测试、实时风险监控、风险归因与限额管理。"
---

# Risk Management Module

风险管控模块。

## 职责
- VaR/CVaR 计算
- 压力测试
- 实时风险监控
- 风险归因

## 目录结构
```
risk/
├── models/        # 风险模型
├── monitoring/    # 实时监控
├── reports/       # 风险报告
└── limits/        # 限额管理
```

## 状态
🚧 建设中；上述目录为能力规划，不代表已建立实时风控服务。

## 与 Trading 的协作（规划）

依据 [RFC-26-072](../../docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md)：Risk 是横切业务能力，主责风险政策、限额、压力测试与组合风险分析；Portfolio 提供资金与风险预算，[Trading](../trading/SKILL.md) 在交易前/中落实相应检查、暂停和异常处理，并反馈实际敞口、拒绝原因与风险事件。不为本次规划新增模块编号或第二套独立限额事实源。

AI/策略不得自行放宽硬限额。暂停、禁止新开仓、撤单、平仓分别定义，风险降低操作按批准策略处理。当前没有已启用检查或运行授权，不将规划要求冒充已有保护。本次不修改风险阈值、交易配置或账户权限。
