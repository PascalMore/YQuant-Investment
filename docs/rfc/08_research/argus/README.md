# ARGUS RFC Package — Engineer Onboarding

**Document set**: RFC-2026-071 ARGUS (机构智慧资金行为追踪系统)
**Version**: v2.0.1
**Status**: APPROVED · 设计已批准, **实装尚未启动 (impl_status = NOT_STARTED)**
**Package date**: 2026-05-05
**Scope**: 设计文档 only — 不含代码 / 数据 / 内部治理上下文

---

## Quick Read Order (建议阅读顺序)

| # | File | 说明 | 估时 |
|:--|:--|:--|:--|
| 1 | `RFC-2026-071_ARGUS/INDEX.md` | 总控, 必读 | 10 min |
| 2 | `RFC-2026-071_ARGUS/01_MOTIVATION.md` | 系统动机 + 行业背景 | 15 min |
| 3 | `RFC-2026-071_ARGUS/02_ARCHITECTURE.md` | 独立子系统架构 (与 Empire 友邦关系) | 20 min |
| 4 | `RFC-2026-071_ARGUS/03_SCHEMA.md` | 13 表权威 DDL (Raw 4 + Processed 6 + Decision 2 + Fallback 1) | 25 min |
| 5 | `RFC-2026-071_ARGUS/04_SIGNAL_SCORING.md` | 贝叶斯信誉评分 + 多时间框架信号融合 | 20 min |
| 6 | `RFC-2026-071_ARGUS/05_POOL_WEB.md` | 4 区动态股票池 + Web 接口 | 15 min |
| 7 | `RFC-2026-071_ARGUS/06_ADVANCED_ANALYSIS.md` | 达尔文时刻 + 多产品共识 | 15 min |
| 8 | `RFC-2026-071_ARGUS/07_IMPACT_ALTERNATIVES.md` | 影响评估 + 替代方案 | 10 min |
| 9 | `RFC-2026-071_ARGUS/08_MIGRATION_ACCEPTANCE.md` | 迁移路径 + 验收标准 | 15 min |
| 10 | `RFC-2026-071_ARGUS/APPENDIX/A_PARAMETERS.md` | 参数注册表 | 速查 |
| 11 | `RFC-2026-071_ARGUS/APPENDIX/B_RISKS.md` | 风险登记 | 速查 |

合计 ~150 min 完整通读。

---

## 关键事实

- **ARGUS 是独立子系统**, 不嵌入 `empire_data.db`。两库通过文件系统 JSON 交换 (Claude Bridge)。
- **跟踪对象 = 基金产品** (`product_code`), 不是基金经理。
- **数据节奏**: 日度 T+1 全持仓 + 交易 + NAV。
- **技术栈**: Python 3.13+ / FastAPI / Jinja2 / HTMX / Pico CSS / SQLite 3.45 (WAL) / openpyxl / pytest。
- **当前状态**: 设计已批准, 代码本体尚未实装。**接手人主要任务 = 实装 v2.0.1 设计或对其升级**。

## 范围声明 (Scope Statement)

本包**只含 RFC 设计文档**。以下内容**不在本包**, 接手时另行向 owner 索取:

- ❌ 代码本体 (Python / SQL / FastAPI 实装)
- ❌ 历史数据 (`argus.db` / xlsx 导入样本)
- ❌ 真实管理人/产品名映射文件 (本地维护, 不版本控制)
- ❌ 内部治理审议记录 (DC 评审, 专家咨询纪要)
- ❌ Empire 主系统代码与配置

## 已知 Gap (与文档原始路径不符的事项)

1. **路径标注**: 文档内若出现 `D:/Private Research OS/PROS_V9/...` 类绝对路径, 这是 owner 本地旧路径, 现已归档。接手实装时请以接手目录为准, 与 owner 协商最终路径。
2. **v2.1.0 增量补丁**: v2.0.1 之后存在一份 v2.1.0 增量, 涉及 xlsx parser + 化名映射机制等接入细节。**本包暂不含 v2.1.0**, 由 owner 在接手讨论中另行评估是否提供。
3. **frontmatter 治理引用**: 各章 frontmatter 已脱敏内部审议编号, 不影响技术可读性。

## 联络人

- **Owner**: Empire Owner (本仓所有人)
- **接手目标**: 实装或重构 ARGUS v2.0.1, 双轨 fork 期 2 个月, 之后再议合并/重构
- **沟通**: 直接与 owner 对接, 本包不含 Claude session 上下文

## 完整性

- 文件清单见 `MANIFEST.sha256`
- 11 个 markdown 文件, 总字节数见 manifest

---

*This package was prepared 2026-05-05 by the Empire Owner's automated workflow with sensitivity scrubbing applied to internal references.*
