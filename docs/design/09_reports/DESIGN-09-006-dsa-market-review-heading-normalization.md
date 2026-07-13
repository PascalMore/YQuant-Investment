# DESIGN-09-006: DSA 大盘复盘标题归一化低冲突增强

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-13 |
| 最后更新 | 2026-07-13 |
| 来源 RFC | RFC-09-006 |
| 来源 SPEC | SPEC-09-006 |
| 目标模块 | reports / daily_stock_analysis |

## 1. 设计摘要

本设计在 `MarketAnalyzer._inject_data_into_review()` 入口前插入一个幂等、fail-safe 的标题归一化步骤 `_normalize_market_review_headings()`，把 LLM 单市场正文里漂移的标题层级（`#/##` 混用）映射回 prompt 模板期望的 `## 日期标题 + ### 正文章节`。归一化完成后，现有 `_CHINESE_SECTION_PATTERNS` / `_ENGLISH_SECTION_PATTERNS` 正则无需修改即可稳定命中，stats / indices / fundflow / sector 四类数据表注入恢复正常。

核心取舍：

- **不改 prompt 大段 f-string**（降低 upstream conflict，符合 Pascal 要求）。
- **不改 `_CHINESE_SECTION_PATTERNS` / `_ENGLISH_SECTION_PATTERNS`**（归一化后的文本天然命中现有正则）。
- **不改 `core/market_review.py`**（orchestrator 临时修改与本设计正交；建议保留，理由见 §6）。
- **helper 放为 `@staticmethod`**（纯函数，不依赖实例状态，便于独立单测）。

## 2. 现状分析

### 2.1 相关目录

- `skills/research/daily_stock_analysis/src/`
- `skills/research/daily_stock_analysis/tests/`

### 2.2 相关文件

| 文件 | 行号 | 现状 |
|---|---|---|
| `src/market_analyzer.py` | 41-54 | `_ENGLISH_SECTION_PATTERNS` + `_CHINESE_SECTION_PATTERNS`，正则强制 `###` |
| `src/market_analyzer.py` | 914-968 | `_inject_data_into_review()`，调用 `_insert_after_section()` 注入四类数据表 |
| `src/market_analyzer.py` | 970-987 | `_insert_after_section()`，用 `re.search(heading_pattern)` 找标题，找 `\\n###\\s` 找下一节 |
| `src/market_analyzer.py` | 1443-1690 | `_build_review_prompt()`，定义 `## {日期 大盘复盘}` + `### 一/二/三` 输出模板（**不改**） |
| `src/market_analyzer.py` | 220-230 | `_get_review_title()`，返回 `## {date} {market_name}` 或 `## {date} 大盘复盘` |
| `src/core/market_review.py` | 111-144 | `_get_market_review_text()`，定义 wrapper 层 `# 🎯 大盘复盘` / `# A股大盘复盘`（**不改**） |
| `tests/test_market_analyzer_generate_text.py` | 2753-2895 | 现有 3 个 inject 测试（**不改，需回归通过**） |

### 2.3 现有约束

- `_get_review_language()` 对 `ko` 返回 `"en"`（复用英文脚手架），所以归一化只需处理 `zh` / `en`。
- `_insert_after_section()` 内部找下一节用的是 `r'\n###\s'`，所以归一化必须保证正文章节是 `###`。
- `_split_report_sections()`（line 866）匹配 `r'^(#{2,3})\s+(.+?)\s*$'`，归一化后 `## + ###` 天然兼容。

### 2.4 兼容性风险

- 低。归一化是 post-hoc 文本变换，不改任何对外接口、不改 prompt、不改持久化。

## 3. 方案设计

### 3.1 模块/文件改动

| 文件 | 改动 | 原因 |
|---|---|---|
| `src/market_analyzer.py` | 新增 `_normalize_market_review_headings()` staticmethod（约 60-80 行）；在 `_inject_data_into_review()` 入口加 1 行调用 | 归一化漂移标题，使现有注入正则稳定命中 |
| `tests/test_market_analyzer_generate_text.py` | 新增 7 个 helper 单测 + 2 个漂移集成测试（约 150-200 行） | 覆盖 SPEC A-001 到 A-011 |

改动总量：约 2 个文件，新增 ~230 行，不删除现有代码。

### 3.2 数据流/控制流

```text
generate_market_review()
  │
  ├─ review = analyzer.generate_text(prompt)        # LLM 原始输出（可能漂移）
  │
  ▼
_inject_data_into_review(review, overview, news)
  │
  ├─ review = _normalize_market_review_headings(    # 【新增】归一化
  │     review, language=_get_review_language(),
  │     date=overview.date,
  │  )
  │
  ├─ stats_block   = _build_stats_block(overview)
  ├─ indices_block = _build_indices_block(overview)
  ├─ fundflow_block= _build_fundflow_block(overview)
  ├─ sector_block  = _build_sector_block(overview)
  │
  ├─ _insert_after_section(review, patterns["market_summary"],    stats_block)
  ├─ _insert_after_section(review, patterns["index_commentary"],  indices_block)
  ├─ _insert_after_section(review, patterns["funds_sentiment"],   fundflow_block)
  ├─ _insert_after_section(review, patterns["sector_highlights"], sector_block)
  │
  ▼
归一化 + 注入后的完整报告
  │
  ▼
core/market_review.py 多市场 wrapper（不改）
```

### 3.3 接口与数据结构

#### 3.3.1 新增：`_normalize_market_review_headings`（伪代码）

```python
import re

# 中文主章节标题匹配（序号 + 标题文本，兼容变体）
_ZH_SECTION_RE = re.compile(
    r'^(#{1,4})\s*([🎯📈📉💰🔥⚡🚀🌟💡⚠️✅❌]?)\s*'
    r'([一二三四五六七])、(.+)$'
)

# 英文主章节标题匹配（数字序号 + 标题文本）
_EN_SECTION_RE = re.compile(
    r'^(#{1,4})\s*([🎯📈📉💰🔥⚡🚀🌟💡⚠️✅❌]?)\s*'
    r'(\d)\.\s*(.+)$'
)

# 日期报告标题匹配（YYYY-MM-DD + 可选市场名 + 大盘复盘/Market Recap）
_ZH_TITLE_RE = re.compile(
    r'^(#{1,4})\s*([🎯📈📉🔥🌟]*)\s*'
    r'(\d{4}-\d{2}-\d{2})\s+(.+大盘复盘)$'
)
_EN_TITLE_RE = re.compile(
    r'^(#{1,4})\s*([🎯📈📉🔥🌟]*)\s*'
    r'(\d{4}-\d{2}-\d{2})\s+(.+Market Recap)$'
)


@staticmethod
def _normalize_market_review_headings(review: str, *, language: str, date: str) -> str:
    """Normalize drifted Markdown heading levels. Idempotent. Fail-safe."""
    if not review or not review.strip():
        return review
    try:
        lines = review.split('\n')
        normalized = []
        for line in lines:
            stripped = line.strip()
            new_line = line

            if language == "zh":
                # 1. 尝试匹配日期报告标题 -> 统一成 ##
                m = _ZH_TITLE_RE.match(stripped)
                if m:
                    emoji = m.group(2) or ""
                    date_part = m.group(3)
                    title_part = m.group(4)
                    new_line = f"## {emoji}{date_part} {title_part}".strip()
                else:
                    # 2. 尝试匹配中文正文章节 -> 统一成 ###
                    m = _ZH_SECTION_RE.match(stripped)
                    if m:
                        emoji = m.group(2) or ""
                        numeral = m.group(3)
                        title = m.group(4)
                        new_line = f"### {emoji}{numeral}、{title}".strip()
            else:  # en (含 ko)
                m = _EN_TITLE_RE.match(stripped)
                if m:
                    emoji = m.group(2) or ""
                    date_part = m.group(3)
                    title_part = m.group(4)
                    new_line = f"## {emoji}{date_part} {title_part}".strip()
                else:
                    m = _EN_SECTION_RE.match(stripped)
                    if m:
                        emoji = m.group(2) or ""
                        numeral = m.group(3)
                        title = m.group(4)
                        new_line = f"### {emoji}{numeral}. {title}".strip()

            normalized.append(new_line)
        return '\n'.join(normalized)
    except Exception:
        # fail-safe: 任何意外都返回原文，不阻断注入流程
        return review
```

> 注意：上面 emoji 字符类是示意。实际实现时，emoji 匹配应设计成"可选的非空白非字母非数字非#前缀"或直接用 `(\S*)` 捕获可选 emoji 段，避免硬编码 emoji 列表导致漏匹配。推荐写法见 §3.3.2。

#### 3.3.2 更稳健的 emoji 处理（推荐实现）

不硬编码 emoji，而是捕获 `#` 后面的可选非字母数字前缀：

```python
# 匹配: 1-4 个 # + 可选 emoji/符号前缀 + 中文序号 + 、 + 标题
_ZH_SECTION_RE = re.compile(
    r'^(#{1,4})\s+([^\w\u4e00-\u9fff]*)\s*([一二三四五六七])、\s*(.+)$'
)
# 匹配: 1-4 个 # + 可选 emoji/符号前缀 + 数字序号 + . + 标题
_EN_SECTION_RE = re.compile(
    r'^(#{1,4})\s+([^\w]*)\s*(\d)\.\s*(.+)$'
)
# 日期标题
_ZH_TITLE_RE = re.compile(
    r'^(#{1,4})\s+([^\d]*)\s*(\d{4}-\d{2}-\d{2})\s+(.+大盘复盘)$'
)
_EN_TITLE_RE = re.compile(
    r'^(#{1,4})\s+([^\d]*)\s*(\d{4}-\d{2}-\d{2})\s+(.+Market Recap)$'
)
```

归一化逻辑：

```python
new_line = f"## {emoji_or_empty}{date_part} {title_part}"
# 或
new_line = f"### {emoji_or_empty}{numeral}、{title_part}"
```

其中 `emoji_or_empty` 是捕获到的 emoji 前缀（可能为空字符串）。

#### 3.3.3 调用点改动（`_inject_data_into_review`）

```python
def _inject_data_into_review(
    self,
    review: str,
    overview: MarketOverview,
    news: Optional[List] = None,
) -> str:
    """Inject structured data tables into the corresponding LLM prose sections."""
    # 【新增】归一化漂移标题，使后续 ### 正则稳定命中
    review = self._normalize_market_review_headings(
        review,
        language=self._get_review_language(),
        date=overview.date,
    )

    # Build data blocks（以下完全不变）
    stats_block = self._build_stats_block(overview)
    ...
```

### 3.4 持久化设计（Persistence Design）

无持久化需求。归一化发生在 `_inject_data_into_review()` 的内存调用栈中。

### 3.5 UI/原型设计

无 UI 改动。

## 4. 实现计划

- [ ] Step 1：在 `market_analyzer.py` 模块级（靠近 `_CHINESE_SECTION_PATTERNS` 定义处，约 line 54 之后）新增 4 个编译正则常量。
- [ ] Step 2：在 `MarketAnalyzer` 类内新增 `_normalize_market_review_headings()` staticmethod（建议放在 `_inject_data_into_review()` 之前，约 line 910 附近）。
- [ ] Step 3：在 `_inject_data_into_review()` 入口（line 920 docstring 之后、line 922 `stats_block` 之前）插入归一化调用（1 行）。
- [ ] Step 4：在 `test_market_analyzer_generate_text.py` 新增 7 个 helper 单测 + 2 个漂移集成测试。
- [ ] Step 5：运行全部测试，确认回归通过。

## 5. 测试策略

### 5.1 单元测试（helper 专项）

| 测试名 | 输入要点 | 断言要点 | 对应验收 |
|---|---|---|---|
| `test_normalize_headings_chinese_h1_h2_drift_to_h2_h3` | `# 2026-03-05 大盘复盘` + `## 一、盘面总览` | 日期→`##`，章节→`###` | A-001 |
| `test_normalize_headings_english_h1_h2_drift_to_h2_h3` | `# 2026-03-05 A-share Market Recap` + `## 1. Market Summary` | 日期→`##`，章节→`###` | A-002 |
| `test_normalize_headings_already_correct_is_noop` | 已是 `## + ###` | 输出 == 输入 | A-003 |
| `test_normalize_headings_preserves_h4_subsections` | 含 `#### 行业板块领涨 Top 5` | H4 不变 | A-004 |
| `test_normalize_headings_unrecognized_returns_original` | `### 今日主线观察`（无中文序号） | 输出 == 输入，无异常 | A-005 |
| `test_normalize_headings_idempotent` | 对输出再调一次 | 二次输出 == 一次输出 | A-010 |
| `test_normalize_headings_preserves_emoji_prefix` | `## 🎯 一、盘面总览` | 输出 `### 🎯 一、盘面总览` | A-011 |

### 5.2 集成测试（漂移场景端到端）

| 测试名 | 输入要点 | 断言要点 | 对应验收 |
|---|---|---|---|
| `test_inject_data_into_review_with_drifted_chinese_headings` | 漂移输入 `# 日期` + `## 一/二/三` + 完整 overview | 四表标记全存在（盘面信号 / 指数表 / 行业板块领涨 Top 5） | A-006 |
| `test_inject_data_into_review_with_drifted_english_headings` | 漂移输入 `# 日期` + `## 1./2./4.` + 完整 overview | 四表标记全存在（Market Signal / Index 表 / Leading Industry Sectors） | A-007 |

### 5.3 回归测试

- 现有 3 个 inject 测试（`test_inject_data_into_review_matches_english_headings`、`test_inject_data_into_review_matches_reference_style_chinese_headings`、`test_inject_data_into_review_appends_sector_block_when_heading_drifts`）必须全部通过。
- 命令：
  ```bash
  cd /home/pascal/workspace/yquant-investment/skills/research/daily_stock_analysis
  python -m pytest tests/test_market_analyzer_generate_text.py -v
  python -m py_compile src/market_analyzer.py
  ```

### 5.4 手工验证（可选）

- 无强制手工验证。若 T3 Verify 需要端到端 smoke，可用 `--dry-run` + mock overview 触发一次 `generate_market_review()`，检查输出 Markdown 标题结构。

### 5.5 回归范围

- 仅限 `market_analyzer.py` 的 heading + inject 路径。
- 不影响 `core/market_review.py`、`market_review_runtime.py`、推送、API、Web。

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 归一化误伤已正确标题 | helper 幂等设计；A-003 测试保证 no-op | 回滚：删除 `_normalize_market_review_headings` 调用行（1 行），其余代码不受影响 |
| 归一化正则与现有 patterns 不一致 | Design 保证归一化目标就是 `###`，与 patterns 对齐 | 回滚同上 |
| emoji 匹配漏覆盖 | 推荐 §3.3.2 的 `[^\w]` 写法，不硬编码 emoji | 回滚同上 |
| orchestrator 在 `market_review.py` 的临时修改与本设计冲突 | 本设计不改 `market_review.py`；建议保留 orchestrator 临时修改（空 wrapper segment fallback 是独立防护） | 若 Pascal 决定撤回 orchestrator 临时修改，单独走一个轻量 task，不并入本 RFC |
| helper 在极端输入下抛异常 | `try/except` 全包裹，fail-safe 返回原文 | 回滚同上 |

### 6.1 回滚方案（精确步骤）

1. 删除 `_inject_data_into_review()` 中的归一化调用行（1 行）。
2. （可选）删除 `_normalize_market_review_headings()` 方法和 4 个正则常量。
3. 删除新增测试用例。
4. 回滚后系统回到"漂移即丢表"的旧行为，不影响其他功能。

### 6.2 冲突控制说明

- **不改 `core/market_review.py`**：当前 orchestrator 临时修改（`_append_missing_sector_payload_block_to_market_segment` 的空 segment fallback，line 637-653）与本设计正交。归一化在 `market_analyzer.py` 层完成后，`market_review.py` 渲染层拿到的已是归一化文本。建议保留 orchestrator 临时修改，理由：
  1. 它是多市场 wrapper 层的独立防护（处理 `# A股大盘复盘` wrapper 后紧跟 `# 日期` 导致的空 segment）。
  2. 撤回它需要独立的回归验证，不在本 RFC 范围内。
  3. 保留它不会与归一化冲突——两者作用在不同层、不同文本阶段。
- **不改 prompt**：`_build_review_prompt()` 的 f-string（line 1443-1690）保持原样。

## 7. 交接给实现者

### 7.1 必须遵守

- 只改 `src/market_analyzer.py` 和 `tests/test_market_analyzer_generate_text.py`。
- helper 用 `@staticmethod`，签名严格按 SPEC §4.1。
- helper 必须 fail-safe（`try/except` 返回原文）。
- helper 必须幂等（已正确输入 no-op）。
- emoji 处理用 §3.3.2 推荐写法（`[^\w]`），不硬编码 emoji 列表。
- 新增测试必须覆盖 SPEC A-001 到 A-011 全部验收点。
- 现有 3 个 inject 测试必须回归通过。

### 7.2 可自行判断

- 正则常量放在模块级（靠近 `_CHINESE_SECTION_PATTERNS`）还是方法内部（编译缓存考量）。推荐模块级。
- helper 方法放在 `_inject_data_into_review()` 之前还是之后。推荐之前（读代码时先看到归一化再看到注入）。
- 漂移集成测试是否复用现有 `test_inject_data_into_review_matches_reference_style_chinese_headings` 的 overview 构造。推荐复用（减少重复）。

### 7.3 遇到以下情况退回 Principal

- 发现归一化无法覆盖某种 LLM 实际漂移模式（需要扩 SPEC）。
- 发现不改 `_CHINESE_SECTION_PATTERNS` 正则就无法命中（需要重新评估"不改 patterns"约束）。
- 发现需要改 `core/market_review.py` 才能达成验收（触发 RFC 非目标边界）。
- 测试发现归一化破坏了 `_split_report_sections()` 的行为（需要评估兼容性）。
