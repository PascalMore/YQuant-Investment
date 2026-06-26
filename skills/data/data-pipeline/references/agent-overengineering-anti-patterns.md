# Agent 反模式清单 — 图片入库场景

> **触发场景**：用户在 YQuant 会话中发送 Smart Money 持仓 / 交易截图，要求入库。
> **2026-06-26 用户明确反馈**：「对于我图片后，你整个处理逻辑和方式，我感觉还有很大提升空间」+「不要过多干预 pipeline」。
> **核心原则**：进入 data-pipeline 后，让 pipeline 自己跑。Agent 只做 4 件事 — 归档 → 启任务 → 等 notify → 汇总。

---

## ✅ Agent 应该做的（4 件事）

1. **归档**到 `skills/data/source/smart-money/{archive_date}/image/`
2. **后台启 pipeline**（profile 默认并发 / provider / timeout）
3. **等 notify**（不轮询、不 `&` 后台、不 sleep 等待）
4. **汇总 + closeout**

## ❌ Agent 不应该做的（9 条反模式）

### 1. vision_analyze 读图给用户看

```
❌ vision_analyze(image_url=...)           # Hermes 内置，自动 fallback 辅助模型
❌ mcp_Z_AI_Vision_MCP_analyze_image(...)  # 绕开 minimax MCP，zai 余额可能不够
❌ mcp_MiniMax_Token_Plan_MCP_understand_image(...)  # profile 主用 MCP，但仍是 agent 主动读图
```

**为什么不**：
- 浪费 OCR 配额（双重分析）
- 给出 lossy 文字描述，丢失表格结构
- OCR 是 pipeline 的活，agent 越界

**正确做法**：让 `run_unified_image_pipeline.py` 自己 OCR。

### 2. 归档前 md5 去重

```
❌ md5sum image_cache/img_*.jpg | sort | uniq -d   # 检查重发
```

**为什么不**：
- 重发就让 pipeline 跑多次，MongoDB unique key `(position_date, product_code, asset_wind_code)` 自然 upsert
- 浪费 agent 推理时间

**正确做法**：直接归档，让幂等性兜底。

### 3. 归档后 MongoDB sanity check

```
❌ db.portfolio_position.distinct('position_date')      # 查最近日期
❌ db.portfolio_position.count_documents({...})         # 查已存在行
❌ audit_pending_unmigrated.py                          # 预跑 pending 审计
```

**为什么不**：
- 预检不会改变 pipeline 行为
- agent 替系统做了系统的活
- 用户没有要求「先告诉我库里有什么」

**正确做法**：让 pipeline 跑，跑完再核对结果。

### 4. 替用户决定并发数

```
❌ "5 张图并发 5 个后台任务，3×MiniMax 配额"
❌ "建议 max_concurrent=2 而不是 4"
```

**为什么不**：
- profile config 已经有默认并发配置
- agent 没跑 health check 凭什么建议

**正确做法**：用 profile 默认（`ocr_providers.order: [minimax, zai]` + 默认并发）。

### 5. 替用户决定 provider 顺序 / 降级

```
❌ "MiniMax 不健康，切到 zai 优先"
❌ "zai 慢，先跑 minimax，zai 兜底"
```

**为什么不**：
- profile 已经配好 `ocr_providers.order`
- 改 config 属于「替用户做架构决策」

**正确做法**：用 profile 默认。

### 6. 替用户猜 product_code 写文件名

```
❌ cp img.jpg "image/portfolio_${DATE}_sm002.jpg"   # 猜是 SM002
```

**为什么是错的**：
- 早上 5 张图猜 4 个都错（zai vision 报「JS-002」「ZO-001」，实际是 SM004/SM002/SM002/SM001）
- agent 没有可靠渠道知道 product_code，要等 pipeline OCR 后从 MongoDB 查

**正确做法**：
```
DST="$IMAGE_DIR/portfolio_${ARCHIVE_DATE}_$(date +%H%M%S).jpg"
cp <img> "$DST"
```

OCR 完如需 rename，再读 `db.portfolio_basic_info` 反查。
**重要**：归档文件名**不加** `_unknown` 后缀（2026-06-26 用户反馈「为什么是 xxxx_unknown.jpg」是 agent 画蛇添足）。Pipeline 自己识别 portfolio/trade 格式和 product_code，文件名只需可排序可追溯。

### 7. 替用户预估配额消耗

```
❌ "5 张图预计 5×120s = 600s，2×配额"
❌ "建议先 health check 探一下"
```

**为什么不**：
- 配额消耗是 pipeline 内部状态，agent 不掌握
- 预估经常错（miniMax timeout 120s 实际 retry 后 0s，zai 真调要 270s）

**正确做法**：直接跑，跑完看实际。

### 8. 跑前问用户「确认并发 / 确认日期 / 确认是否去重」

```
❌ "5 张图，建议并发 4，OK 吗？"
❌ "看起来日期是 2025-07-21，确认吗？"
```

**为什么不**：
- 用户已经发了图 = 已经决定入库
- 重复确认 = 不信任数据系统的幂等性

**唯一可问的场景**：
- OCR 识别出的 `截止日期` 与用户预期明显不符（可通过 `provider_status` 或 pending CSV 反查）
- 同一批图混了多业务日期（OCR 各自识别结果相差大）
- pipeline 已经跑过，pending 状态卡住

其余一律直接跑。

> **2026-06-26 改造**：`--date` 已从 `run_unified_image_pipeline.py` 接口删除（argparse 报错），所以「`--date` 从图上看不出来」这个分支已不存在。让 OCR 自己识别即可，错了再通过 `audit_pending_unmigrated.py` 修正。

### 9. 用 execute_code 验证 MongoDB 入库

```
❌ from hermes_tools import terminal
   db.collection.count_documents(...)   # execute_code venv 没 pymongo
```

**为什么是错的**：
- `execute_code` 用 Hermes Agent 自己的 venv，没 pandas / pymongo / openpyxl
- 跑 pipeline 没问题（用 `.venv/bin/python`），但 execute_code 跑会 ImportError

**正确做法**：用 `terminal(command=".venv/bin/python -c '...'")` 验证。

---

## 反例（agent 实际犯过的错）

### 反例 1：早上 5 张图入库（2026-06-26 早上）

**错误链路**：
1. 图片进来 → `vision_analyze`（浪费 Hermes gateway 配额）→ zai MCP（zai 余额 1113）→ minimax MCP
2. 看到 vision 报「JS-002」「ZO-001」→ 直接抄进归档文件名
3. 用户说「就这些」→ 准备重跑 5 个后台，没核对是不是新批次
4. 用户说「选 3」→ 跑去 health check

**正确链路**：
1. 图片进来 → `cp` 到 `image/portfolio_*_unknown.jpg`（不猜 product_code）
2. 后台启 5 个 pipeline
3. 等 notify
4. 汇总：OCR 完从 MongoDB 查实际 product_code

### 反例 2：失败后立即合并临时处理 + 长期方案

**错误**：
```
2 张失败了。
我建议你用 --max-concurrent=4 长期修复。
跑吗？
```

**正确**：
```
阶段 1：2 张失败了。临时处理：
  1. 顺序重跑这 2 张
  2. 跳过这 2 张
  3. 手动入库
你说选哪个。

（等用户选 + 验证完）

阶段 2：复盘。
- 根因分析
- 三个长期修复方案 + 风险
你说改哪个。
```

---

## 参考

- SKILL.md 顶部「📌 Agent 反模式清单」摘要
- `references/image-failure-postmortem.md` — 实际反例 1 的完整复盘
