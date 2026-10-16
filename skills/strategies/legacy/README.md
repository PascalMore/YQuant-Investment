# Legacy Strategies Archive

> 旧 A 股 / QUANTAXIS 量化策略历史归档，**仅供历史参考与代码考古，不作为实盘建议**。

## 范围

本目录按 1:1 原样保存以下历史产物，未做任何代码重构、格式整理或换行转换：

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| `strategy_BottomLaunch.py` | 8390 | `1adf9fd9266d22c1abb963112bb9f72a335f7bc4fe37e07f70311364b73e61b3` |
| `strategy_OppositeTrend.py` | 6492 | `d7aa2ee52e63037d1e7fd2409aa905ac18b414a1b9f4fb28b2cc3fbd2d1a7306` |
| `strategy_ShockBottom.py` | 14547 | `458341b6f006547723def21265a480b43d982b3dfec092589f0f364f3857bb2f` |
| `strategy_TrendBack.py` | 11666 | `9356bd266d1f38ff2410995c8bbf3bf66eeeb752b1da069ab6d96cd14741e8b7` |
| `strategy_executor.py` | 4747 | `c5c9f05b5eabd5dd376d3524dd74175bc47e94239175e47a9f23005b88821593` |
| `strategy_executor.bat` | 176 | `3ffa3a036b59aa35fea3add4fd097db48486300965f68d20cdf4192583c37755` |
| `strategy.log` | 12213505 | `b41ba74af4a0440fd1bdbc0f5895b5afa2f91d89059e563b00269cdca1561986` |

## 定位与边界

- **不验证**：本归档未对四个旧策略做任何回测、参数扫描或与现代数据源的兼容性验证。
- **不部署**：`strategy_executor.py` / `strategy_executor.bat` 仅保留以备历史复现，**不要在生产、研究或回测任务中直接 import 或执行**。
- **不修改**：除非另有明确任务授权，不要在本目录内修复旧 bug、调整参数或重命名导入。所有导入与相对依赖保持原始形态。
- **不自动运行**：`strategy.log` 是历史本地日志，被 `.gitignore` 忽略，保留原状供归档证据，不参与任何流水线。

## 使用场景

- 历史策略思路考古（仅阅读）。
- 与新策略库的接口对比参考。
- 当且仅当 Pascal 明确授权时，才能引用其中的代码片段用于新策略研发。

## 数字货币方向

数字货币方向的策略计划使用 OctoBot 接入。当前 OctoBot 接入决策（分支选型、是否启用、部署形态）**尚未确认**，本归档不包含数字货币策略，也未对 OctoBot 做任何接入、克隆或占位写入。