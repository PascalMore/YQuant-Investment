# RFC-07-002: Predict.fun 最小实盘接入基础（Toolkits + 官方 SDK）

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | V1.1 窄修订草稿；显式 RPC 与官方直接 SDK/Privy 路由输入已闭合，待主控 Gate；非实现/实盘授权 |
| 作者 | YQuant Principal |
| 创建日期 / 最后更新 | 2026-11-13 / 2026-11-13（Asia/Shanghai，UTC+08:00） |
| 版本 / 所属模块 | V1.1 / 07_trading |
| 依赖 RFC | [RFC-07-001](RFC-07-001-predictfun-btc5m.md)（历史基线与研究边界） |
| 替代 RFC | 无；不重写或追认 07-001 历史签收 |
| 派生 SPEC | [SPEC-07-002](../../spec/07_trading/SPEC-07-002-predictfun-live-foundation.md) V1.1 |
| 后续 Design | [DESIGN-07-002](../../design/07_trading/DESIGN-07-002-predictfun-live-foundation.md) V1.1，已独立存在；原 T2 历史保留 |
| AI 适配 / 来源任务 | Hermes Full Flow；T1 `t_58c245a7`；工作区 `/home/pascal/workspace/yquant-investment` |
| 标签 | #交易 #复用 #成交语义 #账户核对 #安全 |

## 1. 执行摘要（Executive Summary）

唯一执行底座继续使用已有 Toolkits 用户 fork；修正 Predict.fun 实际成交与未知订单的记账/风险语义，并以 `predict-sdk==0.0.22` 直接 import 增加人工显式授权/赎回薄工具。成功是代码经离线验证后具备申请人工值守、限额限时试运行的基础，不等于真实账户接通、真实成交/赎回已验证或策略盈利。

## 2. 背景与动机（Background & Motivation）

- [Intake](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/intake.md) 记录 Pascal 已授权推进 AI Coding Pipeline 的研发范围；没有授予真实资金动作权限。[最小方案](../../../data/reports/2026-11-13-predictfun-infra-reuse/minimal-integration.md) 是选型输入，不是已冻结 Design；与 Intake/本契约不同的旧建议不转为本轮要求。
- 已核 Toolkits main/HEAD 为 `4aaeefafd597bade591867f6b8a94c2677a1554f`，主仓 T1 开始 HEAD 为 `60de53dc3b7c49250ce1a6ebef4f4b8505c5fd1c`。BOT 指 `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/`。
- BTC5m 路径是 `RoundTaker → Broker::take → OrderVenue::place → PredictFunTrader`。BOT `src/bot/runtime.rs:418–435` live 把未知数量回退请求量、用 limit 和模型费用记账；`src/service/order_executor.rs:194–208` 另有 copy 未知满额分支。只修 copy 无法覆盖 BTC5m。
- 既有 `predict_fun.rs:1348–1529` 已含成交轮询、签名提交、remove、order_state 和分页 positions；认证刷新、启动敞口、removing 及限额亦已存在。要复用，不重新开发 client/OMS。
- SDK 证据采用[既有发行版签名输出恢复](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/sdk-release-prior-output.md)：仅证明此前 v0.0.22 ref 的同步方法与参数名。`source-snapshots.json` 中 SDK 为 HEAD `55381bfed02323c5edbc6eed0f5c603ae84172ef`，不是发行版快照。Intake 的 tag commit `6da1708e1f3a9341f5cfd8d0b91bb66c8f43bef1` 仅作主控既有记录；当前没有独立重验映射、安装或运行 SDK。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

1. BTC5m live 按已确认事实区分零/部分/全额/未知成交，保留 order ID 与已签 order hash，按实际金额、VWAP、费用、净份额更新；未知不能伪装零或满额。
2. 提交结果不明保留预算、停止相关新增、不重签补单；去重增量记账，remove 未闭合仍有风险，读取失败不得变成健康零账户。
3. 复用既有 REST/持仓与风险保护；由显式 `--predict-rpc-url` 补足原本不存在的 BSC 只读上下文，保持同链、同交易地址、同账户模式及重启人工核对边界。
4. 同 BOT `tools/predictfun/` 内直接调用官方 SDK，默认 plan/check 不加载 signer、不签名、不广播。显式 approve/redeem 可作为受控能力实现，但本轮不真实执行。
5. 保持无钱包 paper、策略/历史研究及其他 venue 行为；共享回执只做必要兼容。

### 3.2 非目标（Out of Scope）

不引入 dr-manhattan、TS SDK、其他 bot、第二执行工程、新 SDK submodule、Rust 授权/赎回移植、跨语言订单热路径、Web UI、daemon、数据库或调度。不做自动赎回、链上 merge/cancel、跨日/跨重启自动风险恢复，不新增持久 OMS/journal 平台。不改变原模型公式、EWMA、edge、5m 选择、价格源、历史研究或资金参数；不重跑 94 日研究/6h paper。不将本轮工程授权解释为账户登录、私有 API、真实签名、真实/场馆模拟订单、撤单、approve/redeem、充值提款或生产库读写权限。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

一个 Rust 执行入口、一套既有风险状态；SDK 仅补人工资金工具。确认事实与保守风险占用分离，未知向停止新增降级，而不是制造成交或清零敞口。

### 4.2 架构总览

`Rust DecisionCore → RoundTaker → Broker → 既有 PredictFunTrader → 官方订单/成交事实 → 同一 Broker 记账与风险保护`。

独立人工工具 `BOT/tools/predictfun → import predict_sdk → 授权/赎回计划、只读核对或显式受控操作`；Rust 不在每次下单调用 Python，工具不提交订单、不常驻。实现差量留在同一用户 fork，保留已有 submodule，不改 gitlink。

### 4.3 模块分工

| 模块 | 职责与边界 |
|---|---|
| 既有 venue/adapter | 回执事实、稳定订单身份、复用官方状态/成交/分页持仓读取；不造第二 client |
| 既有 runtime/Broker | 真实增量记账、未闭合占用与停止新增；copy 仅必要回执兼容 |
| SDK 薄工具 | 目标/账户核验、无 signer 默认、显式授权/赎回及读回；不接策略热路径 |
| YQuant 正式文档/流水线 | 需求、实现设计、独立 Verify/Review、主控签收；不接生产数据库或部署 |

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

1. live 新增前检查账户身份、余额/gas、所需授权、完整持仓与未闭合订单，以及既有限额；不可读/身份不符/未解释风险时拒绝新增。
2. 在发送前保留已签 hash 与保守预算；提交可返回 accepted、明确未提交/拒绝或结果不明，后两者不能通过普通错误丢掉已可能发出的订单身份。
3. 使用同一订单身份查询，确认数量与现金/份额/费用事实按唯一成交增量应用。终态零才能释放全部未成交占用；已确认部分只记实际部分，未闭合余量继续保留风险。
4. 传输超时、未知费用/金额、撤单竞争或读回失败，保持未确认/诊断及风险占用，允许同订单查询与停止相关活动，不允许新 salt 自动补单。remove 成功不等于不可成交。
5. 人工工具默认仅计划/检查；未来具体获准后才加载 signer 执行明确目标。签名、tx hash、成功 receipt、资金/份额到账读回是不同证据，任何一项不能替代后一项；结果不明禁止自动重发。

### 5.2 数据模型（Data Model）

下表是逻辑契约，不规定 Rust 类型布局或 SDK 原始字段名；可计算规则见 SPEC §4。

| 实体 | 必需语义 | 约束 |
|---|---|---|
| 账户身份 | chain、交易地址、账户模式；signer 与资金地址关系 | 不能默认 signer 地址等于实际持仓地址 |
| 订单 | 本地关联身份、已签 hash、可选 venue order ID、请求上限、状态证据 | order ID/hash 不混用；无 order ID 不等于未提交 |
| 成交 | 唯一事实身份、累计/增量数量、实际对价、费用币种与数量、净份额、来源/时间 | 重复不重记，缺失不补零，limit/模型费用不是实际成交 |
| 风险占用 | 已确认风险 + 未闭合剩余风险、账户阻断原因 | 不因未知/撤单请求释放；不把同笔成交与预留重复累计 |
| 资金操作结果 | 目标、计划、授权范围或赎回参数、tx/receipt 与读回证据 | 未确认不得标 completed；错误保留步骤与原因 |

### 5.2bis 持久化策略（Persistence Strategy）

无新增生产持久化需求；不建库、表、索引、TTL 或恢复日志平台。运行期订单身份/去重/预算属于现有进程内状态，复用既有脱敏日志与官方事实核对，日志不冒充可自动恢复主账。进程崩溃/重启后，必须先对账，未解释订单/风险或新运行预算未经人工确认不得继续；空内存和余额非零不构成恢复完成。

本轮过程记录仅在 `data/tasks/active/2026-11-13-predictfun-live-foundation/`，后续真实验证报告仅在 `data/reports/2026-11-13-predictfun-live-foundation/` 及其 `evidence/`。主控完成后整体归档过程目录，不删除/覆盖既有证据；无自动清理、迁移、备份或跨项目复制。公开源码/契约可记录，账户诊断最小化脱敏；真实私钥、认证材料、原始私密账户数据不进入 Git、报告或 Kanban。没有 schema 迁移或生产回滚动作。

### 5.3 接口契约（API Contract）

不新增 HTTP 服务/API。现有 Rust 接口承载可区分确认/未确认的回执；所有直接消费者须尊重同一 Predict.fun 语义。工具的逻辑操作为 plan/check/approve/redeem：输入是明确账户上下文和市场/操作目标，输出是计划、可读性/授权状态或分步骤资金操作证据；缺字段/身份不符/未知状态按 SPEC 错误语义返回，不能成功附带静默零值。具体函数签名、CLI flags、文件 allowlist 由 T2 定义。

本次 Pascal 已批准的窄修订 `t_188a7257`：只增加主 CLI 显式 `--predict-rpc-url`，在凭据加载前解析，经既有进程内确认槽和 trader 构造接线，不增加持久配置/服务。paper/非 Predict 不要求该参数、不创建 RPC 上下文或因它联网；Predict live 缺失/非法/链不符拒绝新增。不复用 Polygon RPC、不采用 SDK 的公开默认 URL。完整 URL 可含凭据，禁止日志、Debug、错误链和示例泄漏；具体校验/脱敏见 SPEC §4.5、Design §3.3.5。Rust 仍只读，approve/redeem 仍仅既有官方 SDK 薄工具。

部署/ABI 的新依据限本地固定 wheel 的公开 constants/ABI 与固定官方公开文档，详见 Design §3.3.5 的逐链逐路由表及[源证据](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/public-data-final.json)。既有 deployment 仅有四个 exchange，并没有完整资产/validator 读上下文；本修订纠正此前“直接复用已有部署即可”的假设。已核 wheel 不证明链上部署现状或 HEAD→发行版映射。

官方依据闭合（本地 HTML 仅作纯文本读取；URL 非不可变 ref，以以下 SHA256 固定本次内容）：

- https://dev.predict.fun/trading/approvals ，[official-approvals.html](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-approvals.html)，SHA256 `84b21b78886c9faf6d86a87fcc61b1b80af747a97f6283e62f58bb7ff4a1a6a1`：直接 SDK 经 PredictAccount 发授权交易，由 Privy signer 签名并支付 BNB gas；资产/授权归 trading_address。此 payer 依据不证明 matcher 结算 gas 由用户承担，不扩至网页代付/任意 paymaster。
- https://dev.predict.fun/trading/authentication ，[official-authentication.html](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-authentication.html)，SHA256 `a3db7f4d12ce5bdcce2ff28f4b796f81a02d4cac98ce38aba61684519b731cf5`：SDK 链上核对 Privy owner，未初始化/owner 不符拒绝。
- https://dev.predict.fun/resources/order-signing ，[official-order-signing.html](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-order-signing.html)，SHA256 `9f0c094bfabdbffbb3c1b2d6225887413f04dc0c6cb4d02573f31425dc716c93`：仅支持官方 Kernel 0.3.1/ERC-1271 路由，既有 Kernel 包装及 EIP-191 签名后以 `0x01 + 0x845ADb2C711129d4f3966735eD98a9F09fC4cE57 + 65字节签名` 得86字节，两链 validator 相同。保留 owner/初始化/同链身份检查，发送前以同账户 ERC-1271 验证既有签名，精确谓词见 SPEC §4.5/Design §3.3.5；不新增签名路径，不要求泛化 rootValidator/isModuleInstalled 模块枚举。

### 5.4 AI 模型设计

无新增模型或训练，原 DecisionCore、估值和阈值不变；本轮不以执行加固替代策略评估或宣称 alpha。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行

按独立 SPEC/Design 最小实现，在同 BOT 内直接 import 锁版 SDK；保留许可证。后续 Implement 仅在工具隔离环境安装获准 SDK 及必要锁定传递/测试依赖，不升级共享主仓 `.venv` 或系统工具链。对实际 BTC5m consumer、copy 必要兼容、资金工具默认拒绝和边界条件作无网 fixture/fake 验证；固定公开测试向量仅允许本地离线签名对拍，不使用真实密钥。

### 6.2 先询问再执行

超出冻结范围、依赖升级/替换、生产数据/配置或实际资金/账户动作必须另获明确授权。已批准锁版 SDK 的隔离实施无需重新选型；T1 不安装，T2 先由主控核对 RFC/SPEC 后派发。真实首单可在以后获准后验证，不设置“首单前必须已真实成交”的循环门槛。

### 6.3 绝对禁止

不读交易 secret/继承密钥、不真实认证/签名/私有 API/资金动作、不新 paper。禁止修改其他项目、Hermes/profile/审批/model/provider、服务/代理/长期调度；禁止 reset/stash/clean/checkout、git add/commit/push/gitlink 更新及证据覆盖。T1 不联网取证、运行 SDK、安装或测试；既有网络安全拒绝保持未执行，不换工具/命令/委派重做。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 / 影响 | 应对及降级 |
|---|---|---|
| 发行包行为与 HEAD 参考不同 | 未知 / 高 | 恢复输出仅证明方法签名；T2 定位映射，T3 隔离制品/API/无网行为验证；不猜字段或暗中换版本 |
| API 不提供完整成交/费用事实 | 未知 / 高 | 明确 unknown 与来源，保留预算并阻断新增；不以模型费率或 limit 冒充实绩 |
| 超时、分页缺页、撤单与成交竞争 | 存在 / 高 | 保留稳定身份、现有页数保护与 removing；未闭合不释放风险、不自动重签 |
| ERC20 超额授权或误解 operator | 存在 / 高 | ERC20 显式有限额；ERC1155 是布尔 operator 权限，单独呈现确认，不宣传金额封顶 |
| 重启丢失进程内风险状态 | 存在 / 高 | 人工对账/预算确认前不继续；明确无自动恢复保证，不扩持久 OMS |
| 大文件继续膨胀 | 存在 / 中 | runtime 1597 行、predict_fun 2284 行基线；T2 按 G3 定职责/增长/拆分触发，主体放候选 helper，独立 Review |

## 8. 备选方案（Alternatives Considered）

- dr-manhattan/第二 Python 执行器：增加状态映射与第二订单入口，本轮不选。
- 将 SDK 授权/赎回移植 Rust 或复制源码：重复维护协议，不选；直接包依赖。
- 同时 SDK submodule + pip、TS SDK 或其他 bot：增加版本漂移与部署面，不选。
- 持久 OMS/自动赎回/跨日恢复：超出人工值守最小基础，不作为本轮前提。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

以 SPEC §5 的 A-001–A-012 为唯一细化矩阵：实际 BTC5m 零/部分/全额/未知、实际现金/费用/净份额、重复/乱序增量、超时身份保留、remove 竞争、账户失败、重启阻断、SDK 默认无签名/显式有限操作/分步骤读回均有可证伪输入输出。仅具备代码不足，后续必须真实运行离线验证并独立 Review。

### 9.2 非功能验收

范围不漂移，原无钱包 paper 不新增 SDK/密钥前提；保留分页上限与既有限额，查询有界，不增加 daemon/新网络热路径。当前不引入延迟、收益或亏损绝对保证数值门槛。真实账户、成交/费用、approve/redeem、到账与盈利均另列未执行，不用 mock 成功替代。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

T1 RFC/SPEC → 主控核对 → T2 独立 Design → Implement → 独立 Verify → 独立 Review → 主控 Closeout。T1/T2 已有历史交付；当前仅同步现有三层的 V1.1 窄修订，不新建阶段、不改代码、不创建下游或解锁实现。原 A-001–A-012 不变。

### 10.2 任务清单

Principal 冻结行为与验收；T2 定具体文件/消费者/字段映射、无网测试命令及降级回滚。Developer 仅按已核 Design 实现；Tester 独立复跑矩阵；Reviewer 核范围/三层一致性/G3；主控最终签收。真实试运行需以后具体授权，不增设额外 Activation/runtime 平台。

## 11. 开放问题（Open Questions）

无待用户猜定的需求层关键语义。SDK 制品/返回字段/无 signer contracts 行为、官方成交字段覆盖与单位是后续实现验证事项，不是已证明能力；不能映射到 SPEC 时报告具体失败，不替换版本或编造事实。真实账户兼容与资金结果留在以后获准验证，不阻断本次需求交付。

V1.1 原 run3669 的 payer/控制路由来源阻断已由上述官方快照与主控限定的直接 SDK/Privy 范围闭合，见[依据裁定](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-basis-resolution.md)及[窄修订交接](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/rpc-input-correction-handoff.md)追加闭合记录。未知代付/任意 Kernel 模块不属于本次支持范围，不据此永久拒绝已支持路由；必要读项失败、owner/初始化/签名/身份不符仍失败关闭。输入闭合不表示 reader、adapter→Broker、G3 或独立验收已完成，仍由主控 Gate 后恢复既有实现卡。

## 12. 参考资料（References）

- [SPEC-07-002](../../spec/07_trading/SPEC-07-002-predictfun-live-foundation.md)、[Intake](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/intake.md)、[发行版既有输出及证据级别](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/sdk-release-prior-output.md)。
- [最小方案（非 Design）](../../../data/reports/2026-11-13-predictfun-infra-reuse/minimal-integration.md)；证据校正以 Intake/恢复输出为准，不把旧方案的 tag 已核措辞扩大为本次独立验证。
- [历史 SPEC-07-001](../../spec/07_trading/SPEC-07-001-predictfun-btc5m.md)、[历史 DESIGN-07-001](../../design/07_trading/DESIGN-07-001-predictfun-btc5m.md)；旧阶段禁令不覆盖本轮已新增研发授权，也不改变历史结果。
- 官方包来源：https://github.com/PredictDotFun/sdk-python 。本 T1 未新联网或执行外部代码。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-11-13 | 最小接入基础需求、风险与授权差量；SDK 证据分级；分离工程验收与真实试运行 | YQuant Principal |
| V1.1 | 2026-11-13 | t_188a7257：冻结显式只读 RPC 输入/脱敏与部署 ABI；官方快照闭合直接 SDK/Privy payer/控制谓词，保留 run3669 历史及全部原验收；待主控 Gate | YQuant Principal |
