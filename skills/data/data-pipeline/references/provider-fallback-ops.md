# Provider Fallback 运维实战笔记

> 2026-06-26 首次生产环境 fallback 测试记录。MiniMax 额度耗尽 → Z.AI glm-4.6v 接管 → 数据成功入库。

## 触发条件

MiniMax Coding Plan 套餐 Token 到达上限（HTTP 200 + `"已达到 Token Plan 用量上限"`）。所有 `mmx vision` 调用返回额度错误，pipeline 主路径全部失败。

## Fallback 链路

```
MiniMax (primary)  → ❌ 额度到上限
  ↓ VisionProviderRouter 自动切换
Z.AI glm-4.6v (fallback)  → ✅ OCR 成功
  ↓ extract_json → normalize_columns → clean_data
Pipeline 后续步骤正常执行
  ↓
27 持仓 + 1 NAV 入库 MongoDB
```

关键日志：
```
[minimax] 失败: 已达到 Token Plan 用量上限
MCP Server started successfully [{"mode":"ZHIPU","name":"zai-mcp-server","version":"0.1.2"}]
Request ZAI chat completions API [{"model":"glm-4.6v","messageCount":2}]
provider_status: name=zai, fallback_used=True ✅
duration_ms=103679 (≈103s)
```

## 发现并修复的 4 个 Bug

### Bug 1: ZAI MCP 子进程缺少 PATH/HOME

**症状**：`Z_AI_API_KEY` 已在环境变量中设置，但 MCP server 启动报 `Z_AI_API_KEY environment variable is required`。

**根因**：`zai_provider.py` 的 `ZAIMCPClient._load_server_params()` 构建 `StdioServerParameters` 时，只传了 config.yaml 中 server 声明的 env vars（`Z_AI_API_KEY`、`Z_AI_MODE`），**没有继承 `PATH`、`HOME`、`NODE_PATH` 等**。`npx` 子进程找不到 `node` 二进制，根本没启动到读 env 那步。

**修复**（`zai_provider.py` L234-241）：

```python
# 修复前（有 bug）
env = _resolve_env(env, os.environ)
return StdioServerParameters(command=command, args=args, env=env)

# 修复后
resolved = _resolve_env(env, os.environ)
merged = dict(os.environ)  # inherit full parent environment
merged.update(resolved)    # server-specific vars take precedence
return StdioServerParameters(command=command, args=args, env=merged)
```

**教训**：MCP SDK 的 `StdioServerParameters(env=...)` 如果提供了 `env` 参数，**会完全替换**而非合并父进程环境。这与 `subprocess.Popen(env=...)` 行为一致——必须在 env 中包含子进程需要的所有基础变量。

### Bug 2: Fallback 超时太短

**症状**：Z.AI MCP server 成功启动，API 请求发出，但 ~120s 后收到 SIGTERM，glm-4.6v 响应被杀。

**根因**：Router 用 `asyncio.wait_for(timeout=fallback_timeout_seconds + 30)`。原配置 `fallback_timeout_seconds=90`（有效超时 120s）。glm-4.6v 处理复杂表格截图需要 ~100-105s，刚好卡在超时边界。

**修复**：`config.yaml` 中 `fallback_timeout_seconds: 90 → 240`。

### Bug 3: `_pick_image_tool` 启发式选错 tool（2026-06-26 发现，2026-06-26 修复）

**症状**：zai MCP fallback 链路**实际上从未工作过**。minimax 主路径一直通，fallback 失败从未被发现。

**根因**：`zai_provider.py` 的 `_pick_image_tool` 用 `name 包含 "image"` 子串匹配，遍历 `list_tools()` 返回的 8 个 tool 第一个匹配。`@z_ai/mcp-server` v0.1.2 暴露的 tools（按 list 顺序）：

| 顺序 | tool 名 | 必填参数 | 是否能用于持仓 OCR |
|---|---|---|---|
| 1 | `ui_to_artifact` | `image_source, output_type, prompt` | ❌ 缺 `output_type` |
| 2 | `extract_text_from_screenshot` | `image_source, prompt` | ✅ **首选** |
| 3 | `diagnose_error_screenshot` | `image_source, prompt, context` | ⚠️ 偏题 |
| 4 | `understand_technical_diagram` | `image_source, prompt, diagram_type` | ⚠️ 偏题 |
| 5 | `analyze_data_visualization` | `image_source, prompt` | ✅ 也行 |
| 6 | `ui_diff_check` | `expected, actual, prompt` | ❌ 双图 |
| 7 | `analyze_image` | `image_source, prompt` | ✅ **兜底** |
| 8 | `analyze_video` | `video_source, prompt` | ❌ 视频 |

旧启发式匹配到 `ui_to_artifact`（第一个含 "image"），`output_type` 没传 → MCP server 报 `missing required argument: output_type` → fallback 失败。

**修复**（`zai_provider.py` L431-453）：`_pick_image_tool` 改为显式 allowlist：

```python
# 修复后
by_name = {getattr(t, "name", ""): t for t in tools}
for preferred in ("extract_text_from_screenshot", "analyze_image"):
    if preferred in by_name:
        return by_name[preferred]
# 然后才回到启发式 fallback
```

**用户决策**（2026-06-26）：优先 `extract_text_from_screenshot` → `analyze_image`。两者参数都是 `{image_source, prompt}` 最小集，适合持仓截图 OCR。

**教训**：启发式字符串匹配遇上「多个 tool 共享子串」时容易选错。OCR/视觉类 MCP server 通常暴露 ≥5 个 tool，**必须用显式 allowlist**，不能纯靠子串。

### Bug 4: 裸跑 `.venv/bin/python` 时 profile `.env` 不会被自动注入（2026-06-26 发现并修复）

**症状**：`terminal(background=true)` 启的 `.venv/bin/python` 进程跑 pipeline → minimax 失败 → fallback zai → 报 `Z_AI_API_KEY environment variable is required`。

**关键区分**（这跟 Bug 1 是**两个不同的问题**）：
- **Bug 1**：zai_provider 自己构建的 `StdioServerParameters` 没继承父进程 env。已修。
- **Bug 4**：父 Python 进程 `os.environ` 里**根本没有** `Z_AI_API_KEY`。是更上游的问题。

**根因**：`Z_AI_API_KEY` 在 `~/.hermes/profiles/yquant/.env` 里设了，但 Hermes gateway **只给它自己启动的子进程注入 env**。`terminal(background=true)` 经由外部 shell 启进程，绕开了 gateway 的 env 注入。

**验证**：
```bash
unset Z_AI_API_KEY
.venv/bin/python -c "import os; print('Z_AI_API_KEY' in os.environ)"
# → False  ← 父进程 os.environ 里就是没有
```

**修复**（双层防御，已落地）：
1. `run_unified_image_pipeline.py` 入口处（line 16-24）：
   ```python
   _PROFILE_ENV = Path.home() / ".hermes" / "profiles" / "yquant" / ".env"
   if _PROFILE_ENV.exists():
       try:
           from dotenv import load_dotenv as _load_profile_env
           _load_profile_env(_PROFILE_ENV, override=False)
       except ImportError:
           pass
   ```
2. `zai_provider.py` 的 `ZAIVisionProvider.__init__` 内（line 67-80）：同样的 self-load，作为保险。

两者都用 `override=False` — 幂等，Hermes 启的进程（已有 env）直接 skip。

**症状 → 排查**：
- 失败日志里 `Z_AI_API_KEY environment variable is required`
- **不是** Bug 1 那个 PATH/HOME 继承 bug（已修）
- 排查：`env | grep Z_AI_API_KEY` 看父进程有没有；没有就是 Bug 4

**教训**：Hermes gateway 的 env 注入机制是**它自己启动的进程**才能享受。任何外部 shell 启的 Python 子进程（cron、terminal background、ad-hoc 脚本）都不会被注入。`dotenv` self-load 应该是数据 pipeline 的默认动作。

## 配置优化

### Z_AI_VISION_MODEL

`@z_ai/mcp-server` 源码（`build/core/environment.js` L108）：
```javascript
model: config.Z_AI_VISION_MODEL || 'glm-4.6v',
```

通过 MCP server env 块添加 `Z_AI_VISION_MODEL` 可以覆盖默认模型：
- `glm-4.6v`（默认）— 准确率高，复杂表格 OCR ~100s
- `glm-4v-flash` — 更快，但复杂场景准确率可能下降

在 `config.yaml` 的 `Z.AI Vision MCP` env 块添加：
```yaml
env:
  Z_AI_API_KEY: ${Z_AI_API_KEY}
  Z_AI_MODE: ZHIPU
  Z_AI_VISION_MODEL: glm-4v-flash   # 或 glm-4.6v
```

## 运维诊断命令

```bash
# 检查 Z_AI_API_KEY 是否在环境中
env | grep Z_AI_API_KEY

# 手动测试 Z.AI MCP server 启动
npx -y @z_ai/mcp-server --help 2>&1 | head -5

# 查看 MCP server 版本
npm info @z_ai/mcp-server 2>/dev/null | grep version | head -1

# 检查 ocr_providers 配置
grep -A6 "^ocr_providers:" ~/.hermes/profiles/yquant/config.yaml

# 检查 Z.AI Vision MCP server 配置
grep -A10 "Z.AI Vision MCP:" ~/.hermes/profiles/yquant/config.yaml
```

## 首次 Fallback 测试数据

| 维度 | 值 |
|------|-----|
| 图片 | SM012 持仓截图（业务日期 2025-07-21） |
| MiniMax 状态 | HTTP 200 + 额度上限错误 |
| Z.AI 模型 | glm-4.6v |
| Z.AI 耗时 | 103,679ms (~103s) |
| OCR 输出 | 29 行，10 列 |
| 入库持仓 | 27 条（2 条 pending review） |
| 入库 NAV | 1 条 |
| fallback_used | True |
| provider_status.name | zai |
