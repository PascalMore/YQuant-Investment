# RFC-03-014: P3-A Sector Provider 激活 — 真实 AKShare endpoint 映射与受控激活边界

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.2 修正 endpoint 契约：离线源码验证发现 `stock_board_industry_rank_em` 不存在、`cons_em` 返回成分股而非板块级聚合；将 `stock_board_industry_name_em()` 固定为 sector.snapshot 与 sector.ranking 共享主候选 endpoint。真实 payload 仍待受控授权 smoke 验证。） |
| 版本号 | V0.2 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-014（Unified Data Phase 3 主 RFC，V0.19）、RFC-03-007（Unified Data Layer 总纲）、RFC-03-012（Phase 1D 外部 Provider 激活模式参考） |
| 依赖 SPEC | SPEC-03-014（Phase 3 持久化扩展契约，V0.19）、SPEC-03-014-p3a-sector-provider-activation（本 RFC 对应之 SPEC） |
| 关联 Design | DESIGN-03-014（Phase 3 详细设计 V0.21）、待 T2 创建 DESIGN-03-014-p3a-sector-provider-activation |
| 替代 RFC | 无（不替代主 RFC-03-014；为主 RFC 的 P3-A 子链提供精确 Provider 激活契约） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #phase3 #p3a #sector #provider #akshare #activation |

---

## 1. 执行摘要

本 RFC 为 Unified Data Phase 3 的 P3-A 子链（板块/行业快照）定义真实 AKShare Provider 的激活路径：将 `sector.snapshot` / `sector.ranking` 两个 capability 从当前的 schema-level stub（0-row DataFrame）推进到真实 AKShare endpoint 调用，通过精确的 endpoint 选择、字段映射、空集/异常处理、rate-limit/retry 策略和受控授权 Gate，在不触发任何真实 I/O 的前提下完成全部离线可实现设计。真实 AKShare 调用、MongoDB DDL/DML、canary 和 cron 仅在后续 Pascal 分项授权 Gate 中激活。

**成功标准**：RFC + SPEC 两份独立文档存在且互相一致；不触发真实 I/O；T2 Design 拥有精确 allowlist 与不可修改路径；后续真实 smoke 和 production activation 作为 Pascal 分项授权 Gate。

---

## 2. 背景与动机

### 2.1 现状

P3-A sector 已完成 P0（离线可实现契约）和 P1（受控 Mongo 物化与显式 refresh 的零副作用代码路径）。commit `1232028` 冻结了 P1 fake-only materialized read baseline。当前两个 capability 的状态为：

| Capability | 离线 stub | AKShareProvider 注册 | Real fetch | Real persistence | Refresh 三态守卫 | Live smoke |
|---|---|---|---|---|---|---|
| `sector.snapshot` | ✅ schema-level stub（12-col 0-row DataFrame） | ✅ P3-A stub | ❌ 未实现 | ❌ 未执行 | ✅ unauthorized（默认 deny） | ❌ B2 SSLError |
| `sector.ranking` | ✅ schema-level stub（8-col 0-row DataFrame） | ✅ P3-A stub | ❌ 未实现 | ❌ 未执行 | ✅ unauthorized | ❌ B2 同 endpoint |

**关键事实**：AKShareProvider 当前 `fetch()` 对 sector capability 返回 `stub_dataframe_for(capability)` — 即一个空 DataFrame（正确的列定义但 0 行数据）。没有 endpoint 选择、没有真实 API 调用、没有 canonical mapping。

### 2.2 B2 Smoke 冻结证据

2026-07-26 B2 单次只读 smoke 对 `sector.snapshot` 调用 `akshare.stock_board_industry_cons_em("BK0489")` 两次，均返回 **SSLError**（`requests.exceptions`，TLS 握手失败或出口被阻断）。B2 证据冻结在 `/tmp/yquant-b2-pr234-20260726/pr2/smoke-sector-20260726.yaml`（只读副本，不可移动/提交/重跑）。

> **V0.2 修正（离线源码验证）**：B2 对 `cons_em` 的 smoke 试图获取板块级聚合，但 `cons_em` 的离线源码确认其返回的是**成分股列表**（每行一只股票：代码/名称/最新价/涨跌幅/成交量...），不是 SectorSnapshot 所需的板块级聚合。因此 `cons_em` 不是 `sector.snapshot` 的正确 endpoint。正确 endpoint 见 §5.1.1 修正后的裁定。

**B2 裁定（主 RFC §13.4.5.4 / §13.4.5.8）**：`sector.snapshot` 和 `sector.ranking` 当前为 **offline stub** — 预期字段集基于公开文档推断，标注「未 live-read 验证」。仅允许后续单变量网络诊断（切换网络出口、验证上游可达性、检查 TLS 版本）后重试 live-read，且须 Pascal 独立授权。

### 2.3 业务价值

| 能力 | 消费方 | 价值 |
|---|---|---|
| `sector.snapshot`（单板块快照） | researcher（行业表现分析）、strategies（行业轮动信号） | 获取单板块当日涨幅、领涨股、涨跌家数 |
| `sector.ranking`（板块排名） | strategies（行业轮动回测）、reporter（每日板块复盘） | 获取当日全行业/概念板块涨跌幅排名 |

### 2.4 触发原因

Pascal 确认按 Phase 3 推荐顺序推进：P3-A（sector）→ P3-B（flow）→ P3-C（sentiment）。P3-A 是首选起点。在 P1 fake-only baseline 冻结后，下一步是将 sector Provider 从 stub 推进到真实 AKShare endpoint 映射，为后续 Pascal 授权的真实 smoke 做好离线设计准备。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义 `sector.snapshot` 和 `sector.ranking` 从 schema-level stub 到真实 AKShare endpoint 的受控演进路径
- [ ] 为每个 capability 精确选定 AKShare endpoint（基于公开文档 + B2 冻结证据），定义参数、日期窗口、sector_type 映射
- [ ] 定义 AKShare 中文字段 → canonical `SectorSnapshot` 字段的精确映射表
- [ ] 定义空集、异常、rate-limit、retry 的可测试契约
- [ ] 定义数据合理性与 schema-drift 规则：禁止为缺失字段编造值
- [ ] 保持 P3 query read-only 不变；真实写入仅允许后续 P1.5/P2 门禁
- [ ] 定义 fake client / injected transport 的离线测试方式
- [ ] 定义后续真实 smoke 的最小参数、报告模板、失败回滚和 Pascal 授权清单
- [ ] 明确 P3-B/P3-C 不在本链范围，northbound Pascal C fail-stop 不变

### 3.2 非目标（Out of Scope）

- **不创建 Design**（由后续 T2 交付 DESIGN-03-014-p3a-sector-provider-activation）
- **不实现代码、不修改现有代码、不修改配置/requirements/SKILL/README/脚本/cron/systemd/gateway/webhook**
- **不读取 `.env` 或凭据**
- **不连接 MongoDB、不执行任何网络/API/provider 调用**
- **不执行 DDL/DML**
- **不重跑 B2 live-read**（B2 预算已用尽；本 RFC 基于 B2 冻结证据 + 公开文档）
- 不修改 `SectorSnapshot` domain object 的 19 字段 schema（SPEC §3.1 已冻结）
- 不修改 `_EXPECTED_SECTOR_*_FIELDS` / STUB_COLUMNS 定义（P0 已冻结）
- 不修改 `providers/akshare.py` 的 `kline_daily` 路径
- 不修改 P3-B / P3-C 的任何逻辑
- 不修改主 RFC-03-014 / SPEC-03-014 / DESIGN-03-014 的已有内容（本 RFC 只交叉引用）
- 不修改 router.py、client.py、adapters/ 的读路径
- 不解冻 QualitySummary（Phase 2 仍冻结）

---

## 4. 整体设计

### 4.1 核心设计哲学

P3-A sector Provider 激活遵循**受控演进**原则：从 schema-level stub → 离线 endpoint 映射设计 → 真实 smoke（Pascal 授权）→ 生产激活（Pascal 授权）。每一步都有明确的零副作用边界和可回滚点。本 RFC（T1）只完成离线设计，不触发任何真实 I/O。

**持久化目标**：与主 RFC 一致，`03_data_ud_market_sector_snapshot` 物化集合以 MongoDB（`tradingagents` 库）为唯一生产持久化目标。本 RFC 不涉及 DDL/DML。

### 4.2 演进路线

```
当前状态 (commit 1232028)
  │
  ├── P0 ✅ schema-level stub（12-col / 8-col 0-row DataFrame）
  ├── P1 ✅ fake-only materialized read + refresh 三态守卫
  │
  ▼
T1 (本 RFC/SPEC) — 离线 endpoint 映射设计
  │  定义 AKShare endpoint 选择、字段映射、空集/异常/retry 契约
  │  定义 fake transport / injected client 离线测试方式
  │  定义后续 smoke 最小参数、报告、回滚
  │  ❌ 不触发真实 I/O
  │
  ▼
T2 (Design) — 详细设计
  │  实现 endpoint 选择逻辑、canonical mapping、fake transport 接口
  │  定义 allowlist / 禁止修改清单
  │
  ▼
T3 (Implement) — 离线实现
  │  AKShareProvider.fetch() sector 分支激活
  │  fake transport 单元测试 + fixture
  │  ❌ 不触发真实 AKShare 调用
  │
  ▼
后续 Gate (Pascal 分项授权)
  │
  ├── PR-2 Gate: 真实 AKShare smoke（单板块、≤3 日窗口、零持久化写）
  │     前置条件：B2 SSL 网络诊断通过（切换网络出口 / TLS 版本检查）
  │
  ├── G-A-2 Gate: refresh 生产激活（_is_refresh_authorized() → True）
  │
  ├── PR-DDL-P3A: MongoDB 集合创建（已冻结，主 RFC §13.6）
  │
  └── PR-CANARY-P3A: 手动 canary 写入
```

### 4.3 与主 RFC/SPEC 的关系

本 RFC 是主 RFC-03-014 的 **P3-A 子链精确化**，不替代主 RFC。本 RFC 聚焦 sector Provider 激活的 endpoint 映射和受控授权边界，主 RFC 提供整体架构（分期方案、读写职责边界、Gate 体系、副作用矩阵）。

**交叉引用约束**：
- 主 RFC §5.1 定义 `sector.snapshot` / `sector.ranking` 的业务语义、数据维度、external fallback 链、公共能力级契约。本 RFC 不重复这些定义，只引用并精确化 Provider 层。
- 主 RFC §13.4.5 定义 B2 冻结证据、全 capability 映射裁决总表、单次 live-read 预算、T2 实现所需最小文件范围。本 RFC 继承这些冻结约束。
- 主 SPEC §3.1 定义 `SectorSnapshot` 19 字段 schema。本 RFC 不修改 schema，只定义从 AKShare 原始字段到 schema 的映射规则。
- 主 SPEC §P0.4 定义 PA-1~PA-9 映射验收项。本 RFC 继承并精确化 PA-1/PA-2 的 endpoint 来源。

### 4.4 与 P3-B / P3-C 的关系

P3-A sector 激活与 P3-B（flow）/ P3-C（sentiment）完全独立。三者在 Provider 层不共享 endpoint、不共享字段映射、不共享授权 Gate。P3-B 的 `flow.northbound_daily` Pascal C fail-stop（恒 None）在 P3-A 激活中不受影响。

---

## 5. 详细设计

### 5.1 AKShare Endpoint 选择

#### 5.1.1 endpoint 候选与裁定（V0.2 修正：基于离线源码验证）

> **V0.2 修正背景**：V0.1 基于公开文档推断 endpoint。V0.2 通过对已安装 AKShare 包的**离线源码静态检查**（`.venv` 中 `akshare/stock/stock_board_industry_em.py`，无网络调用）获得以下硬事实：
>
> 1. `stock_board_industry_rank_em` **不存在**。在 `akshare/__init__.py` 导入清单和源文件 `stock_board_industry_em.py` 中均无此函数。
> 2. `stock_board_industry_cons_em(symbol)` 存在，但其源码明确返回**板块成分股列表**（每行一只股票，列为：序号/代码/名称/最新价/涨跌幅/涨跌额/成交量/成交额/振幅/最高/最低/今开/昨收/换手率/市盈率-动态/市净率），**不是**板块级聚合（SectorSnapshot/Ranking）。
> 3. `stock_board_industry_name_em()` 存在，其源码返回**板块级排名 DataFrame**，包含 12 列：`排名, 板块名称, 板块代码, 最新价, 涨跌额, 涨跌幅, 总市值, 换手率, 上涨家数, 下跌家数, 领涨股票, 领涨股票-涨跌幅`。**无参数**，一次返回全部行业板块。

基于上述离线源码验证，每个 sector capability 的 endpoint 映射如下：

| Capability | 推荐 endpoint | 用途 | 离线源码验证状态 | 裁定 |
|---|---|---|---|---|
| `sector.snapshot` | `stock_board_industry_name_em()` | 获取单行业板块的板块级聚合（从全量返回中按 sector_code 过滤） | ✅ 源码确认返回板块级排名 12 列 | **选定** |
| `sector.ranking` | `stock_board_industry_name_em()` | 获取全行业板块涨跌幅排名（全量返回直接使用） | ✅ 源码确认返回板块级排名 12 列 | **选定** |

**关键设计变更（V0.1 → V0.2）**：V0.1 为两个 capability 指定了不同的 endpoint（snapshot → `cons_em`，ranking → `rank_em`）。V0.2 修正后，**两个 capability 共享同一 endpoint `stock_board_industry_name_em()`**：

- `sector.ranking`：直接消费 `name_em()` 全量返回（所有行业板块，每板块一行）。
- `sector.snapshot`：调用同一 `name_em()`，在 Provider/Client 层按 `sector_code`（或 `sector_name`）过滤出单板块行，构造单板块快照。

**endpoint 裁定约束**：

1. **`stock_board_industry_rank_em` 不存在**，任何引用该 endpoint 的设计、代码、测试、smoke 参数均属错误，必须移除。

2. **`cons_em` 不作为 sector.snapshot/ranking 的主数据源**。其源码确认返回成分股列表（个股粒度），不是 SectorSnapshot 所需的板块级聚合。`cons_em` 仅可作为**未来 component enrichment** 的候选（如填充 `members` 成分股列表字段），但明确不在 P3-A 本链 mapping scope 内（见 §5.2.3）。

3. `stock_board_industry_name_em()` 的真实 payload/字段集**仍待受控授权 smoke 验证**。V0.2 的字段列表来自离线源码静态读取（源文件 line 42-112 的 column 赋值），不是 live-read 证据。源码与线上行为可能存在差异（如东财 API 返回空、字段顺序变化、字段重命名），以真实 smoke 报告为准。

4. **AKShare 匿名调用**：`name_em()` 无需 token / API key。AKShare 是匿名数据源（主 RFC OQ-8 已解决）。

5. **禁止臆定**未在源码中出现的 endpoint 或字段名。

#### 5.1.2 sector_type 映射

`SectorSnapshot.sector_type` 支持 `industry` / `concept` / `region` / `style` 四种类型。AKShare 的板块接口分布如下：

| sector_type | AKShare endpoint 族 | 备注 |
|---|---|---|
| `industry` | `stock_board_industry_*` | 东方财富行业板块（如 BK0489 白酒） |
| `concept` | `stock_board_concept_*` | 东方财富概念板块（如 BK0475 华为概念） |
| `region` | 暂无直接对应 endpoint | 地域板块数据源待后续评估 |
| `style` | 暂无直接对应 endpoint | 风格板块数据源待后续评估 |

**当前阶段裁定**：P3-A 激活优先覆盖 `industry` 类型（B2 已验证的 endpoint 族）。`concept` 类型作为次优先（endpoint 命名模式相似）。`region` / `style` 标注为「数据源待定」，不阻塞当前阶段。

### 5.2 字段映射

#### 5.2.1 sector.snapshot 字段映射表

`stock_board_industry_name_em()` 返回的板块级字段（离线源码验证：12 列）→ `SectorSnapshot` canonical 字段映射：

> **注（V0.2）**：`sector.snapshot` 调用 `name_em()` 全量返回后，在 Provider/Client 层按 `sector_code`（`板块代码` 列）或 `sector_name`（`板块名称` 列）过滤出单板块行。`name_em()` 一次返回所有行业板块，snapshot 只取匹配的那一行。

| SectorSnapshot 字段 | AKShare 原始字段（源码验证） | 转换 | 单位 | 必填 | 备注 |
|---|---|---|---|---|---|
| `sector_code` | `板块代码` | str 直传 | — | 是 | 如 `BK0489` |
| `sector_name` | `板块名称` | str | — | 是 | 如 `白酒` |
| `sector_type` | 不在 API 返回中 | 调用方注入（`"industry"`） | — | 是 | 由 endpoint 选择决定 |
| `snapshot_date` | 不在 API 返回中（`name_em` 是实时排名，无日期列） | 使用 fetch 日期（`datetime.now()` 的 `YYYY-MM-DD`） | — | 是 | 实时数据，快照日期取获取日 |
| `market` | 不在 API 返回中 | 常量 `"CN"` | — | 是 | A 股市场 |
| `provider` | 不在 API 返回中 | 常量 `"akshare"` | — | 是 | |
| `rank` | `排名` | int | — | 否 | `name_em` 返回的排名 |
| `pct_chg` | `涨跌幅` | float | % | 否 | 板块涨跌幅 |
| `leading_stock` | `领涨股票` | str | — | 否 | 领涨股代码或名称（源码列名为 `领涨股票`，可能含代码或名称） |
| `leading_stock_name` | 不在 `name_em` 返回中 | None（默认） | — | 否 | `name_em` 只提供 `领涨股票` 单列，不区分代码/名称；待 smoke 确认后决定填充策略 |
| `leading_pct_chg` | `领涨股票-涨跌幅` | float | % | 否 | |
| `advance_count` | `上涨家数` | int | 家 | 否 | |
| `decline_count` | `下跌家数` | int | 家 | 否 | |
| `total_count` | 派生（advance+decline+flat） | int | 家 | 否 | `name_em` 不直接返回总家数，派生计算 |
| `turnover_rate` | `换手率` | float | % | 否 | |
| `main_net_inflow` | 不在 `name_em` 返回中 | None（默认） | — | 否 | `name_em` 不含主力净流入字段；如需此字段需另寻 endpoint（后续评估） |
| `members` | 不在 `name_em` 返回中 | None（默认） | — | 否 | 成分股列表需 `cons_em` 获取，见 §5.2.3 |
| `fetched_at` | 不在 API 返回中 | `datetime.now().isoformat()` | ISO-8601 | 否 | 数据获取时间戳 |
| `raw_payload` | 不映射到 canonical | 保留原始 dict | — | 否 | 调试/审计用 |

**映射规则**：

1. **缺失字段填 None / 0**：`from_dict()` 松弛映射保证不抛 KeyError。`advance_count` / `decline_count` / `total_count` 默认 0；其余可选字段默认 None。
2. **单位不变**：AKShare 涨跌幅单位是 `%`（如 `2.35`），直接映射；`main_net_inflow` 单位是 `元`。
3. **禁止编造**：如果 AKShare 不返回某字段（如 `market_temperature` 在 sector 中不存在），该字段保持 None/默认值，不通过计算或其他方式编造。
4. **日期格式**：`snapshot_date` 统一为 `YYYY-MM-DD`。AKShare 如果返回 `2026-07-30` 格式则直传；如果返回 `20260730` 则转换。
5. **中文字段名**：AKShare 返回的 DataFrame 列名为中文（如 `涨跌幅`、`换手率`）。映射层负责中→英 alias 转换。

#### 5.2.2 sector.ranking 字段映射表

`stock_board_industry_name_em()` 返回全行业板块排名（离线源码验证：12 列）→ `_EXPECTED_SECTOR_RANKING_FIELDS`（8 字段子集）：

| SectorSnapshot 字段 | AKShare 原始字段（源码验证） | 备注 |
|---|---|---|
| `sector_code` | `板块代码` | 如 `BK0489` |
| `sector_name` | `板块名称` | 如 `白酒` |
| `sector_type` | 调用方注入（`"industry"`） | 不在 API 返回中 |
| `snapshot_date` | 不在 `name_em` 返回中 | 使用 fetch 日期 |
| `rank` | `排名` | int，1=涨幅最高 |
| `pct_chg` | `涨跌幅` | float % |
| `advance_count` | `上涨家数` | int |
| `decline_count` | `下跌家数` | int |

**ranking 与 snapshot 共享 endpoint（V0.2）**：ranking 和 snapshot 调用同一 `name_em()`。ranking 直接消费全量返回（多板块多行），snapshot 按 `sector_code` 过滤单板块行。ranking 不需要额外字段。

#### 5.2.3 cons_em 定位：未来 component enrichment 候选（不在 P3-A mapping scope）

`stock_board_industry_cons_em(symbol)` 的源码确认返回**成分股列表**（个股粒度，16 列：序号/代码/名称/最新价/涨跌幅/涨跌额/成交量/成交额/振幅/最高/最低/今开/昨收/换手率/市盈率-动态/市净率）。它不是板块级聚合数据源，因此在 P3-A 本链中：

- ❌ 不作为 `sector.snapshot` 或 `sector.ranking` 的主数据源。
- ❌ 不在 P3-A 本链的字段映射 scope 内。
- ✅ 可作为**未来 component enrichment** 的候选：当需要填充 `SectorSnapshot.members`（成分股代码列表）时，`cons_em` 可获取单板块的成分股代码（`代码` 列）。但此功能属于后续迭代，不在 P3-A 激活链中实现。

### 5.3 空集与异常处理

#### 5.3.1 空集语义

| 场景 | AKShare 行为 | DataResult 语义 | source_trace |
|---|---|---|---|
| 板块代码不存在 | 返回空 DataFrame 或报错 | `DataResult.success(data=None/is_empty, provider="akshare")` | 不含 `"ud_materialized(ok)"` 或 `"cache(ok)"`（允许 `skipped` / `miss`） |
| 非交易日请求 | 返回空 DataFrame | 同上 | 同上 |
| 正常返回数据 | 返回非空 DataFrame | `DataResult.success(data=SectorSnapshot/list, provider="akshare")` | |

**关键约束**：空集 ≠ 失败。空 DataFrame 正常返回 `DataResult.success`，不抛异常、不重试。与主 RFC §5.1.5 空返回语义一致。

#### 5.3.2 异常处理

| 异常类型 | 来源 | 处理 | source_trace |
|---|---|---|---|
| `SSLError` / 网络超时 | TLS 握手失败 / 出口阻断 | `DataResult.error(provider="error", source_trace=["akshare(error: SSLError: ...)"])` | 记录错误类型 |
| `ConnectionError` | DNS / 网络不可达 | 同上 | |
| `TimeoutError` | 请求超时 | 同上 | |
| `ProviderError` | API 内部错误 / 字段缺失 | 同上 | |
| `JSONDecodeError` / `ValueError` | 解析异常 | 同上 | |

**异常处理约束**：
1. **不自动重试**：所有异常仅记录，不自动重试（主 RFC §13.4.5.5 零写入边界）。
2. **不降级写入**：异常不触发物化写入或 Cache 写入。
3. **SSL 失败特殊处理**：B2 的 SSL 失败是网络层 egress 限制。后续 Pascal 授权的独立网络诊断中处理，不在本 RFC 范围。

### 5.4 Rate-Limit 与 Retry 策略

AKShareProvider 继承 `BaseExternalProvider` 的 rate limiter（`rate_limit_rpm=200`）和 retry 配置（`retry_max_attempts=3`，`retry_backoff_base=1.0`）。

| 参数 | 当前值 | sector 适用性 | 备注 |
|---|---|---|---|
| `rate_limit_rpm` | 200 | ✅ 复用 | AKShare 匿名调用，200 rpm 足够 |
| `retry_max_attempts` | 3 | ⚠️ 需讨论 | 主 RFC 要求 smoke 不自动重试；但 Provider 内部 retry 是网络层重试，不是 smoke 层重试 |
| `retry_backoff_base` | 1.0s | ✅ 复用 | 指数退避基准 |

**裁定**：sector Provider 的 rate-limit/retry 复用 AKShareProvider 的现有配置。`retry_max_attempts=3` 是 Provider 内部的网络层重试（针对瞬时网络抖动），与主 RFC §13.4.5.5 的「smoke 不自动重试」不冲突 — smoke 层面的「不重试」指的是 smoke 脚本不会对失败的 capability 发起第二次完整 smoke 调用，而 Provider 内部的 retry 是单次 fetch 内的透明重试。

### 5.5 离线测试方式

#### 5.5.1 Fake Transport / Injected Client 模式

sector Provider 激活后的离线测试采用 **injected transport** 模式（参考 Phase 1D `kline_daily` 的 `KlineClient` 注入模式）：

```
AKShareProvider
  ├── __init__(http_client=None)  ← 默认 lazy 构造 AKShareKlineClient
  │                                 测试注入 FakeKlineClient / FakeSectorClient
  │
  ├── _fetch_kline_daily(security_id, params)
  │     └── 使用 KlineClient（Phase 1D 已有）
  │
  └── _fetch_sector(operation, security_id, params)   ← T2/T3 新增
        └── 使用 SectorClient（新接口，T2 定义）
              ├── AKShareSectorClient（真实调用，T2/T3 实现但不触发）
              └── FakeSectorClient（返回 fixture DataFrame，离线测试用）
```

**SectorClient 接口（T2 定义精确签名）**：

> **V0.2 变更**：两个方法底层均调用 `stock_board_industry_name_em()`。`get_sector_ranking()` 直接返回全量；`get_sector_snapshot()` 在 Client 层按 `sector_code`（或 `sector_name`）过滤单板块行。

```python
class SectorClient(Protocol):
    """Abstract sector data client (injected into AKShareProvider)."""

    def get_sector_snapshot(
        self, sector_code: str, sector_type: str = "industry"
    ) -> pd.DataFrame:
        """Return board-level aggregate row for a single sector.

        Internally calls stock_board_industry_name_em() and filters by sector_code.
        Returns a 1-row DataFrame (or empty if sector_code not found).
        """
        ...

    def get_sector_ranking(
        self, sector_type: str = "industry"
    ) -> pd.DataFrame:
        """Return ranking DataFrame for all sectors of a type.

        Internally calls stock_board_industry_name_em() and returns the full result.
        """
        ...
```

**FakeSectorClient**（离线测试用）：

```python
class FakeSectorClient:
    """Returns fixture DataFrames without network calls."""

    def __init__(self, snapshot_df=None, ranking_df=None):
        self._snapshot_df = snapshot_df or _default_snapshot_fixture()
        self._ranking_df = ranking_df or _default_ranking_fixture()

    def get_sector_snapshot(self, sector_code, sector_type="industry"):
        return self._snapshot_df.copy()

    def get_sector_ranking(self, sector_type="industry"):
        return self._ranking_df.copy()
```

**关键约束**：
1. `FakeSectorClient` 不调用任何真实 AKShare 函数，不发起网络请求。
2. Fixture DataFrame 包含 AKShare 中文字段名（模拟真实返回结构），映射层负责中→英转换。
3. 离线测试验证：endpoint 选择 → fake fetch → canonical mapping → `SectorSnapshot.from_dict()` → DataResult 封装全链路。
4. 异常测试：`FakeSectorClient` 可注入异常（如 `raise SSLError(...)`）验证异常处理路径。

#### 5.5.2 离线测试覆盖

| 测试集 | 覆盖内容 | 需网络 | 文件路径 |
|---|---|---|---|
| endpoint 选择 | `sector.snapshot` → `name_em()` + 过滤；`sector.ranking` → `name_em()` 全量 | 否 | `tests/test_sector_provider_activation.py`（T3 新增） |
| 字段映射 | AKShare 中文 DataFrame → `SectorSnapshot.from_dict()` | 否 | 同上 |
| 空集处理 | 空 DataFrame → `DataResult.success(data=None)` | 否 | 同上 |
| 异常处理 | `FakeSectorClient` 注入 SSLError → `DataResult.error` | 否 | 同上 |
| ranking 排序 | 多板块返回 → `pct_chg` desc 排序 | 否 | 复用 `test_sector_service.py` |
| sector_type 映射 | industry / concept endpoint 选择 | 否 | 同上 |
| snapshot 单板块过滤 | `name_em()` 全量返回中按 sector_code 过滤出单行 | 否 | 同上 |

### 5.6 后续真实 Smoke 最小参数

后续 Pascal 授权的真实 smoke（主 RFC PR-2 Gate）使用以下最小参数：

| 参数 | sector.snapshot | sector.ranking |
|---|---|---|
| endpoint | `stock_board_industry_name_em()` | `stock_board_industry_name_em()` |
| 标的 | 单板块 `BK0489`（白酒行业，从全量返回中过滤） | 全行业（全量返回直接使用） |
| 日期窗口 | 实时数据，单次调用（无日期参数） | 同上 |
| 调用次数 | ≤2 次（snapshot 和 ranking 可共享同一次 `name_em()` 调用） | ≤1 次 |
| sector_type | `industry` | `industry` |
| 写入 | 零写入（不写物化集合、不写 Cache） | 同上 |

**Smoke 报告模板**：复用主 RFC §13.4.2 的 YAML 模板，包含 connectivity、auth、permissions、field_mapping、data_sample、vs_fixture、overall verdict。

**Smoke 前置条件**：B2 SSL 网络诊断必须先通过。B2 的 SSL 失败是 egress 限制，后续单变量网络诊断（切换网络出口、TLS 版本检查）须 Pascal 独立授权并在 smoke 前完成。

### 5.7 失败回滚

| 失败场景 | 回滚操作 | 数据影响 |
|---|---|---|
| Provider 激活后字段映射不匹配 | 回退到 schema-level stub（`stub_dataframe_for`） | 无（stub 不写数据） |
| Smoke 失败（SSL/网络/字段差异 >50%） | 不进入 DDL/CANARY Gate | 无（零写入） |
| Canary 写入数据质量异常 | `delete_by_filter` 清理脚本（主 RFC PR-CANARY） | 可逆（删除写入的文档） |

---

## 6. 授权 Gate 与副作用边界

### 6.1 本阶段（T1 RFC/SPEC）副作用矩阵

| 操作 | 本阶段权限 | 风险 |
|---|---|---|
| 读写 RFC/SPEC 文档 | ✅ | 无 |
| 读取现有代码/测试/文档 | ✅ | 无 |
| 真实 AKShare API 调用 | ❌ 禁止 | — |
| 真实 MongoDB 连接 | ❌ 禁止 | — |
| DDL/DML | ❌ 禁止 | — |
| Cache 写入 | ❌ 禁止 | — |
| cron/systemd 注册 | ❌ 禁止 | — |
| Git commit/push | ❌ 禁止 | — |
| 读取 secrets / `.env` | ❌ 禁止 | — |

### 6.2 后续 Gate 清单

| Gate | 内容 | 授权方 | 前置条件 |
|---|---|---|---|
| PR-2 | 真实 AKShare smoke（sector.snapshot + sector.ranking） | Pascal | B2 SSL 网络诊断通过 |
| G-A-2 | refresh 生产激活（`_is_refresh_authorized()` → True） | Pascal | T3 离线实现通过 |
| PR-DDL-P3A | MongoDB 集合 `03_data_ud_market_sector_snapshot` 创建 + 索引（已冻结） | Pascal | PR-2 smoke verdict ≥ conditional_pass |
| PR-CANARY-P3A | 手动 canary refresh 调用写入 | Pascal | PR-DDL-P3A 完成 |

---

## 7. 验收标准

### 7.1 功能验收

- [ ] RFC-03-014-p3a-sector-provider-activation.md 和 SPEC-03-014-p3a-sector-provider-activation.md 两份独立文档存在且互相交叉引用
- [ ] 每份文档区分「已验证事实」「假设」「待验证」「Pascal 授权 Gate」
- [ ] `sector.snapshot` / `sector.ranking` 的 endpoint 选择、字段映射、空集/异常/retry 契约明确定义
- [ ] 离线测试方式（fake transport / injected client）明确定义
- [ ] 后续真实 smoke 最小参数、报告模板、回滚策略明确
- [ ] 明确 P3-B/P3-C 不在本链范围
- [ ] 明确 T2 Design 所需 allowlist 与不可修改路径

### 7.2 非功能验收

- [ ] 不触发真实 AKShare 调用（静态检查：本阶段无 `akshare.stock_*` 调用代码）
- [ ] 不触发真实 MongoDB 连接（静态检查）
- [ ] 不修改 SectorSnapshot 19 字段 schema
- [ ] 不修改 `_EXPECTED_SECTOR_*_FIELDS` / STUB_COLUMNS 定义
- [ ] 不修改主 RFC/SPEC/DESIGN-03-014 已有内容（仅交叉引用）
- [ ] `git diff --check` exit 0
- [ ] `git diff --name-status` 中本卡 diff 仅含本 RFC 和对应 SPEC 两份文档
- [ ] 声明所有板块/行业数据为辅助研究数据，不构成交易指令或投资建议

### 7.3 与主 RFC 的一致性验收

- [ ] 本 RFC 的 endpoint 选择与主 RFC §13.4.5.8 B2 裁决总表一致（`sector.snapshot` / `sector.ranking` 为 offline stub → 待 smoke 验证）
- [ ] 本 RFC 的副作用矩阵与主 RFC §13.1 / SPEC §P0.8 / §P1.8 一致
- [ ] 本 RFC 的 Gate 清单与主 RFC §6.2 PR-2 / PR-DDL-P3A / PR-CANARY-P3A 对应
- [ ] 本 RFC 不引入与主 RFC 冲突的决策

---

## 8. 开放问题

- [x] ~~OQ-P3A-1~~（**V0.2 已解决**）：`stock_board_industry_cons_em` 返回的是**成分股列表**（个股粒度），不是板块级聚合。离线源码已确认。`sector.snapshot` 和 `sector.ranking` 共享 `stock_board_industry_name_em()` 作为板块级聚合主 endpoint。
- [ ] OQ-P3A-2：`concept` 类型（`stock_board_concept_*`）是否在当前阶段一并激活，还是仅覆盖 `industry`？建议仅 industry，concept 后续。
- [ ] OQ-P3A-3：`region` / `style` 类型暂无直接对应的 AKShare endpoint。是否在 P3-A 范围内标注为「数据源待定」，还是需要另寻数据源？
- [ ] OQ-P3A-4：B2 SSL 失败的单变量网络诊断何时执行？由 Pascal 手动还是 Agent 辅助？
- [ ] OQ-P3A-5：`retry_max_attempts=3` 是否适用于 sector endpoint？AKShare 匿名调用是否需要不同的重试策略？
- [ ] OQ-P3A-6（V0.2 新增）：`stock_board_industry_name_em()` 返回的 `领涨股票` 列是股票代码还是名称？`leading_stock` / `leading_stock_name` 如何映射？待 smoke 确认。
- [ ] OQ-P3A-7（V0.2 新增）：`name_em()` 是实时排名，不含历史日期维度。`snapshot_date` 取 fetch 日期是否满足业务需求？如需历史板块快照，是否需要 `stock_board_industry_hist_em` 作为补充？

---

## 9. 参考资料

- RFC-03-014（Unified Data Phase 3 主 RFC，V0.19）—— §5.1 sector 业务语义、§13.4.5 B2 冻结证据、§P0/P1 状态矩阵
- SPEC-03-014（Phase 3 契约，V0.19）—— §3.1 SectorSnapshot 19 字段、§P0.4 PA-1~PA-9 验收项、§P1.5 refresh 契约
- DESIGN-03-014（Phase 3 详细设计，V0.21）—— §3.1 sector 文件矩阵、§17.x provider 路由
- RFC-03-012（Phase 1D 外部 Provider 激活）—— `KlineClient` 注入模式参考
- AKShare 官方文档：`stock_board_industry_name_em`、`stock_board_industry_cons_em`（离线源码验证：`.venv/lib/python3.12/site-packages/akshare/stock/stock_board_industry_em.py`）
- B2 smoke 冻结证据：`/tmp/yquant-b2-pr234-20260726/pr2/smoke-sector-20260726.yaml`（只读副本）

---

## 声明

本 RFC 中涉及的板块/行业数据为辅助研究数据范畴。RFC 本身不包含可执行的交易指令或投资建议。所有 domain object 对应的 SPEC-03-014 中强制标注「辅助研究数据，不构成交易指令或投资建议」，该声明通过静态 grep 验证。
