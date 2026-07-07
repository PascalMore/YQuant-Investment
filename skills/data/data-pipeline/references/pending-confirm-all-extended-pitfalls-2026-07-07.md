# `--confirm-all` 续坑 & trade / skip 状态新坑（2026-07-07 实战）

> 本文件补充 `references/pending-confirm-all-pitfalls-2026-07-06.md`（P10-P14）。2026-07-07 入库 6 张图（5 portfolio + 1 trade），发现 3 个新坑，全部记录。**核心新增 P15/P16/P17**。

## P15. OCR trade 数据 `product_code` 末位 `0` 截断（2026-07-07 实战）

**症状**：用户 7/7 发了 1 张 trade 截图（5 个产品共 17 行），入库后查 MongoDB 发现 `portfolio_trade` 里多了 `SM03` (13 行) 和 `SM04` (2 行) 两个**系统不存在的产品代码**。

**根因**：OCR 把 `SM003` 末位 `0` 丢了，读成 `SM03`。同样 `SM004` → `SM04`。trade 截图只有 `(截止日期, 产品代码, 产品名称, Wind代码, ...)` 单布局，OCR 在长字符串末尾看错位的概率高于 portfolio 截图。

**MongoDB trade 集合受影响**（2026-07-07 修复前）：
- SM03 trade: 13 条（2026-07-06 当日）
- SM04 trade: 8 条（跨历史日期）
- SM003 历史正常: 1182 / SM004 历史正常: 1159

**反模式**：`load_pending_confirmed.py` 处理 trade 表需要 CSV 是 trade 格式 — 但 OCR 不会把 trade 截图输出为 trade CSV（因为 product_code 是错的，会进 missing_master，但 trade 路径不同）。所以 **trade 数据无 pending CSV 路径**。

**正确处理 — 直接 MongoDB `update_many` 修正**：

```python
from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
r1 = db['portfolio_trade'].update_many({'product_code': 'SM03'}, {'$set': {'product_code': 'SM003'}})
r2 = db['portfolio_trade'].update_many({'product_code': 'SM04'}, {'$set': {'product_code': 'SM004'}})
```

**为什么 unique key 不冲突**：`portfolio_trade` 的 unique key 是 `(trade_date, product_code, asset_wind_code, direction)`。把 `SM03` 改成 `SM003` 之前该 trade_date + SM003 + asset + direction 不存在，所以改 product_code 不触发冲突，幂等安全。

**判定触发**：用户发图批量跑完 → `db['portfolio_trade'].distinct('product_code')` 比对系统已知产品代码清单（`SM001/SM002/SM003/SM004/SM012/CCT-001`）→ 出现清单外的值 = OCR 截断。

**长期方案**：
1. `MiniMaxVisionExtractor` prompt 加 `"产品代码必须保留所有字符（如 SM003、SM004 末尾的 0 不能丢）"`
2. product_code normalize 时校验 `in KNOWN_PRODUCT_CODES`，错的标 missing_master

**⚠️ 与 portfolio 路径区别**：portfolio 截图 OCR 也会读错 product_code（如 `SM003` → `SM03`），但 portfolio 表会先生成 pending CSV（含 missing_master 行），可以用 `--name-mapping` + `delete_many` + `--confirm-all` 处理（虽然同样产生幽灵记录）。trade 路径**完全跳过** CSV 生成，所以必须用 MongoDB `update_many`。

## P16. `status='skip'` 在 `--confirm-all` 下被脚本忽略（2026-07-07 实战）

**症状**：用户想跳过 SM004 的 `001248.SZ 华润新能源`（missing_master）— 我 `sed -i 's/missing_master/skip/g'` 改 CSV status 为 `skip`，但 `--confirm-all --name-mapping` 跑完后这条记录**仍然入库了 MongoDB**。

**根因**：`load_pending_confirmed.py` 的状态机硬编码 `pending_review`/`missing_master` 才拦截。`skip`/`rejected`/`ignore` 状态不在拦截列表里。`--confirm-all` 等于「CSV 里所有非空 Wind code 的行一律入库」，不认 `skip`。

**反模式**：
```bash
# ❌ sed 改 status='skip' 不能阻止 --confirm-all 入库
sed -i 's/missing_master/skip/g' pending.csv
load_pending_confirmed.py --csv X --name-mapping '{...}' --confirm-all
# → 幽灵记录照样入库
```

**正确处理（按场景）**：

**A. 真要跳过（不入库）— 从 CSV 物理删除该行**：
```bash
sed -i '/001248\.SZ/d' pending.csv   # 物理删除该行
load_pending_confirmed.py --csv X --name-mapping '{...}' --confirm-all
```

**B. 真要替换 — 必须先 `delete_many` 旧库再入库**：
```python
# 1. 看 MongoDB 有没有该记录
n = db['portfolio_position'].count_documents({
    'position_date': '2026-07-06',
    'asset_wind_code': '001248.SZ',
    'product_code': 'SM004'
})
# 2. 真要替换就 delete_many
db['portfolio_position'].delete_many({...})
# 3. 然后 --confirm-all 入库
```

**触发场景**：
- 用户报「这行忽略」+ CSV 里又确实有这行 → 默认要被 `--confirm-all` 拦截是不可能的
- 用户报「这行替换 wind_code」+ 改 CSV → 还必须清 MongoDB 旧记录

**长期修复（脚本 bug）**：
- `load_pending_confirmed.py` 应把 `status='skip'/'rejected'/'ignore'` 视为跳过
- 当前没改（需用户决策是否承担 ghost record 默认行为的破坏性变更）

## P17. P11 + P16 叠加 = 幽灵记录更容易产生（2026-07-07 实战根因汇总）

**幽灵记录产生的两个根因常一起出现**：

1. **P11** — `--name-mapping` 给 missing_master 行 → asset_name 被覆盖
2. **P16** — `status='skip'` 不识别 → `--confirm-all` 强制入库

**叠加效果**：missing_master + `--confirm-all --name-mapping` + 改 `status='skip'` 想跳过 → 失败，依然入库。

**完全免疫的最小变更路径（不修脚本 bug）**：
1. `delete_many` 旧记录（如有）
2. `sed -i '/<key>/d' CSV` 物理删除该行
3. `--confirm-all --name-mapping` 入库剩余行

或直接 `update_many` + `replace_one`，不走 `load_pending_confirmed.py`。

## 本次会话新增的 stock_name_corrections（2026-07-07 实测）

| OCR 错 | 正确 | 来源 |
|---|---|---|
| `000725.SZ` OCR `京东方A`（半角）| `京东方Ａ`（全角）| 关键修复：`a_share_name_corrector.py` 加 NFKC 归一化 |
| `688008.SH` 联讯仪器 OCR 误读代码 | `688808.SH` 联讯仪器 | 用户确认后用 sed 改 CSV + sed 改 DB |
| `001399.SZ` 惠利股份（旧名/形近字误读）| `N惠科股份` | corrector 不兼容形近字，必须手动确认改名 |
| `001248.SZ` 华润新能源 | 主数据无此代码 | 用户保留为幽灵记录（按 a 选项）|

## 关联参考

- `references/fullwidth-halfwidth-unicode-normalization.md` — 全角/半角字符漂移根因 + NFKC 修复（2026-07-07 同会话）
- `references/pending-confirm-all-pitfalls-2026-07-06.md` — P10-P14（先文档）
- `references/portfolio-mongo-schema.md` — `portfolio_trade.distinct('product_code')` 全集查询
