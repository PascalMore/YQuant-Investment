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
- 实盘部署支持

## 目录结构

```
strategies/
├── SKILL.md         # 本文件
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
├── execution/       # 执行算法 (TWAP/VWAP)（待建设）
└── templates/       # 策略模板（待建设）
```

## 状态

- **legacy/**：旧 A 股 / QUANTAXIS 策略的历史归档，1:1 原样保留，未做任何重构或修复。
  不作为实盘建议；未经授权不得 import、执行或修改其中代码。
- **backtest / signals / execution / templates**：🚧 建设中。
- **数字货币方向**：计划使用 OctoBot 接入，**当前 OctoBot 接入决策（分支、是否启用）尚未确认**，
  不得描述为已部署 / 已接入。