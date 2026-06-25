# Image Pipeline 入库实战笔记

> 本文件记录 `data-pipeline` 在 YQuant 项目中跑通 Smart Money 图片入库的**真实会话经验**——SKILL.md 里的 3 个日期概念、孤儿 CSV 现象、字段名陷阱等，都来自 2026-06-25 / 26 两次完整跑通。

## 完整流程（实测版）

```
用户发图 → agent 归档（archive_date）→ 跑 pipeline（business_date）→ review_pending → 用户审 → load_pending_confirmed
```

### 步骤 1：归档图片（agent 必做）

```bash
# 归档日期 = 今天，不是图片业务日期
ARCHIVE_DATE=$(date +%Y-%m-%d)
IMAGE_DIR="/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image"
mkdir -p "$IMAGE_DIR"
cp <用户截图本地路径> "$IMAGE_DIR/portfolio_<product>_<archive_date>_<HHMMSS>.jpg"
```

**注意**：
- 命名 `<product>` 字段从图片内容识别（截图里的"产品代码"列）— agent 应当读完图后再命名
- 同一批次的多张图（5 个产品）放同一个目录，命名带产品码便于回溯

### 步骤 2：跑 pipeline

```bash
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image "<归档后路径>" \
  --date <业务日期 YYYY-MM-DD>
```

**实操**：
- **一次一张**（≥3 张图不要后台批量，详见 SKILL.md "批量图片并行处理模式"）
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
| **业务日期** (business_date) | `--date` 入参 + MongoDB 字段 | 入库数据时间错乱 |
| **系统日期** (system_date) | pipeline 内部用，可能跨日 | 不影响主流程 |

**用户 2026-06-25 23:17 发图，业务日期 2026-06-24**：
- ❌ 错误归档：`source/smart-money/2026-06-25/image/` （我误用的）
- ✅ 正确归档：`source/smart-money/2026-06-26/image/` （系统日期）

### P3. "孤儿 CSV" 现象

**实战数据**（2026-06-26）：44 行历史 pending CSV 中 **42 行（95.5%）实际已在 MongoDB**。

**原因**：
- pipeline 早期版本可能直接入库但不回填 CSV 状态字段
- JSON `status` 字段也会滞后
- CSV 状态列 = 审计文件，不应作为"是否入库"的判定

**正确判定**：用 `scripts/audit_pending_unmigrated.py` 跨 CSV + MongoDB 核对。

### P4. clarify 工具偶发 user_response 格式异常

`clarify` 工具偶发返回 `user_response: "<其他回答>"` 但不包含 choices 选项——UI 弹不出选项。

**回退方案**：直接用文字提问列出关键决策点，**不依赖** clarify。

## 命令模板

### 单图入库完整流程（5 行命令）

```bash
# 1. 归档
ARCHIVE_DATE=$(date +%Y-%m-%d)
mkdir -p "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image"
cp /tmp/user_screenshot.jpg "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image/portfolio_SM001_${ARCHIVE_DATE}_$(date +%H%M%S).jpg"

# 2. 跑 pipeline
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment \
  .venv/bin/python \
  skills/data/data-pipeline/scripts/run_unified_image_pipeline.py \
  --image "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/${ARCHIVE_DATE}/image/portfolio_SM001_${ARCHIVE_DATE}_*.jpg" \
  --date 2026-06-24

# 3. 验证入库
cd /home/pascal/workspace/yquant-investment && \
  PYTHONPATH=/home/pascal/workspace/yquant-investment:/home/pascal/workspace/yquant-investment/skills/data/data-pipeline/scripts \
  .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
print(db['portfolio_position'].count_documents({'position_date': '2026-06-24'}))
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

### 审计所有 pending 状态

```bash
.venv/bin/python skills/data/data-pipeline/scripts/audit_pending_unmigrated.py
```

输出 4 类：
- ✅ 已在 DB（可归档 CSV 到 review_resolved/）
- ❌ 孤儿 CSV（CSV resolved 但 DB 无，需 confirm-all 重试）
- ⏸ 待人工复核（pending_review/missing_master）
- 🚫 Wind 代码空（无法入）
