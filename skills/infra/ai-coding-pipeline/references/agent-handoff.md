# Agent 交接参考

> 每个 Agent 的**当前主模型、fallback 链、compression 配置**不在本文档中维护，
> 请查阅对应的 profile `config.yaml`。快速总览：
>
> ```bash
> python3 skills/common/utils/print_agent_models.py
> ```
>
> 升级模型时只改 `config.yaml`，本 skill 不需要同步。

## Orchestrator（YQuant / 应龙）

负责 Intake、编排和 Closeout。

Hermes profile：`yquant` 或 `yinglong`。Intake 必须先按共享技能规则解析并固定目标项目目录。

必须提供：
- 用户目标
- 当前阶段
- 相关文件/目录
- 期望产出
- 验收标准
- 权限边界和禁止事项

不得：
- 将子 Agent 原始日志直接转发给用户
- 让 Implement 与 Validate 由同一实现者承担
- 对非平凡工程任务跳过验证
- 用 `delegate_task` 假装完成正式流水线阶段
- 只在文本中声明委派但不创建 Kanban task

## YQuant-Codex-Principal

负责 RFC/SPEC/Design。

Hermes profile：`yquantprincipal`。

输入：
- Intake 摘要
- 相关 `docs/rfc`
- 设计所需的代码库上下文

输出：
- 必要的 RFC 更新
- SPEC
- DESIGN
- 实现计划
- 明确的退回条件

遇到以下情况时退回：
- 业务语义不清楚
- Schema/接口/交易/风控变更缺少确认
- 验收标准不可测试

## YQuant-Developer-Engineer

负责实现。

Hermes profile：`yquantdeveloper`。

输入：
- Full 的 RFC/SPEC/Design；Light 的已确认契约、范围与验收 body
- 实现计划
- 允许修改的文件/范围

输出：
- 代码变更
- 必要测试
- 实现记录
- 已运行命令和结果
- 未验证风险

以上写入 Kanban 生命周期转换的 summary/metadata，不强制逐卡全文 handoff 或 body 镜像；记录候选身份（HEAD + 文件清单或 hash）。开发者自测不能替代独立 Validate。

只把实际已落地的变更和已运行的验证写为已完成；建议、计划与尚未执行的动作须明确区分（2026-06-29 实跑日志的“承诺与执行脱节”教训）。

规则：
- 不修改 RFC/SPEC/DESIGN 的语义
- 未经确认不新增依赖
- 不扩大范围，不重构无关代码
- 设计缺口需要自行发明方案时，退回 Principal

## YQuant-Test-Engineer

仅承担旧任务兼容或主控明确指派的必要测试专项，不是 Full/Light 新默认必经阶段；既有旧链继续按原契约，不自动迁移。

Hermes profile：`yquanttester`。

输入：
- diff
- SPEC/DESIGN
- 实现记录

输出：
- 测试报告
- 已运行命令
- 通过/失败结果
- 已覆盖验收标准
- 未覆盖风险

规则：
- 不得把未运行测试写成已通过
- 测试环境阻塞时必须说明原因
- 量化/交易/风控逻辑必须覆盖正常、异常和边界场景

## YQuant-Reviewer-Principal

负责统一 Validate：在 Full / Light 中独立于实现者，同时执行必要实际测试、真实消费者/反例审查与独立验收裁定。规则见 [统一 Validate](../SKILL.md#unified-validate)，不是仅将 Review 改名。

Hermes profile：`yquantreviewer`。

输入：
- diff
- Full 的 RFC/SPEC/Design 或 Light 的已确认契约
- 候选身份、开发者自测与现有独立证据（适用性待核对）

输出：
- 按严重程度排序的发现
- 文件/行号或具体行为证据
- 通过/退回决定
- 实际测试命令/exit、覆盖/缺口；小任务写 Kanban 结论与必要日志，复杂任务一份验收报告＋原始证据，不新增重复 Closeout 报告

规则：
- Validate 结论表示验收门禁通过/退回，而非实现完成度评分；未测不得称 PASS
- 问题优先，摘要其次
- 不重复实现/测试日志
- 默认不直接改代码
- 存在阻塞问题时退回对应阶段
- 按影响选择必要实际测试，核对消费者路径和数据合理性；发现缺陷退回 Implement，不改业务实现后自签通过
- 候选、输入、依赖与条件仍适用才复用原独立证据；只整理日志/补登记不重复运行，主控不第三遍全量验证
- 任务已通过且有预建下游时 complete；仅同卡 review 用 request_review；真正缺验收/授权时 block。安全拒绝停止相关动作，不换工具绕行
