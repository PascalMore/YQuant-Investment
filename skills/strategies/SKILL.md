---
name: strategies
description: "YQuant 量化策略研发与回测模块：用于策略设计实现、历史回测、过拟合检测与实盘部署支持。"
---

# Strategies Module

量化策略研发与回测模块。

## 职责
- 策略设计与实现
- 历史回测与验证
- 过拟合检测
- 策略/模型版本发布与部署交接；获准实例的运行编排、执行和对账归 Trading

## 目录结构

```
strategies/
├── SKILL.md         # 本文件
├── README.md        # 目录说明、当前状态与移除记录
├── legacy/          # 旧 A 股 / QUANTAXIS 策略历史归档（仅供历史参考）
│   ├── README.md
│   ├── strategy_BottomLaunch.py
│   ├── strategy_OppositeTrend.py
│   ├── strategy_ShockBottom.py
│   ├── strategy_TrendBack.py
│   ├── strategy_executor.py
│   ├── strategy_executor.bat
│   └── strategy.log  # .gitignore 忽略，本地日志
├── backtest/        # 回测引擎与框架（待建设）
├── signals/         # 信号生成器（待建设）
└── templates/       # 策略模板（待建设）
```

## 状态

- **legacy/**：旧 A 股 / QUANTAXIS 策略的历史归档，1:1 原样保留，未做任何重构或修复。
  不作为实盘建议；未经授权不得 import、执行或修改其中代码。
- **OctoBot 已移除**：2026-10-22 按 Pascal 明确决定移除源码 submodule；不再登记、安装或自动发现。其虚拟环境已按授权直接删除，历史调研不代表当前接入。
- **backtest / signals / templates**：🚧 建设中，以上目录为规划而非已实现能力。
- TWAP/VWAP 等执行算法改归 Trading 的规划范围；本次没有迁移代码或建立执行接口。

## 与 Trading 的协作（规划）

依据 [RFC-26-072](../../docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md)：本模块负责策略/模型的规则、训练验证、回测优化、信号语义、参数边界与版本发布。Trading 加载获准版本，承载自动化触发、线上决策调用、实例运行、资金协调、风险检查、订单执行与恢复对账，不另写一套策略逻辑。

运行结果与费用、风险和执行偏差回流研究/回测，形成候选优化；不得自动修改生产策略或扩大权限。回测与实盘复用明确的策略/执行契约，不代表成交模型和交易环境完全相同，也不表示已完成一致性验证。

legacy 保持原位置与内容；OctoBot 已从当前接入中移除。不因新增 [Trading 技能](../trading/SKILL.md) 宣称任何机器人已可运行。
