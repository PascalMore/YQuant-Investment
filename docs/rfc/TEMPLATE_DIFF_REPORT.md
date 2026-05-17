# RFC 模板差异报告

## 1. 检查范围
本报告检查 docs/rfc/ 下 00~10 各模块的 RFC-00-000-rfc-template.md，与 RFC-00-001 第 11 章定义的全局 RFC 机制进行一致性对比。

检查对象：
- docs/rfc/00_project_overview/RFC-00-000-rfc-template.md
- docs/rfc/01_app/RFC-00-000-rfc-template.md
- docs/rfc/02_common/RFC-00-000-rfc-template.md
- docs/rfc/03_data/RFC-00-000-rfc-template.md
- docs/rfc/04_knowledge/RFC-00-000-rfc-template.md
- docs/rfc/05_portfolio/RFC-00-000-rfc-template.md
- docs/rfc/06_strategy/RFC-00-000-rfc-template.md
- docs/rfc/07_trading/RFC-00-000-rfc-template.md
- docs/rfc/08_research/RFC-00-000-rfc-template.md
- docs/rfc/09_reports/RFC-00-000-rfc-template.md
- docs/rfc/10_infra/RFC-00-000-rfc-template.md

## 2. 结论
11 个模块模板内容完全一致，模块之间不存在模板差异。

但模板本身与新的全局 RFC 机制存在治理字段和流程约束不一致，需要统一修订。建议后续用一次独立 PR 批量更新所有模块模板，避免本文档变更扩大到模板迁移。

## 3. 与全局 RFC 机制的差异
| 检查项 | 当前模板 | 新全局机制要求 | 修正建议 |
|---|---|---|---|
| 文件命名 | RFC-{XX}-{XXX}: {标题}，并暗示 RFC-xx-xxx | RFC-{YY}-{NNN}-{模块名}-{简述}.md | 标题与文件名示例统一改为 RFC-{YY}-{NNN}-{module}-{short-title}.md |
| 状态枚举 | 草稿/评审中/已采纳/已废弃 | Draft/Review/Accepted/Implemented/Rejected/Withdrawn/Superseded/Obsolete | 元数据状态字段补齐完整生命周期，可保留中文说明但需映射英文标签 |
| 目录规则 | 未声明模块目录表达式 | docs/rfc/{模块编号}_{模块名}/RFC-{YY}-{NNN}-{模块名}-{简述}.md | 在模板元数据后新增“目录与编号”说明 |
| PR-based 流程 | 未体现 issue -> PR draft -> review -> merge -> implemented | 明确 GitHub PR-based RFC 流程 | 在“落地计划”或新增“RFC 流程”章节中补充流程与状态更新要求 |
| 审核机制 | 未声明审核人与评论期 | 按影响范围分层审核，关键 RFC 至少 1~3 个自然日评论期 | 新增“评审要求”小节，区分单模块、跨模块、交易/风控/Schema、全局架构 |
| 变更管理 | 只有“替代RFC”字段 | Superseded/Obsolete 需显式标注替代关系 | 元数据增加 Superseded by / Supersedes / Related PRs 字段 |
| AI 实装关联 | 有 AI 实装规范，但未强制 RFC 关联 | 所有代码实装必须关联 RFC，无 RFC 不许实装 | 在 AI 实装规范中增加 Implements/Refs RFC 要求、验收结果回填要求 |
| 实现状态 | 无实现状态字段 | Accepted 后需要跟踪 Implemented | 元数据增加 Implementation Status、Implementation PR、Verification 字段 |

## 4. 建议模板修订方向
1. 将状态字段改为：Draft / Review / Accepted / Implemented / Rejected / Withdrawn / Superseded / Obsolete。
2. 将文件名与标题占位符改为：RFC-{YY}-{NNN}-{module}-{short-title}.md。
3. 元数据建议增加：Supersedes、Superseded by、Reviewers、Review Period、Implementation PR、Verification。
4. 在模板中补充“RFC 流程与评审要求”章节，明确 issue、Draft PR、评论期、评审、合并、实现、验收回填。
5. 在“AI实装规范”中加入强制项：所有 AI 代码任务必须引用 RFC 编号，代码 PR 必须写明 Implements RFC-xxxx 或 Refs RFC-xxxx。
6. ARGUS 现有设计包位于 docs/rfc/08_research/argus/RFC-2026-071_ARGUS/，命名与结构来自历史包，建议后续以迁移 RFC 或索引映射方式纳入统一编号，不建议直接重命名历史包。

## 5. 是否已修改模板
本次未修改各模块 RFC-00-000-rfc-template.md。原因是任务目标要求“审查并提出修正建议”，且模板批量迁移会影响全部模块的后续写作入口，建议单独作为一次模板治理 PR 执行。
