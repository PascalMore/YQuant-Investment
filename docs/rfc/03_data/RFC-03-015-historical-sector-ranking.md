# RFC-03-015: 简化历史行业 sector.ranking — 按交易日查询的板块日涨跌幅排名

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.5 修订：T2.11 文档修正 — §5.6.3 冻结表新增成功完整 ranking 行（`completeness:complete, materialized:ok`）；§5.6.2 成功行补充物化语义与成功 trace；元数据关联 Design 指针更新为 `DESIGN-03-015-historical-sector-ranking.md (V0.5)`，三层版本指针同步。V0.4 修订保留：T2.9 source_trace 枚举闭合 — §5.8.2 `completeness` 枚举补齐为 `{complete|incomplete|empty}`，`materialized` 枚举收敛为 `{ok|miss}`，删除并明确禁止未使用的 `skipped`；§5.6.3 冻结约束补充枚举封闭声明，Category 1~4 语义唯一。V0.3 修订保留：T2.7 契约纠偏 — 新增 §5.6.3 结果语义冻结表，消除"数据完整性失败返回 error 还是 empty + warning"的二义性；4 类情形（参数非法 / 读集合无记录 / build 完整性失败 / build 零有效行）结果类型与稳定 warning token 唯一冻结，三文档一致。V0.2 修订保留：G-01 完整性语义改为 100% exact-match，expected universe 显式传入不硬编码；G-02 收紧第一版实现范围，明确 TA-CN 聚合/SW 常量表/realtime 检测/Provider 改动均不在第一版离线实现。对齐 Design Gate REVISE 反馈。） |
| 版本号 | V0.5 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-014（Unified Data Phase 3 主 RFC）、RFC-03-014-p3a-sector-provider-activation（P3-A Sector Provider 激活，V0.2）、RFC-03-007（Unified Data Layer 总纲） |
| 依赖 SPEC | SPEC-03-015-historical-sector-ranking（本 RFC 对应之 SPEC，V0.5） |
| 关联 Design | DESIGN-03-015-historical-sector-ranking.md（V0.5） |
| 替代 RFC | 无（不替代 P3-A 的 sector.ranking；为新增的按交易日查询历史能力，与现有实时 stub 隔离） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #sector #ranking #historical #ta_cn #sw2021 #daily |

---

## 1. 执行摘要

本 RFC 为 YQuant 数据层定义一个**新增的历史行业板块日涨跌幅排名能力**（capability `sector.ranking_history`），支持按交易日（`trade_date`）查询全行业板块的当日涨跌幅排名。该能力采用独立的新 Mongo namespace（`03_data_ud_sector_ranking_daily`）、极简的 9 字段行 schema、`dataset` 维度区分数据源与分类口径，以及固定的 close-to-pre_close 收益口径。第一版仅交付离线/fake/mongomock 可验证实现，所有生产 I/O 冻结。

**成功标准**：RFC + SPEC 两份独立文档存在且互相一致；不触发任何真实 I/O；T2 Design 拥有明确的输入边界与 T3 实施范围；语义不与用户冻结决策和现有 P3-A fake-only 基线冲突。

**关键边界**：本能力与现有 P3-A `sector.ranking`（实时快照 stub）是**两个独立能力**，不共享 collection、不共享 schema、不共享 unique key、不迁移、不回填。旧 collection 冻结不动。

---

## 2. 背景与动机

### 2.1 现状

当前 YQuant 数据层有两个 sector 相关 capability（P3-A 子链，RFC-03-014-p3a）：

| Capability | 数据性质 | Endpoint | Collection | Schema | Unique Key | 状态 |
|---|---|---|---|---|---|---|
| `sector.snapshot` | 实时单板块快照 | AKShare `name_em()` 过滤 | `03_data_ud_market_sector_snapshot` | SectorSnapshot 19 字段（12 列投影） | `{market, sector_code, snapshot_date}` | P1 fake-only stub（commit `1232028`） |
| `sector.ranking` | 实时全行业排名 | AKShare `name_em()` 全量 | `03_data_ud_market_sector_snapshot` | SectorSnapshot 19 字段（8 列投影） | `{market, sector_code, snapshot_date}` | P1 fake-only stub |

**核心限制**：

1. **无历史维度**：`name_em()` 返回实时排名，不含历史日期。`snapshot_date` 取 fetch 日期，无法回查"3 天前白酒行业排名第几"。
2. **schema 偏重**：SectorSnapshot 19 字段包含领涨股、涨跌家数、换手率、主力净流入等实时聚合字段，不适合存储为历史日线序列。
3. **无数据源隔离**：当前只有一个 provider（AKShare），无法区分"这是申万分类"还是"这是东财行业分类"。
4. **TA-CN SW 历史日线未利用**：TA-CN MongoDB 的 `index_daily_quotes` 集合已存储申万行业指数日线（`sector_code`/`trade_date`/`close`/`pct_chg`），但未被任何 capability 消费为历史排名。

### 2.2 业务价值

| 能力 | 消费方 | 价值 |
|---|---|---|
| 按交易日查历史行业排名 | researcher（行业轮动因子回测）、strategies（行业动量/反转策略历史回测）、reporter（历史板块复盘） | 获取任意历史交易日的申万一级行业涨跌幅排名，支撑因子研究和策略回测 |
| `dataset` 维度 | researcher（多数据源交叉验证） | 区分申万/东财/同花顺分类口径，避免混排 |

### 2.3 触发原因

用户（Pascal）明确要求：
1. 将"盘后排名"与"历史排名"合并为一个按交易日查询的历史能力，实时路径暂缓。
2. 第一版采用极简单集合设计，不做 run+item 两表。
3. 固定 close-to-pre_close 收益口径，禁止使用 close-to-open。
4. TA-CN 仅作只读上游候选，未经验证不得宣称可用。
5. 必须排除 TA-CN 的 realtime fallback 污染。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义新增 capability `sector.ranking_history` 的业务语义：按 `trade_date` 查询某 `dataset` 下全行业板块的当日涨跌幅排名
- [ ] 定义新 Mongo namespace `03_data_ud_sector_ranking_daily` 的 9 字段最小行 schema 与唯一键 `{dataset, trade_date, sector_code}`
- [ ] 定义 `dataset` 维度的枚举与严格禁止混排规则
- [ ] 定义固定的 close-to-pre_close 收益口径：`pct_chg = (close - pre_close) / pre_close * 100`
- [ ] 定义 `trade_date` 必须来自可证明的历史交易日线（禁止 `date=None`/实时 latest 作为历史语义）
- [ ] 定义缺 `pre_close`/全行业覆盖不足时的 fail/empty 语义
- [ ] 定义 TA-CN 只读上游候选的输入路径、日期格式兼容与 realtime fallback 排除策略
- [ ] 定义新能力与旧 `sector.ranking`/`sector.snapshot`/`SectorSnapshot` 的边界与迁移隔离
- [ ] 定义 `sector.ranking_history` 对外参数与 source trace/provenance 最小可观测契约
- [ ] 定义第一版仅交付离线/fake/mongomock 可验证实现，不执行真实 collection/index creation 或写入
- [ ] 为 T2 Design 提供明确输入，为 T3 实施提供可计算验收矩阵

### 3.2 非目标（Out of Scope）

- **不创建 Design**（由后续 T2 交付 DESIGN-03-015-historical-sector-ranking）
- **不修改任何 Python、测试、配置、既有 RFC/SPEC/Design、README/SKILL**
- **不实现代码**（属 T3）
- **不修改 `SectorSnapshot` 19 字段 schema**（P0 已冻结，属 P3-A 范围）
- **不修改 `_EXPECTED_SECTOR_*_FIELDS` / STUB_COLUMNS**（P0 已冻结）
- **不修改 `providers/akshare.py`**（P3-A fake-only 基线，非本卡范围）
- **不修改 `services/sector_service.py`**（属 T3，非本卡范围）
- **不修改 P3-A 的任何文件**（akshare.py / sector_client.py / fixtures / tests）
- **不迁移、不回填旧 collection**（`03_data_ud_market_sector_snapshot` 冻结不动）
- **不执行真实 HTTP/API/Tushare token/Mongo/cache/DDL/DML/cron/systemd/服务重启/Git commit/push**
- **不读取 `.env` 或凭据**
- **不宣称 TA-CN SW 历史数据"已可用"**（未经生产 Mongo 验证）
- **不存储/编造涨停家数、跌停家数、领涨股、资金流、成员列表、run_id、raw_payload、复杂版本字段**
- **不处理 concept/region/style 类型**（第一版仅 industry）

---

## 4. 整体设计

### 4.1 核心设计哲学

**新增隔离，极简起步**：不修改、不扩展、不迁移任何现有的 sector 能力和 collection。新增一个独立的、极简的历史日排名能力，用新 namespace、新 schema、新 unique key，从零开始构建可验证的离线实现。

**数据源可证明**：每一条历史排名行的 `trade_date` 必须可追溯到一条已收盘的历史交易日日线，禁止将实时/盘中数据作为历史记录。

**口径固定**：涨跌幅排名一律使用 close-to-pre_close 口径，不使用 close-to-open，不接受上游自带的 `pct_chg` 字段作为排名依据。

### 4.2 能力边界总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    YQuant Sector Capabilities                    │
├──────────────────────┬──────────────────────────────────────────┤
│  sector.snapshot     │  实时单板块快照（P3-A，frozen stub）     │
│  (EXISTING, FROZEN)  │  collection: 03_data_ud_market_sector_   │
│                      │               snapshot                    │
│                      │  schema: SectorSnapshot 12-col projection │
│                      │  key: {market, sector_code, snapshot_date}│
├──────────────────────┼──────────────────────────────────────────┤
│  sector.ranking      │  实时全行业排名（P3-A，frozen stub）     │
│  (EXISTING, FROZEN)  │  collection: 同上                         │
│                      │  schema: SectorSnapshot 8-col projection  │
│                      │  key: 同上                                │
├──────────────────────┼──────────────────────────────────────────┤
│  sector.ranking_     │  历史行业日涨跌幅排名（NEW, 本 RFC）      │
│  history (NEW)       │  collection: 03_data_ud_sector_ranking_  │
│                      │               daily                       │
│                      │  schema: 9 字段最小行                     │
│                      │  key: {dataset, trade_date, sector_code}  │
│                      │  上游候选: TA-CN index_daily_quotes (SW)  │
└──────────────────────┴──────────────────────────────────────────┘
```

**迁移隔离原则**：
- 旧 `03_data_ud_market_sector_snapshot`：不改、不迁、不回填、不删除。
- 新 `03_data_ud_sector_ranking_daily`：全新 namespace，从零构建。
- 两个 collection 独立存在，无外键、无触发器、无 ETL 联动。

### 4.3 演进路线

```
当前状态
  │
  ├── P3-A sector.snapshot / sector.ranking ✅ fake-only stub（frozen）
  │
  ▼
T1 (本 RFC/SPEC) — 离线契约定义
  │  定义新 capability、schema、unique key、dataset 维度
  │  定义 close-to-pre_close 口径、trade_date 证明、fail/empty 语义
  │  定义 TA-CN 只读上游候选、realtime fallback 排除
  │  定义迁移隔离边界
  │  ❌ 不触发真实 I/O
  │
  ▼
T2 (Design) — 详细设计
  │  collection schema、索引设计、TA-CN 读取适配
  │  pre_close 推导逻辑、ranking 计算逻辑
  │  mongomock repository + 只读查询 service 设计（T3 收紧范围）
  │  allowlist / 禁止修改清单
  │
  ▼
T3 (Implement) — 离线实现
  │  mongomock collection + fake client 单元测试
  │  ❌ 不触发真实 Mongo / TA-CN / AKShare
  │
  ▼
后续 Gate (Pascal 分项授权)
  │
  ├── Gate-1: TA-CN SW 历史数据真实可达性 smoke（只读 Mongo）
  ├── Gate-2: 新 collection 创建 + 索引（DDL）
  ├── Gate-3: 历史 backfill（真实 TA-CN → 新 collection 写入）
  └── Gate-4: 生产读取激活
```

---

## 5. 详细设计

### 5.1 新增 Capability 定义

#### 5.1.1 Capability 字符串

```
sector.ranking_history
```

- `domain` = `"sector"`
- `operation` = `"ranking_history"`

**命名理由**：使用 `ranking_history` 而非 `ranking` 以与现有 P3-A `sector.ranking`（实时）明确隔离。`history` 后缀表明该能力返回的是**已收盘的历史交易日**排名，不是实时/盘中数据。

#### 5.1.2 业务语义

| 维度 | 定义 |
|---|---|
| 能力描述 | 按 `trade_date` 查询某 `dataset` 分类口径下，全部行业板块在该交易日的日涨跌幅排名 |
| 查询参数 | `trade_date`（必填，`YYYY-MM-DD`，必须为已收盘的历史交易日）、`dataset`（必填，见 §5.4）、`limit`（可选，默认返回全部） |
| 返回类型 | 按板块列表（`list[dict]`），每个 dict 为 9 字段行 schema |
| 排序口径 | 按 `pct_chg` 降序；`pct_chg` 相同按 `sector_code` 升序 |
| 数据性质 | **历史已收盘日线**，不是实时/盘中数据 |

#### 5.1.3 禁止的查询语义

- **禁止 `trade_date=None`**：不支持"查最新"语义。`trade_date` 必须是明确的、已收盘的历史交易日。
- **禁止 `trade_date=今日`**（当市场尚未收盘时）：如果 `trade_date` 是当前交易日且市场未收盘，视为参数非法，抛出 `ValueError`（结果语义见 §5.6.3 冻结表 Category 1）。
- **禁止跨 dataset 混合查询**：单次查询只能指定一个 `dataset`，不允许多 dataset 并列返回。

### 5.2 Mongo Namespace 与行 Schema

#### 5.2.1 Collection 名称

```
03_data_ud_sector_ranking_daily
```

**命名规则**：沿用 YQuant unified_data 的 `03_data_ud_` 前缀约定。`sector_ranking_daily` 表明这是按日存储的板块排名集合。

#### 5.2.2 最小行 Schema（9 字段）

| 字段 | 类型 | 说明 | 约束 |
|---|---|---|---|
| `dataset` | str | 数据源与分类口径的稳定标识（见 §5.4） | 非空；必须为已知 dataset 枚举值 |
| `trade_date` | str | 交易日，格式 `YYYY-MM-DD` | 非空；必须为已收盘的历史交易日 |
| `sector_code` | str | 板块代码 | 非空；dataset 内唯一 |
| `sector_name` | str | 板块名称 | 非空 |
| `pct_chg` | float | 日涨跌幅（%），口径 `(close - pre_close) / pre_close * 100` | 非空（缺 pre_close 时整行不入库，不写 0/None） |
| `rank` | int | 当日涨跌幅排名（1 = 涨幅最高） | 非空 |
| `close` | float | 当日收盘价/收盘指数 | 非空 |
| `pre_close` | float | 前一交易日收盘价/收盘指数 | 非空（缺失时整行不入库） |
| `updated_at` | str (ISO-8601) | 行写入/更新时间戳 | 非空；由写入方生成 |

#### 5.2.3 唯一键

```
{dataset, trade_date, sector_code}
```

- 同一 `dataset` + 同一 `trade_date` 下，每个 `sector_code` 最多一行。
- upsert 语义：相同唯一键的行被覆盖更新。

#### 5.2.4 明确不存储的字段

以下字段在第一版**不存储、不编造**：

| 字段类别 | 说明 |
|---|---|
| 涨停家数 / 跌停家数 | 第一版不采集 |
| 领涨股 / 领涨股涨跌幅 | 第一版不采集 |
| 资金流（主力净流入等） | 第一版不采集 |
| 成分股列表（members） | 第一版不采集 |
| `run_id` | 不采用 run+item 两表模型，无 run 概念 |
| `raw_payload` | 不存储原始 payload |
| 版本号 / 变更追踪字段 | 第一版不需要 |
| `volume` / `amount` / `turnover_rate` | 第一版不采集（最小 schema） |

**缺失值规则**：未来如需扩展字段，缺失值**不能写 0**。缺失即不入库该行（fail 语义）或字段保持 None（如 schema 扩展后）。

### 5.3 固定收益口径

#### 5.3.1 pct_chg 公式

```
pct_chg = (close - pre_close) / pre_close * 100
```

- `close`：当日收盘价/收盘指数
- `pre_close`：前一交易日收盘价/收盘指数

**禁止**使用以下替代口径：
- ❌ `(close - open) / open * 100`（close-to-open 口径）
- ❌ 直接取上游自带的 `pct_chg` 字段（上游口径可能不一致）
- ❌ 使用前一日 TA-CN 的 `pct_chg` 字段作为 pre_close 推导

#### 5.3.2 pre_close 来源

`pre_close` 必须来自**同一 `sector_code` 在前一交易日的 `close` 值**。

| 场景 | 处理 |
|---|---|
| 上游直接提供 `pre_close` 字段 | 校验 `pre_close ≈ 前一日 close`（容差由 T2 定义）；校验通过后使用上游值 |
| 上游不提供 `pre_close` | 从历史日线中取同一 `sector_code` 前一交易日的 `close` 作为 `pre_close` |
| 前一交易日无 `close` 数据（如上市首日/数据缺失） | 该 `sector_code` 的行**不入库**（fail 语义） |

#### 5.3.3 rank 计算

```
rank = 按 pct_chg 降序排列后的位次（1-based）
```

- `pct_chg` 相同的板块：按 `sector_code` 升序排列后分配连续 rank。
- rank 计算在整个 `dataset` + `trade_date` 的全量板块集合上进行，不能对部分板块计算 rank。

### 5.4 dataset 维度

#### 5.4.1 dataset 枚举

`dataset` 是数据源与分类口径的稳定标识，不可混排。

| dataset 标识 | 分类口径 | 数据源 | 预期板块数 | 第一版状态 |
|---|---|---|---|---|
| `sw2021_ta_cn` | 申万 2021 一级行业分类 | TA-CN MongoDB `index_daily_quotes` | ~31 个 L1 行业 | **第一版候选** |
| `eastmoney_industry` | 东方财富行业板块 | AKShare `name_em()` / 东财 API | ~86 个板块 | 后续扩展 |
| `ths_industry` | 同花顺行业板块 | 同花顺 API | 待定 | 后续扩展 |
| `sina_industry_eod` | 新浪行业 EOD | 新浪财经 API | 待定 | 后续扩展 |

#### 5.4.2 严格禁止混排规则

1. **查询隔离**：单次 `sector.ranking_history` 查询只能指定一个 `dataset`。不支持跨 dataset 联合查询。
2. **存储隔离**：不同 `dataset` 的行存储在同一 collection 中，但通过 `dataset` 字段严格隔离。查询时必须按 `dataset` 过滤。
3. **禁止静默 fallback**：如果 `dataset=sw2021_ta_cn` 查询无数据，**不得**静默回退到 `eastmoney_industry` 或其他 dataset。无数据即返回 empty。
4. **sector_code 不可跨 dataset 复用**：不同 dataset 的 sector_code 可能重叠（如东财 `BK0489` 和申万 `801120` 是不同分类体系），通过 `dataset` 字段区分，不能去重合并。

### 5.5 trade_date 证明与 realtime fallback 排除

#### 5.5.1 trade_date 来源要求

`trade_date` 必须满足以下全部条件：

1. **格式**：`YYYY-MM-DD` 字符串（入库前从 TA-CN 的 `YYYYMMDD` 转换）。
2. **已收盘**：该交易日必须已收盘（market closed）。如果 `trade_date` 是当前交易日且当前时间早于收盘时间，该日期不合法。
3. **可证明**：该 `trade_date` 必须有对应的、已确认的历史日线记录（不是 realtime fallback）。

#### 5.5.2 realtime fallback 排除策略

**背景**：TA-CN 的 SW 同步机制在某些情况下（如无历史日线时）会写入 realtime/盘中数据到 `index_daily_quotes`。这些记录不是最终收盘日线，不能作为历史排名的合法数据源。

**排除策略（第一版原则）**：

第一版**不实现精确检测逻辑**（精确信号留待后续 Gate 以权威数据定义）。第一版只要求：凡缺行业/重复/`close` 或 `pre_close` 非法的行，均不得进入正式 ranking（已在 §5.6 定义完整性约束覆盖此安全边界）。

| 检测信号 | 说明 | 处理 |
|---|---|---|
| `trade_date` 为当日且市场未收盘 | 实时数据混入 | 该 `trade_date` 的全部行不作为历史数据返回 |
| 记录缺少 `close` 字段或 `close` 为 None | 数据不完整 | 该行不入库 |
| 记录的 `pct_chg`（如有）与 close-to-pre_close 公式计算结果偏差超容差 | 可能是盘中/非最终记录 | 该行标记为可疑；T2 定义容差阈值与处理方式 |
| 记录的 `source` 字段标记为 realtime/intraday（如 TA-CN 有此标记） | 明确的实时标记 | 该行不入库 |

**设计原则**：宁可拒绝（按 §5.6.3 冻结表 Category 3/4 返回 empty + warning，不抛 error），不可将非最终记录作为历史排名返回。realtime fallback 排除的精确检测逻辑由 T2 Design 定义，本 RFC 只定义原则。

### 5.6 缺 pre_close / 全行业覆盖不足时的 fail/empty 语义

#### 5.6.1 单板块缺 pre_close

| 场景 | 处理 |
|---|---|
| 某 `sector_code` 在 `trade_date` 有 `close`，但前一交易日无 `close`（缺 `pre_close`） | 该板块行**不入库**。不影响同 `trade_date` 其他板块的入库。 |
| 某 `sector_code` 在 `trade_date` 既无 `close` 也无 `pre_close` | 该板块行**不入库**。 |

**关键约束**：缺 `pre_close` 时整行不入库，**不写 0**，**不写 None**，**不用 open 替代**。

#### 5.6.2 全行业覆盖完整性（100% exact-match）

**完整性判定原则（严格）**：正式 ranking 仅当 `observed_sector_codes == expected_sector_codes` 时生成。即 100% 覆盖、无重复、每行有有效 `close`/`pre_close`。不存在"部分覆盖即生成正式 ranking"的中间态。

| 场景 | 处理 |
|---|---|
| `observed_sector_codes == expected_sector_codes`（100% 覆盖、无重复、每行有效 close/pre_close） | 生成正式 ranking 并物化（source_trace `completeness:complete, materialized:ok`，见 §5.6.3 冻结表成功行） |
| `observed_sector_codes ⊊ expected_sector_codes`（缺行业）| **不生成正式 ranking**；`BuildOutcome(status="incomplete")`，不物化（不写库、不返回部分榜单）。对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-incomplete"])`（见 §5.6.3 冻结表 Category 3） |
| `observed_sector_codes` 含 expected 之外的代码或重复代码 | **不生成正式 ranking**；同上，`BuildOutcome(status="incomplete")`，不物化。对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-incomplete"])`（Category 3） |
| 某行 `close` 或 `pre_close` 非法（None/缺字段） | 该行不 materialize（在 build 阶段剔除）；剔除后若 `observed != expected` 则按上面两行处理（Category 3） |
| 某 `trade_date` 下零个板块有完整数据 | `BuildOutcome(status="empty")`，不物化。对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-empty"])`（Category 4） |

**expected universe 来源（显式传入，非硬编码）**：
- expected universe 必须由**调用方或 fixture 显式传入**（`expected_sector_codes: frozenset[str]` 或等价结构）。
- 第一版**不在 T3 硬编码**未经验证的"31 个 SW L1 常量表"作为 expected universe 来源。
- 离线 fixture 的 expected universe 仅证明构建/校验逻辑正确，不代表生产真实 universe。
- 生产真实 expected universe 的确认仍为独立 Pascal Gate（Gate-1 权威验证）。

**设计原则**：覆盖不足不抛未捕获异常（参数非法除外，见 Category 1），但**第一版不得将部分覆盖结果 materialize 为正式 ranking**。查询方通过 source_trace 感知完整性状态（`complete`/`incomplete`/`empty`）。empty ≠ error。

#### 5.6.3 结果语义冻结表（T2.7 契约纠偏 — 消除 empty/error 二义性）

以下 4 类失败情形与 1 类成功情形（完整 ranking）的结果类型与稳定 token **唯一、冻结，三文档一致**。Developer / Tester 不得自行选择，不得保留"error 或 empty"、"empty 或 warning"等二选一措辞。

| Category | 触发情形 | 结果类型 | 稳定 token / 错误信号 | 是否物化 | source_trace 顺序 |
|---|---|---|---|---|---|
| **1 — 参数非法** | `trade_date` 空/格式非法/当日盘中；`dataset` 空/未知枚举/列表型；`limit` 类型非法 | `ValueError`（service 入口抛出，不构造 DataResult） | 异常类型 = `ValueError`；不产生 error token | — | — |
| **2 — 读集合无记录** | 物化集合中 `{dataset, trade_date}` 下零条记录（trade_date 合法但未 backfill / 未命中） | `DataResult.success(data=[], warnings=["historical-ranking-empty"])` | warning token = `historical-ranking-empty` | 不物化（读路径本身无写） | `dataset` → `trade_date` → `source` → `coverage:0/{expected}` → `completeness:empty` → `materialized:ok` |
| **3 — build 完整性失败** | build 阶段 `observed != expected`（缺行业 / 含多余 / 重复 sector_code）；或有效行剔除后 `observed != expected` | `BuildOutcome(status="incomplete")`；对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-incomplete"])` | warning token = `historical-ranking-incomplete` | **不得物化**（不写库、不返回部分榜单） | `dataset` → `trade_date` → `source` → `coverage:{actual}/{expected}` → `completeness:incomplete` → `materialized:miss` |
| **4 — build 零有效行** | build 阶段零个 sector_code 有完整有效行（全部缺 close/pre_close/sector_name） | `BuildOutcome(status="empty")`；对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-empty"])` | warning token = `historical-ranking-empty` | **不得物化** | `dataset` → `trade_date` → `source` → `coverage:0/{expected}` → `completeness:empty` → `materialized:miss` |
| **成功 — build 完整且已物化** | build 阶段 `observed == expected`（100% 覆盖、无重复、每行有效 close/pre_close），正式 ranking 行已物化 | `DataResult.success(data=正式 ranking 列表, warnings=[])` | 无 warning token（`warnings=[]`） | **已物化**（正式 ranking 行写入物化集合，查询读取命中） | `dataset` → `trade_date` → `source` → `coverage:{actual}/{expected}` → `completeness:complete` → `materialized:ok` |

**冻结约束**：
- 不存在"error 与 empty 二选一"的措辞：Category 1 是 `ValueError`，Category 2/3/4 均为 `DataResult.success(data=[])`。
- 不存在"empty 或 warning"的措辞：Category 2/4 必带 warning token `historical-ranking-empty`；Category 3 必带 warning token `historical-ranking-incomplete`。
- `materialized` 字段区分：Category 2 为 `ok`（命中物化集合读取但空），Category 3/4 为 `miss`（build 侧未写入）。
- `coverage` 格式固定为 `{actual}/{expected}`，实际值为整数（Category 2/4 实际 = 0）。
- 上述 token 字符串为契约冻结值，T3 实现须逐字使用。
- 成功完整 ranking（`observed == expected`、正式行已物化）的 trace 为 `completeness:complete, materialized:ok`，`warnings=[]`；成功/失败 trace 一律冒号格式，逐字可测。
- **枚举封闭（T2.9）**：`completeness` 仅允许 `complete | incomplete | empty`；`materialized` 仅允许 `ok | miss`。`skipped` 已废弃禁用，不得作为任一字段的对外可能值（三文档声明与本表一致）。

### 5.7 TA-CN 只读上游候选

#### 5.7.1 TA-CN 作为上游的条件

TA-CN MongoDB 的 `index_daily_quotes` 集合存储申万行业指数日线。作为 `sw2021_ta_cn` dataset 的上游候选，需满足：

1. **只读**：仅通过 `TA_CNMongoAdapter.get_index_daily_bars(sector_code=..., start_date=..., end_date=...)` 读取，不写入 TA-CN。
2. **日期格式兼容**：TA-CN 内部 `trade_date` 为 `YYYYMMDD`，需转换为 `YYYY-MM-DD` 入库。
3. **字段映射**：TA-CN `index_daily_quotes` → 新 schema 的映射由 T2 Design 定义。

#### 5.7.2 TA-CN `index_daily_quotes` 字段（参考 fixture）

| TA-CN 字段 | 新 schema 字段 | 转换 | 备注 |
|---|---|---|---|
| `sector_code`（如 `801120`） | `sector_code` | str 直传 | 申万 L1 行业代码 |
| `trade_date`（如 `20260713`） | `trade_date` | `YYYYMMDD` → `YYYY-MM-DD` | 日期格式转换 |
| `close` | `close` | float | 当日收盘指数 |
| —（前一交易日 close） | `pre_close` | 从前一交易日同 `sector_code` 的 `close` 推导 | TA-CN 无 pre_close 字段 |
| —（计算） | `pct_chg` | `(close - pre_close) / pre_close * 100` | 固定口径，不取 TA-CN 的 `pct_chg` |
| —（计算） | `rank` | 按 `pct_chg` 降序排名 | 全量板块集计算 |
|| —（TA-CN 无） | `sector_name` | 需额外映射（如从 `stock_sector_info` 的 `l1_name` 或预定义 SW L1 代码表） | **不在 T3 硬编码全表**；来源留待 Gate-1 权威验证。离线 fixture 可显式传入测试用名称 |
| —（运行时生成） | `updated_at` | `datetime.now().isoformat()` | 写入时间戳 |
| `sw2021_ta_cn`（常量） | `dataset` | 调用方注入 | 不从 TA-CN 推断 |

#### 5.7.3 TA-CN 不可宣称"已可用"

- TA-CN SW 历史日线的**实际覆盖率和历史完整性未经生产 Mongo 验证**。
- 未经 Pascal 授权的只读 Mongo smoke 前，**不得在任何代码、文档、配置中宣称 TA-CN SW 历史数据"已可用"或"已覆盖"**。
- TA-CN 仅标注为"只读上游候选"，其可用性作为后续 Gate-1 的验证项。

### 5.8 sector.ranking_history 对外参数与 Source Trace

#### 5.8.1 对外查询参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `trade_date` | str (`YYYY-MM-DD`) | 是 | 已收盘的历史交易日 |
| `dataset` | str | 是 | dataset 标识（第一版仅 `sw2021_ta_cn`） |
| `limit` | int | 否 | 返回前 N 个板块；默认全部 |

**禁止参数**：
- `date=None`：不支持"查最新"语义
- 跨 dataset 参数（如 `dataset=["sw2021_ta_cn", "eastmoney_industry"]`）

#### 5.8.2 Source Trace / Provenance 最小可观测契约

查询返回的 `DataResult.source_trace` 必须包含以下最小信息（不能只靠 `provider=akshare`）：

| source_trace 条目 | 说明 |
|---|---|
| `dataset:{dataset}` | 本次查询的 dataset 标识 |
| `trade_date:{trade_date}` | 本次查询的交易日 |
| `source:{upstream}` | 数据来源标识（如 `ta_cn:index_daily_quotes`） |
| `coverage:{actual}/{expected}` | 实际覆盖板块数 / 期望板块数（冻结占位符，见 §5.6.3） |
| `completeness:{complete\|incomplete\|empty}` | 完整性判定（枚举封闭，见 §5.6.3 冻结表） |
| `materialized:{ok\|miss}` | 是否命中物化集合读取（`skipped` 已废弃禁用，不得作为对外值） |

**理由**：source_trace 需让调用方（researcher/strategies）能判断数据的来源、完整性和可信度，而不是仅看到一个 `provider` 标签就假设数据可靠。

### 5.9 迁移隔离

#### 5.9.1 旧 collection 处理

| 旧 collection | 处理 |
|---|---|
| `03_data_ud_market_sector_snapshot` | **不改、不迁、不回填、不删除**。P3-A 的 `sector.snapshot` / `sector.ranking` 继续以此为物化目标（fake-only stub 状态不变）。 |

#### 5.9.2 旧 capability 处理

| 旧 capability | 处理 |
|---|---|
| `sector.snapshot` | **冻结**。不做任何修改。 |
| `sector.ranking` | **冻结/暂缓**。实时路径暂缓（用户决策 #1），不做任何修改。未来如需将 `sector.ranking` 演进为历史能力，作为独立 RFC 决策。 |

#### 5.9.3 新 capability 与旧 capability 的关系

- `sector.ranking_history` 是**新增** capability，不替代、不覆盖、不合并 `sector.ranking`。
- 两者独立存在，各自有独立的 collection、schema、unique key。
- 查询路径不交叉：`sector.ranking_history` 通过新 collection 读取，不经过旧 collection。

---

## 6. 第一版实现范围（离线 only）

### 6.1 第一版交付物（T3 离线最小范围）

第一版仅交付**可纯函数测试的离线核心**，不包含任何真实 I/O、上游聚合或生产改动。

| 交付物 | 说明 |
|---|---|
| `SectorRankingDaily` domain object | 9 字段最小行，`from_dict()` 严格校验（全部必填，缺失任一 → ValueError） |
| 确定性构建/校验/排序纯函数 | 输入 rows + expected sector codes；公式 `(close-pre_close)/pre_close*100`；排序 `pct_chg DESC, sector_code ASC`；连续 1-based rank；100% exact-match 完整性校验 |
| 注入式 mongomock repository | 仅操作 `03_data_ud_sector_ranking_daily`，key `{dataset, trade_date, sector_code}`；接受外部传入的 mongomock db |
| 只读历史查询 service | 强制 `dataset + trade_date`，按稳定排序返回；直读物化集合，不经 router |
| 离线单元测试 + fixture | 覆盖 domain 校验、排序、完整性判定（complete/incomplete/empty）、mongomock 读写、read-only query |
| UnifiedDataClient facade（条件性） | **仅当**可从已注入 fake/mongomock db 端到端实测时，才追加最薄的 `get_sector_ranking_history()` facade；否则后置到未来 Gate |

**expected_sector_codes** 在离线测试中由 fixture 显式传入，**不是硬编码常量表**。

### 6.2 第一版禁止事项（明确不在 T3 实现）

- ❌ `HistoricalRankingClient` Protocol / Fake（上游 client 抽象层）
- ❌ 真实 TA-CN 获取与任何 real-time origin 检测逻辑
- ❌ 硬编码 SW L1 代码→名称全表（sector_name 来源留待 Gate-1 权威验证）
- ❌ 真正的 backfill、真实 Mongo collection/index creation、DDL/DML
- ❌ router、P3-A、TA-CN adapter/scheduler 或真实 Provider 改动
- ❌ 真实 Mongo / TA-CN / AKShare / HTTP 调用
- ❌ cron / systemd / 服务重启 / Git commit/push

### 6.3 后续 Gate 清单（生产化路径）

realtime fallback 排除的精确检测、SW L1 全表权威校验、真实 backfill、生产 DDL 等均移至后续 Gate，不在第一版承诺。

| Gate | 内容 | 授权方 | 前置条件 |
|---|---|---|---|
| Gate-1 | TA-CN SW 历史数据真实可达性 smoke（只读 Mongo，验证覆盖率和完整性） | Pascal | T3 离线实现通过 |
| Gate-2 | 新 collection `03_data_ud_sector_ranking_daily` 创建 + 索引（DDL） | Pascal | Gate-1 verdict ≥ conditional_pass |
| Gate-3 | 历史 backfill（真实 TA-CN → 新 collection 批量写入） | Pascal | Gate-2 完成 |
| Gate-4 | 生产读取激活（`sector.ranking_history` 真实查询路径上线） | Pascal | Gate-3 canary 通过 |

---

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| TA-CN SW 历史日线覆盖率不足（缺交易日/缺板块） | 中 | 高 | Gate-1 smoke 验证覆盖率和完整性；incomplete 标记机制 | 返回 empty + source_trace 标注 incomplete |
| TA-CN realtime fallback 污染历史数据 | 中 | 高 | realtime fallback 排除策略（§5.5.2）；宁可拒绝不可混入 | 拒绝可疑 trade_date 全部行 |
| pre_close 推导依赖前一交易日数据，链式缺失 | 低 | 中 | 单板块缺 pre_close → 该行不入库；不编造 | 覆盖率降低 → incomplete 标记 |
| sector_name 无直接 TA-CN 来源 | 中 | 低 | T2 定义 sector_name 映射来源（SW L1 代码表或 `stock_sector_info.l1_name`） | sector_name 临时为空 → 行不入库 |
| dataset 扩展时 sector_code 冲突 | 低 | 中 | dataset 字段严格隔离；不同 dataset 不去重 | — |

---

## 8. 备选方案

### 8.1 备选方案 A：扩展现有 `sector.ranking` capability

- **方案**：在现有 `sector.ranking` 中增加 `trade_date` 历史查询参数，复用 `03_data_ud_market_sector_snapshot` collection。
- **不选用原因**：现有 schema 是 SectorSnapshot 19 字段（偏重实时聚合），unique key 是 `{market, sector_code, snapshot_date}`（无 dataset 维度），且 P3-A fake-only 基线已冻结。扩展会破坏冻结约束，且 schema 不匹配历史日线序列需求。

### 8.2 备选方案 B：采用 run + item 两表模型

- **方案**：`sector_ranking_run`（run 元数据）+ `sector_ranking_item`（逐板块行）两表分离。
- **不选用原因**：用户明确决策"不采用 run + item 两表"（决策 #2）。极简单集合更适合第一版快速验证。

### 8.3 备选方案 C：直接使用 TA-CN 自带的 `pct_chg` 字段

- **方案**：排名直接使用 TA-CN `index_daily_quotes.pct_chg`，不重新计算。
- **不选用原因**：用户明确决策"固定 close-to-pre_close 口径"（决策 #6），不接受上游自带 pct_chg。TA-CN 的 pct_chg 口径未经确认，可能与 close-to-pre_close 不一致。

---

## 9. 验收标准

### 9.1 文档验收

- [ ] RFC-03-015-historical-sector-ranking.md 和 SPEC-03-015-historical-sector-ranking.md 两份独立文档存在且互相交叉引用
- [ ] 文件名和编号准确（`03-015`）
- [ ] 每份文档区分「已验证事实」「假设」「待验证」「Pascal 授权 Gate」

### 9.2 语义验收

- [ ] 新能力与旧 `SectorSnapshot`/P3-A realtime stub 的边界与迁移隔离明确定义
- [ ] 简单单集合 schema、唯一键、dataset 枚举与严禁混排规则明确
- [ ] `trade_date` 必须来自可证明的历史日线的约束明确
- [ ] 固定 close-to-pre_close 公式、缺 pre_close/覆盖不足时的 fail/empty 语义明确
- [ ] TA-CN 只读输入、日期格式兼容与 realtime fallback 排除策略明确
- [ ] 第一版仅离线/fake/mongomock 可验证，不执行真实 collection/index creation 或写入
- [ ] `sector.ranking_history` 对外参数与 source trace/provenance 最小可观测契约明确
- [ ] 迁移策略明确（旧 collection 不改、不迁、不回填，新 namespace）

### 9.3 边界验收

- [ ] 语义不与用户冻结决策冲突
- [ ] 语义不与现有 P3-A fake-only 基线冲突
- [ ] 不将 `date=None`/实时 latest 作为历史 data 的合法语义

### 9.4 非功能验收

- [ ] `git diff --check` exit 0
- [ ] `git diff --name-status` 中本卡 diff 仅含 RFC + SPEC 两份文档
- [ ] 声明板块/行业数据为辅助研究数据，不构成交易指令或投资建议

### 9.5 T2/T3 验收矩阵输入

- [ ] 有明确的 T2 Design 输入（collection schema、索引、pre_close 推导、ranking 计算、fake client 接口）
- [ ] 有明确的 T3 实施范围原则与可计算验收矩阵（离线测试覆盖项）

---

## 10. 开放问题

- [ ] OQ-015-1：`sector_name` 的来源？SW L1 代码（如 `801120`）到中文名称（如 `食品饮料`）的映射表从哪里获取？（候选：TA-CN `stock_sector_info.l1_name` / 预定义常量表 / AKShare SW 分类接口）
- [x] OQ-015-2：全行业覆盖不足的阈值？**已裁定（V0.2）**：第一版严格 100% exact-match（`observed == expected` 才生成正式 ranking），不存在 90% partial-complete 中间态。expected universe 由调用方/fixture 显式传入，不硬编码。
- [ ] OQ-015-3：pre_close 容差校验——如果上游提供 pre_close，与前一交易日 close 的偏差超过多少视为不一致？
- [ ] OQ-015-4：TA-CN realtime fallback 的精确检测信号？`index_daily_quotes` 中是否有明确的 source/type 字段区分 realtime 和 historical？
- [ ] OQ-015-5：`sector.ranking_history` 是否需要同时写入 `rank` 字段，还是查询时动态计算？第一版建议写入（避免每次查询重算），但 backfill 时 rank 需全量重算。
- [ ] OQ-015-6：未来 `eastmoney_industry` dataset 的 sector_code（如 `BK0489`）与 `sw2021_ta_cn`（如 `801120`）如何在 collection 中共存而不混淆？（答：通过 `dataset` 字段隔离，已在 §5.4.2 定义）

---

## 11. 参考资料

- RFC-03-014（Unified Data Phase 3 主 RFC）—— 整体架构、Gate 体系
- RFC-03-014-p3a-sector-provider-activation（V0.2）—— P3-A Sector Provider 激活、endpoint 映射、字段映射
- SPEC-03-014-p3a-sector-provider-activation（V0.2）—— P3-A 可执行契约
- DESIGN-03-014-p3a-sector-provider-activation（V0.2）—— P3-A 离线实现设计
- RFC-03-007（Unified Data Layer 总纲）—— TA-CN MongoDB adapter 设计
- TA-CN `index_daily_quotes` fixture：`skills/data/unified_data/tests/fixtures/ta_cn_mock_docs.py` — `sw_industry_daily_quotes()`
- TA-CN adapter：`skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` — `get_index_daily_bars()`
- P3PersistenceWriter：`skills/data/unified_data/adapters/p3_persistence_writer.py` — collection/key mapping
- SectorService：`skills/data/unified_data/services/sector_service.py` — 现有 P3-A read path

---

## 12. 声明

本 RFC 中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本 RFC 不修改任何现有 RFC/SPEC/Design/代码/测试/配置。所有新定义为新增，不与 P3-A 冻结基线冲突。
