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
├── README.md        # 顶层 README（目录说明 + origin/main ← upstream/master 映射）
├── legacy/          # 旧 A 股 / QUANTAXIS 策略历史归档（仅供历史参考）
│   ├── README.md
│   ├── strategy_BottomLaunch.py
│   ├── strategy_OppositeTrend.py
│   ├── strategy_ShockBottom.py
│   ├── strategy_TrendBack.py
│   ├── strategy_executor.py
│   ├── strategy_executor.bat
│   └── strategy.log  # .gitignore 忽略，本地日志
├── OctoBot/         # OctoBot 源码子模块（git submodule，PascalMore/OctoBot.git @ main）
├── backtest/        # 回测引擎与框架（待建设）
├── signals/         # 信号生成器（待建设）
├── execution/       # 执行算法 (TWAP/VWAP)（待建设）
└── templates/       # 策略模板（待建设）
```

## 状态

- **legacy/**：旧 A 股 / QUANTAXIS 策略的历史归档，1:1 原样保留，未做任何重构或修复。
  不作为实盘建议；未经授权不得 import、执行或修改其中代码。
- **OctoBot/**：以 git submodule 形式接入的 OctoBot 源码（`PascalMore/OctoBot.git @ main`）。
  仅作为源码仓库接入，**未做依赖安装、未做任何回测、未启动任何模拟或实盘机器人**。
  子模块本地配置了 upstream=Drakkar-Software/OctoBot，仅用于读取官方 `upstream/master`
  作为分支映射参考；当前 SHA 与 fork 的 `origin/main` 一致。
- **backtest / signals / execution / templates**：🚧 建设中。
