# Strategies 模块目录说明

本目录为 YQuant 的量化策略研发与回测模块。

## 当前布局

- `SKILL.md`：模块说明、目录结构、当前状态总览。
- `legacy/`：旧 A 股 / QUANTAXIS 策略历史归档，仅作历史参考，不作为实盘建议。
- `OctoBot/`：**OctoBot 源码子模块**（git submodule）。
  - 远端：`git@github.com:PascalMore/OctoBot.git`，分支：`main`。
  - 子模块本地另配 `upstream = git@github.com:Drakkar-Software/OctoBot.git`，
    仅用于读取官方 `upstream/master`，不做任何 merge / 升级 / push。
  - 当前 `skills/strategies/OctoBot/HEAD`（fork `main`）与
    `skills/strategies/OctoBot/upstream/master` SHA 相同，
    即 `origin/main ← upstream/master` 的分支映射关系成立（仅指明远端分支命名差异）。
- `backtest/`、`signals/`、`execution/`、`templates/`：待建设。

## 接入状态

- 仅完成 OctoBot **源码仓库**接入（git submodule）。
- 未执行依赖安装、未运行任何回测、未启动任何模拟 / 实盘机器人。
- 原升级脚本兼容性的真实状态由主控独立评估，本目录不声明已支持或运行过它。

## 分支映射约定

- 维护者 fork 使用 `main` 作为默认分支；
- 官方上游 Drakkar-Software/OctoBot 仍使用 `master`；
- 本仓库以 fork 的 `main` 为接入分支，`upstream/master` 仅作为对照参考。
