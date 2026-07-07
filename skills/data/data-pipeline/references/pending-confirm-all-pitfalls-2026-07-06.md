# `--confirm-all` 副作用 & pending 处理新坑（2026-07-06 实战 + 2026-07-07 续）

> 本文件补充 `image-pipeline-workflow.md` P6 段。2026-07-06 入库 21 张持仓截图时发现 3 个 P6 没覆盖的副作用，全部记录。2026-07-07 入库 6 张图又发现 2 个新坑 — OCR 把 trade 数据 product_code 截断（无 pending CSV 路径），以及 `status='skip'` 在 `--confirm-all` 下被脚本静默忽略。

## P10. `--confirm-all` 会把 CSV 里所有 `pending_review` + `missing_master` 一起放行（2026-07-06 实战）

**症状**：用户说"先处理京东方A 那 3 行"，`--confirm-all --name-mapping '{"000725.SZ": "京东方Ａ"}'`，结果 CSV 里 `002244.SZ 巨星科技` 和 `603368.SH 柳发股份` 也一并入了 MongoDB —— 用户没要求处理这两行。

**根因**：`--confirm-all` 是 CSV 级别的"全放行"开关，对所有非空 Wind code 的 pending 行一律入库。`--name-mapping` 只决定 `asset_name` 字段值，**不决定**"哪些行要入库"。

**反模式（不要这样做）**：
```bash
# ❌ --confirm-all 会把 CSV 里所有待确认行一并入库
load_pending_confirmed.py --csv X --name-mapping '{"000725.SZ": "京东方Ａ"}' --confirm-all
```

**正确处理（精细控制）**：

```bash
# 方案 A：分两步（默认行为不加 --confirm-all，只入「resolved」/空状态）
# CSV 里 192605 / 192615 / 193310 都是「自动可入」+ 1 行 pending_review 的混合
# 不加 --confirm-all 时：自动行入库，pending_review 拦截
load_pending_confirmed.py --csv X --name-mapping '{"000725.SZ": "京东方Ａ"}'

# 方案 B：sed 过滤 CSV，把不要的行 status 改成 'skip'
sed -i 's/pending_review/skip/g' X.csv   # 该行不被脚本读
load_pending_confirmed.py --csv X --name-mapping '{...}' --confirm-all
```

**判定规则**：
- CSV 里有 **单一品种待确认**（如只有京东方A）→ 不用 `--confirm-all`，默认行为自动通过
- CSV 里有 **多种待确认且只想入一种** → 必须 sed 改其他行状态为 `skip`
- CSV 里有 **多种待确认且全部要入** → `--confirm-all` 合适

## P11. `--name-mapping` 给 `missing_master` 也会写入 `asset_name`，造成"幽灵记录"（2026-07-06 实战）

**症状**：用户对 `001248.SZ 华润新能源` 的处置是"暂不处理，等用户确认"。但我跑 192550/193257 的 `--confirm-all --name-mapping '{"001248.SZ": "华润新能源"}'` 时，001248 这行（missing_master）**也被入库了**，asset_name 用 mapping 覆盖成"华润新能源"。

**根因**：
1. `--name-mapping` 解决的是"OCR 名字和主数据名不一致 → 强制用 mapping"问题
2. `--confirm-all` 解决的是"status=pending_review/missing_master → 强制放行"问题
3. 两者叠加 = missing_master 行被入库 + asset_name 被覆盖 + wind_code 保持 OCR 错值（如 001248.SZ）
4. 即使主数据 stock_basic_info 里**根本没有** 001248.SZ，仍然写进 MongoDB

**反模式**：
```bash
# ❌ 给 missing_master 行传 name-mapping = 默认该行入库 + asset_name 被覆盖
load_pending_confirmed.py --csv X --name-mapping '{"001248.SZ": "华润新能源"}' --confirm-all
```

**正确处理 — missing_master 行必须先 sed 改 wind_code**：

```bash
# 1. 先确认真实 wind_code（用主数据查 + 用户确认）
# 2. sed 改 CSV 里的 wind_code 字段
sed -i 's/001248\.SZ/<真实代码>.SH/' X.csv
# 3. 再跑 name-mapping 覆盖 asset_name + --confirm-all
load_pending_confirmed.py --csv X --name-mapping '{"<真实代码>.SH": "<真实名>"}' --confirm-all
```

**审计要求**：sed 改 CSV 字段必须留痕（与 P6a 一致）。

## P12. 同一 CSV 在「pipeline partial_success」+「--confirm-all」下会被处理两次（2026-07-06 实战）

**症状**：193310 CSV 里京东方A + 巨星科技 + 柳发股份 3 行。pipeline 第一次跑（partial_success）已经把这些 pending 行写进 CSV。我后来 `--confirm-all` 入库，**pipeline 之前是否已经入库过**这 3 行不可见 —— 默认假设没入 → 重复入库。

**根因**：CSV status 字段是审计文件，不是入库 truth；多次跑 `--confirm-all` 会重复触发 unique key upsert（idempotent）但浪费 OCR 配额 + audit 噪声。

**正确处理 — 入库前先查 MongoDB**：

```bash
# 用 PortfolioMongoLoader 反查 (position_date, product_code, asset_wind_code) 是否已存在
PYTHONPATH=... .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
for code in ['688808.SH', '300274.SZ']:
    cnt = db['portfolio_position'].count_documents({'position_date': '2026-07-01', 'asset_wind_code': code})
    print(f'{code} 7/1: {cnt}')
"
```

**判定**：
- 已有 → 不需要再入库（除非 wind_code 错了要覆盖更新）
- 没有 → 跑 `--confirm-all` 入库

## P13. Wind code 错误修复必须 sed 改 CSV + 删 MongoDB 旧记录（2026-07-06 实战）

**场景**：OCR 把 688808 读成 688008（错一位）。CSV 里是 688008.SH 联讯仪器，MongoDB 也存了 688008.SH 联讯仪器（错记录）。修复：

```bash
# 1. sed 改 CSV wind_code
sed -i 's/688008\.SH/688808.SH/g' X.csv

# 2. 删 MongoDB 旧记录（unique key = (position_date, product_code, asset_wind_code)）
PYTHONPATH=... .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
res = db['portfolio_position'].delete_many({
    'asset_wind_code': '688008.SH',
    'position_date': '2026-07-01',
    'product_code': 'SM004'
})
print(f'删除: {res.deleted_count}')
"

# 3. 再跑入库（用新 wind_code）
load_pending_confirmed.py --csv X.csv --name-mapping '{"688808.SH": "联讯仪器"}' --confirm-all
```

**反模式**：
- ❌ 只改 CSV 不删 MongoDB → 旧错记录永久留存
- ❌ 直接 update MongoDB 改 wind_code → 绕开 pipeline 审计
- ❌ 不改 CSV 直接 update_many → CSV 字段和 DB 字段不一致

## P14. stock_basic_info 字段名是 `full_symbol` 不是 `code`（2026-07-06 实战三次踩坑）

```python
# ❌ 错 — code 字段不存在
db['stock_basic_info'].find_one({'code': '688808.SH'})  # → None

# ✅ 对 — 用 full_symbol（带 .SH/.SZ 后缀）
db['stock_basic_info'].find_one({'full_symbol': '688808.SH'})
```

**完整字段（实测）**：`full_symbol / symbol / name / industry / list_date / market / area / category / pe / pb / ps / total_mv / circ_mv / total_share / float_share / turnover_rate / volume_ratio / source / updated_at`

---

## P15. OCR trade 数据 product_code 截断 — 必须 MongoDB update_many 修正，无 pending CSV 路径（2026-07-07 实战）

**症状**：trade 截图（不是 portfolio 截图）的 `产品代码` 列被 OCR 误读，`SM003` → `SM03`、`SM004` → `SM04`（OCR 把 trailing digit `00` 当多余字符丢掉）。入库后 `portfolio_trade` 里出现 `SM03` (13 行) + `SM04` (8 行) 这些 **系统不存在的 product_code**。系统里只有 `SM001 / SM002 / SM003 / SM004 / SM012` 这 5 个。

**根因 — 与 portfolio pipeline 的关键区别**：trade 截图的 OCR 输出**没有 pending CSV 路径**。`run_unified_image_pipeline.py` 只在 portfolio 行 `asset_name` 与主数据不匹配时才写 pending.csv；trade 数据直接 upsert 入库，**没有 audit 追踪**。所以你看不到"13 行 trade 被误识别"的报告，必须靠 MongoDB 聚合反查才能发现。

**正确诊断 — trade 入库后必查一遍 product_code**：

```bash
PYTHONPATH=... .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
# 列出所有 trade product_code，对比基础 5 个
KNOWN = {'SM001', 'SM002', 'SM003', 'SM004', 'SM012'}
for pc in sorted(db['portfolio_trade'].distinct('product_code')):
    flag = '🚨' if pc not in KNOWN else ''
    n = db['portfolio_trade'].count_documents({'product_code': pc})
    print(f'{flag} {pc}: {n} 条')
"
```

**修正路径 — 直接 MongoDB update_many**（trade 没有 pending CSV 审计，复用 `load_pending_confirmed.py` 不通）：

```bash
PYTHONPATH=... .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
r1 = db['portfolio_trade'].update_many({'product_code': 'SM03'}, {'\$set': {'product_code': 'SM003'}})
r2 = db['portfolio_trade'].update_many({'product_code': 'SM04'}, {'\$set': {'product_code': 'SM004'}})
print(f'SM03 → SM003: matched={r1.matched_count}, modified={r1.modified_count}')
print(f'SM04 → SM004: matched={r2.matched_count}, modified={r2.modified_count}')
"
```

**反模式**：
- ❌ 跑 `load_pending_confirmed.py --csv trade_pending.csv` — trade 数据没有这个 CSV
- ❌ 直接重跑 pipeline — 浪费 OCR 配额，且 unique key upsert 只更新数字不更新 product_code
- ❌ 信任 pipeline 的 audit report — trade partial_success 不会写 audit 文件

**审计要求**：update_many 必须在 `/tmp/pending_csv_audit_<date>.md` 或专门的 trade_fix 审计文件留痕，记录 `date / product_code_old / product_code_new / matched / modified / reason`（用户原话确认）。

**长期修复（待办）**：OCR provider 在 trade pipeline 里加 product_code 后置校验 — 如果读到非 `SMxxx` 格式、或者长度不对（`SM03` 只有 4 位），自动 raise 或归类为 pending。这条目前没有，本会话还是手动 update_many。

---

## P16. `status='skip'` 在 `--confirm-all` 下被脚本静默忽略 — 真要跳过某行必须 delete_many 或 sed 改 wind_code 到有效值（2026-07-07 实战）

**症状**：我想跳过 `001248.SZ 华润新能源`（stock_basic_info 没这个 code）不写入 MongoDB，于是 `sed -i 's/missing_master/skip/' X.csv`，期望 `--confirm-all` 时脚本只跳过 skip 行。但实际跑完后 MongoDB 仍然有 `001248.SZ + 2026-07-06 + SM004 = 华润新能源` 这条记录。`load_pending_confirmed.py --confirm-all` 没看 `status='skip'` 字段，对**任何非空 wind_code 行**一律入库。

**根因**：`load_pending_confirmed.py` 的"哪些行入库"判定只基于 wind_code 是否非空，不读 CSV 的 `名称复核状态` 列。`--confirm-all` 实际只是"不依赖 status 字段强制入库"的开关。**'skip' 状态是个 actor's promise，但脚本没有 enforcement**。

**反模式**：
```bash
# ❌ sed 把 status 改成 skip 来"防入库" — 脚本忽略这个状态
sed -i 's/missing_master/skip/' X.csv
load_pending_confirmed.py --csv X.csv --confirm-all
# 结果：该行照样入库；agent 误以为"已跳过"
```

**正确处理 — 真要跳过某行**：

```bash
# 方案 A：入库后再从 MongoDB delete_many（麻烦但准确）
PYTHONPATH=... .venv/bin/python -c "
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
res = db['portfolio_position'].delete_many({
    'asset_wind_code': '001248.SZ',
    'position_date': '2026-07-06',
    'product_code': 'SM004'
})
print(f'删除: {res.deleted_count}')
"

# 方案 B：把 wind_code 改成实际不存在但合法的占位（不推荐，可能被认成另一只股票）

# 方案 C：彻底从 CSV 物理删除该行（最干净）
sed -i '/001248\.SZ/d' X.csv
load_pending_confirmed.py --csv X.csv --confirm-all
```

**判定规则**：
- 想跳过某行 → **sed 删除 CSV 该行**（方案 C），不要依赖 status 字段
- user 已确认该行 wind_code 是真的 → `--name-mapping` + `--confirm-all` 入库，接受幽灵记录（接受 P11 风险）
- user 已确认是误读 → sed 改 wind_code 到真实值，再入库

**长期修复（待办，本会话没动）**：

1. `load_pending_confirmed.py` 增加 `status='skip'` 识别 — 跳过这些行（不论 `--confirm-all` 与否）
2. 在 batch_report 里多打一行"CSV 中 status='skip' 的行：N（脚本会强制入库，skip 是 agent 自承诺）"，让用户明确知道

---

## 本次会话新增的 stock_name_corrections（2026-07-06 + 07-07 实测）

| OCR 错 | 正确 | 来源 |
|---|---|---|
| `688347.SH` 资产名"华虹宏济" | `688347.SH` → "华虹宏力" | SM004 trade 6/30 |
| `688008.SH` → `688808.SH` 联讯仪器 | `688808.SH` 联讯仪器 | SM004 portfolio 7/1, 7/3, **7/6（07-07 证实）** |
| `600274.SH` → `300274.SZ` 阳光电源 | `300274.SZ` 阳光电源 | SM002 trade 7/1 |
| `002244.SZ` → `002444.SZ` 巨星科技 | `002444.SZ` 巨星科技 | SM002 portfolio 7/3 |
| `603368.SH` → `603268.SH` 松发股份 | `603268.SH` 松发股份 | SM002 portfolio 7/3 |
| **`001399.SZ` 资产名"惠利股份"** | `001399.SZ` → "N惠科股份" | SM004 portfolio **7/6（07-07 证实）** |
| **`000725.SZ` 资产名"京东方A"（半角）** | `000725.SZ` → "京东方Ａ"（全角）| SM002 portfolio **7/6（07-07 证实）** |

**已知 corrector 不生效的 case（2026-07-07 证实，需要排查）**：`stock_name_corrections.py` 里**已经配置**了 `000725.SZ → 京东方Ａ` 的全角映射，但 7/6 新图 OCR 仍读成半角 A，进入 pending.csv。说明 corrector 在 portfolio pipeline 的执行时机或调用路径有问题，**下一步要排查 corrector 实际加载和执行位置**。

**长期修复（已知 trade 数据 5 个产品对应 SM001/SM002/SM003/SM004/SM012）**：

1. **加入 `stock_name_corrections.py`**：把上面 7 行新映射全部加入。这是永久 fix，对新图立即生效。
2. **修正 OCR trade product_code 截断 bug**：OCR provider 在 trade pipeline 增加 post-OCR 校验，把 `SMxx` 长度异常的纠正（虽然不保证 100% 准确，至少标记出来）。
3. **`stock_basic_info` 补全 `001248.SZ`**：如果用户确认 001248 是有效代码（新股或长期使用），需要补建 stock_basic_info 主数据记录。否则 001248 在 portfolio_position / portfolio_trade 永远是幽灵记录，不能 join。
4. **`load_pending_confirmed.py` skip 状态支持** — 见 P16 待办。

## 本次会话待用户确认的 long-term 项

1. **`001248.SZ 华润新能源`**：已入库 7/6 SM004 portfolio（幽灵记录）+ 历史 6/24-6/29 数据。stock_basic_info 主数据查不到。可能是：(a) 用户长期使用的非标准代码，需要保留；(b) OCR 误读，正确代码未确认；(c) 新股上市，主数据未及时入库。**当前 2026-07-07 已入库确认**，等用户最终决定删除 / 保留 / 补建主数据。
2. **wind_code 错位映射**（688008↔688808 / 600274→300274 / 002244→002444 / 603368→603268）：pipeline OCR 改进 / 加 OCR 后置校验。
3. **skill update 落实**：把上面 7 行新映射加入 `stock_name_corrections.py`。
4. **`load_pending_confirmed.py` skip 状态支持**（P16）。
