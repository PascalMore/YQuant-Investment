# RFC-03-006: OCR Provider Fallback（MiniMax → Z.AI / GLM）

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | ✅ 已实现（Implemented） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-24 |
| 最后更新 | 2026-06-25 |
| 所属模块 | data（OCR Provider 层） |
| 依赖RFC | RFC-03-003、RFC-03-004、RFC-03-005 |
| 替代RFC | 无 |
| AI适配 | OpenClaw/Codex |
| 标签 | #smart-money #数据管道 #OCR #Vision #Fallback #MCP #稳定性 #可恢复性 |

## 1. 执行摘要（Executive Summary）

当前 Smart Money Image Pipeline 单一依赖 `mmx vision describe`（MiniMax Token Plan MCP）做截图 OCR。一旦 Token Plan 额度耗尽或上游故障，整条 OCR 链路完全中断、整批图片无法入库。本 RFC 提出**抽象 `VisionProvider` 接口、引入 Z.AI/GLM Vision MCP 作为 fallback**，在主 provider 失败时自动降级到备用 provider，保持下游 schema 不变，使 Transform / Validate / Loader / Closeout 完全无需改动。核心原则：**接口稳定、provider 可插拔、fallback 触发条件可观测**。

## 2. 背景与动机（Background & Motivation）

### 2.1 现状痛点

- `skills/data/data-pipeline/scripts/extractors/minimax_image_extractor.py` 内部硬编码 `subprocess.run(["mmx", "vision", "describe", ...])`，调用 MiniMax Token Plan MCP 的 CLI 包装。
- MiniMax Token Plan 是计费产品，配额用尽后会返回 `quota exceeded / rate limit / system error` 等错误。当前 `_is_retryable_failure` 仅重试 3 次（指数退避最多 7s），**重试耗尽后整张图片直接报 `RuntimeError`**，被 `run_unified_image_pipeline.py` 顶层 catch 后整批失败。
- 即使 `mmx` CLI 自身仍可启动，**额度耗尽会让所有用户、所有 agent、所有 pipeline 同时不可用**，没有热路径绕过方案。
- 当前没有把"OCR 调用失败"与"下游数据校验失败"区分开 —— 用户收到 `failed` 状态时，无法判断是图片问题还是上游 API 配额问题，导致运营决策困难。
- Transformer / Validator / Loader 均以"DataFrame 已稳定"为前提假设，反向修改上游的代价高、风险大。

### 2.2 业务价值

| 维度 | 当前 | 目标 |
|---|---|---|
| OCR 链路可用性 | 单点依赖 MiniMax | 主备双 provider |
| 单图失败率（额度耗尽时） | ~100% | 仅在双 provider 同时失败时失败 |
| 失败归属 | 无法判断是 OCR 还是数据问题 | `provider_status` 字段明示 |
| 下游代码改动 | N/A | 0（保持 schema 稳定） |

### 2.3 触发原因

风险驱动 + 需求驱动：

- **风险**：MiniMax Token Plan 配额耗尽或临时不可用已经发生过（最近一次导致 Image Pipeline 整批中断），未来只会更频繁。
- **需求**：Pascal 明确要求"额度超限时 fallback 使用 GLM MCP"，且"只要两个 MCP 输出标准化，后面的流程就无需改动"。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

- [ ] 抽象 `VisionProvider` 接口，覆盖单图 OCR 调用与失败判定。
- [ ] 现有 `MiniMaxImageExtractor` 改造为 `MiniMaxVisionProvider`（实现接口），不再直接被 pipeline 实例化。
- [ ] 新增 `ZAIVisionProvider`（实现接口），通过 Z.AI MCP "General Image Analysis tool" 调用 GLM Vision。
- [ ] pipeline 入口（`run_unified_image_pipeline.py` 等）改为**先主 provider，失败后自动 fallback 到备 provider**。
- [ ] 两个 provider 输出**统一 schema**：`{df: pd.DataFrame, source_path: str, provider_status: {...}}`，下游消费者无感知。
- [ ] fallback 触发条件必须显式可记录：哪张图、哪个 provider、什么错误、是否已 fallback。
- [ ] provider 层可独立配置（API key 已在 `~/.hermes/profiles/yquant/.env`，MCP server 已在 `config.yaml`）。
- [ ] 同一图片在两个 provider 都失败时，记录双 provider 错误日志并按现有失败语义上抛。

### 3.2 非目标（Out of Scope）

- [ ] 不在本次更换 OCR 模型 prompt 模板（仍沿用现有 `VISION_PROMPT`）。
- [ ] 不在本次修改 Transform / Validate / Loader / Closeout / Review Gate 任何下游代码。
- [ ] 不在本次引入第三个 provider（Qwen-VL、Doubao 等）或本地 OCR 模型。
- [ ] 不在本次修改 `run_message_pipeline.py`（消息路径不走 OCR）。
- [ ] 不在本次新增 MongoDB 集合、不修改 schema validator 对 OCR 输出的硬约束。
- [ ] 不在本次实现"按 provider 自动路由"（例如按图片类型分流）；本阶段只用"主失败 → 备"的简单顺序策略。
- [ ] 不在本次实现 provider 性能基准测试或成本对比；仅做可用性 fallback。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

**接口稳定 + provider 可插拔 + fallback 显式**。在现有 Extractor 内部把"调用哪个上游"做成可替换的 provider，pipeline 入口只看到统一接口。fallback 不是隐藏行为，而是带可审计状态的事件。

### 4.2 架构总览

```
图片输入
  ↓
run_unified_image_pipeline.py
  ↓
Extractor (兼容旧 API，内部委托)
  ↓
VisionProviderRouter
  ├─→ PrimaryProvider (MiniMax) ──success──→ DataFrame
  └─→ FallbackProvider (Z.AI/GLM) ──success──→ DataFrame
  ↓
统一 schema 输出 → Transform / Validate / Loader （不变）
```

### 4.3 模块分工

| 模块 | 核心职责 | 依赖 | 输入 / 输出 |
|---|---|---|---|
| `VisionProvider`（新接口） | 定义 `async def describe(image_path) -> ProviderResult` 与失败判定 | 无 | 入参：图片路径；出参：统一 schema |
| `ProviderResult`（新数据类） | 封装 DataFrame、source_path、provider_status（name、fallback_used、attempts、errors） | 无 | dict 形式向下兼容 |
| `MiniMaxVisionProvider`（新类） | 封装现有 `mmx vision describe` 调用与重试逻辑 | mmx CLI | 同接口 |
| `ZAIVisionProvider`（新类） | 通过 MCP 客户端调用 Z.AI "General Image Analysis tool" | Z.AI MCP server | 同接口 |
| `VisionProviderRouter`（新类） | 顺序尝试 providers，主失败切备；记录每次结果 | 上述两者 | 出参：合并 ProviderResult |
| `MiniMaxImageExtractor`（重构） | 内部使用 Router，对外保持 `BaseExtractor.extract` 接口不变 | Router | 对调用方零改动 |

## 5. 详细设计（Detailed Design）

> 注：本节仅描述业务边界与数据语义；具体接口签名、异常类型、调用序列留给 SPEC 章节。

### 5.1 业务边界（Business Boundary）

- **provider 层只负责**：调用上游 MCP / CLI、解析原始输出、规范化 DataFrame、把 OCR 失败语义化为 `ProviderResult` 中的可读错误。
- **provider 层不负责**：资产名称复核（仍由 `asset_identity_review` 处理）、格式识别（仍由 `detect_format` 处理）、Excel 归档（仍由 pipeline 处理）。
- **fallback 的归属**：fallback 是 provider 层的事件，不是 pipeline 层的异常。任何 "OCR 不可用 → 自动切备" 的判断都发生在 Router 内部；pipeline 入口看到的只是最终 DataFrame。

### 5.2 统一 Schema 契约（语义层）

| 字段 | 类型 | 含义 | 提供方 |
|---|---|---|---|
| `df` | `pd.DataFrame` | 与现有 `_parse_vision_output` 输出一致 | 任一 provider |
| `source_path` | `str` | 原图绝对路径 | 任一 provider |
| `provider_status.name` | `str` | 实际生效的 provider（`minimax` 或 `zai`） | Router 写入 |
| `provider_status.fallback_used` | `bool` | 是否经历了主→备切换 | Router 写入 |
| `provider_status.attempts` | `list[dict]` | 每次尝试的 provider、错误摘要、耗时 | Router 写入 |
| `provider_status.errors` | `list[str]` | 人类可读错误（脱敏后） | Router 写入 |

下游（Transformer / Validator / Loader）只读 `df` 与 `source_path`；`provider_status` 作为审计字段透传到 `run_pipeline` 返回 dict 中，供批次汇总使用。

### 5.3 Fallback 触发判定

| 触发情形 | 主 provider 是否重试 | 是否切到 fallback |
|---|---|---|
| 网络/超时/5xx（transient） | 是，按现有 3 次指数退避 | 重试全部失败后切 |
| 配额耗尽（quota / 429） | 否，立即识别为不可重试 | 立即切 |
| CLI 启动失败（`mmx` 不在 PATH） | 否 | 立即切 |
| JSON 解析失败（输出格式异常） | 否 | 立即切 |
| Z.AI 也失败 | — | 上抛 RuntimeError，沿用现有失败语义 |

判定由 `_classify_failure(retryable: bool, error_kind: str)` 完成；具体分类规则与错误关键字留给 SPEC。

### 5.4 与现有 Review Gate 的协作

- 资产身份复核（RFC-03-004）继续在 OCR 之后运行，与 provider 无关。
- 如果 Z.AI provider 对同一张图识别出与 MiniMax 不同的 `Wind代码`，`asset_identity_review` 仍按现有"名称不兼容则进入 pending"语义处理，不假设哪个 provider 更准。
- fallback 路径产出的 pending 审计文件 `pending.csv` / `pending.json` 在 `provider_status` 字段记录实际 provider，便于人工追溯。

### 5.5 失败语义保留

- **两 provider 都失败** → 抛 `RuntimeError`，pipeline 仍按 `failed` 状态返回，与当前行为一致。
- **仅主失败、备成功** → 返回 `success` 或 `partial_success`（取决于 pending 情况），`provider_status.fallback_used=true` 仅作审计。
- **同一图片被 provider A 成功、被 provider B 部分行解析失败** → 当前不在处理范围（每个 provider 内部自己决定是否整图失败；这是 provider 层职责）。

## 6. AI实装规范（AI Implementation Rules）

### 6.1 必须执行

- provider 接口的输入输出与现有 `_run_vision_extraction` 保持一致语义，避免 Transform 层被牵连修改。
- 任何 provider 内部失败必须显式写入 `provider_status.errors`，不得吞掉。
- 测试用例必须覆盖：主成功、主失败备成功、主备皆失败、quota 关键词触发立即切换。
- 审计 debug JSON（`pic_*_vision_raw.json` / `pic_*_vision_error.json`）的命名与目录保持兼容，新增 provider 时复用 `_write_vision_debug` 工具。

### 6.2 先询问再执行

- 新增第三方 MCP 客户端依赖（如 `mcp` Python SDK）。
- 修改 `MiniMaxImageExtractor` 的公开签名（保持 `BaseExtractor.extract` 接口不变是默认目标，但若要扩展 `**kwargs` 需先确认）。
- 把任何 provider 默认顺序从"主 MiniMax / 备 Z.AI"反过来（默认保持主 MiniMax）。

### 6.3 绝对禁止

- 在未确认 schema 兼容前修改 Transform / Validate / Loader 的入参。
- 在 provider 内部静默重试到无上限。
- 把 `Z_AI_API_KEY` 写进任何代码或配置文件（必须经环境变量 / `.env`）。
- 在 fallback 路径上丢掉原始错误日志。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| Z.AI 输出 schema 与 MiniMax 差异大，导致后续 Transformer 失败 | 中 | 高 | 统一 `_normalize_columns` 与 `_clean_data`，在 provider 层强制收敛 | schema 校验在 provider 出口处执行；失败时整图 fallback 失败语义 |
| Z.AI MCP 占用主对话 token 预算，影响其他 agent 能力 | 中 | 中 | Z.AI MCP 仅在 OCR 路径按需调用；不用作通用 chat | provider 路由仅在 data-pipeline 进程内启用 |
| Z.AI 配额独立耗尽 | 低 | 中 | 双 provider 同时耗尽时回到现有失败语义；可在 Router 内接入"配额预算计数器" | 暂未实现，留作后续 RFC |
| fallback 路径产生的 `pending` 数据被人工误判为 MiniMax 误识 | 低 | 低 | `pending.json` 与 `provider_status` 中记录实际 provider | 人工补录时显式提示 provider 来源 |
| 两个 provider 对同一图识别不一致 → 重复入库 | 低 | 高 | OCR 阶段不写库；写入由 Transform/Loader 单点控制；fallback 不改变 Transformer 行为 | MongoDB unique key 兜底（已有） |
| 主备切换引入额外延迟（每图多一次 ~10s 调用） | 中 | 中 | 仅在主 provider 失败时切；正常路径无开销 | 未来可加超时预算 |
| `mmx` CLI 与 Z.AI MCP 安装/配置状态不一致导致行为漂移 | 中 | 中 | 启动时检查 provider 可用性并记录；不让"静默缺失"成为隐式 bug | 仅在两个 provider 都不可用时失败 |

## 8. 备选方案（Alternatives Considered）

- **方案 A：直接把 Z.AI 作为新独立 extractor 并行运行**
  - 优：实现简单
  - 缺：无法自动 fallback；两张图两次调用成本翻倍；schema 漂移风险高；**不采纳**
- **方案 B：智能路由（按图片类型 / 历史准确率选择 provider）**
  - 优：长期可优化
  - 缺：需要历史数据、需要 A/B 框架，超出本次范围；**留作后续 RFC**
- **方案 C：把 OCR 完全外移到独立微服务**
  - 优：解耦最彻底
  - 缺：本地工具链改动大、部署成本高、与现有 mmx CLI 调用方式不兼容；**不采纳**
- **方案 D（采纳）：抽象 provider 接口 + 主备顺序策略 + 统一 schema**
  - 优：实现集中、影响面小、保持下游不变、与 Pascal 原始需求一致
  - 缺：fallback 路径增加一次潜在调用延迟

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

- 主 provider 正常时，整张图处理结果与未引入 fallback 时完全一致。
- 主 provider 因 quota/timeout/network/parse-error 失败时，备 provider 接管并产出可用 DataFrame。
- 两个 provider 都失败时，pipeline 返回 `failed` 状态并保留双方错误日志。
- 审计 JSON 文件中可看到 `provider_status.name`、`fallback_used`、`attempts`、`errors`。
- 现有所有测试（`test_load_pending_confirmed.py` 等）在不动测试用例的前提下保持通过。

### 9.2 非功能验收

- 主 provider 成功路径不增加可见延迟（fallback 逻辑零开销）。
- API key、配置信息无明文落库。
- `pending.csv` / `pending.json` 中包含实际 provider 标记。
- 任何 provider 调用失败都在日志与审计文件中留下痕迹（不可静默）。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

1. 补齐 SPEC（接口签名、错误分类、调用序列、测试矩阵）。
2. 实现 `VisionProvider` / `ProviderResult` / `MiniMaxVisionProvider` / `ZAIVisionProvider` / `VisionProviderRouter`。
3. 重构 `MiniMaxImageExtractor`，内部走 Router，对外接口不变。
4. 接入 `run_unified_image_pipeline.py` 与 `run_image_pipeline.py`、`run_trade_image_pipeline.py`（如仍使用）。
5. 单元测试：mock 主 provider 失败、备 provider 成功；mock 双 provider 失败；mock 正常路径。
6. Review 与 closeout 文档。

### 10.2 任务清单（角色）

- Principal：SPEC / RFC 审阅、门禁。
- Developer：provider 接口与 Router 实现。
- Test Engineer：单元测试与回归。
- Reviewer：diff 与行为一致性。

## 11. 开放问题（Open Questions）

- [ ] fallback 优先级是否可由运行时配置覆盖（如临时把 Z.AI 设为主）？默认锁定"MiniMax 主，Z.AI 备"。
- [ ] 当一张图被 provider A 完全识别为另一格式（误把 trade 当 portfolio）时，是否需要在 provider 层做"格式 sanity check"，还是交给 `detect_format` 处理？
- [ ] fallback 路径触发的 pending 是否需要进入单独的 audit 目录（如 `review_pending/fallback/`）以便人工区分？或与现有 `review_pending/` 合并，仅靠 `provider_status` 字段区分？
- [ ] Z.AI 输出偶尔返回 markdown 包裹的 JSON（与 MiniMax 类似但包裹字符可能不同），`ZAIVisionProvider` 是否需要独立的 prompt？默认沿用现有 `VISION_PROMPT` 是否足够？
- [ ] 是否需要把 provider 列表做成可配置（YAML / 环境变量）？还是硬编码在代码中？
- [ ] 当 Z.AI MCP 暂时连不上但配额未耗尽时，是否要回退到 MiniMax（构成双向 fallback）？还是保持单向？

## 12. 待 SPEC 解决的问题（Out-of-RFC, to be solved in SPEC）

> 以下条目留给 SPEC 阶段定义，不在 RFC 中给出具体签名：

- `VisionProvider` 与 `ProviderResult` 的 Python 类型签名、异常层级。
- `VisionProviderRouter` 的具体调用序列（先主后备、并发策略、timeout 预算）。
- `_classify_failure(retryable, error_kind)` 的具体错误关键字集合与映射。
- `ZAIVisionProvider` 调用 Z.AI MCP 的具体 client 选型（Hermes MCP SDK vs stdio 子进程 vs HTTP）与 prompt 微调。
- `MiniMaxImageExtractor.extract` 内部到 Router 的委托方式，保持 `BaseExtractor.extract` 接口兼容的具体实现策略。
- 测试矩阵：单测 / 集成测 / 手工验证的具体 mock 方案。
- 调试日志格式与 `pic_*_vision_*.json` 的扩展字段。
- 是否新增 `VisionProviderRouter` 的状态计数器（用于观察 fallback 频率）以及持久化位置。

## 13. 参考资料（References）

- `skills/data/data-pipeline/SKILL.md`（Image Portfolio / Trade Pipeline 段）
- `skills/data/data-pipeline/scripts/extractors/minimax_image_extractor.py`（现有 OCR 实现）
- `skills/data/data-pipeline/scripts/extractors/base.py`（BaseExtractor 接口）
- `skills/data/data-pipeline/scripts/run_unified_image_pipeline.py`（pipeline 入口）
- `docs/rfc/03_data/RFC-03-004-smart-money-pipeline-review-gate.md`
- `docs/rfc/03_data/RFC-03-005-smart-money-batch-closeout.md`
- `docs/spec/SPEC-03-004-smart-money-pipeline-review-gate.md`
- `docs/design/DESIGN-03-004-smart-money-pipeline-review-gate.md`
- `~/.hermes/profiles/yquant/config.yaml`（MCP servers 配置）
- `~/.hermes/profiles/yquant/.env`（`Z_AI_API_KEY` 存放位置）

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-06-24 | 初始创建；定义 VisionProvider 抽象、Z.AI fallback、统一 schema 与触发判定；列出开放问题与待 SPEC 解决条目 | YQuant-Codex-Principal |