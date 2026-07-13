# RFC-09-006: DSA 大盘复盘标题归一化低冲突增强

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿 |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-13 |
| 最后更新 | 2026-07-13 |
| 所属模块 | reports / daily_stock_analysis（DSA） |
| 依赖 RFC | 无 |
| 替代 RFC | 无 |
| AI 适配 | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| 标签 | #报告 #低冲突 #归一化 |

## 1. 执行摘要（Executive Summary）

DSA 大盘复盘报告在多市场引入后，单市场 LLM 正文 Markdown 标题层级会漂移（出现 `# 日期标题` + `## 一/二/三章节`），导致 `_inject_data_into_review()` 的注入逻辑只匹配 `###` 时少表/错位。本 RFC 提出低冲突精简方案：在 `MarketAnalyzer._inject_data_into_review()` 入口附近新增一个标题归一化 helper，把 LLM 单市场输出统一到稳定的 `## 日期报告标题` + `### 正文章节` 两层结构，不碰 prompt 大段 f-string、不重构多市场 renderer、不改推送配置。

## 2. 背景与动机（Background & Motivation）

### 2.1 现状痛点

- 7/10 08:34 正确报告对应 DSA commit `154fe27d`。之后唯一 DSA 变更是 `5632f18e` 振幅计算修复，不涉及报告结构。
- 问题主因是 LLM 输出标题层级漂移：`# 日期标题 + ## 一/二/三章节`，导致旧插表逻辑（`_insert_after_section` 只找 `###`）在缺少 `###` 时少表或错位。
- 多市场引入后，`src/core/market_review.py` 在最外层新增了 market wrapper 层（`# 🎯 大盘复盘` / `# A股大盘复盘`），单市场 LLM 正文仍然独立产出；当 LLM 正文标题漂移时，`_CHINESE_SECTION_PATTERNS` / `_ENGLISH_SECTION_PATTERNS` 的正则匹配失效。

### 2.2 根因定位（基于实际代码）

当前 `_inject_data_into_review()`（`market_analyzer.py:914`）依赖以下 heading 正则：

```
_CHINESE_SECTION_PATTERNS = {
    "market_summary": r"###\s*一、(?:盘面总览|市场总结)",
    "index_commentary": r"###\s*二、(?:指数结构|指数点评|主要指数|风格分析)",
    "sector_highlights": r"###\s*三、(?:板块主线|热点解读|板块表现)",
    "funds_sentiment": r"###\s*四、(?:资金与情绪|资金动向)",
    "news_catalysts": r"###\s*五、(?:消息催化|后市展望)",
}
_ENGLISH_SECTION_PATTERNS = {
    "market_summary": r"###\s*(?:1\.\s*)?Market Summary",
    ...
}
```

这些正则强制要求 `###`（H3）。但 prompt 模板（`_build_review_prompt`，line 1443）里定义的输出模板是 `## {日期 大盘复盘}` + `### 一/二/三`。当 LLM 把日期标题提到 `#`、把章节降到 `##` 时，所有注入正则全部 miss。

### 2.3 业务价值

- 报告数据表注入成功率从"漂移即丢表"恢复到稳定。
- 不需要改 prompt 大段文本、不重构 `core/market_review.py` 的多市场渲染器，降低 upstream conflict。
- 为后续（非本 RFC）标题治理留出清晰的单点入口。

### 2.4 触发原因

风险驱动 + 需求驱动：Pascal 发现报告丢表，要求"低冲突精简方案"。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

- [ ] 单市场 LLM 正文标题层级漂移时，stats / indices / fundflow / sector 四类数据表仍能注入到正确章节。
- [ ] 日期报告标题统一成 `## {YYYY-MM-DD ... 大盘复盘/Market Recap}`（H2）。
- [ ] 中文正文主章节 `一、盘面总览` 到 `七、风险提示` 统一成 `### ...`（H3）。
- [ ] 英文正文主章节 `1. Market Summary` / `2. Index Commentary` / `3. Fund Flows` / `4. Sector Highlights` / `5. Outlook` / `6. Risk Alerts` / `7. Strategy Plan` 统一成 `### ...`（H3）。
- [ ] `#### 行业板块领涨 Top 5` 等数据表小节（H4）保持不动。
- [ ] 改动集中，优先只改 2 个文件。

### 3.2 非目标（Out of Scope）

- [ ] 不改 `_build_review_prompt()` 的大段 f-string（降低 upstream conflict）。
- [ ] 不重构 `src/core/market_review.py` 的多市场 wrapper / payload renderer。
- [ ] 不改推送渠道（企业微信/飞书/Telegram）、不改通知模板。
- [ ] 不改生产数据库、不改 MongoDB 集合、不改调度。
- [ ] 不改 DSA `.env`（Pascal 已确认 M3 配置保留）。
- [ ] 不做 LLM 标题治理的"根治"方案（如改 prompt 强约束 + few-shot），留作后续独立 RFC。
- [ ] 不处理 `core/market_review.py` 现有 orchestrator 临时修改，除非 Design 明确证明不加极小 guard 无法达成验收（若建议 guard，必须标为可选并说明冲突风险）。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

"先归一再注入"。在 `_inject_data_into_review()` 调用现有的 `_insert_after_section()` 之前，先对单市场 LLM 正文做一次 heading 归一化，把漂移的标题层级映射回 prompt 模板期望的 `## + ###` 结构。归一化是纯文本变换，幂等、无副作用、可独立测试。

### 4.2 架构总览

```
LLM 原始正文（可能漂移: # + ## 或 ## + ### 或混合）
        │
        ▼
_normalize_market_review_headings(text, language, date)   ← 新增 helper
        │  统一到: ## 日期标题 + ### 正文章节
        ▼
_inject_data_into_review(...)   ← 现有正则继续工作（无需改 patterns）
        │
        ▼
带数据表的完整报告
        │
        ▼
core/market_review.py 多市场 wrapper（不改）
```

### 4.3 模块分工

- **新增 helper（`market_analyzer.py`）**：`_normalize_market_review_headings()`，纯函数式，接收 review 文本 + 语言 + 日期，返回归一化后的文本。
- **调用点（`market_analyzer.py::_inject_data_into_review`）**：在构建 data blocks 之前调用一次归一化。
- **测试（`test_market_analyzer_generate_text.py`）**：新增 heading normalization 专项用例 + 确保现有注入测试仍通过。

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

- **触发条件**：`generate_market_review()` 成功拿到 LLM 正文后，调用 `_inject_data_into_review()`。
- **核心处理逻辑**：
  1. 进入 `_inject_data_into_review()`。
  2. （新增）调用 `_normalize_market_review_headings(review, language, date)`。
  3. 归一化后的文本进入现有 `_build_*_block()` + `_insert_after_section()` 流程。
  4. 返回带数据表的完整报告。
- **正常分支**：LLM 标题已正确 → 归一化为 no-op，原样返回。
- **异常降级分支**：归一化正则全部 miss（极端漂移）→ 原样返回原文，不抛异常，不阻断注入（现有 fallback 仍生效）。

### 5.2 数据模型（Data Model）

无新增数据模型。归一化 helper 只处理字符串 in / 字符串 out。

### 5.2bis 持久化策略（Persistence Strategy）

无持久化需求。归一化发生在内存中的报告文本上，不落盘、不写库。最终报告的持久化仍由 `core/market_review.py` 的 `save_report_file` / `persist_history` 负责，本 RFC 不改这两条路径。

### 5.3 接口契约（API Contract）

内部 helper，无对外 API。函数签名详见 SPEC-09-006 §4。

### 5.4 AI 模型设计

不涉及。

## 6. 风险与缓解（Risks & Mitigations）

| 风险 | 等级 | 缓解 |
|---|---|---|
| 归一化误伤已正确的标题（重复 `#` 或改坏 emoji） | 中 | helper 幂等；已有"正确标题"输入时应 no-op。测试必须覆盖"已正确"用例。 |
| 归一化正则与 `_CHINESE_SECTION_PATTERNS` 不一致，导致归一化后注入仍 miss | 中 | Design 必须保证归一化后的标题能被现有 patterns 命中（即统一到 `###`）。测试覆盖中文 + 英文。 |
| 改 `core/market_review.py` 导致与 orchestrator 临时修改冲突 | 中 | 本 RFC 默认不改 `market_review.py`。若 Design 认为需要极小 guard，必须标为可选。 |
| LLM 未来再次漂移到全新标题形式 | 低 | helper 设计为"尽力而为 + no-op fallback"，不会因 miss 而崩溃。 |

## 7. 建议与决策（Recommendations）

1. **默认不改 `core/market_review.py`**：当前 orchestrator 临时修改（空 wrapper segment fallback）与本 RFC 正交。归一化在 `_inject_data_into_review` 入口完成后，`market_review.py` 的渲染层拿到的已经是归一化文本，不需要额外 guard。Design 应说明"建议保留 orchestrator 临时修改"或"建议撤回"，但本 RFC 倾向保留（低风险）。
2. **不改 prompt 大段文本**：降低 upstream conflict 是 Pascal 明确要求。归一化是 post-hoc 修补，不碰 prompt。
3. **helper 放在 module 级或 staticmethod**：便于独立单测，不依赖实例状态。

## 8. 开放问题（Open Questions）

- [ ] 归一化是否需要处理韩文（`ko`）？当前 `_get_review_language()` 对 ko 返回 `"en"`（复用英文脚手架），所以 helper 只需处理 zh / en 两个分支。
- [ ] 是否在归一化时顺便去掉 LLM 可能多输出的顶层 `#` emoji 标题（如 `# 🎯 大盘复盘`）？倾向不动——那是 `market_review.py` wrapper 层的职责，归一化只管单市场正文。

## 9. 下一步（Next Steps）

- SPEC-09-006：定义 helper 行为契约和验收标准。
- DESIGN-09-006：定义改动位置、伪代码、测试计划、回滚方案。
