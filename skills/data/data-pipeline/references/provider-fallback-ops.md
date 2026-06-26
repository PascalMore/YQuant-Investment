# Provider Fallback 运维实战笔记

> 2026-06-26 首次生产环境 fallback 测试记录。MiniMax 额度耗尽 → Z.AI 接管 → 数据成功入库。
>
> 2026-06-26 晚间二次校准：`zai-mcp-tools.md` 的 tool 优先级从 `extract_text_from_screenshot` 优先改为 `analyze_image` 优先（commit `e78ccd8`），并发现 Bug 1 的根因是 YAML parser 把 `env:` 拍平。

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
持仓 + NAV 入库 MongoDB
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

### Bug 1: ZAI MCP 子进程拿不到 `Z_AI_API_KEY`（轻量 YAML parser 拍平 `env:` 块）

> **2026-06-26 晚间修订**：原版本把根因归为「缺 PATH/HOME 继承」，实际根因更深一层——`zai_provider._parse_mcp_servers()` 的轻量 YAML 解析器**不保留嵌套 mapping 上下文**，把 `env:` 块下的 key 全部拍平到 server spec 顶层；`_load_server_params()` 读 `spec.get("env")` 时拿到 `None`/空 dict，构造的 `StdioServerParameters(env={})` 让 npx 子进程没有任何 env vars 启动。

**症状**：`Z_AI_API_KEY` 在父进程 `os.environ` 里能看到，但 MCP server 启动报 `Z_AI_API_KEY environment variable is required` + `McpError: Connection closed`。

**根因追溯**：

```yaml
# config.yaml 原文（看起来正确）
mcp_servers:
  "Z.AI Vision MCP":
    command: npx
    args: ["-y", "@z_ai/mcp-server"]
    env:
      Z_AI_API_KEY: ${Z_AI_API_KEY}
      Z_AI_MODE: ZHIPU
      Z_AI_VISION_MODEL: glm-5v-turbo
```

被 `_parse_mcp_servers()` 解析成：

```python
{
  "command": "npx",
  "args": ["-y", "@z_ai/mcp-server"],
  "Z_AI_API_KEY": "${Z_AI_API_KEY}",   # 拍平到顶层
  "Z_AI_MODE": "ZHIPU",
  "Z_AI_VISION_MODEL": "glm-5v-turbo",
}
# spec.get("env") → None  ← 这里读不到 env 块
```

**修复**（`zai_provider.py` `_load_server_params`，commit `e78ccd8`）：

```python
env = spec.get("env") or {}
if not isinstance(env, dict):
    env = {}
# Compatibility: lightweight YAML parser flattens env: block to top-level
if not env:
    env = {
        k: v
        for k, v in spec.items()
        if isinstance(k, str) and k.isupper()
    }
# Resolve ${VAR} placeholders using current process env, then merge
# with the parent environment so the subprocess inherits PATH, HOME,
# and other variables needed by npx/node/uvx.
resolved = _resolve_env(env, os.environ)
merged = dict(os.environ)  # inherit full parent environment
merged.update(resolved)    # server-specific vars take precedence
return StdioServerParameters(command=command, args=args, env=merged)
```

两层修复：① 顶层大写 env 字段自动重组成 `env` 块；② 即便显式 `env` 块缺失，merge 父进程 `os.environ` 兜底（解决 PATH/HOME/NODE 继承）。

**教训**：MCP SDK 的 `StdioServerParameters(env=...)` 如果提供了 `env` 参数，**会完全替换**而非合并父进程环境（与 `subprocess.Popen(env=...)` 行为一致）。轻量 YAML parser 不能把「nested mapping」扁平化后假装它还在原位——要么修 parser，要么在消费端 recover。

### Bug 2: Fallback 超时太短

**症状**：Z.AI MCP server 成功启动，API 请求发出，但 ~120s 后收到 SIGTERM，glm-4.6v 响应被杀。

**根因**：Router 用 `asyncio.wait_for(timeout=fallback_timeout_seconds + 30)`。原配置 `fallback_timeout_seconds=90`（有效超时 120s）。glm-4.6v 处理复杂表格截图需要 ~100-105s，刚好卡在超时边界。

**修复**：`config.yaml` 中 `fallback_timeout_seconds: 90 → 240`。

### Bug 3: `_pick_image_tool` 选错 tool（2026-06-26 修复 + 晚间二次校准）

**症状**：zai MCP fallback 链路**实际上从未工作过**。minimax 主路径一直通，fallback 失败从未被发现。

**根因**：`zai_provider.py` 的 `_pick_image_tool` 用 `name 包含 "image"` 子串匹配，遍历 `list_tools()` 返回的 8 个 tool 第一个匹配。`@z_ai/mcp-server` v0.1.2 暴露的 tools（按 list 顺序）：

| 顺序 | tool 名 | 必填参数 | 是否能用于持仓 OCR |
|---|---|---|---|
| 1 | `ui_to_artifact` | `image_source, output_type, prompt` | ❌ 缺 `output_type` |
| 2 | `extract_text_from_screenshot` | `image_source, prompt` | ⚠️ 纯 OCR 文本 |
| 3 | `diagnose_error_screenshot` | `image_source, prompt, context` | ❌ 偏题 |
| 4 | `understand_technical_diagram` | `image_source, prompt, diagram_type` | ❌ 偏题 |
| 5 | `analyze_data_visualization` | `image_source, prompt` | ❌ 偏题 |
| 6 | `ui_diff_check` | `expected, actual, prompt` | ❌ 双图 |
| 7 | `analyze_image` | `image_source, prompt` | ✅ **首选** |
| 8 | `analyze_video` | `video_source, prompt` | ❌ 视频 |

**两次校准**：

1. **2026-06-26 早上**：旧启发式匹配到 `ui_to_artifact` → 缺 `output_type` → 失败。改显式白名单 `extract_text_from_screenshot` 优先 + `analyze_image` 兜底。
2. **2026-06-26 晚间**：生产实测发现 `extract_text_from_screenshot` 返回纯 OCR 文本，pipeline 用 `extract_json()` 解析失败（`parse_error: no JSON array in zai output`）。**调换为 `analyze_image` 优先**（commit `e78ccd8`）。

**最终优先级**（`zai_provider.py` `_pick_image_tool`，2026-06-26 晚间）：

```python
# analyze_image 优先（遵循 prompt，能返回 JSON 数组/代码块）
# extract_text_from_screenshot 次选（纯 OCR，可能返普通文本）
# 启发式回退
for preferred in ("analyze_image", "extract_text_from_screenshot"):
    if preferred in by_name:
        return by_name[preferred]
```

**与 `Z_AI_VISION_MODEL` 的交互**（晚间新发现）：

- config 默认 `glm-4v-flash` → `analyze_image` 触发 `max_tokens parameter is illegal（范围[1,1024]）`
- 临时改 `glm-5v-turbo` → `analyze_image` 工作正常
- 用户当前选择：**保持 `glm-4v-flash`**，遇到 `max_tokens` 报错时再临时切换

**教训**：OCR/视觉类 MCP server 通常暴露 ≥5 个 tool，**必须用显式 allowlist**，不能纯靠子串匹配。即便用了 allowlist，还要按「是否遵循 prompt 的输出契约」排序（`analyze_image` 优先于 `extract_text_from_screenshot`），不能光看「哪个参数最少」。

### Bug 4: 裸跑 `.venv/bin/python` 时 profile `.env` 不会被自动注入（2026-06-26 发现并修复）

**症状**：`terminal(background=true)` 启的 `.venv/bin/python` 进程跑 pipeline → minimax 失败 → fallback zai → 报 `Z_AI_API_KEY environment variable is required`。

**关键区分**（这跟 Bug 1 是**两个不同的问题**）：
- **Bug 1**：zai_provider 自己构建的 `StdioServerParameters` 没拿到 env vars（即使父进程有）。已修。
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
- 父进程 `env | grep Z_AI_API_KEY` 看有没有
- 有 → Bug 1（YAML 拍平）
- 没有 → Bug 4（profile .env 未加载）

**教训**：Hermes gateway 的 env 注入机制是**它自己启动的进程**才能享受。任何外部 shell 启的 Python 子进程（cron、terminal background、ad-hoc 脚本）都不会被注入。`dotenv` self-load 应该是数据 pipeline 的默认动作。

## 配置优化

### Z_AI_VISION_MODEL

`@z_ai/mcp-server` 源码（`build/core/environment.js` L108）：
```javascript
model: config.Z_AI_VISION_MODEL || 'glm-4.6v',
```

通过 MCP server env 块添加 `Z_AI_VISION_MODEL` 可以覆盖默认模型：
- `glm-4.6v`（默认）— 准确率高，复杂表格 OCR ~100s
- `glm-4v-flash`（当前 config）— 更快，但 `analyze_image` 受 `max_tokens<=1024` 限制
- `glm-5v-turbo` — `analyze_image` 工作正常，作为 `glm-4v-flash` 报错时的临时替代

在 `config.yaml` 的 `Z.AI Vision MCP` env 块添加：
```yaml
env:
  Z_AI_API_KEY: ${Z_AI_API_KEY}
  Z_AI_MODE: ZHIPU
  Z_AI_VISION_MODEL: glm-4v-flash   # 或 glm-4.6v / glm-5v-turbo
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

# 验证 MCP env 实际传入子进程的变量（commit e78ccd8 修复后）
PYTHONPATH=skills/data/data-pipeline/scripts:/home/pascal/workspace/yquant-investment \
  .venv/bin/python - <<'PY'
import sys, hashlib
from pathlib import Path
sys.path.insert(0, 'skills/data/data-pipeline/scripts')
from providers.zai_provider import ZAIVisionProvider, ZAIMCPClient
p = ZAIVisionProvider()
client = ZAIMCPClient(server_name=p.mcp_server_name, config_path=p.config_path)
for k in ['Z_AI_API_KEY','GLM_API_KEY']:
    v = client._params.env.get(k)
    print(k, 'set=', bool(v), 'len=', len(v or ''))
print('Z_AI_VISION_MODEL=', client._params.env.get('Z_AI_VISION_MODEL'))
PY
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

## 二次校准（2026-06-26 晚间）两张 Smart Money 截图处理

| 截图 | 业务日期 | provider | 入库 | 备注 |
|---|---|---|---|---|
| portfolio_2026-06-26_194148.jpg | 2025-07-16 | minimax（主） | 26 行 position | MiniMax 临时恢复 |
| portfolio_2026-06-26_194149.jpg | 2025-07-16 | zai（fallback） | 28 行 position | duration_ms=49176 |

修复 commit：`e78ccd8 fix(data-pipeline): Z.AI MCP fallback for MiniMax quota exhaustion`。
