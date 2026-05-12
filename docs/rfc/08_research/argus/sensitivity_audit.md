# Argus RFC 交付包 · 敏感扫描 audit (2026-05-05)

## 扫描范围

A 类 12 文件 (INDEX + 01-08 + APPENDIX A/B + v2.1.0 patch),源路径 `D:/Private Research OS/帝国往事/permanent/legacy/PROS_V9/staging/RFC-2026-071_ARGUS/`。

关键词组: `兄弟|路演|后台|私域|moat|内部消息|认识|私人|个人持仓|真实账户|本金|S-1\d{2}|DR-2026|IMM-|操作者`

## 命中分布

| 文件 | 命中数 | 严重等级 | 状态 |
|:--|:--|:--|:--|
| `INDEX.md` | 6 | 🟠 中 | 治理编号 + S 编号 + n<10 |
| `01_MOTIVATION.md` | 0 | ✅ 干净 | 第一轮已扫, 仅"友邦关系"架构隐喻 |
| `02_ARCHITECTURE.md` | 3 | 🔴 **最高** | **L49 兄弟公司后台导出 (字面 moat 披露)** |
| `03_SCHEMA.md` | 0 | ✅ 干净 | — |
| `04_SIGNAL_SCORING.md` | 0 | ✅ 干净 | — |
| `05_POOL_WEB.md` | 1 | 🟢 低 | "操作者信心" 中性 |
| `06_ADVANCED_ANALYSIS.md` | 0 | ✅ 干净 | — |
| `07_IMPACT_ALTERNATIVES.md` | 0 | ✅ 干净 | — |
| `08_MIGRATION_ACCEPTANCE.md` | 3 | 🟠 中 | 治理编号 + S 编号 |
| `APPENDIX/A_PARAMETERS.md` | 1 | 🟢 低 | "操作者可自行调整" 中性 |
| `APPENDIX/B_RISKS.md` | 10 | 🟢 低 | 全为"责任方=操作者", 中性 |
| `RFC-2026-071_v2.1.0_INCREMENTAL_PATCH.md` | 16 | 🔴 **最高** | **操作者私域路径 + 友军基金经理 + sm_mapping.yaml** |

总命中: **43 处** across 8 个文件。

---

## 🔴 红色条目 (HALT, 需 R11 决策)

### R-1 · 02_ARCHITECTURE.md L49 — 字面 moat 披露 ⚠️ 最严重

```
1. operator 收到聪明钱情报 (兄弟公司后台导出 / 路演记录 / 照片 / 截图)
2. 在 Claude Windows 桌面客户端打开 session
```

**问题**: "兄弟公司后台导出" 是 operator 真实信息源 moat 的**直接字面披露**。给数据上游供方 = 把核心商业秘密 (我从兄弟基金公司后台拿数据) 递到供方手里。
**风险等级**: 不可逆主权泄露
**建议处理**:
- (a) **删除整段** "兄弟公司后台导出 / 路演记录 / 照片 / 截图" 括号注释 → 保留 "operator 收到聪明钱情报"
- (b) **改写为通用化**: "operator 收到聪明钱情报 (来自多种渠道, 含定性记录与定量持仓数据)"
- (c) 放弃 02_ARCHITECTURE 整章, 不交付
- 推荐 (b), 既保留语义连贯也不暴露源

### R-2 · v2.1.0_PATCH L142 — 操作者私域路径披露 ⚠️ 严重

```
sm_mapping.yaml 路径: D:/Private Research OS/帝国往事/操作者私域/argus/sm_mapping.yaml
```

**问题**: 直接告诉对方"操作者私域"目录存在 + 真实名映射文件路径。即使对方拿不到文件,这违反 [feedback_three_realm_isolation.md] 物理隔离 — "私域" 概念本身不能外泄。
**建议处理**:
- (a) **改写为占位**: "sm_mapping.yaml 路径: <operator local only, never git-tracked>"
- (b) 整段 GR-2 SM00N 改写为通用: "真实名 → 化名映射文件,仅本地维护,永不进版本控制"
- 推荐 (b), GR-2 整段重写

### R-3 · v2.1.0_PATCH L20-26 — 友军基金经理数据流披露

```
友军基金经理 (D:/Private Research OS/帝国往事/inbox/友军基金经理数据/) 提供 16 产品 ×
3-sheet xlsx 持仓数据流, 操作者要求 Argus 接入并提供持仓变动可视化, 同时严守"真实管理人/产品名
不上 GitHub"红线.
```

**问题**: (a) 暴露另一个私域目录路径 `inbox/友军基金经理数据/`; (b) 数量精确 "16 产品 × 3-sheet" 是商业敏感; (c) 提到 "真实管理人/产品名" 暗示 operator 持有此数据。
**注意**: 给 RFC 的工程师本身就是 "友军数据上游" — 他可能就是这 16 产品里的一部分供方。让他知道 "operator 拿了 16 个供方数据" 反而暴露 operator 的供应链结构。
**建议处理**:
- (a) **改写**: 删路径, 数量改为模糊 (例 "若干友军提供方"), 删除 "16 产品 × 3-sheet" 精确规格
- (b) 删除 §1 Background 整段, 改写为不指明数据源的版本

---

## 🟠 黄色条目 (建议自动脱敏, 报操作者 confirm)

### Y-1 · 帝国治理编号 (DR / CL / S-XXX / IMM- / DR-WDC-XXX)

**位置**: 散见多文件
- INDEX.md frontmatter: `dr: "DR-2026-076"` `cl: "CL-2026-040"`; 正文 "S-107", "S-108"
- 02_ARCHITECTURE.md frontmatter 同
- 08_MIGRATION_ACCEPTANCE.md frontmatter 同 + 正文 "S-106/107 precedent"
- v2.1.0_PATCH: `DR-2026-104 / CL-2026-071`, `RFC-2026-067`, `DR-2026-103 (xalpha)`, `DR-WDC-011`, `S-107 RFC-063`

**问题**: 暴露帝国治理结构 (DC 委员会编号体系, WDC 私域委员会存在), 对方拿到也无法 verify, 但反向推断 "operator 有完整内部治理 + 私域 WDC" 即是策略外泄。
**建议处理**: 全部脱敏
- frontmatter `dr:` `cl:` 字段 → 删除或改 `dr: <internal>`
- 正文 "S-107/108", "DR-2026-XXX", "CL-2026-XXX", "IMM-XXX", "DR-WDC-XXX" → 全替换为 "<governance ref>" 或删除整句
- `RFC-2026-067` 关联 RFC 引用 → 删, 因为不交付那份 RFC

### Y-2 · v2.1.0_PATCH 多处 "操作者" 操作描述

**位置**: L7, 21, 25, 151, 228, 237-238, 247-248, 256-257
**问题**: 中性,但 "操作者经验论点 无 N≥3 实证" "Forum B 5 视角同质性 操作者亲自评" 等暴露 operator 是单人决策且依赖直觉。
**建议处理**: "操作者" → "用户" / "owner",或保留但 confirm operator 是否在意。

### Y-3 · INDEX.md "operator 数据量不够 n<10" + "凌晨 autoDC 单 session"

**位置**: INDEX L37-38, 41-42, 270; 08_MIGRATION L47
**问题**: 暴露用户是 single user + 用 autoDC 模式 (帝国内部术语)
**建议处理**:
- "operator 数据量不够 n<10" → "数据样本量较小 (n<10), 先验不稳定" (去 operator 字面)
- "凌晨 autoDC 单 session ~3-4h 闭环 (继承 S-106/107 precedent)" → 整句删除或改 "单次会话内闭环"

---

## 🟢 绿色条目 (中性, 保留)

- B_RISKS 表格 "责任方" 列 10 处 "操作者" — 标准 RFC 风险登记格式, 可保留 (或全替 "用户")
- A_PARAMETERS L33 "L1: 操作者可自行调整" — 标准参数审批级别
- 05_POOL_WEB L307 "INV-12 要求: 同时展示失败案例, 校准操作者信心" — UI 设计准则, 中性

---

## 处理路线建议

### 路线 A · Claude 自动脱敏 (Y-1/Y-2/Y-3) + R11 确认 R-1/R-2/R-3

1. Claude 直接产出脱敏副本到 `handoff_external/argus_rfc_2026-05-05/RFC-2026-071_ARGUS/` (不动源 staging/)
2. R-1/R-2/R-3 按本文档"建议处理"中的 (b) 选项改写,产出后给 operator R11 抽样
3. 黄色条目全自动按上面的规则替换
4. 提交 operator 抽审 02_ARCHITECTURE / v2.1.0_PATCH 两个高风险文件 (各 ~5 min)
5. 通过后继续 README + sha256 + ZIP

### 路线 B · 缩小交付范围 (避险)

放弃 v2.1.0_PATCH + 02_ARCHITECTURE 章 → 只给 INDEX + 01_MOTIVATION + 03_SCHEMA + 04-08 + APPENDIX (10 文件), 黄色条目仍脱敏。
代价: 对方拿不到最新 v2.1.0 友军 xlsx parser 设计 + 02 架构图。但 v2.1.0 PATCH 里的 sm_mapping.yaml + xlsx parser 部分恰好就是数据上游侧的内容,对方反而最敏感。

### 路线 C · 暂停, operator 亲自审 02_ARCH + v2.1.0_PATCH

不脱敏不删, operator 自己读这两份文档逐字判断哪些保留哪些改。最稳, 但耗 operator ~30 min。

---

## R11 决策点 (待操作者回复)

请逐项选择:

**Q1**: 02_ARCHITECTURE L49 "兄弟公司后台导出 / 路演记录 / 照片 / 截图" 如何处理?
- (a) 删除整段括号注释
- (b) 改写为通用化 "多种渠道, 含定性记录与定量持仓数据" (推荐)
- (c) 放弃整章不交付
- (d) 我自己改

**Q2**: v2.1.0_PATCH 整体如何处理? (含 sm_mapping.yaml 路径 + 友军基金经理 16 产品 + sm_mapping.yaml + DR-WDC-011)
- (a) Claude 按上述建议全部脱敏 → 副本交付
- (b) 放弃 v2.1.0_PATCH, 不交付 (对方只拿到 v2.0.1 主体, 不知道有 v2.1.0)
- (c) 我自己重写 v2.1.0_PATCH 的"对外版"

**Q3**: 黄色条目 (Y-1/Y-2/Y-3) 是否授权 Claude 自动脱敏?
- (a) 是,按本文档规则全自动 (推荐)
- (b) 我先看再决定

**Q4**: 整体路线选择
- 路线 A · 自动脱敏 + R11 高风险条目 (推荐)
- 路线 B · 缩小范围避险
- 路线 C · operator 亲自审

---

## Audit 元信息

- 扫描者: Claude (autoDC mode)
- 时间: 2026-05-05
- 关键词组: 16 项
- 范围: A 类 12 文件
- 总扫描行数: ~5,000 行 (估)
- 风险等级判定: P3 可审计性 + IL-05 世界状态诚实 + 三私域物理隔离规则
