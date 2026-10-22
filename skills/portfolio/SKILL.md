---
name: portfolio
description: "YQuant 组合管理模块：用于资产配置优化、组合构建、再平衡、绩效归因与组合分析。"
---

# Portfolio Management Module

组合管理模块。

## 职责
- 资产配置优化
- 组合构建
- 再平衡策略
- 绩效归因

## 目录结构
```
portfolio/
├── optimization/  # 组合优化
├── rebalancing/    # 再平衡
├── attribution/    # 绩效归因
└── analytics/      # 组合分析
```

## 状态
🚧 建设中；上述目录为能力规划，不是本技能证明已实现的清单，实际功能须核对对应源码与验证证据。

## 与 Trading 的协作（规划）

依据 [RFC-26-072](../../docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md)：Portfolio 主责配置目标、目标权重、策略资金分配、组合风险预算和再平衡意图；[Trading](../trading/SKILL.md) 主责获准意图的计划/触发与执行、共享资金占用检查、订单/成交、费用和对账反馈。Risk 提供相关风险约束。

组合视图区分目标与实际，依据成交及账户对账证据更新现金、持仓、净值和归因，不以计划、未确认成交或策略估算权益代替账户事实。再平衡不在本模块另外建设绕过 Trading 的下单通道。本次仅更新规划，不写入生产持仓或账户数据。
