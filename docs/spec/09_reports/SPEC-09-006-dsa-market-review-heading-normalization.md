# SPEC-09-006: DSA 大盘复盘标题归一化低冲突增强

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-13 |
| 最后更新 | 2026-07-13 |
| 来源 RFC | RFC-09-006 |
| 目标模块 | reports / daily_stock_analysis |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

## 1. 需求摘要

本 SPEC 定义一个标题归一化 helper 的行为契约。该 helper 在 `MarketAnalyzer._inject_data_into_review()` 入口处被调用，把 LLM 单市场正文里漂移的 Markdown 标题层级（如 `# 日期 + ## 章节`）统一映射回 prompt 模板期望的 `## 日期标题 + ### 正文章节` 两层结构，使现有的 `_CHINESE_SECTION_PATTERNS` / `_ENGLISH_SECTION_PATTERNS` 正则能稳定命中，从而保证 stats / indices / fundflow / sector 四类数据表注入到正确章节。归一化是纯文本变换，幂等、无副作用、fail-safe。

## 2. 范围

### 2.1 In Scope

- [ ] 新增 module 级或 staticmethod 函数 `_normalize_market_review_headings()`。
- [ ] 在 `_inject_data_into_review()` 入口调用该函数。
- [ ] 中文正文主章节归一化：`一/二/三/四/五/六/七` 系列。
- [ ] 英文正文主章节归一化：`1. Market Summary` 到 `7. Strategy Plan` 系列。
- [ ] 日期报告标题归一化：统一成 `## {YYYY-MM-DD ...}`（H2）。
- [ ] 数据表小节（`#### 行业板块领涨 Top 5` 等 H4）保持不动。
- [ ] 新增专项测试用例。

### 2.2 Out of Scope

- [ ] 不改 `_build_review_prompt()` 的大段 f-string。
- [ ] 不改 `_CHINESE_SECTION_PATTERNS` / `_ENGLISH_SECTION_PATTERNS` 正则本身（归一化后的文本应能命中现有正则）。
- [ ] 不改 `src/core/market_review.py`（除非 Design 明确证明需要可选 guard）。
- [ ] 不改推送、数据库、调度、`.env`。
- [ ] 不做韩文专属归一化（ko 复用 en 脚手架，`_get_review_language()` 返回 `"en"`）。
- [ ] 不改 `_split_report_sections()`（该方法匹配 `#{2,3}`，归一化后自然兼容）。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 中文日期标题归一化 | 含 `# 2026-03-05 大盘复盘` 或 `### 2026-03-05 大盘复盘` 的正文 | 该行变成 `## 2026-03-05 大盘复盘` | 若已是 `##` 则 no-op |
| F-002 | 中文正文章节归一化 | 含 `## 一、盘面总览` 或 `# 一、盘面总览` 的正文 | 这些行变成 `### 一、盘面总览` | `####`（H4）不动；非标准中文标题（如"今日主线观察"）不强制改层级 |
| F-003 | 英文日期标题归一化 | 含 `# 2026-03-05 A-share Market Recap` 或其他层级的正文 | 该行变成 `## 2026-03-05 ... Market Recap` | 若已是 `##` 则 no-op |
| F-004 | 英文正文章节归一化 | 含 `## 1. Market Summary` 或 `# 1. Market Summary` 的正文 | 这些行变成 `### 1. Market Summary` | `####` 不动；英文序号范围 1-7 |
| F-005 | 幂等性 | 已归一化的文本再次输入 | 原样返回 | 不重复降级 |
| F-006 | fail-safe | 完全无法识别的标题（极端漂移） | 原样返回原文 | 不抛异常 |
| F-007 | 集成调用 | `_inject_data_into_review(review, overview, news)` 被调用 | 归一化先于注入执行 | 归一化失败不阻断注入（归一化是 no-throw） |

### 3.1 中文章节归一化清单（完整）

归一化目标（统一到 `###`）：

```
### 一、盘面总览
### 二、风格分析          # 兼容: 指数结构 / 指数点评 / 主要指数
### 三、板块主线          # 兼容: 热点解读 / 板块表现
### 四、资金与情绪        # 兼容: 资金动向
### 五、消息催化          # 兼容: 后市展望
### 六、明日交易计划
### 七、风险提示
```

> 说明：helper 不需要把"指数结构"改写成"风格分析"，只需把层级统一到 `###`。章节标题文本保持 LLM 原样（现有 patterns 已兼容这些变体）。

### 3.2 英文章节归一化清单（完整）

归一化目标（统一到 `###`）：

```
### 1. Market Summary
### 2. Index Commentary    # 兼容: Major Indices
### 3. Fund Flows
### 4. Sector Highlights   # 兼容: Sector/Theme Highlights
### 5. Outlook
### 6. Risk Alerts
### 7. Strategy Plan
```

## 4. 数据与接口契约

### 4.1 函数签名

```python
@staticmethod
def _normalize_market_review_headings(
    review: str,
    *,
    language: str,        # "zh" | "en"（已由 _get_review_language() 解析，ko 归 en）
    date: str,            # overview.date，格式 YYYY-MM-DD
) -> str:
    """Normalize drifted Markdown heading levels in a single-market LLM review.

    Maps drifted H1/H2/H4 main-section headings back to the prompt template's
    expected H2 (report title) + H3 (body sections) structure so that
    _inject_data_into_review()'s ###-based regex patterns can match reliably.

    Idempotent and fail-safe: returns the original text on no-match.
    """
```

### 4.2 调用点契约

在 `MarketAnalyzer._inject_data_into_review()`（`market_analyzer.py:914`）中，在构建 data blocks **之前**插入：

```python
def _inject_data_into_review(self, review, overview, news=None):
    review = self._normalize_market_review_headings(
        review,
        language=self._get_review_language(),
        date=overview.date,
    )
    # ... 现有 stats_block / indices_block / ... 逻辑不变
```

### 4.3 兼容性约束

- helper 必须能处理 LLM 可能输出的 emoji 前缀（如 `# 🎯 大盘复盘`、`## 🎯 一、盘面总览`）。归一化时保留 emoji，只改 `#` 数量。
- helper 必须保留日期标题中的市场名变体（如 `## 2026-03-05 A-share Market Recap`、`## 2026-03-05 美股大盘复盘`、`## 2026-03-05 日股大盘复盘`）。
- helper 不得改变非标题行（正文、表格、列表）。
- helper 不得删除或合并空行。

### 4.4 幂等性/审计要求

- 幂等：对已归一化文本再次调用，输出等于输入。
- 无审计需求（内存变换，不落盘）。

## 4.bis 持久化契约

无持久化需求。归一化发生在 `_inject_data_into_review()` 的内存调用栈中，不触发任何 DB / 文件写入。最终报告持久化由 `core/market_review.py` 负责，本 SPEC 不改持久化路径。

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | 中文漂移输入（`# 日期` + `## 一/二/三`）归一化后，所有主章节变成 `###`，日期变成 `##` | 单测断言行前缀 |
| A-002 | 英文漂移输入（`# 日期` + `## 1./2./3.`）归一化后，所有主章节变成 `###`，日期变成 `##` | 单测断言行前缀 |
| A-003 | 已正确的输入（`## 日期` + `### 章节`）归一化后 no-op（输出 == 输入） | 单测断言相等 |
| A-004 | `#### 行业板块领涨 Top 5`（H4 数据表小节）归一化后保持 `####` | 单测断言未被改成 `###` |
| A-005 | 极端漂移（完全无法识别的标题）归一化后原样返回，不抛异常 | 单测断言相等 + 无异常 |
| A-006 | 归一化后的中文文本进入 `_inject_data_into_review()`，stats/indices/fundflow/sector 四表全部注入成功 | 集成测试断言表标记存在 |
| A-007 | 归一化后的英文文本进入 `_inject_data_into_review()`，四表全部注入成功 | 集成测试断言表标记存在 |
| A-008 | 现有测试 `test_inject_data_into_review_matches_reference_style_chinese_headings` 和 `test_inject_data_into_review_matches_english_headings` 仍通过 | 回归测试 |
| A-009 | `test_inject_data_into_review_appends_sector_block_when_heading_drifts` 仍通过 | 回归测试 |
| A-010 | helper 幂等：对归一化输出再次调用，输出等于首次输出 | 单测断言相等 |
| A-011 | emoji 前缀标题归一化后 emoji 保留，只改 `#` 数量 | 单测断言 |

## 6. 测试要求

### 6.1 单元测试（新增，放在 `test_market_analyzer_generate_text.py`）

- `test_normalize_headings_chinese_h1_h2_drift_to_h2_h3`：输入 `# 日期` + `## 一、盘面总览`，断言输出为 `## 日期` + `### 一、盘面总览`。
- `test_normalize_headings_english_h1_h2_drift_to_h2_h3`：输入 `# 日期 Market Recap` + `## 1. Market Summary`，断言输出为 `## ...` + `### 1. Market Summary`。
- `test_normalize_headings_already_correct_is_noop`：输入已是 `## + ###`，断言输出 == 输入。
- `test_normalize_headings_preserves_h4_subsections`：输入含 `#### 行业板块领涨 Top 5`，断言 H4 不变。
- `test_normalize_headings_unrecognized_returns_original`：输入完全无法识别的标题，断言输出 == 输入，无异常。
- `test_normalize_headings_idempotent`：对归一化输出再调一次，断言相等。
- `test_normalize_headings_preserves_emoji_prefix`：输入 `## 🎯 一、盘面总览`，断言输出 `### 🎯 一、盘面总览`。

### 6.2 集成测试（新增或扩展）

- `test_inject_data_into_review_with_drifted_chinese_headings`：构造漂移输入，走完整 `_inject_data_into_review()`，断言四表存在。
- `test_inject_data_into_review_with_drifted_english_headings`：同上英文版。

### 6.3 回归测试

- 现有 3 个 inject 测试（见 A-008 / A-009）必须全部通过。

### 6.4 不可自动化验证项

- 无。本 SPEC 全部行为可单测覆盖。

## 7. 实现约束

### 7.1 禁止事项

- 禁止改 `_build_review_prompt()` 的 f-string。
- 禁止改 `_CHINESE_SECTION_PATTERNS` / `_ENGLISH_SECTION_PATTERNS`。
- 禁止改 `src/core/market_review.py`（除非 Design 明确证明需要可选 guard 并标注冲突风险）。
- 禁止改推送、数据库、调度、`.env`。
- 禁止在 helper 里做 LLM 调用、网络请求、文件 IO。
- 禁止 helper 抛异常（必须 fail-safe 返回原文）。

### 7.2 依赖限制

- helper 只允许用 Python 标准库 `re`。不引入新依赖。

### 7.3 性能/安全/风控约束

- helper 必须是 O(n) 文本扫描，n = review 字符数（典型 < 20KB）。
- 无安全/风控约束（纯文本变换）。

## 8. 实现约束补充

### 8.1 允许修改的文件（T2 Implement）

1. `skills/research/daily_stock_analysis/src/market_analyzer.py`
2. `skills/research/daily_stock_analysis/tests/test_market_analyzer_generate_text.py`

### 8.2 测试命令

```bash
cd /home/pascal/workspace/yquant-investment/skills/research/daily_stock_analysis
python -m pytest tests/test_market_analyzer_generate_text.py -v
python -m py_compile src/market_analyzer.py
```

### 8.3 完成状态选择（T2 Implement worker 必读）

- 验收标准全 PASS → `kanban_complete(status="done", summary=..., metadata={...})`。
- 任何验收 FAIL → `kanban_complete(status="blocked", reason="<哪条 FAIL + 期望 vs 实际>")`。
- 不要因"残余风险待确认"使用 blocked——残余风险属于 done 的 summary/metadata。

## 9. 开放问题

- [ ] 若 LLM 输出的日期标题带额外修饰（如 `# 🎯 2026-03-05 A股大盘复盘`），helper 是否需要保留 emoji？答：是，保留 emoji，只改 `#` 数量。已在 A-011 覆盖。
