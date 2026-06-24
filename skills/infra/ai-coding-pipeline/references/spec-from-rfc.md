# SPEC 编写手册（从 RFC 派生）

> 适用场景：RFC 已存在且 Pascal 在 RFC 末尾给出"开放问题"清单与决策，本阶段任务是把这些决策落到可执行 SPEC。这是 YQuant 项目里 RFC→SPEC 的标准工作流。

## 何时使用本手册

满足以下全部条件：

- 输入是单个已发布的 `docs/rfc/{模块}/RFC-XX-XXX-*.md` 文件
- 任务是用 `docs/spec/{模块}/SPEC-XX-XXX-*.md` 形式产出对应的 SPEC
- RFC §11「开放问题」或对话上下文给出了 Pascal 已决策的若干条结论
- 不写代码（design 阶段才写）

不适用场景：

- 直接从 Intake 写 RFC（用 `references/agent-handoff.md` 的 YQuant-Codex-Principal 输入契约）
- RFC→Design 阶段（design 手册另开）
- SPEC 改写（去更新现有 SPEC 而不是新建）

## 强制前置动作

### 1. 先扫描已有 SPEC 的命名与骨架

```bash
ls docs/spec/{模块}/
```

- 若已有 `SPEC-00-000-spec-template.md`，先 `read_file` 看章节骨架与字段命名。
- 若已有同模块 SPEC（如 `SPEC-03-004`、`SPEC-03-005`），先 `read_file` 至少 1 篇作为结构参考，确保新 SPEC 与同模块其它文件风格一致。
- 命名格式：`SPEC-{模块编号}-{序号}-{short-name}.md`，与 RFC 同构。

### 2. 摸清项目现状（避免空中楼阁）

光读 RFC 写不出可落地的 SPEC。至少读这些：

| 必读 | 为什么 |
|---|---|
| RFC 全文 | 主要输入 |
| `SPEC-00-000-spec-template.md`（如存在） | 章节骨架 |
| 同模块最近 1-2 篇 SPEC | 风格对齐 |
| RFC 引用的现有 extractor / pipeline 代码 | 落地路径真实存在 |
| pending CSV / JSON 现有列结构 | 兼容旧数据 |
| `~/.hermes/profiles/yquant/config.yaml` 的 MCP servers 段 | 真实可用 provider 名 |

**必读但易漏**：RFC 引用的 `_write_vision_debug`、`detect_format` 等工具函数的真实签名。SPEC 里写"扩展某函数"时必须基于真实签名。

### 3. 确保目录存在

```bash
mkdir -p docs/spec/{模块}/
```

避免 `write_file` 失败。Hermes 多数版本会自动创建父目录，但显式 `mkdir -p` 比依赖隐式行为更安全。

## 决策→契约映射（核心模式）

Pascal 已给出的开放问题决策是 SPEC 的灵魂。**禁止把它们当作 RFC 注释埋在散文中**——必须在 SPEC 单设一节"行为契约"或"决策落地"，用表格把每条决策对应到具体代码/接口/测试位置。

模板：

```markdown
## X. 行为契约（N 个开放问题 → 代码层映射）

| 决策 | SPEC 落地点 | 章节 |
|---|---|---|
| 1. <Pascal 决策原文> | <落地的接口/函数/配置项> | <章节号> |
| 2. ... | ... | ... |
```

为什么这很重要：

- Developer 拿 SPEC 就能验证每条决策是否真的被落实，不会"RFC 写了但 SPEC 漏了"。
- Reviewer 可以逐行 grep `decision 1` / `decision 2` 关键词定位。
- 后续 RFC 改动时，重写这一节就能溯源决策位置。

## 必含章节（按 SPEC-00-000 模板扩展）

SPEC-00-000 模板给了 8 节，但 RFC→SPEC 的实际工作需要至少 12 节。下面是推荐章节清单，按本项目惯例：

| 章节 | 必含原因 |
|---|---|
| 元数据 | 来源 RFC、关联 RFC/SPEC、状态（草稿/Accepted/Published）、目标模块 |
| 需求摘要 | 3-5 条交付物清单，不重复 RFC 背景 |
| 范围（In/Out of Scope） | 明确不动的下游代码（防范围漂移） |
| 功能规格 F-NNN | 编号化行为表 |
| 数据与接口契约 | 类型签名、抽象类、注册表 API、Router、错误分类、字段映射 |
| 配置契约 | config.yaml 完整 YAML、默认值表、不暴露原则 |
| **行为契约（决策→代码映射）** | 上面核心模式 |
| 错误契约 | fallback 触发条件表、终态失败语义、脱敏规则 |
| 文件改动清单 | 明确"新增 / 修改 / 不动"三段列表（不动清单比修改清单还重要） |
| 测试要求 | 编号化 UT 矩阵 + IT + 回归 + 不可自动化项 |
| 验收标准 | A-NNN 表，每个对应至少一个 UT |
| 实现约束 | 禁止事项、依赖限制、性能/安全/风控 |
| 风险与未解决问题 | RFC §7 风险映射 + 移交给 Design 的未决项 |

## 关键陷阱（pitfalls）

### P-1：把 SPEC 当 RFC 缩写版

RFC 是「为什么 + 业务边界」，SPEC 是「具体怎么做」。SPEC 不能简单复制 RFC 章节，必须把 RFC 第 5 节「详细设计」中留白的签名、异常类型、调用序列、测试矩阵全部补齐。

判定方法：把 SPEC 丢给 Developer，对方能否不问任何 RFC 问题就动手实现？能就是合格 SPEC，否则退回补齐。

### P-2：漏写"不改动"清单

SPEC 改代码影响面广时，明确列出「不动的下游文件」清单（如 `transformers/*.py`、`validators/*.py`、`loaders/*.py`）。这一段让 Reviewer 知道改动边界。

模板：

```markdown
### 8.3 不改动（明确列出）
- <具体文件路径>
```

### P-3：硬编码模型版本号 / 配额阈值

SPEC 中所有版本号、阈值、token 限制必须指向 `config.yaml` 的字段名，禁止直接写 "GPT-5.5" 或 "100 RPM"。

错误：
```yaml
quota: 100  # requests per minute
```

正确：
```yaml
quota: <from config.yaml ocr_providers.{provider}.quota_rpm>
```

或在 SPEC 中说明「引用 config.yaml 中 `ocr_providers.zai.quota_rpm` 字段」。

### P-4：忘记向后兼容

如果新 SPEC 修改的 CSV/JSON/MongoDB 文档结构由其他模块读取，必须：

1. 在 "数据契约" 章节明确「writer 端向后兼容」逻辑（如「无 provider_status 时不写新列」）。
2. 在测试矩阵中加一条「兼容旧调用」的 UT（UT-XX 形式）。
3. 在"实现约束"中列出 reader 端的迁移责任归属（本 SPEC 写还是其它 SPEC 写）。

### P-5："不暴露给普通用户" 类配置散落文中

如果 RFC 提到某些配置不暴露给普通用户（如 provider 顺序），SPEC 必须单设一节"配置契约"，包含：

- 完整 YAML
- 默认值表
- 「不暴露原则」的落地方式（CLI 不增参数、closeout 不打印全文等）

不能只在注释里写一行 `# not for users`。

### P-6：测试矩阵不够具体

测试矩阵不能写「mock 主失败」。必须包含：

- mock 的具体方法（monkeypatch、`unittest.mock.patch`）
- mock 的具体返回值（抛什么异常、返回什么 ProviderResult）
- 断言的具体字段值（不是「fallback 生效」而是 `provider_status.fallback_used=True`）

每条 UT 应该能直接复制成 pytest 函数。

### P-7：混淆 SPEC 与 Design 的边界

SPEC 写「做什么、接口长什么样、什么算成功」，Design 写「具体用什么库/SDK、怎么组装、迁移路径」。SPEC 不应包含：

- 具体的 Python import 语句（除非是类型签名）
- 具体的 pip 依赖（交给 Design 的 spike）
- 具体的代码片段（除接口签名外）

如果发现 SPEC 在写 `import` 或代码片段，需要重新划分到 Design。

## 验证清单（提交前自查）

- [ ] 元数据齐全：状态、作者、来源 RFC、目标模块、关联 RFC/SPEC
- [ ] RFC §11 开放问题每条都有对应落地章节（决策→代码映射表完整）
- [ ] 数据契约包含类型签名、字段表、向后兼容说明
- [ ] 接口契约包含抽象类、注册表、Router 完整签名
- [ ] 错误契约包含 fallback 触发判定表 + 终态失败语义
- [ ] 配置契约包含完整 YAML + 默认值表 + 不暴露原则
- [ ] 测试矩阵覆盖主成功、主失败备成功、双失败、兼容旧调用、脱敏
- [ ] 文件改动清单分「新增 / 修改 / 不动」三段
- [ ] 风险表对应 RFC §7（如有）+ 本 SPEC 新发现的风险
- [ ] RFC 文件未被修改（md5 一致）
- [ ] 不硬编码模型版本号、阈值

## 完成回报模板

任务完成后回报应包含：

1. SPEC 路径、行数、字节数
2. RFC 未修改的证据（md5 或 git status）
3. 关键章节摘要（一段话或一张表）
4. 移交 Design 阶段的待决项清单（如果有）

## 参考实例

- `docs/spec/03_data/SPEC-03-006-smart-money-ocr-provider-fallback.md`：6 条 Pascal 决策全部映射到「行为契约」章节；包含 20 条 UT 矩阵 + 决策落地表的完整范例。
- `docs/spec/03_data/SPEC-03-004-smart-money-pipeline-review-gate.md`：经典 review-gate 模式（pending CSV/JSON 增列）。
- `docs/spec/03_data/SPEC-03-005-smart-money-batch-closeout.md`：状态机 + closeout 字段契约的范例。