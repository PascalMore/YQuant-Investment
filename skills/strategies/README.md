# Strategies 模块目录说明

本目录为 YQuant 的量化策略研发与回测模块。

## 当前布局

- `SKILL.md`：模块说明、目录结构、当前状态总览。
- `legacy/`：旧 A 股 / QUANTAXIS 策略历史归档，仅作历史参考，不作为实盘建议。
- `strategy-lab/`：Strategy Lab 研发工具与策略实例——工具资产（SKILL、README、`scripts/`、
  `templates/`、`tests/`）在根层，具体策略/研究实例在 `strategy-lab/strategies/<strategy-id>/`；
  现有样例为 `strategy-lab/strategies/spy-ma-smoke/` 与 `strategy-lab/strategies/spy-close-research/`。
- `backtest/`、`signals/`、`templates/`：待建设（规划目录，非已实现）。
- TWAP/VWAP 等执行算法改归 [Trading](../trading/SKILL.md) 的规划范围，不在本次建立或迁移执行代码。

## OctoBot 移除记录（2026-10-22）

按 Pascal 明确决定，已从 YQuant 移除 OctoBot：

- 移除 `skills/strategies/OctoBot` 源码 submodule 登记及 `.gitmodules` 条目，gitlink 已从主仓索引删除。
- 其本地虚拟环境（`venv/`，Python 3.13，115MB）按授权直接删除，未做备份。
- 移除前只读核验：子模块工作树干净、无本地未推送提交（HEAD 与本地 `origin/main` 同为 `c45fdc2c95c5bd3d649251fa90c327e2e8f86b00`）、无相关运行进程。
- 移除前完成模式级核验：OctoBot 内置网格链路最终继承 SPOT 支持声明，未核实合约网格适配；其合约 DCA 为单向多头且拒绝 hedge；现货目标权重篮子已有实现。结论是它不适合作为三机器人统一承接平台。
- 移除不代表否定该项目能力，仅表示不在 YQuant 当前接入范围内。历史调研证据保留在会话 scratch，不作为已实现能力。

后续如重新引入，需重新核验版本、许可与目标场景，并明确源码归属目录（不默认回到 `strategies/`）。

## 策略研发与交易运行分工

本模块负责规则/模型研发、回测与参数验证、信号语义和版本发布；Trading 承载获准版本的自动化、策略化与智能化交易运行，管理计划/触发、实例、订单、资金协调、恢复对账和事实反馈。策略规则不在两边重复实现。

规划依据：[RFC-26-072](../../docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md)。本次没有修改现有策略源码、子模块或运行配置。

## 接入状态

- 本目录当前不含任何 Git submodule；OctoBot 已于 2026-10-22 按用户决定移除，详见上方移除记录。
- 未执行依赖安装、未运行任何回测、未启动任何模拟 / 实盘机器人。
- 原升级脚本 `scripts/upgrade/update_submodules.py` 从 `.gitmodules` 自动发现子模块，OctoBot 移除后不再出现在发现结果中；脚本本身未修改。
