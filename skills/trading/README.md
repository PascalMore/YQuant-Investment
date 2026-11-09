# Trading · 自动化、策略化与智能化交易

归属既有 `07_trading`。定位是交易业务与运行，不是只有交易所通道或下单 SDK；与 `06_strategy` 并列，共同完成从研究验证到获准运行及反馈的闭环。

## 当前实际状态

**仅完成规划与技能文档入口，未实现 YQuant 自有交易功能。** 未接账户、未安装引擎、未运行回测/模拟/实盘，未修改生产数据库、配置、调度、网关或推送。没有可供调用的订单接口。

已登记的第三方交易源码（submodule，只读保留原版）：

| 源码 | 路径 | 状态 |
|---|---|---|
| QuantDinger / -Vue / -Mobile | `skills/trading/auto-trading/quantdinger/{QuantDinger,QuantDinger-Vue,QuantDinger-Mobile}` | 源码已登记（`.gitmodules` 三条 `branch=main`）；本次未核验功能、构建或交易能力 |
| Prediction-Markets-Trading-Bot-Toolkits（fork `PascalMore/Prediction-Markets-Trading-Bot-Toolkits`） | `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits` | 已接入（`branch=main`，实际 SHA `71c0e4ff9e299f9a4d81757fd6b15cf54da69b38`）；**Implement 原版构建及安全离线测试通过**（`cargo build --locked` exit 0；`cargo test --locked` 164 passed / 0 failed / 3 ignored，均为源码级 `#[ignore]` 真实联网测试）；联网/交易路径未验证，待独立 Verify/Review |

源码接入不等于运行许可：本次未新增模拟/实盘、账户或运行控制授权。

```text
skills/trading/
├── SKILL.md   # 技能触发、使用方法、协作与权限边界
├── README.md  # 目录入口、实际状态与后续扩展规则
└── auto-trading/
    ├── quantdinger/            # QuantDinger / -Vue / -Mobile 源码（submodule）
    └── prediction-markets/
        └── Prediction-Markets-Trading-Bot-Toolkits   # Toolkits fork 源码（submodule）
```

能力范围和业务流程统一维护在 [RFC-26-072](../../docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md)，本目录不维护第二份详细架构正文。该 RFC 为 Draft，不代表已批准实现或运行。

## 入口与分工

- [Trading 技能](SKILL.md)：处理自动化/策略/智能交易规划与相关边界。
- [Strategy](../strategies/SKILL.md)：研发、回测、参数与模型验证、规则与版本发布。
- [Portfolio](../portfolio/SKILL.md)：配置、目标权重、预算、组合事实视图与归因。
- [Risk](../risk/SKILL.md)：横切的风险政策、限额和压力分析；交易边界执行检查。
- [Reports](../reports/SKILL.md)：研究/回测/实际运行与执行质量报告。
- [项目规则](../../AGENTS.md)：授权与工程流程。
- [Predict.fun BTC5m M1 契约集](../../docs/rfc/07_trading/RFC-07-001-predictfun-btc5m.md)：Toolkits fork 接入与原版基线的来源、范围与验收口径（RFC V1.1 / SPEC V1.1 / Design V1.0）。

自动化是运行方式，策略交易是规则/模型驱动，智能交易是 AI 参与决策；可组合，但不建立三套互相绕过的执行系统。Strategy 发布交易逻辑，Trading 承载运行与执行；结果反馈不意味着线上自动改变策略版本或权限。

## 后续增量建设

1. 针对首个明确市场、账户范围和交易场景，确认所需 SPEC/Design 及实现授权。
2. 优先复用成熟框架，先验证只读账户/订单口径，再按授权验证离线、模拟或测试环境；每种模式单独标识。
3. 经独立运行授权和风控审批后，才考虑外部执行系统的受限实盘验证；规划同意不等于交易许可。
4. 后续源码遵循获准设计；不为能力清单提前创建空服务、空适配器或第二套数据管道。

OctoBot 已于 2026-10-22 按用户决定从 YQuant 移除，不默认重新引入。QuantDinger 源码已登记为 submodule（`skills/trading/auto-trading/quantdinger/QuantDinger`、`QuantDinger-Vue`、`QuantDinger-Mobile`）；Prediction-Markets-Trading-Bot-Toolkits fork 源码已接入（`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`），其 Implement 原版构建及安全离线测试已通过，联网与交易路径未验证，待独立 Verify/Review。两者都只是源码存在，不代表已启用模拟或实盘。当前不引入新 Agent runtime，不新增数据库模型或配置默认值。

## 本次核验范围

核验文件、相对引用、技能元数据/可发现性及相邻模块职责一致性；本轮另核验 Toolkits fork 的来源读回、submodule 登记/归属/版本一致性与原版源码副作用审查。不声称进行了回测、账户连接、交易功能测试或独立流水线审查。
