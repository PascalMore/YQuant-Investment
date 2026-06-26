# Z.AI MCP fallback runtime fixes — 2026-06-26 evening

Context: MiniMax Token Plan quota was exhausted while ingesting Smart Money portfolio screenshots. The image pipeline fell back to Z.AI MCP but initially failed in two separate ways. These fixes make the fallback path production-usable.

**Status (2026-06-26 晚间更新)**：Bug 1 (env 拍平) + Bug 2 (tool 优先级) 已 commit `e78ccd8`。Bug 3 (`Z_AI_VISION_MODEL` 与 `max_tokens`) 是已知 trade-off——用户选择保持 `glm-4v-flash` 作为默认，遇到 `max_tokens` 报错时再临时切 `glm-5v-turbo`。

## Symptoms observed

1. Router final error was opaque:

```text
RuntimeError: all providers failed: [minimax] ... Token Plan 用量上限 ... / [zai] unknown:
```

2. Direct MCP reproduction showed the real startup error:

```text
Application startup failed: Z_AI_API_KEY environment variable is required
McpError: Connection closed
```

3. After env propagation was fixed, `extract_text_from_screenshot` ran but returned plain OCR text, causing:

```text
[zai] parse_error: no JSON array in zai output
```

4. `analyze_image` is the correct tool for the pipeline JSON prompt, but with `Z_AI_VISION_MODEL=glm-4v-flash` (current config) the MCP server fails:

```text
HTTP 400: The max_tokens parameter is illegal. 限制数值范围[1,1024]
```

## Root causes

### 1. Lightweight config parser flattened `env:` entries

`_parse_mcp_servers()` did not preserve nested mapping context. The YAML block:

```yaml
mcp_servers:
  "Z.AI Vision MCP":
    command: npx
    args: ["-y", "@z_ai/mcp-server"]
    env:
      Z_AI_API_KEY: ${Z_AI_API_KEY}
      Z_AI_MODE: ZHIPU
      Z_AI_VISION_MODEL: glm-5v-turbo
```

was parsed as:

```python
{
  "command": "npx",
  "args": ["-y", "@z_ai/mcp-server"],
  "Z_AI_API_KEY": "${Z_AI_API_KEY}",
  "Z_AI_MODE": "ZHIPU",
  "Z_AI_VISION_MODEL": "glm-5v-turbo",
}
```

`_load_server_params()` only read `spec.get("env")`, so the MCP subprocess launched without the credential.

Fix: if `env` is empty, recover uppercase top-level keys from the server spec, then merge them over `os.environ` (so PATH / HOME / etc. are inherited).

### 2. Tool choice must prefer `analyze_image`, not pure OCR

`extract_text_from_screenshot` is pure OCR. It may ignore the pipeline prompt's JSON-array contract and return text. For the image pipeline, prefer:

```text
analyze_image -> extract_text_from_screenshot -> heuristic fallback
```

`analyze_image` follows the prompt and can return JSON arrays that `extract_json()` can parse.

### 3. `glm-4v-flash` is too constrained for JSON table extraction — known trade-off

The Z.AI MCP server uses an internal `max_tokens` value that violates `glm-4v-flash`'s `[1,1024]` output limit for `analyze_image`.

**User decision (2026-06-26)**：保持 `Z_AI_VISION_MODEL: glm-4v-flash` 作为 config 默认值（速度优先）。Pipeline 在该模型下 `analyze_image` 不可用，会触发 `max_tokens parameter is illegal`。**临时绕过**：把 `Z_AI_VISION_MODEL` 改为 `glm-5v-turbo`，跑通后还原。

不要把 `glm-5v-turbo` 当成"永久修复"——这是临时绕过手段。用户偏好"**4.6v 不要 turbo**"。

`glm-5v-turbo` 成功跑通 Smart Money 截图的实测：返回 `json` 代码块，parse 正常，30+ 行 position 全部入库。

## Verification pattern

### Check parsed MCP env before launching

```bash
cd /home/pascal/workspace/yquant-investment && \
PYTHONPATH=skills/data/data-pipeline/scripts:/home/pascal/workspace/yquant-investment \
.venv/bin/python - <<'PY'
import sys, os, hashlib
sys.path.insert(0, 'skills/data/data-pipeline/scripts')
from providers.zai_provider import ZAIVisionProvider, ZAIMCPClient
p = ZAIVisionProvider()  # triggers profile .env self-load when needed
client = ZAIMCPClient(server_name=p.mcp_server_name, config_path=p.config_path)
for k in ['Z_AI_API_KEY','GLM_API_KEY']:
    v = client._params.env.get(k)
    print(k, 'set=', bool(v), 'len=', len(v or ''))
print('Z_AI_MODE=', client._params.env.get('Z_AI_MODE'))
print('Z_AI_VISION_MODEL=', client._params.env.get('Z_AI_VISION_MODEL'))
PY
```

预期：`Z_AI_API_KEY set=True len=49`（不是占位符 `${Z_AI_API_KEY}`）。

### Check MCP tools and selected tool

```bash
cd /home/pascal/workspace/yquant-investment && \
PYTHONPATH=skills/data/data-pipeline/scripts:/home/pascal/workspace/yquant-investment \
timeout 120 .venv/bin/python - <<'PY'
import asyncio, sys
sys.path.insert(0, 'skills/data/data-pipeline/scripts')
from providers.zai_provider import ZAIVisionProvider, ZAIMCPClient, _pick_image_tool
async def main():
    p = ZAIVisionProvider()
    client = ZAIMCPClient(server_name=p.mcp_server_name, config_path=p.config_path)
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    async with stdio_client(client._params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools = tools_result.tools if hasattr(tools_result, 'tools') else tools_result
            print([t.name for t in tools])
            print('picked:', _pick_image_tool(tools).name)
asyncio.run(main())
PY
```

预期：MCP 启动，tools 包含 `analyze_image`，picked = `analyze_image`。

## Production outcome from this session

After applying fixes 1 + 2 (commit `e78ccd8`):

- One image succeeded through MiniMax:

```text
provider_status: name='minimax', fallback_used=False
mongodb: position=26, nav=1, basic_info=1
pending_rows=0
```

- One image succeeded through Z.AI fallback:

```text
provider_status: name='zai', fallback_used=True, duration_ms≈49176
mongodb: position=28, nav=1, basic_info=1
pending_rows=0
```

## Operator note

When MiniMax quota is exhausted, do not immediately switch to manual OCR. First verify Z.AI fallback with the env/tool/model checks above.

If fallback reaches `parse_error: no JSON array`, inspect tool choice — should be `analyze_image`.

If it reaches `max_tokens parameter is illegal`, the config has `Z_AI_VISION_MODEL=glm-4v-flash` (current default). Two options:

1. 临时：把 `Z_AI_VISION_MODEL` 改成 `glm-5v-turbo`，跑完后还原。
2. 接受：保持 `glm-4v-flash`，pipeline 在 `analyze_image` 路径上 fallback 不通，但 `extract_text_from_screenshot` 仍可用（纯 OCR，无 max_tokens 限制，但需下游手动 JSON 解析）。

用户当前选择：方案 1（临时切换）。如 fallback 失败且不想改 model，回退到方案 2。
