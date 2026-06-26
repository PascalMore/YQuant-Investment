# 数据采集 Provider Fallback 设计参考

YQuant data-pipeline 当前的 `MiniMaxImageExtractor` 只调 `mmx vision` CLI，没有任何 fallback。
MiniMax 一旦触发 QPS 限额、套餐耗尽或服务降级，pipeline 立即失败。
本文件记录添加 fallback 时的**设计原则和坑**，下次同类任务时直接照做。

## 1. Fallback 的设计目标

**坑**：很多人以为 fallback 就是"把 `mmx vision` 换成 `glm vision` CLI"。

**现实**（2026-06-24）：
- MiniMax 走 **Anthropic Messages 协议**（`mmx vision describe` 内部封装）
- zai 走两条路：
  - **`api.z.ai/api/paas/v4` 通用付费 API** — OpenAI 兼容协议，按 token 付费
  - **`@z_ai/mcp-server` 视觉 MCP** — stdio + JSON-RPC，共享 Coding Plan 5h 池子
- 后者（视觉 MCP）是**正解**——为已有 Coding Plan 套餐的用户准备，避免重复付费

**做法（已确定）**：在 agent 层做 fallback，不改 pipeline 代码。详见 §4。

Pipeline 链路（agent 层 fallback 视角）：

```
调用 run_unified_image_pipeline.py
        ↓
   mmx CLI OCR (主路径)
        ↓ 失败
   pipeline 返回 {"status": "fallback_needed", ...}
        ↓
   agent 调 zai MCP image_analysis
        ↓ 拿到 JSON 数组
   agent 写 Excel，继续 pipeline 后置步骤
        ↓
   Transform → Validate → MongoDB
```

## 2. zai 视觉 Fallback — 唯一正解：用 Coding Plan 专属视觉 MCP

**坑（2026-06-24 修正）**：之前以为 OCR fallback 走 `api.z.ai/api/paas/v4` pay-as-you-go 调 `glm-4.6v` API。**错了**。这是按 token 付费路径，与 Coding Plan 套餐**不共享额度**——对已有 Coding Plan 套餐的用户来说，等于要再付一份钱。

**正解**：Z.AI 为 GLM Coding Plan 用户提供了**专属视觉 MCP server**：
- NPM 包：`@z_ai/mcp-server`（**>= 0.1.2** 才能用 GLM-4.6V；老用户需 `npx` 清缓存或加 `@latest`）
- 底层模型：GLM-4.6V
- 启动方式：`npx -y "@z_ai/mcp-server"`
- 认证：环境变量 **`Z_AI_API_KEY`**（**注意：与 `GLM_API_KEY` 是两个不同的 key**）
  - `Z_AI_API_KEY` 在智谱个人中心「个人编程套餐 > 套餐概览」新建
  - 官方明确："团队套餐 Key 与平台其他 API Key 不通用"
- **额度共享 Coding Plan 5h prompt 资源池**（不单独计费！走同一个池子）
- 提供工具：`analyze_data_visualization`、`image_analysis`、`video_analysis`

**YQuant config.yaml 配置**（`~/.hermes/profiles/yquant/config.yaml`）：

```yaml
mcp_servers:
  "MiniMax Token Plan MCP":          # 现有
    # ...
  "Z.AI Vision MCP":                  # ← 新增
    command: npx
    args: ["-y", "@z_ai/mcp-server"]
    env:
      Z_AI_API_KEY: "${Z_AI_API_KEY}"
      Z_AI_MODE: ZHIPU
    connect_timeout: 120
    timeout: 120
```

**环境变量**（`~/.hermes/profiles/yquant/.env`）：

```bash
Z_AI_API_KEY=your-cp-...4e8e  # 在智谱个人中心「编程套餐」页面新建
```

**`GLM_API_KEY` 仍然保留**——用于 compression 等其他用途。**不**用于视觉 fallback。

**常见混淆**：
| 变量 | 用途 | 计费 |
|------|------|------|
| `GLM_API_KEY` | `api.z.ai/api/paas/v4` 通用付费 API | 按 token 付费 |
| `Z_AI_API_KEY` | Coding Plan 套餐专用 key | 共享套餐 5h 池子 |

**两个 key 在 Z.AI 后台是两个独立条目，需要分别创建。**

**为什么用 MCP 而非 Python 直接调 API**：
- `@z_ai/mcp-server` 本质是给 agent 用的 MCP 工具（stdio + JSON-RPC）
- 在 Python pipeline 里调它涉及子进程协议、stdio 解析，复杂度高
- 让 agent 在主路径失败后用 MCP 工具走 fallback，最自然
- MCP 模式下 prompt、错误处理、响应解析都由 zai 自家包封装好了

## 3. MCP 提供的工具（实测 v0.1.2）

| 工具 | 用途 | 适用场景 |
|------|------|---------|
| `extract_text_from_screenshot` | 纯 OCR 文本提取 | **OCR 场景首选**（持仓截图、表格、Excel 截图） |
| `analyze_image` | 通用图像理解 | OCR 备选，参数 `{image_source, prompt}` |
| `analyze_data_visualization` | 仪表盘/统计图表 | K 线图、收益曲线 |
| `understand_technical_diagram` | 架构图/UML 解释 | 流程图、ER 图 |
| `diagnose_error_screenshot` | 错误截图诊断 | 报错信息分析 |
| `ui_to_artifact` | UI 截图 → 代码/spec | 用途不同，需要 `output_type` 必填参数 |
| `ui_diff_check` | 两张 UI 截图 diff | 需同时传两张图 |
| `analyze_video` | 视频理解 | 不适用于截图 OCR |

**`_pick_image_tool` 优先级**（2026-06-26 修正）：
1. `extract_text_from_screenshot`（明确选择）
2. `analyze_image`（明确选择）
3. 启发式 fallback：`name 包含 "image"`
4. 启发式 fallback：`name 包含 "analyze"/"analyse"`
5. `tools[0]`

**绝对不要** 用「子串匹配 + 第一个」启发式 — 8 个 tool 里多个含 "image"，第一个是 `ui_to_artifact`（需要 `output_type`，provider 没传）→ 报 `missing required argument`。ZAI fallback 链路在修复前**从未真正工作过**。详见 `provider-fallback-ops.md` Bug 3。

**额度规则**（关键）：
- 视觉 MCP 共享 Coding Plan **5h prompt 资源池**——和主对话是**同一个池子**
- 池子耗尽时 MCP 调用也会失败 → **必须有兜底**
- ⚠️ 频繁用视觉 MCP fallback 会挤压主对话额度（GLM-5.2/5-Turbo 也是这个池子）

## 4. Fallback 在哪一层实现 — 选 agent 层（推荐）还是 extractor 层？

### 方案对比

| 方案 | 实现位置 | 优点 | 缺点 |
|------|---------|------|------|
| **A. extractor 内 fallback** | `minimax_image_extractor.py` 内 import MCP 客户端，Python 子进程调 MCP | 透明，对调用方零改动 | 在 Python 里调 MCP server 涉及 stdio + JSON-RPC 协议；agent 与 extractor 都要写错误处理；引入新故障面 |
| **B. agent 层 fallback** ✅ | pipeline 主路径失败时返回 "fallback needed" 标记；agent 看到后调 zai MCP `image_analysis` 工具，拿到结果后写 Excel，继续后续步骤 | 不改 pipeline 代码；利用 MCP 工具抽象；失败处理复用 agent 自身 | 需在 skill 文档里约定 fallback 协议；agent 必须理解标记 |

**推荐 B**：zai 视觉 MCP 是给 agent 用的工具。在 Python pipeline 里强行集成会增加维护成本。让 agent 在主路径失败后用 MCP 工具走 fallback，最自然。

### Fallback 协议（agent 层实现要点）

```
1. Agent 调 run_unified_image_pipeline.py 处理图片
2. Pipeline 第一步：mmx CLI OCR
3. mmx 失败时（超时/限额/JSON 解析失败）：
   - Pipeline 返回 {"status": "fallback_needed", "image_path": "...", "reason": "..."}
   - 不直接报错退出
4. Agent 看到 fallback_needed 标记
5. Agent 调 zai MCP image_analysis(image_path, prompt=<原 VISION_PROMPT>)
6. 拿到 JSON 数组后，手动写 Excel 到 pipeline 期望路径
7. 继续调用后续步骤（Transform/Validate/Load）
8. 最终返回给 agent 正常的 load_result
```

### 输出格式差异

**坑**：换了 provider 输出格式不一定一样。

- MiniMax M3 在 prompt 强约束下输出 `[{...}, {...}]` JSON 数组
- zai MCP `image_analysis` 同样支持强 prompt 约束，但**不一定**严格遵守 JSON-only
- 建议 prompt 末尾加 `严格输出 JSON 数组，不要任何额外文字`
- 后处理用 `json_repair` 库或正则提取（参考 `minimax_image_extractor.py:_extract_json()`）
- 解析失败则视为 fallback 输出无效，告知用户手动处理

### 4.1 何时触发 fallback（判定条件）

- `mmx vision describe` subprocess 失败：returncode != 0 / TimeoutExpired
- 套餐限额：返回内容含 "rate limit" / "quota exceeded" / HTTP 429
- 输出空或截断：返回内容 < 100 字符
- JSON 解析失败：连续 3 次重试都解析不出有效数组

**重试 vs Fallback 分离**：
- 同一个 provider 重试 3 次（指数退避 1s/2s/4s）—— 处理瞬时抖动
- 全部重试失败 → 切 fallback —— 处理 provider 级故障

## 6. 启用/禁用 fallback 的开关

视觉 fallback 由 agent 在对话层根据 `fallback_needed` 标记自动触发，**不需要在 pipeline config 里加开关**。

但 zai MCP 本身的启用/禁用由 `mcp_servers` 配置块控制：
- 默认启用 → yquant 启动时加载 `@z_ai/mcp-server`
- 临时禁用 → 从 config.yaml 删掉 `"Z.AI Vision MCP"` 条目并 `/new` 重启
- 永久禁用 → 同上，且不设 `Z_AI_API_KEY` 环境变量

**为什么不需要单独的 fallback 开关**：
- MCP 是只读工具，不引入新故障面
- 没有触发时（MiniMax 正常），agent 不会主动调它
- 触发了也只是多调一个工具，不会污染数据

## 7. 不要混淆的边界

- **`auxiliary.vision`**（Hermes gateway 自动 vision_analyze）≠ pipeline OCR 的 vision provider
  - 前者由 gateway 调用，后者由 pipeline 调用
  - 两套 provider 配置互不影响
- **MCP**（如 `mcp_MiniMax_Token_Plan_MCP_understand_image`）≠ CLI
  - MCP 在对话中被 agent 主动调用（如"仔细看看这张图"）
  - CLI 在 pipeline 中被动调用（如"截图入库"）
  - 改 fallback 路径只动 CLI/MCP 的实现，**不要动 gateway 的 vision_analyze**

## 8. 验证清单

实现完后跑：

```bash
# 单元：mock MiniMax 失败，验证 zai 接管
python3 -m pytest tests/test_minimax_image_extractor.py::test_zai_fallback

# 集成：真图跑一次 pipeline，确认 fallback 输出可被下游 _parse_vision_output 解析
.venv/bin/python skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image tests/fixtures/portfolio_screenshot.png \
  --force-fallback

# 监控：fallback 命中率打到日志，定期 review
grep "vision_fallback_hit" ~/.hermes/profiles/yquant/logs/agent.log
```

## 9. 相关文件

- 当前唯一 OCR 实现：`skills/data/data-pipeline/scripts/extractors/minimax_image_extractor.py`
- Pipeline 入口：`skills/data/data-pipeline/scripts/run_unified_image_pipeline.py`
- 数据 schema：`skills/data/data-pipeline/references/schemas/`
