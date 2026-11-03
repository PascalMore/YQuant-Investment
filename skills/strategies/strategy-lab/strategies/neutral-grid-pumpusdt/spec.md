# 需求冻结：PUMP/USDT 中性等比网格（研究实例）

## 目标
在 QuantDinger 原生 executor 网格上评估 PUMP/USDT 的中性等比网格策略，
四个合约各用独立资金池，不跨池挪用。

## 参数（由真实行情推导，见 data/reports/2026-10-31-neutral-grid-param-derivation/）
- 数据源：gate.io spot K 线（agent 路由只读）
- 几何窗口：最近 365 根日线（2025-11-01 ~ 2026-10-31）
- 网格下界：`0.0011514`　上界：`0.0068061`（H/L = 5.911）
- 格数 N = 120，等比间距 1.492%（约束区间 0.45%–1.5%）
- 模式：neutral（GRID_SIDE='neutral'，中点以下 long_entry、以上 short_entry，初始仓位 0）
- 预算：每格 1/N，总计 1000 USDT（`total_amount_quote`=1000，`initial_capital`=1000）
- 交易所杠杆：未启用（实际回执 `leverageEnabled=false`、`leverage=1.0`）——本次为 1 倍自有资金账户，无借款、无强平路径
- 组合级风控：显式置 0/false（equity_take_profit_pct=0、equity_stop_loss_pct=0、trailing=false），
  避免平台缺省注入的 10%/6%/trailing 污染基准比较
- `max_open_orders`=4（对应生成源码 `MAX_OPEN_ENTRY_ORDERS`）
- `min_spread_between_orders`=0.007459（半个格距，限制平台侧挂单不叠格）

## 回测口径
- 初始资金 1000 USDT，commission 0.0005，slippage 0.0005
- `fundingMode=not_modeled`（资金费不计入，已与用户确认）
- 平台撮合为 OHLC 假设（当前 bar 的 high/low 触发挂单，同 bar open 优先于 limit 价），
  非逐 tick 保证；结论按此口径解读
- 口径修正（2026-11-03）：本实例 spec 原声明「交易所杠杆 10x」，但平台真实回执为 `leverageEnabled=false` / `leverage=1.0`（1 倍自有资金）；原因：提交时未传 `--leverage-enabled`，平台按 1 倍静默执行；平台层已修复（新增回执读回断言）；本实例结论为 1 倍口径，不可作为 10 倍杠杆结论使用，10 倍口径待 Path B 重跑后更新。

## 验收标准（回测后核对）
1. 报告含年化收益、最大回撤、夏普、卡玛、换手率、信息比率
2. 最大回撤 ≤ 35%
3. 实际持仓杠杆 ≤ 250%：不适用——本次执行未启用杠杆（`leverageEnabled=false`、`leverage=1.0`，实际回执），无「持仓杠杆 vs 250%」判定口径；如后续启用杠杆须重新核算
4. 强平价估算口径：不适用——1 倍自有资金账户无强平路径（实际回执 `leverageEnabled=false`）；如后续启用杠杆，须按当时口径重新标注（原声明的 MMR 三档仅适用于杠杆情形），不冒充交易所实盘强平输出

## 已知限制
- 网格上下界取自历史极值，存在前视性质；结论须以「滚动重定界」为前提
- 数据源为 gate.io 而非币安，价格序列可能存在细微差异
- 平台无 250% gross / 35% MDD 事前闸门，只能事后筛选
