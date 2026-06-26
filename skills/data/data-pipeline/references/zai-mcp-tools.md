# Z.AI MCP Server Tools Reference

> **来源**：实测 `@z_ai/mcp-server` v0.1.2（mode=ZHIPU）的 `list_tools()` 输出。
> **维护**：MCP server 升级时（v0.1.x → 0.2.x）应重新跑 `list_tools()` 验证 tool 列表。
> **触发场景**：zai provider fallback 行为异常 / OCR 准确度问题 / 想要换 tool。

---

## 实测验证命令

```python
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / ".hermes" / "profiles" / "yquant" / ".env", override=False)

import asyncio
from providers.zai_provider import ZAIMCPClient
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async def main():
    client = ZAIMCPClient(server_name="Z.AI Vision MCP")
    async with stdio_client(client._params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            for t in tools:
                name = getattr(t, "name", "?")
                schema = getattr(t, "inputSchema", None) or {}
                print(f"{name:<32} required={schema.get('required', [])}")
asyncio.run(main())
```

## Tool 列表（v0.1.2 实测）

| Tool 名 | 用途 | required params | properties |
|---|---|---|---|
| `ui_to_artifact` | UI 截图 → 代码 / prompt / spec / description | `image_source`, `output_type`, `prompt` | `image_source`, `output_type`, `prompt` |
| `extract_text_from_screenshot` | **纯 OCR** | `image_source`, `prompt` | `image_source`, `prompt`, `programming_language` |
| `diagnose_error_screenshot` | 错误截图诊断 | `image_source`, `prompt` | `image_source`, `prompt`, `context` |
| `understand_technical_diagram` | 架构 / 流程图 / UML 解释 | `image_source`, `prompt` | `image_source`, `prompt`, `diagram_type` |
| `analyze_data_visualization` | 图表 / 仪表盘分析 | `image_source`, `prompt` | `image_source`, `prompt`, `analysis_focus` |
| `ui_diff_check` | 两张 UI 截图 diff | `expected_image_source`, `actual_image_source`, `prompt` | 同 required |
| `analyze_image` | **通用图像分析**（pipeline JSON 优先选） | `image_source`, `prompt` | `image_source`, `prompt` |
| `analyze_video` | 视频分析（不在我们用范围） | `video_source`, `prompt` | `video_source`, `prompt` |

## Provider 实际选择逻辑

`zai_provider.py` `_pick_image_tool` 优先级（2026-06-26 晚间二次校准后，commit `e78ccd8`）：

1. **显式白名单**：
   - `analyze_image`（**优先**；遵循 prompt，能返回 JSON 数组/代码块，适合表格结构化）
   - `extract_text_from_screenshot`（**次选**；纯 OCR，可能返回普通文本导致 `parse_error: no JSON array in zai output`）
2. **启发式回退**：
   - name 含 `"image"`
   - name 含 `"analyze"` / `"analyse"`
3. **最后**：`tools[0]`

**变更历史**：
- 2026-06-26 早上：纯启发式 → 选到 `ui_to_artifact` 失败（缺 `output_type` 参数）
- 2026-06-26 早上：首次修复改 `extract_text_from_screenshot` 优先
- 2026-06-26 晚间：生产实测发现 `extract_text_from_screenshot` 虽参数最少，但返回纯 OCR 文本不满足 pipeline 的 JSON 契约 → 调换为 `analyze_image` 优先

## 修复前的 bug（2026-06-26 之前）

旧版 `_pick_image_tool` 用纯启发式（name 包含 `"image"`），`list_tools` 返回顺序里**第一个**含 "image" 的是 `ui_to_artifact`，需要 `output_type` 参数 provider 没法填，导致 fallback 必然失败。

**症状**：
- 早上看 health_check `false`（zai provider 报 `Z_AI_API_KEY` 缺失）
- 实际不一定总是 env 缺失
- minimax fallback zai 失败时，zai 报的不是 env 缺失而是 `missing required argument: output_type`（被通用错误消息掩盖）

**修复**：`_pick_image_tool` 加显式白名单（line 440-447）。

## 已知 tool 行为差异

- `analyze_image` 在 pipeline JSON 契约下**优先**：能遵循 prompt 输出 JSON 数组/代码块，被 `extract_json()` 正确解析
- `extract_text_from_screenshot` 是**纯 OCR 兜底**：可能忽略 prompt 的 JSON 输出要求，返回普通文本（实测中触发 `parse_error: no JSON array in zai output`）
- `analyze_data_visualization` 适合 K 线 / dashboard，但**对持仓表的列名识别不准确**
- `ui_to_artifact` 需要 `output_type` 参数，pipeline provider 没传 → **不能用**

## 升级 MCP server 时

```bash
# 查看当前版本
npx -y @z_ai/mcp-server --version
# 或从 server 启动日志读
# "MCP Server started successfully [{\"mode\":\"ZHIPU\",\"name\":\"zai-mcp-server\",\"version\":\"0.1.2\"}]"

# 升级后重新跑上面的 list_tools 验证脚本
```

如 tool 列表变化（增 / 删 / 改 required），**先检查 `_pick_image_tool` 白名单是否仍命中**，否则 OCR fallback 会静默失败。

## Z_AI_VISION_MODEL 与 tool 选择的相互作用（2026-06-26 实战发现）

`Z_AI_VISION_MODEL` 是 MCP server 端调用的 GLM 模型（默认 `glm-4.6v`，可改 `glm-4v-flash` / `glm-5v-turbo`），与 tool 选择是**两个独立维度**。

**已知兼容矩阵**（v0.1.2 实测）：

| `Z_AI_VISION_MODEL` | `analyze_image` | `extract_text_from_screenshot` |
|---|---|---|
| `glm-4v-flash`（当前 config 默认） | ❌ 报 `max_tokens parameter is illegal. 限制范围[1,1024]` | ✅（OCR 纯文本） |
| `glm-5v-turbo` | ✅ 返回 JSON 代码块 | ✅（OCR 纯文本） |
| `glm-4.6v`（MCP 默认） | ✅ 准确率最高 | ✅ |

**结论**：
- 若 config 用 `glm-4v-flash`（用户当前选择），则 `analyze_image` 优先的 pipeline 走不通，会触发 `max_tokens` 报错。**用户已选择保持 `glm-4v-flash`，接受这个限制**——遇到 `max_tokens` 报错时临时改 `glm-5v-turbo`。
- 若 config 用 `glm-5v-turbo`，则 `analyze_image` + tool 优先级 = 最稳的组合。

详见 `references/zai-mcp-fallback-runtime-2026-06-26.md` 和 `references/provider-fallback-ops.md`。
