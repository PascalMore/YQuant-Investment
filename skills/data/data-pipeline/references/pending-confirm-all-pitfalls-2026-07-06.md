# `--confirm-all` 副作用 & pending 处理新坑（2026-07-06 实战）

> 本文件补充 `image-pipeline-workflow.md` P6 段。2026-07-06 入库 21 张持仓截图时发现 3 个 P6 没覆盖的副作用，全部记录。

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

## 本次会话新增的 stock_name_corrections（2026-07-06 实测，待加入 `scripts/stock_name_corrections.py`）

| OCR 错 | 正确 | 来源 |
|---|---|---|
| `688347.SH` 资产名"华虹宏济" | `688347.SH` → "华虹宏力" | SM004 trade 6/30 |
| `688008.SH` → `688808.SH` 联讯仪器 | `688808.SH` 联讯仪器 | SM004 portfolio 7/1, 7/3 |
| `600274.SH` → `300274.SZ` 阳光电源 | `300274.SZ` 阳光电源 | SM002 trade 7/1 |
| `002244.SZ` → `002444.SZ` 巨星科技 | `002444.SZ` 巨星科技 | SM002 portfolio 7/3 |
| `603368.SH` → `603268.SH` 松发股份 | `603268.SH` 松发股份 | SM002 portfolio 7/3 |

**长期修复**：把 `688347.SH → 华虹宏力` 加入 `scripts/stock_name_corrections.py`。`688008.SH ↔ 688808.SH` 涉及代码错位，无法用名称映射处理，只能靠 pipeline OCR 改进或人工核图。`600274.SH / 002244.SZ / 603368.SH` 是代码错位（数字错读），同样只能人工核图。

## 本次会话待用户确认的 long-term 项

1. **`001248.SZ 华润新能源`**：5 行 portfolio + 2 行 trade，stock_basic_info 主数据查不到。可能是：(a) 用户长期使用的非标准代码，需要保留；(b) OCR 误读，正确代码未确认；(c) 新股上市，主数据未及时入库。当前已入库到 MongoDB（含历史 6/24-6/29 数据），等用户确认处置。
2. **wind_code 错位映射**（688008↔688808 / 600274→300274 / 002244→002444 / 603368→603268）：pipeline OCR 改进 / 加 OCR 后置校验。
3. **skill update 落实**：把上面 5 行新映射加入 `stock_name_corrections.py`。