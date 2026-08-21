# T1 RFC/SPEC 独立放行审计清单

适用：涉及数据模型、持久化、外部 Provider、查询路径或生产授权的 Full Flow T1 完成后、创建 T2 Design 之前。

## 原则

`task=done`、worker handoff、文件存在、`git diff --check` 只证明交付和基础格式，不证明 RFC/SPEC 可安全派生 Design。T2 必须等待 orchestrator 的独立只读审计 PASS。

## 最小审计

1. **范围与阶段事实**：复核 name-status 与 diff-check；T1 仅含 allowlist 文档；计划/候选/待验证内容不得写成已实现、已注册、已通过或已激活。
2. **静态基线交叉核对**：被引用的接口、配置落点、registry API、TTL 语义、测试目录和已有能力名必须与代码一致；不可引用不存在 API、错误注册点或不可达配置键。
3. **契约自洽性**：摘要、schema、`from_dict`、验收和测试计划的字段数/字段名一致；代码式 dataclass/签名语法可用；唯一键覆盖市场、时间、标的/记录 scope，市场级与标的级记录不可共用含混主键。
4. **读写与治理边界**：标准 query 默认只读，cache miss/fallback fetch 不能隐式 Mongo/Cache 物化写入；物化仅发生在显式 refresh/ETLV ingest。记录级 provenance/quality 标记须与冻结的 QualitySummary 明确区分。
5. **外部与生产 Gate**：Provider 覆盖、许可证/token、频率、timeout、限速、字段映射均是待验证项，除非可追溯证据已存在。每个真实 API probe、DDL、DML/canary 须独立列明目标、最小样本/最大请求量、影响、停止与回滚条件；“临时集合/测试库”不自动豁免真实 Mongo 授权。
6. **分期一致性**：独立子阶段与 Gate 前置条件必须一致；并行计划态文档不可被描述为已完成前置。

## 决策

- 全部通过：创建 T2 Design，`parents=[T1]`。
- 任一阻断项失败：创建仅文档 allowlist 的 T1.x correction card，`parents=[T1]`；T2 不得创建或放行，修订后重新独立审计。
- 旧卡因 worker/transport 失败且无产物：保留为审计记录；创建自包含替代卡，不对旧卡 blind retry，也不把它作为有效 parent/output。
