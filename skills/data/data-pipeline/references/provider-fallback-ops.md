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

## 发现并修复的 2 个 Bug

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
