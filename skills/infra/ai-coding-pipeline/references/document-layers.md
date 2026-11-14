# RFC/SPEC/DESIGN 文档分层

## 强制规则

完整流水线中，RFC/SPEC/Design **必须产出三个独立文件**，分别存放在 `docs/rfc/`、`docs/spec/`、`docs/design/` 对应模块子目录下。不允许将三层合并到一个 RFC 文件中。

### 阶段门禁校验

YQuant Orchestrator 在完成每个阶段后，必须校验产出物存在性：

| 阶段 | 校验项 | 不通过时行为 |
|---|---|---|
| RFC/SPEC 结束 | `docs/rfc/{模块}/RFC-XX-XXX-*.md` 已更新 **且** `docs/spec/{模块}/SPEC-XX-XXX-*.md` 已创建 | 退回，补齐后再进入 Design |
| Design 结束 | `docs/design/{模块}/DESIGN-XX-XXX-*.md` 已创建 | 退回，补齐后再进入 Implement |
| Implement 结束 | Full 引用 SPEC/Design；Light 引用已确认契约与验收 body | 退回，补齐本模式实际输入 |
| Validate 结束 | Reviewer 独立测试并审查实现与 SPEC/Design 一致 | 偏离则退回 Implement |

Full 保留 RFC/SPEC 与 Design 两个阶段及三份独立文件，不合并为 Plan。Light 用已确认契约与验收 body，可以不新建三层文件；分流依据是契约明确、范围受限、风险可控，而不是文件数。两者共用 [统一 Validate](../SKILL.md#unified-validate)，不以 Closeout 自审代替独立验收。Quick 入口已退役；仅后续新任务使用新规则，旧任务不自动迁移。

---

## `docs/rfc`

项目需求与架构约束层。

用于说明：
- 为什么要做
- 业务目标与非目标
- 模块边界
- 数据/接口方向
- 验收标准
- 交易、风控、生产或治理语义

现有 RFC 继续作为项目需求文档使用，不需要为了适配流水线而迁移。

涉及以下变化时，必须先更新 RFC 再进入实现：
- 数据模型或 Schema
- 模块边界
- 外部 API/接口
- 交易或风控行为
- 生产/部署行为
- 跨模块契约

## `docs/spec`

从 RFC 派生出的可执行工程规格层。

用于说明：
- 精确行为
- 输入与输出
- 错误与边界情况
- 兼容性与幂等性
- 验收标准映射
- 测试要求

Full 的 Developer 和 Validate 验收者以 SPEC 作为直接工作契约；Light 以已确认契约和验收 body 为准。必要测试专项仍按自己的任务契约执行。

## `docs/design`

从 SPEC 派生出的实现设计层。

用于说明：
- 涉及文件/模块
- 数据流/控制流
- 接口形态
- 迁移路径
- UI 状态（如适用）
- 测试策略
- 回滚与降级
- 实现者交接信息

不要在 DESIGN 中展开大段业务动机；业务背景应链接回 RFC/SPEC。
