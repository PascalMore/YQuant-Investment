# 图片入库多批推送实战（2026-06-27）

## 场景

用户分多批推送同一批持仓截图到飞书：

| 推送时间 | image_cache 文件数 | unique hash | pipeline 实际跑过 |
|---|---|---|---|
| 09:46~09:47 | 18 张 | 18 个 | 第一轮 10 个后台任务（跑 0949 序列前 10 张）|
| 10:02 | 9 张 | 9 个（第一轮 9:46-50 子集）| 第二轮"重跑"，9 个全部入库 |
| 10:10 | 9 张 | 9 个（第一轮 9:47-33 子集）| **第三轮，9 个全部入库** |

**关键认知：image_cache unique hash 总数（60）= 三批去重后的全集，但 pipeline 不是一次性跑完。** 仅凭"归档目录里有"不能说"全部入库"。

## 诊断方法

### Step 1: 看 image_cache 时间分布

```bash
for f in /home/pascal/.hermes/profiles/yquant/image_cache/img_*.jpg; do
  TS=$(stat -c '%y' "$f" | cut -c12-19)
  H=$(md5sum "$f" | awk '{print $1}')
  echo "$H $TS"
done | sort -k2,2
```

输出示例（看到 09:46 / 10:02 / 10:10 三个时间簇）：
```
1db53a40bf49bf8adc38742d00c3b257 09:46:48
30d6cdac9533586347f1fa54c65e66e7 09:47:33
a70a46b94a2a42c39af3ce206bffbf0f 10:02:24
27bf7c249ff5bbbbc7e47f4edcb3e93f 10:10:40
```

### Step 2: 看每批的 hash 子集

```bash
# 早 09:46~09:47（18 张）vs 10:02（9 张）vs 10:10（9 张）的 hash 差集
```

**常见模式**：
- 10:02 是 09:46 的 9 张子集（同一批的部分重推）
- 10:10 是 09:47 的 9 张子集（同一批的另一部分重推）

### Step 3: 看归档目录 + pipeline 痕迹

```bash
ARCHIVE_DIR=/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/2026-06-27/image

# 归档图（已 cp 过去的）
md5sum "$ARCHIVE_DIR"/portfolio_*.jpg | awk '{print $1}' | sort -u | wc -l

# pipeline 跑过 = 留下了同名 xlsx / vision_raw
ls "$ARCHIVE_DIR"/*.xlsx | wc -l
ls "$ARCHIVE_DIR"/*vision_raw*.json | wc -l
ls "$ARCHIVE_DIR"/*vision_error*.json | wc -l
```

### Step 4: 辅助脚本

`scripts/check_pending_pipeline_runs.py` 输出决策矩阵（hash 匹配 × xlsx 痕迹 × 跨日期 hash）。

**2026-06-27 晚间重大修复**：脚本从"启发式 80% 阈值"改为"逐张 jpg 时间戳窗口 + 跨日期 hash 查找"。修复前报"73 张未跑"（误判），修复后报"8 跑过 + 39 跨日期重复 + 28 真实未跑"。

### Step 5: 跨日期 hash 查找（关键补充）

**场景**：归档目录里有 N 张图没 pipeline 产物，但用户说"不会有这么多没跑"。根因是**其他日期的图被复制到了今天**（飞书重复推送 / agent 归档时未去重 / watcher 跨日处理）。

```bash
# 把今天 archive 的 jpg hash 与所有其他日期目录比对
python3 -c "
import hashlib
from pathlib import Path
SM = Path('skills/data/source/smart-money')
today = '2026-06-27'
# 其他日期的 hash
other = set()
for d in SM.iterdir():
    if not d.is_dir() or d.name == today: continue
    img = d / 'image'
    if not img.exists(): continue
    for j in img.glob('*.jpg'):
        other.add(hashlib.md5(j.read_bytes()).hexdigest())
# 今天的 hash
arch = SM / today / 'image'
overlap = 0
for j in arch.glob('*.jpg'):
    h = hashlib.md5(j.read_bytes()).hexdigest()
    if h in other:
        overlap += 1
print(f'跨日期重复: {overlap} 张')
"
```

### `check_pending_pipeline_runs.py` 时间戳解析的坑（2026-06-27 实战）

Pipeline 文件命名有 4 种格式，HHMMSS 提取各有坑：

| 文件类型 | 命名示例 | HHMMSS 位置 | 坑 |
|---|---|---|---|
| jpg（归档） | `portfolio_2026-06-27_201808.jpg` | 末尾 `_HHMMSS` | 末尾 6 位就是 HHMMSS，不要剥 `_NN`（jpg 没有） |
| jpg（归档） | `portfolio_20260627_201808.jpg` | 同上 | 同上，兼容 YYYYMMDD 和 YYYY-MM-DD |
| xlsx（产物） | `portfolio_20260627_201858.xlsx` | `_YYYYMMDD_HHMMSS.xlsx` 的 HHMMSS | 不能用 `_(\d{6})` 贪婪匹配（会抓到 `202606` = YYYYMMDD 前 6 位） |
| xlsx（_NN） | `portfolio_20260627_201858_01.xlsx` | HHMMSS 在 `_NN` 之前 | `re.sub(r"(_pending|_\d+)$", "")` 会**误剥 HHMMSS**（6 位也是 `\d+`）→ 必须先验证剥后剩 6 位才是 HHMMSS |
| pending csv | `portfolio_20260627_201944_pending.csv` | `_pending` 之前 | 先剥 `_pending` 再取末尾 6 位 |
| vision_raw | `pic_20260627_035246_vision_raw.json` | `_vision_raw` 之前 | 先剥 `_vision_(raw|error|retry)` 再取末尾 6 位 |

**HHMMSS 整数差 ≠ 秒差**：`201858 - 201810 = 48` 是 48 秒（不是 48 分钟）。必须用 `hhmmss_to_seconds()` 转成当日秒数再算差值。

## 三件事必须分清

| 概念 | 含义 | 检测方法 |
|---|---|---|
| **image_cache** | 飞书推送的所有图（可能含重复推送的副本）| `ls /home/pascal/.hermes/profiles/yquant/image_cache/` |
| **归档目录** | agent 第一步 cp 过去的图（按 unique hash 去重）| `ls skills/data/source/smart-money/{date}/image/` |
| **pipeline 跑过** | 留下了同名 xlsx 和 vision_raw json | `ls skills/data/source/smart-money/{date}/image/*.xlsx` |

**反例**：
- 仅凭"归档目录里有"回复用户"全部入库"
- 看到归档 unique hash 数 == image_cache unique hash 数就说"已处理完"

## MongoDB 业务日期字段实际类型 = 字符串

`portfolio_position.position_date` / `portfolio_nav.nav_date` / `portfolio_trade.trade_date` 在 MongoDB 里**实际类型是 `str`**（如 `'2025-07-07'`），不是 BSON datetime。

**症状 1**：用 `datetime.date(2025,7,7)` 做 `\$gte` 报 `bson.errors.InvalidDocument`
**症状 2**：用 `datetime.datetime` 做范围查询 → 返回 0 行（datetime > str）
**症状 3**：从查询结果读 `.day` → AttributeError

**正确查询模板**：

```python
DATES = [f'2025-07-{d:02d}' for d in range(1,16)]
db['portfolio_position'].find({'position_date': {'$in': DATES}}, ...)

# 取日期部分用字符串切片
for r in cursor:
    day = int(r['position_date'][-2:])  # '2025-07-07' → 7
```

## OCR 噪声：全角括号 `市值（本币）`

`load_pending_confirmed.py` 按精确列名读 CSV，OCR 输出 `市值（本币）`（全角括号）时 loader KeyError，结果 `loaded=0` 静默失败。

**症状**：`Result: format=portfolio, loaded=0, nav_loaded=0, records=0  ERROR: Row 0: '市值(本币)'`

**临时修复（仅针对当天这一行）**：
```bash
sed -i 's/市值（全币）/市值(本币)/g' skills/data/source/smart-money/{date}/review_pending/<file>_pending.csv
PYTHONPATH=skills/data/data-pipeline/scripts .venv/bin/python \
  skills/data/data-pipeline/scripts/load_pending_confirmed.py \
  --csv skills/data/source/smart-money/{date}/review_pending/<file>_pending.csv \
  --confirm-all
```

**长期方案（待用户拍板）**：写 `stock_name_corrections.py` 永久映射，让 OCR 噪声自动归一化。