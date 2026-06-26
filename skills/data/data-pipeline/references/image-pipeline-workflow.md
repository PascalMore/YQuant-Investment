# Image Pipeline 入库实战笔记

> 本文件记录 `data-pipeline` 在 YQuant 项目中跑通 Smart Money 图片入库的**真实会话经验**——SKILL.md 里的 3 个日期概念、孤儿 CSV 现象、字段名陷阱等，都来自 2026-06-25 / 26 两次完整跑通。

## 完整流程（实测版，2026-06-26 修订）

```
用户发图 → agent 归档（archive_date）→ 跑 pipeline（business_date）→ review_pending → 用户审 → load_pending_confirmed
```

### 步骤 1：归档图片（agent 最小动作）

```bash
# 归档日期 = 今天，不是图片业务日期
ARCHIVE_DATE=$(date +%Y-%m-%d)
IMAGE_DIR="/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image"
mkdir -p "$IMAGE_DIR"
cp <用户截图本地路径> "$IMAGE_DIR/portfolio_${ARCHIVE_DATE}_$(date +%H%M%S).jpg"
```

**2026-06-26 用户明确要求 — agent 最小动作规范**：
- **不要**在归档命名里猜 product_code / 产品名（用时间戳即可，不要 `_unknown` 后缀 — 用户 2026-06-26 明确反馈「为什么是 xxxx_unknown.jpg」多此一举）
- **不要**在归档前 `md5sum` 去重 — 重发就让 pipeline 跑重复，MongoDB unique key 自然 upsert
- **不要**在归档后做 MongoDB sanity check / `distinct position_date` 预检 / `audit_pending_unmigrated.py` 预跑
- OCR 跑完从 MongoDB 实际 product_code 决定是否 rename（**用户没要求也不必 rename**）
- **不要**在归档后用 `vision_analyze` / `mcp_Z_AI_Vision_MCP_*` / `mcp_MiniMax_Token_Plan_MCP_understand_image` 给用户描述图（OCR 是 pipeline 的活）
- **不要**自作主张加 namespace 后缀（`_unknown`、产品代码、产品名、格式名 `portfolio_xxx` / `trade_xxx`）— pipeline 自己识别格式和 product_code
- **唯一可问用户的场景**：业务日期从图上看不出，或同一批图混了多业务日期
- **pipeline 失败/partial_success 时**进入「两阶段协议」—— 见 §P7

### 步骤 2：跑 pipeline（2026-06-26 改造后）

**`--date` 参数已删除**，agent 不要传日期 — 业务日期由 OCR 自己从图内 `截止日期` 列识别，传 `--date` 反而 argparse error。

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image "<归档后路径>"
```

**实操**：
- 一次一张（≥3 张图不要 shell 内 `&` 批量后台，详见 SKILL.md "批量图片并行处理模式"）
- pipeline 内部会再用一次 `system_date` 建归档目录（`{system_date}/`），和步骤 1 的 `{archive_date}/` **可能不同**——这是预期
- pipeline 返回的 `status` 字段：
  - `success` — 全部入 DB
  - `partial_success` — 有 pending（OCR 名称异常/主数据缺失）
  - `failed` — pipeline 失败

### 步骤 3：跑完后做 MongoDB 核对

**必须**用项目根 `.venv/bin/python -c`（**不是** `execute_code`，那个 venv 没 pymongo）：

```python
import sys
sys.path.insert(0, '/home/pascal/workspace/yquant-investment')
sys.path.insert(0, '/home/pascal/workspace/yquant-investment/skills/data/data-pipeline/scripts')
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()

# 按业务日期核对
total_pos = db['portfolio_position'].count_documents({'position_date': '<业务日期>'})
total_trade = db['portfolio_trade'].count_documents({'trade_date': '<业务日期>'})

# 按产品聚合
pipeline = [
    {'$match': {'position_date': '<业务日期>'}},
    {'$group': {'_id': '$product_code', 'count': {'$sum': 1}, 'mkt': {'$sum': '$market_value'}}}
]
for d in db['portfolio_position'].aggregate(pipeline):
    print(f'  {d["_id"]}: {d["count"]} 行, 市值 {d["mkt"]:,.0f}')
```

### 步骤 4：pending 出现时的汇报规范（2026-06-26 用户纠正）

当 pipeline 返回 `partial_success` 含 `pending_rows` 时，**agent 主动把产品上下文附在汇报里**，不要让用户再问一次。必须包含：

- `product_code` / `product_name`（从 pending CSV 直接读）
- `nav` / `aum` / `share`（从 `portfolio_nav` 同业务日期同 product_code 查）
- 业务日期
- pending 行的 OCR 名 vs 主数据名 + Wind code + 持仓比例 / 数量 / 市值

**反例（2026-06-26 实际发生）**：agent 汇报时只说「600259.SH OCR 广晟有色，主数据中稀有色」— 用户回「请提供产品代码 / 日期 / share 辅助判断」— agent 第二次才补全。**这是浪费用户时间**。

## 常见 Pitfall（实操中遇到过的）

### P1. NAV 字段名 — 用 `aum` 不是 `scale`

```python
# ❌ 错误 — 字段名猜错，永远返回默认值
nav_record = db['portfolio_nav'].find_one({'product_code': 'SM001'})
print(nav_record.get('scale', 0))  # → 0（不是 None，是字段不存在）

# ✅ 正确 — 实际字段是 aum
print(nav_record.get('aum'))  # → 226570340
```

**校验方法**：第一次用时先 `find_one({...})` 然后打印 `nav_record.keys()` 看实际字段。

### P2. 归档日期 vs 业务日期

| 概念 | 用途 | 错用后果 |
|---|---|---|
| **归档日期** (archive_date) | 目录名 `source/smart-money/{X}/image/` | 跨日发图 → 找不到文件 |
| **业务日期** (business_date) | OCR 从图内 `截止日期` 列读出，写入 MongoDB `position_date` / `nav_date` / `trade_date` | 入库数据时间错乱 |
| **系统日期** (system_date) | pipeline 内部用，可能跨日 | 不影响主流程 |

**用户 2026-06-25 23:17 发图，业务日期 2026-06-24**：
- ❌ 错误归档：`source/smart-money/2026-06-25/image/`（误用业务日期）
- ✅ 正确归档：`source/smart-money/2026-06-26/image/`（系统日期）

**2026-06-26 改造**：`run_unified_image_pipeline.py` 已删除 `--date` 参数，agent 不要再传。OCR 自己读图，业务日期错通过 `audit_pending_unmigrated.py` 或 `update_position_date` 修正。

### P3. "孤儿 CSV" 现象

**实战数据**（2026-06-26）：44 行历史 pending CSV 中 **42 行（95.5%）实际已在 MongoDB**。

**原因**：
- pipeline 早期版本可能直接入库但不回填 CSV 状态字段
- JSON `status` 字段也会滞后
- CSV 状态列 = 审计文件，不应作为"是否入库"的判定

**正确判定**：用 `scripts/audit_pending_unmigrated.py` 跨 CSV + MongoDB 核对（**仅在用户明确询问「还有 pending 没入吗」时跑**，不要 agent 自作主张预跑）。

### P4. clarify 工具偶发 user_response 格式异常

`clarify` 工具偶发返回 `user_response: "<其他回答>"` 但不包含 choices 选项——UI 弹不出选项。

**回退方案**：直接用文字提问列出关键决策点，**不依赖** clarify。

### P5. 健康检查函数是 coroutine（2026-06-26 实战）

`providers.health_check.check_minimax_cli()` 和 `check_zai_mcp()` 都是 async 函数。直接 `print(check_minimax_cli())` 会得到 `<coroutine ...>` + RuntimeWarning，**不是** True/False。

**正确用法**：

```python
import asyncio
from providers.health_check import check_minimax_cli, check_zai_mcp

async def main():
    print(await check_minimax_cli())  # True / False
    print(await check_zai_mcp())

asyncio.run(main())
```

### P6. pending 行入库用 `--name-mapping` 而不是先改 CSV（2026-06-26 实战）

场景：OCR 读到「广晟有色」，主数据是「中稀有色」（公司改名），想用主数据名入库。

**正确做法 — 用 `--name-mapping` 在命令行覆盖**：

```bash
.venv/bin/python skills/data/data-pipeline/scripts/load_pending_confirmed.py \
  --csv "...pending.csv" \
  --name-mapping '{"600259.SH": "中稀有色"}' \
  --confirm-all
```

**反例**：手动编辑 CSV 改 asset_name 字段再 `confirm-all` — 丢失 OCR 原始痕迹，且需要重跑 audit。

### P7. Pipeline 失败时 — 两阶段协议（2026-06-26 用户明确要求）

**关键规则**：用户原话「我问一下，并发的情况下，为什么会出现 zai provider 的并发」「我发你图片 你就归档 不需要归档前什么去重、归档后再 sanity check，归档后就往后，不要过多干预 pipeline」+「如果出现问题，请分析和排查当前 pipeline 中是不是存在缺陷或者待优化的地方，排查出问题并制定优化方案后，待我确认后执行」。

**反例（2026-06-26 实际发生）**：

```
用户：「2 张失败了」
agent：「失败原因是 zai MCP env 缺失。要不要选 A/B/C？」
用户：「A」
agent：立刻启重跑 + 顺手给出长期修复方案 A/B/C
用户：「不是 我选 2 是让你顺序重跑 失败的 2 张」 ← agent 把临时处理和长期方案合并成一个汇报
```

**正确流程（两阶段，不要合并）**：

| 阶段 | 内容 | agent 行为 | 等用户确认 |
|---|---|---|---|
| **阶段 1：临时处理** | 失败的图要不要重跑？顺序还是并发？要不要跳过？要不要手动入库？ | 给选项，**停手** | ✅ 必等 |
| **阶段 2：复盘 + 长期修复** | 临时处理完，回头分析根因 + 给出长期方案（改哪个文件 / 哪一行 / 改成什么 / 风险） | 给方案，**停手** | ✅ 必等 |
| **执行** | 用户明确说「改」「跑」「试」才开始 | — | — |
| **执行后** | 用 MongoDB 核对 / 重跑 pipeline 验证 | — | — |

**反例（不这样做）**：
- 把临时处理和长期方案合并成一个汇报
- 看到失败立刻自己改代码 / 改配置 / 重跑（跳过阶段 1 等确认）
- 临时处理完不进入阶段 2，只说「好了」就结束
- 把失败归咎于外部不可控（配额、网络），不排查代码

**临时处理典型选项模板**：
1. 顺序重跑失败的 N 张（推荐 — 排除并发因素）
2. 并发重跑全部 N+M 张（保留原并发策略）
3. 跳过失败的这几张，等下次自然 idle
4. 手动写 MongoDB 记录（不推荐 — 绕过 audit）

**复盘分析常见根因分类**（不要一上来就猜，按这个顺序排查）：
1. **环境 / 配置**：`.env` 没加载、PATH/HOME 缺失、config.yaml 错
2. **Provider 实现**：tool 选错、prompt 错、解析逻辑错
3. **数据问题**：schema 错、字段类型错、unique key 冲突
4. **并发竞争**：子进程资源、stdio 句柄、npx 缓存
5. **外部不可控**：限流、套餐、网络 — **要排除前 4 项之后才能下结论**

### P8. 归档文件命名 — 时间戳 + 不加 namespace 后缀（2026-06-26 用户明确要求）

用户原话「请改回」。归档命名规则：

```
portfolio_{YYYY-MM-DD}_{HHMMSS}.jpg
```

**反例（agent 画蛇添足）**：
- `portfolio_{ts}_unknown.jpg` ← 用户原话「为什么是 xxxx_unknown.jpg」
- `portfolio_2026-06-26_115837_sm002.jpg` ← 在文件名里猜 product_code
- `portfolio_2026-06-26_115837_trade.jpg` ← 标 format 也没必要，pipeline 自己识别

**多张并发归档**：`TS` 变量自增避免冲突。

**原因**：归档文件名只用于追溯和人类快速定位。Pipeline 自己识别 portfolio/trade 格式、从图内表头读 product_code，不依赖文件名。命名简洁、可排序、不臆断就够了。

### P9. Pipeline 失败时 — 优先排查「2 个常见 env / tool 陷阱」

**失败时第一时间（先于深度排查）跑这套自检**，能覆盖 80% 的「早上看起来好好的现在突然挂了」类问题：

```bash
# 1. 模拟「裸跑」场景，验证 .env 是否能正常加载
unset Z_AI_API_KEY
cd /home/pascal/workspace/yquant-investment
PYTHONPATH=skills/data/data-pipeline/scripts:. .venv/bin/python -c "
import os
print('before:', 'SET' if os.environ.get('Z_AI_API_KEY') else 'MISSING')
from providers.zai_provider import ZAIVisionProvider
ZAIVisionProvider()  # 触发 self-load
print('after:', 'SET' if os.environ.get('Z_AI_API_KEY') else 'MISSING')
"
# 期望: before=MISSING, after=SET
# 失败: after=MISSING → Bug 4 修复未生效，或 dotenv 没装
```

```python
# 2. 验证 zai MCP tool 选对（不是 ui_to_artifact）
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / '.hermes' / 'profiles' / 'yquant' / '.env', override=False)
import asyncio
from providers.zai_provider import ZAIMCPClient, _pick_image_tool
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async def main():
    client = ZAIMCPClient(server_name='Z.AI Vision MCP')
    async with stdio_client(client._params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            picked = _pick_image_tool(tools)
            print(f'picked: {picked.name}')
            assert picked.name in ('extract_text_from_screenshot', 'analyze_image'), \
                f'WRONG TOOL: {picked.name}'

asyncio.run(main())
# 期望: picked: extract_text_from_screenshot
# 失败: 选到 ui_to_artifact → 修复未生效
```

**常见失败原因速查表**：

| 错误现象 | 第一怀疑 | 验证方法 |
|---|---|---|
| `Z_AI_API_KEY environment variable is required` | Bug 4 — .env 没加载 | P9 步骤 1 |
| `missing required argument: output_type` | Bug 3 — `_pick_image_tool` 选错 tool | P9 步骤 2 |
| `Command 'npx' not found` / `node: command not found` | Bug 1 — PATH/HOME 没继承 | `env \| grep -E '^(PATH\|HOME)='` 看父进程 |
| `TimeoutError: 270s` | 复杂表格 OCR，需要更长 timeout | `config.yaml` `fallback_timeout_seconds: 240` |
| `mmx vision describe` 配额上限 | MiniMax Coding Plan 用完 | 等额度刷新或 zai 接管（已 verify） |
| npx 子进程卡住 | node 版本太老 / npx 缓存损坏 | `npm cache clean --force && npx -y @z_ai/mcp-server@latest` |

## 命令模板

### 单图入库完整流程（5 行命令）

```bash
# 1. 归档（时间戳命名，不加 _unknown 后缀）
# 2026-06-26 用户明确要求 — 命名要可排序可追溯，不要画蛇添足的后缀
ARCHIVE_DATE=$(date +%Y-%m-%d)
TS=$(date +%H%M%S)
# 1. 归档（时间戳命名，2026-06-26 用户要求）
ARCHIVE_DATE=$(date +%Y-%m-%d)
TS=$(date +%H%M%S)
mkdir -p "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image"
cp /tmp/user_screenshot.jpg "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image/portfolio_${ARCHIVE_DATE}_${TS}.jpg"

# 2. 跑 pipeline（**不要传 --date**，OCR 自己读图内日期）
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image/portfolio_${ARCHIVE_DATE}_${TS}.jpg"

# 3. 验证入库
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment:/home/pascal/workspace/yquant-investment/skills/data/data-pipeline/scripts \
  .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
print(db['portfolio_position'].count_documents({'position_date': '2025-07-21'}))
"
```

### 补录用户确认的 pending

```bash
# 单个 CSV，指定名字映射覆盖 OCR 误识别
.venv/bin/python skills/data/data-pipeline/scripts/load_pending_confirmed.py \
  --csv "skills/data/source/smart-money/2026-06-23/review_pending/portfolio_20260623_170609_pending.csv" \
  --name-mapping '{"9988.HK": "阿里巴巴-W"}'

# 全部放行
.venv/bin/python skills/data/data-pipeline/scripts/load_pending_confirmed.py \
  --csv "..." \
  --confirm-all
```

### 审计所有 pending 状态（仅用户主动询问时跑）

```bash
.venv/bin/python skills/data/data-pipeline/scripts/audit_pending_unmigrated.py
```

输出 4 类：
- ✅ 已在 DB（可归档 CSV 到 review_resolved/）
- ❌ 孤儿 CSV（CSV resolved 但 DB 无，需 confirm-all 重试）
- ⏸ 待人工复核（pending_review/missing_master）
- 🚫 Wind 代码空（无法入）
