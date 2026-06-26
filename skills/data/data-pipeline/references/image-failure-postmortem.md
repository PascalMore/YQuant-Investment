# Image Failure Postmortem — 2026-06-26 早上 6 张并发 2 张失败

> **触发信号**：`Z_AI_API_KEY environment variable is required` 或 `all providers failed: [minimax] unknown: / [zai] unknown: ...`
> **关键警告**：**不要直接套用 SKILL.md line 774 那个 ZAI MCP env 继承 pitfall** — 那是另一回事（PATH/HOME 缺失）。这个 postmortem 写的是更常见的根因：**profile .env 不被自动注入到裸跑 Python 进程**。

---

## 现象

6 张 Smart Money 持仓截图并发跑 pipeline，2 张失败。失败日志：

```
[minimax Vision] portfolio_xxx.jpg: 26 rows, 8 columns
[Step4] MongoDB: ...
  (中途 minimax 报 unknown 空错)
RuntimeError: all providers failed: 
  [minimax] unknown:  
  / [zai] unknown: unhandled errors in a TaskGroup (1 sub-exception)
```

zai 那一行实际 stdout 还打印过：
```
[2026-06-26T00:42:31.430Z] ERROR: Application startup failed: 
  [{"message":"Z_AI_API_KEY environment variable is required, please set your actual API key"}]
```

## 第一直觉（错的）

我第一反应是「**6 个 npx 子进程并发启动抢 env**」，对应 SKILL.md line 774 那个修复。

**但那是错的**。两个证据反证：

1. 顺序跑 2 张全部 success
2. 但顺序跑成功的 2 张**也没** `Z_AI_API_KEY` env（早上 health_check 返回 `false` 已经证明了）

**所以并发不是 env 缺失的根因，env 缺失是一直存在的，只是顺序跑 minimax 直接成功没触发 fallback。**

## 真正根因（2026-06-26 复盘）

**`Z_AI_API_KEY` 写在 `~/.hermes/profiles/yquant/.env` 里，但 `.venv/bin/python` 启动时 `os.environ` 不会自动加载它。**

证据链：

```bash
$ unset Z_AI_API_KEY
$ PYTHONPATH=skills/data/data-pipeline/scripts \
  .venv/bin/python -c "import os; print(os.environ.get('Z_AI_API_KEY'))"
None
```

`/home/pascal/workspace/yquant-investment/.env` 里有 `Z_AI_API_KEY=477f940b...`（line 505），但 `.venv/bin/python` 是裸 Python 进程，**不读这个文件**。Hermes gateway 自己启动时会 load profile 的 `.env`，但 agent 启的 `terminal(background=true, command=".venv/bin/python ...")` 是**绕过 gateway 的裸子进程**。

## 链路

```
agent 启 6 个 terminal(background=true) 跑 pipeline
    ↓ (每个 .venv/bin/python 独立进程)
    ↓ (os.environ 是裸 Python 启动时的环境，**没** load .env)
    ↓
minimax provider (mmx CLI 走 mmx 自己的配置，不依赖 OS env)
    ↓ 偶尔部分图 minimax 报 unknown 空错（minimax 自身并发问题，单独追）
    ↓ 触发 fallback
zai provider (ZAIMCPClient._load_server_params)
    ↓ merged = dict(os.environ) + resolved(env)  # 都是空的
    ↓
npx @z_ai/mcp-server (子进程 env 空)
    ↓
MCP server 启动失败：Z_AI_API_KEY environment variable is required
    ↓
zai 报 ProviderError(mcp_unavailable)
    ↓
Router raise "all providers failed"
```

## 修复（2026-06-26 已落地）

### 方案 B — Pipeline 入口 load `.env`

`run_unified_image_pipeline.py` 顶部 line 16-24：

```python
# Load profile .env BEFORE importing submodules that spawn provider subprocesses
_PROFILE_ENV = Path.home() / ".hermes" / "profiles" / "yquant" / ".env"
if _PROFILE_ENV.exists():
    try:
        from dotenv import load_dotenv as _load_profile_env
        _load_profile_env(_PROFILE_ENV, override=False)
    except ImportError:
        pass
```

### 方案 A — ZAI provider self-load `.env`

`zai_provider.py` `ZAIVisionProvider.__init__` line 67-80：

```python
if not os.environ.get("Z_AI_API_KEY"):
    _env_path = Path.home() / ".hermes" / "profiles" / "yquant" / ".env"
    if _env_path.exists():
        try:
            from dotenv import load_dotenv as _load_env
            _load_env(_env_path, override=False)
        except ImportError:
            pass
```

**为什么两个都要**：方案 B 修当前 pipeline 路径；方案 A 是防御性，让 provider 在被任何路径 import 时（cron / ad-hoc / 未来的脚本）都自给自足。

**为什么用 `override=False`**：如果父进程已经设了（比如 Hermes gateway 自己 load 过），不覆盖。

## 验证（已通过）

```bash
# 验证 1：实例化 zai provider 后 env 加载
$ unset Z_AI_API_KEY
$ PYTHONPATH=skills/data/data-pipeline/scripts .venv/bin/python -c "
from providers.zai_provider import ZAIVisionProvider
ZAIVisionProvider()
import os
print('Z_AI_API_KEY:', os.environ.get('Z_AI_API_KEY', 'MISSING')[:8] + '...')
"
Z_AI_API_KEY: 477f940b...   ✅

# 验证 2：跑完整 pipeline
$ unset Z_AI_API_KEY
$ PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image skills/data/source/smart-money/2026-06-26/image/xxx.jpg
  → status: success, minimax 一次通
```

详见 `scripts/verify_env_loaded.sh`。

## 与 SKILL.md line 774 pitfall 的区别

| 维度 | line 774 pitfall | 本次 postmortem |
|---|---|---|
| 场景 | `npx` 子进程找不到 `node`（因为 `PATH` / `HOME` 没继承） | `npx @z_ai/mcp-server` 子进程拿不到 `Z_AI_API_KEY` |
| 错误消息 | `Z_AI_API_KEY environment variable is required`（误导，实际是 PATH 缺失） | `Z_AI_API_KEY environment variable is required`（**真**是 Z_AI_API_KEY 缺失） |
| 触发条件 | 用 npx 启任何 MCP server | zai MCP server 启动时 |
| 根因 | `_load_server_params` 没 merge `os.environ` | 父 Python 进程的 `os.environ` 里本来就没有 `Z_AI_API_KEY` |
| 修复 | `merged = dict(os.environ) + resolved(env)` | pipeline 入口 + provider `__init__` 主动 load `.env` |

**实际两个 bug 都存在**：
- 早上修过 line 774 那个（merge os.environ）
- 这次修的是父进程的 os.environ 为空的根因

## 教训

**看到错误先复现 + 跑「裸 env 状态探测」再下结论，不要直接套用既有 pitfall 段。**

下次遇到类似 `xxx environment variable is required`：

1. 跑 `unset && .venv/bin/python -c "import os; print(os.environ.get('XXX', 'MISSING'))"` 看父进程有没有
2. 看错误是来自 `npx` 阶段（PATH 缺失）还是 MCP server 内部（key 缺失）
3. 区分：env 继承 bug vs .env 注入 bug
4. 两个都修了才能彻底解决

## 相关 reference

- SKILL.md 「关键 Pitfall — ZAI MCP 子进程环境变量继承（2026-06-26 发现并修复）」
- SKILL.md 「行为规范 — pipeline 出问题时主动排查」
- `references/agent-overengineering-anti-patterns.md` 反模式 7
