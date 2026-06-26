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
| `extract_text_from_screenshot` | **纯 OCR**（最佳表格截图） | `image_source`, `prompt` | `image_source`, `prompt`, `programming_language` |
| `diagnose_error_screenshot` | 错误截图诊断 | `image_source`, `prompt` | `image_source`, `prompt`, `context` |
| `understand_technical_diagram` | 架构 / 流程图 / UML 解释 | `image_source`, `prompt` | `image_source`, `prompt`, `diagram_type` |
| `analyze_data_visualization` | 图表 / 仪表盘分析 | `image_source`, `prompt` | `image_source`, `prompt`, `analysis_focus` |
| `ui_diff_check` | 两张 UI 截图 diff | `expected_image_source`, `actual_image_source`, `prompt` | 同 required |
| `analyze_image` | **通用图像分析**（兜底） | `image_source`, `prompt` | `image_source`, `prompt` |
| `analyze_video` | 视频分析（不在我们用范围） | `video_source`, `prompt` | `video_source`, `prompt` |

## Provider 实际选择逻辑

`zai_provider.py` `_pick_image_tool` 优先级（2026-06-26 修复后）：

1. **显式白名单**：
   - `extract_text_from_screenshot`（最匹配表格 OCR）
   - `analyze_image`（通用兜底）
2. **启发式回退**：
   - name 含 `"image"`
   - name 含 `"analyze"` / `"analyse"`
3. **最后**：`tools[0]`

## 修复前的 bug（2026-06-26 之前）

旧版 `_pick_image_tool` 用纯启发式（name 包含 `"image"`），`list_tools` 返回顺序里**第一个**含 "image" 的是 `ui_to_artifact`，需要 `output_type` 参数 provider 没法填，导致 fallback 必然失败。

**症状**：
- 早上看 health_check `false`（zai provider 报 `Z_AI_API_KEY` 缺失）
- 实际不一定总是 env 缺失
- minimax fallback zai 失败时，zai 报的不是 env 缺失而是 `missing required argument: output_type`（被通用错误消息掩盖）

**修复**：`_pick_image_tool` 加显式白名单（line 440-447）。

## 推荐配置（per use case）

| 场景 | 推荐 tool | 说明 |
|---|---|---|
| 持仓 / 交易截图（表格） | `extract_text_from_screenshot` | 纯 OCR，参数最少，最适合结构化数据 |
| 流程图 / 架构图 | `understand_technical_diagram` | 带 `diagram_type` hint |
| K 线 / 折线图 | `analyze_data_visualization` | 带 `analysis_focus` hint |
| 错误截图 | `diagnose_error_screenshot` | 不在 pipeline 用，agent 手动调 |
| 兜底 | `analyze_image` | 任何图都能用，但不一定最准 |

## 当前 config

```yaml
Z_AI_VISION_MODEL: glm-4v-flash   # 见 SKILL.md「Z.AI Vision MCP env 配置」
```

`Z_AI_VISION_MODEL` 影响 GLM 后端用哪个模型（`glm-4v-flash` 快，`glm-4.6v` 准），不影响 MCP server 选 tool。

## 已知 tool 行为差异

- `extract_text_from_screenshot` 在纯文本表格上**准确度最高**（OC R 任务专门训练）
- `analyze_image` 在**混合图表 + 文字**上更鲁棒
- `analyze_data_visualization` 适合 K 线 / dashboard，但**对持仓表的列名识别不准确**

## 升级 MCP server 时

```bash
# 查看当前版本
npx -y @z_ai/mcp-server --version
# 或从 server 启动日志读
# "MCP Server started successfully [{\"mode\":\"ZHIPU\",\"name\":\"zai-mcp-server\",\"version\":\"0.1.2\"}]"

# 升级后重新跑上面的 list_tools 验证脚本
```

如 tool 列表变化（增 / 删 / 改 required），**先检查 `_pick_image_tool` 白名单是否仍命中**，否则 OCR fallback 会静默失败。
