# SPEC-03-014: P3-A Sector Provider 激活 — 可执行契约

## 元数据

| 项 | 值 |
|---|----|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.2 修正 endpoint 契约：离线源码验证发现 `stock_board_industry_rank_em` 不存在、`cons_em` 返回成分股而非板块级聚合；将 `stock_board_industry_name_em()` 固定为 sector.snapshot 与 sector.ranking 共享主候选 endpoint。与 RFC-03-014-p3a-sector-provider-activation V0.2 一致。） |
| 版本号 | V0.2 |
| 来源 RFC | RFC-03-014-p3a-sector-provider-activation（V0.2） |
| 关联 RFC | RFC-03-014（Phase 3 主 RFC，V0.19）、RFC-03-007（Unified Data Layer 总纲）、RFC-03-012（Phase 1D Provider 激活模式参考） |
| 关联 SPEC | SPEC-03-014（Phase 3 主 SPEC，V0.19） |
| 关联 Design | DESIGN-03-014（Phase 3 设计 V0.21）、待 T2 创建 DESIGN-03-014-p3a-sector-provider-activation |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Principal（后续 Gate 阶段） |

---

## 0. 术语对齐与基线锚定

本 SPEC 继承 SPEC-03-014（Phase 3 主 SPEC V0.19）的全部基线，不重述背景。以下锁定 P3-A sector Provider 激活链必须一致的措辞：

- **P3-A sector Provider 激活** = 将 `sector.snapshot` / `sector.ranking` 两个 capability 从当前 schema-level stub（0-row DataFrame）推进到真实 AKShare endpoint 调用的受控演进过程。
- **当前状态**：P0 ✅（stub + 测试）、P1 ✅（fake-only materialized read + refresh 三态守卫）。本 SPEC 定义 Provider 激活的离线可实现设计（endpoint 映射、字段映射、测试方式），不触发真实 I/O。
- **B2 冻结证据**：2026-07-26 B2 smoke 对 `stock_board_industry_cons_em("BK0489")` 调用 2 次均 SSLError。证据冻结在 `/tmp/yquant-b2-pr234-20260726/pr2/`（只读副本，不可移动/提交/重跑）。`sector.snapshot` / `sector.ranking` 当前为 **offline stub**（主 SPEC §P0.2 状态矩阵）。
- **endpoint 修正（V0.2）**：`sector.snapshot` → `stock_board_industry_name_em()`（从全量返回中按 sector_code 过滤单板块行）；`sector.ranking` → `stock_board_industry_name_em()`（全量返回直接使用）。两个 capability 共享同一 endpoint。`stock_board_industry_rank_em` 不存在（离线源码验证）；`stock_board_industry_cons_em` 返回成分股列表，不作 sector snapshot/ranking 主数据源。
- **schema 不变**：`SectorSnapshot` 19 字段（SPEC §3.1）、`_EXPECTED_SECTOR_SNAPSHOT_FIELDS`（12 列）、`_EXPECTED_SECTOR_RANKING_FIELDS`（8 列）均已冻结（P0），本 SPEC 不修改。
- **read-only 不变**：`DataRouter.query()` 对 P3 capability 全程零持久化写（主 SPEC §P1.6 / §14.5 Zero-Persistence-Write）。
- **三态守卫不变**：`refresh_sector_snapshot()` / `refresh_sector_ranking()` 的 unauthorized / injected-not-implemented / authorized 三态守卫保持（主 SPEC §P1.5.1）。

### 0.1 本 SPEC 不重复定义的契约

以下契约由主 SPEC-03-014 定义，本 SPEC 仅引用，不重述：

| 契约 | 主 SPEC 定义位置 | 本 SPEC 引用方式 |
|---|---|---|
| SectorSnapshot 19 字段 schema | §3.1 | 映射目标，不修改 |
| `_EXPECTED_SECTOR_SNAPSHOT_FIELDS`（12 列） | §P0.4 PA-1 | endpoint 映射的 expected 基线 |
| `_EXPECTED_SECTOR_RANKING_FIELDS`（8 列） | §P0.4 PA-2 | 同上 |
| STUB_COLUMNS twin 定义 | §P0.4 PA-7 | 不修改 |
| 业务唯一键 `{market, sector_code, snapshot_date}` | §4.bis.1 | upsert 目标，不修改 |
| Zero-Persistence-Write | §14.5 | query 路径约束，不修改 |
| refresh 三态守卫 | §P1.5.1 | 不修改 |
| P3PersistenceWriter upsert/get | §P1.4 | 不修改 |

---

## 1. 需求摘要

将 RFC-03-014-p3a-sector-provider-activation 的需求落为可执行契约，核心交付 6 件事：

1. **endpoint 选择契约**：精确选定 `sector.snapshot` / `sector.ranking` 的 AKShare endpoint，定义参数、日期窗口、sector_type 映射。
2. **字段映射契约**：AKShare 中文字段 → canonical `SectorSnapshot` 字段的精确映射表，含类型转换、单位、缺失处理。
3. **空集/异常/retry 契约**：空 DataFrame、SSL/网络/解析异常、rate-limit/retry 的可测试行为定义。
4. **离线测试方式**：fake transport / injected `SectorClient` 接口定义、fixture 覆盖、异常注入。
5. **数据合理性与 schema-drift 规则**：禁止编造值、缺失字段处理、字段漂移容错。
6. **后续真实 smoke 最小参数与授权清单**：Pascal Gate 的最小调用参数、报告模板、失败回滚。

---

## 2. 范围

### 2.1 In Scope

- [x] endpoint 选择契约定义（§3.1）——基于公开文档 + B2 冻结证据
- [ ] endpoint 选择逻辑实现（❌ 属 T2/T3，不在本 SPEC 阶段）
- [x] 字段映射表定义（§3.2）——AKShare 中文 → SectorSnapshot canonical
- [ ] canonical mapping 代码实现（❌ 属 T2/T3）
- [x] 空集/异常/retry 可测试契约定义（§4）
- [x] 离线测试方式定义（§5）——SectorClient 接口、FakeSectorClient、fixture
- [x] 数据合理性与 schema-drift 规则（§6）
- [x] 后续真实 smoke 最小参数与授权清单（§7）
- [x] T2 Design allowlist 与不可修改路径（§8）

### 2.2 Out of Scope

- ❌ 真实 AKShare API 调用（属后续 PR-2 Gate，Pascal 授权）
- ❌ 真实 MongoDB 连接 / DDL / DML（属后续 Gate）
- ❌ Cache 写入 / cron/systemd / webhook（属后续 Gate）
- ❌ `.env` 读取 / secrets 回显
- ❌ Git commit / push
- ❌ 修改 SectorSnapshot 19 字段 schema（P0 已冻结）
- ❌ 修改 `_EXPECTED_SECTOR_*_FIELDS` / STUB_COLUMNS（P0 已冻结）
- ❌ 修改主 SPEC-03-014 已有内容（仅交叉引用）
- ❌ 修改 `providers/akshare.py` 的 `kline_daily` 路径
- ❌ 修改 router.py / client.py / adapters/ 读路径
- ❌ 修改 P3-B / P3-C 任何逻辑
- ❌ P3-B `flow.northbound_daily` Pascal C fail-stop（恒 None，不变）
- ❌ 重跑 B2 live-read（B2 预算已用尽）
- ❌ `region` / `style` 类型 endpoint（数据源待定，不阻塞当前阶段）

---

## 3. 功能规格

### 3.1 Endpoint 选择契约（V0.2 修正）

> **离线源码验证事实**（`.venv/lib/python3.12/site-packages/akshare/stock/stock_board_industry_em.py`）：
> - `stock_board_industry_rank_em` **不存在**。
> - `stock_board_industry_cons_em(symbol)` 返回**成分股列表**（个股粒度，16 列），不是板块级聚合。
> - `stock_board_industry_name_em()` 返回**板块级排名**（12 列：排名/板块名称/板块代码/最新价/涨跌额/涨跌幅/总市值/换手率/上涨家数/下跌家数/领涨股票/领涨股票-涨跌幅）。无参数。

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | `sector.snapshot` endpoint 选择 | `sector_code`（如 `BK0489`）、`sector_type`（默认 `industry`） | 调用 `stock_board_industry_name_em()` 全量返回，在 Client 层按 `sector_code`（`板块代码` 列）或 `sector_name`（`板块名称` 列）过滤出单板块行 | `sector_type != "industry"` 且 `!= "concept"` → 值待定，当前阶段仅支持 industry；过滤无匹配 → 空 DataFrame（F-030 空集语义） |
| F-002 | `sector.ranking` endpoint 选择 | `sector_type`（默认 `industry`）、`date`（可选，当前忽略，见 F-004）、`limit`（默认 20） | 调用 `stock_board_industry_name_em()` 全量返回直接使用 | 同上 |
| F-003 | `concept` 类型 endpoint 路由 | `sector_type="concept"` | 调用 `stock_board_concept_name_em` / `stock_board_concept_cons_em`（待验证） | 当前阶段标注「次优先」，T2 决定是否一并实现 |
| F-004 | endpoint 参数注入 | `sector_code`、`sector_type` 从 service 层传入 | `name_em()` 无参数；`date` 参数当前被忽略（`name_em` 返回实时排名，不含历史日期维度）；`limit` 在 Client/Provider 层截取前 N 行 | `date=None` 时使用实时数据；如需历史快照需另寻 endpoint（OQ-P3A-7） |
| F-005 | `sector_type` 注入 | AKShare 返回不含 `sector_type` 字段 | 由 endpoint 选择决定（industry endpoint → `"industry"`） | 禁止从 API 返回中推断 sector_type |

**endpoint 契约约束**：

1. `stock_board_industry_name_em()` 是 sector.snapshot 和 sector.ranking 的**共享 endpoint**（V0.2 修正）。snapshot 过滤单板块行，ranking 使用全量返回。
2. `stock_board_industry_rank_em` **不存在**。任何引用该 endpoint 的代码、测试、smoke 参数均属错误。
3. `stock_board_industry_cons_em` 返回成分股列表（个股粒度），**不作为** sector.snapshot/ranking 主数据源。仅可用于未来 component enrichment（填充 `members` 字段），不在 P3-A 本链 mapping scope 内。
4. `name_em()` 的真实 payload 仍待受控授权 smoke 验证。源码静态读取的字段列表不是 live-read 证据。
5. AKShare 匿名调用，无 token / API key（主 RFC OQ-8 已解决）。
6. 禁止臆定未在源码中出现的 endpoint 或字段名。

### 3.2 字段映射契约

#### 3.2.1 sector.snapshot 映射（F-006 ~ F-015）

> **V0.2 修正**：映射源 endpoint 从 `cons_em` 改为 `name_em()`。`name_em()` 返回板块级排名 12 列（离线源码验证）。snapshot 调用全量返回后按 sector_code 过滤单板块行。

| 编号 | 行为 | AKShare 原始字段（源码验证） | SectorSnapshot 字段 | 转换 | 单位 |
|---|---|---|---|---|---|
| F-006 | 板块代码映射 | `板块代码` | `sector_code` | str 直传 | — |
| F-007 | 板块名称映射 | `板块名称` | `sector_name` | str 直传 | — |
| F-008 | 板块类型注入 | 不在 API 返回中 | `sector_type` | 调用方注入 `"industry"` | — |
| F-009 | 日期映射 | 不在 `name_em` 返回中（实时排名无日期列） | `snapshot_date` | 使用 fetch 日期 → `YYYY-MM-DD` | — |
| F-010 | 涨跌幅映射 | `涨跌幅` | `pct_chg` | float | % |
| F-011 | 排名映射 | `排名` | `rank` | int | — |
| F-012 | 涨跌家数映射 | `上涨家数` / `下跌家数` | `advance_count` / `decline_count` | int | 家 |
| F-013 | 换手率映射 | `换手率` | `turnover_rate` | float | % |
| F-014 | 主力净流入映射 | 不在 `name_em` 返回中 | `main_net_inflow` → None | — | — |
| F-015 | 领涨股映射 | `领涨股票` / `领涨股票-涨跌幅` | `leading_stock` / `leading_pct_chg` | str / float | — / % |

**常量字段**（不在 API 返回中，由映射层注入）：

| 字段 | 值 | 来源 |
|---|---|---|
| `market` | `"CN"` | 常量（A 股市场） |
| `provider` | `"akshare"` | 常量 |
| `fetched_at` | `datetime.now().isoformat()` | 运行时生成 |
| `raw_payload` | 原始行 dict（可选） | 调试/审计 |

#### 3.2.2 sector.ranking 映射（F-016 ~ F-019）

> **V0.2 修正**：ranking endpoint 从不存在的 `rank_em` 改为 `name_em()`。ranking 直接消费 `name_em()` 全量返回。

| 编号 | 行为 | AKShare 原始字段（源码验证） | SectorSnapshot 字段 | 备注 |
|---|---|---|---|---|
| F-016 | 多板块代码映射 | `板块代码` | `sector_code` | 每行一个板块 |
| F-017 | 多板块名称映射 | `板块名称` | `sector_name` | |
| F-018 | 排名+涨跌幅映射 | `排名` / `涨跌幅` | `rank` / `pct_chg` | `name_em` 核心字段 |
| F-019 | 涨跌家数映射 | `上涨家数` / `下跌家数` | `advance_count` / `decline_count` | |

**ranking 与 snapshot 共享 endpoint（V0.2）**：ranking 和 snapshot 调用同一 `name_em()`。ranking 直接消费全量返回，snapshot 按 `sector_code` 过滤单板块行。ranking 不需要额外字段。`_EXPECTED_SECTOR_RANKING_FIELDS`（8 列）是 `_EXPECTED_SECTOR_SNAPSHOT_FIELDS`（12 列）的严格子集（P0 PA-7 已验证）。

#### 3.2.3 映射规则（F-020 ~ F-024）

| 编号 | 规则 | 说明 |
|---|---|---|
| F-020 | 缺失字段填默认值 | `from_dict()` 松弛映射；advance/decline/total_count → 0；其余可选 → None |
| F-021 | 单位不变 | 涨跌幅 `%`、净流入 `元`、换手率 `%` 直接映射 |
| F-022 | 禁止编造 | 不通过计算或其他方式为缺失字段编造值 |
| F-023 | 日期格式标准化 | `snapshot_date` → `YYYY-MM-DD`（AKShare 返回 `2026-07-30` 直传；`20260730` 转换） |
| F-024 | 中文字段 alias | AKShare 中文列名 → canonical 英文字段名，映射层负责转换 |

### 3.3 数据合理性与 schema-drift 规则（F-025 ~ F-029）

| 编号 | 规则 | 说明 |
|---|---|---|
| F-025 | unmapped 额外字段 | AKShare 返回的额外字段（不在 expected 集中）静默忽略，不抛异常 |
| F-026 | 缺失字段 | expected 集中的字段缺失 → 填 None/默认值，不抛 KeyError |
| F-027 | 字段漂移 | 真实 smoke 时如果字段名匹配度 <70% → fail（主 RFC §13.4.4），需更新映射后重做 |
| F-028 | 空值校验 | `sector_code` / `sector_name` / `sector_type` / `snapshot_date` 四个必填字段为空时 → 记录 warning，该行映射为 None |
| F-029 | 类型强转容错 | AKShare 返回的数值字段可能为字符串（如 `"2.35%"`）→ `_safe_float` 容错转换，失败填 None |

---

## 4. 空集 / 异常 / Retry 契约

### 4.1 空集语义（F-030 ~ F-032）

| 编号 | 场景 | 行为 | source_trace |
|---|---|---|---|
| F-030 | 板块代码不存在 → 空 DataFrame | `DataResult.success(data=None/is_empty, provider="akshare")` | 不含 `"ud_materialized(ok)"` 或 `"cache(ok)"` |
| F-031 | 非交易日 → 空 DataFrame | 同上 | 同上 |
| F-032 | ranking 返回空列表 | `DataResult.success(data=[], provider="akshare")` | 同上 |

**约束**：空集 ≠ 失败。空 DataFrame 正常返回 `DataResult.success`，不抛异常、不重试。

### 4.2 异常处理（F-033 ~ F-038）

| 编号 | 异常类型 | 处理 | source_trace 条目 |
|---|---|---|---|
| F-033 | `SSLError` / TLS 失败 | `DataResult.error(provider="error", source_trace=["akshare(error: SSLError: ...)"])` | 记录错误类型 |
| F-034 | `ConnectionError` / DNS 失败 | 同上 | `"akshare(error: ConnectionError: ...)"` |
| F-035 | `TimeoutError` | 同上 | `"akshare(error: TimeoutError: ...)"` |
| F-036 | `ProviderError`（API 内部错误） | 同上 | `"akshare(error: ProviderError: ...)"` |
| F-037 | `JSONDecodeError` / `ValueError`（解析异常） | 同上 | `"akshare(error: JSONDecodeError: ...)"` |
| F-038 | `pd.errors.ParserError`（DataFrame 解析异常） | 同上 | `"akshare(error: ParserError: ...)"` |

**异常处理约束**：
1. 不自动重试（主 RFC §13.4.5.5 零写入边界）。
2. 不降级写入（不触发物化写入或 Cache 写入）。
3. SSL 失败特殊处理：B2 SSL 是 egress 限制，后续 Pascal 授权的独立网络诊断中处理。

### 4.3 Rate-Limit 与 Retry（F-039 ~ F-041）

| 编号 | 参数 | 当前值 | sector 适用性 | 备注 |
|---|---|---|---|---|
| F-039 | `rate_limit_rpm` | 200 | ✅ 复用 AKShareProvider 现有配置 | AKShare 匿名，200 rpm 足够 |
| F-040 | `retry_max_attempts` | 3 | ✅ 复用 | Provider 内部网络层重试（瞬时抖动），不与 smoke 层「不重试」冲突 |
| F-041 | `retry_backoff_base` | 1.0s | ✅ 复用 | 指数退避基准 |

---

## 5. 离线测试方式

### 5.1 SectorClient 接口（F-042 ~ F-044）

> **V0.2 修正**：两个方法底层均调用 `stock_board_industry_name_em()`。

| 编号 | 接口 | 签名 | 备注 |
|---|---|---|---|
| F-042 | `SectorClient.get_sector_snapshot()` | `(sector_code: str, sector_type: str = "industry") -> pd.DataFrame` | 调用 `name_em()` 全量返回后按 `sector_code`（`板块代码` 列）过滤单板块行，返回 1-row DataFrame（或空） |
| F-043 | `SectorClient.get_sector_ranking()` | `(sector_type: str = "industry") -> pd.DataFrame` | 调用 `name_em()` 全量返回直接使用，返回全行业排名 DataFrame |
| F-044 | `SectorClient` Protocol | 参考 `KlineClient` 模式（Phase 1D） | AKShareSectorClient / FakeSectorClient 实现同一接口 |

### 5.2 FakeSectorClient（F-045 ~ F-047）

| 编号 | 行为 | 说明 |
|---|---|---|
| F-045 | fixture DataFrame 构造 | 包含 AKShare 中文字段名，模拟真实返回结构 |
| F-046 | 异常注入 | 支持注入 `SSLError` / `ConnectionError` / `TimeoutError` / 空 DataFrame |
| F-047 | industry + concept 覆盖 | fixture 包含 industry（BK0489 白酒）和 concept 两种板块类型 |

### 5.3 离线测试覆盖（F-048 ~ F-053）

| 编号 | 测试 | 覆盖 | 需网络 | 文件 |
|---|---|---|---|---|
| F-048 | endpoint 选择测试 | snapshot → `name_em()` + 过滤；ranking → `name_em()` 全量 | 否 | `tests/test_sector_provider_activation.py` |
| F-049 | 字段映射测试 | 中文 DataFrame → SectorSnapshot.from_dict | 否 | 同上 |
| F-050 | 空集处理测试 | 空 DataFrame → DataResult.success(data=None) | 否 | 同上 |
| F-051 | 异常处理测试 | FakeSectorClient 注入异常 → DataResult.error | 否 | 同上 |
| F-052 | ranking 排序测试 | 多板块返回 → pct_chg desc 排序 | 否 | 复用 `test_sector_service.py` |
| F-053 | sector_type 映射测试 | industry / concept endpoint 路由 | 否 | 同 F-048 |

**离线测试约束**：
- 不调用真实 AKShare 函数。
- 不发起网络请求。
- Fixture DataFrame 包含中文字段名（模拟真实结构）。
- 异常测试覆盖 SSLError / ConnectionError / TimeoutError / 空集 / 解析异常。

---

## 6. 数据合理性与 schema-drift

| 编号 | 规则 | 说明 |
|---|---|---|
| A-DRIFT-1 | 禁止编造值 | 缺失字段保持 None/默认值，不通过计算/推断/别名编造 |
| A-DRIFT-2 | 字段名漂移容忍 | AKShare 返回的额外字段静默忽略（不抛异常） |
| A-DRIFT-3 | 字段名缺失容忍 | expected 字段缺失填 None/默认值（不抛 KeyError） |
| A-DRIFT-4 | 字段类型漂移 | 数值字段返回字符串时 `_safe_float` 容错转换 |
| A-DRIFT-5 | 真实 smoke 字段匹配阈值 | ≥90% pass；70-90% conditional_pass；<70% fail（主 RFC §13.4.4） |

---

## 7. 后续真实 Smoke 最小参数与授权清单

### 7.1 Smoke 最小参数（F-054 ~ F-057）

| 编号 | 参数 | sector.snapshot | sector.ranking |
|---|---|---|---|
| F-054 | endpoint | `stock_board_industry_name_em()` | `stock_board_industry_name_em()` |
| F-055 | 标的 | 单板块 `BK0489`（从全量过滤） | 全行业 |
| F-056 | 日期窗口 | 实时数据，单次调用 | 同上 |
| F-057 | 调用次数 | ≤2 次 | ≤1 次 |

### 7.2 Smoke 报告（F-058）

每个 capability 的 smoke 结果独立记录为 YAML 报告（模板见主 RFC §13.4.2），包含 connectivity、auth、permissions、field_mapping、data_sample、vs_fixture、overall verdict。

### 7.3 授权 Gate 清单（F-059 ~ F-062）

| 编号 | Gate | 内容 | 授权方 | 前置条件 |
|---|---|---|---|---|
| F-059 | PR-2 | 真实 AKShare smoke（sector.snapshot + sector.ranking） | Pascal | B2 SSL 网络诊断通过 |
| F-060 | G-A-2 | refresh 生产激活 | Pascal | T3 离线实现通过 |
| F-061 | PR-DDL-P3A | MongoDB 集合创建（已冻结） | Pascal | PR-2 smoke ≥ conditional_pass |
| F-062 | PR-CANARY-P3A | 手动 canary 写入 | Pascal | PR-DDL-P3A 完成 |

### 7.4 失败回滚（F-063 ~ F-065）

| 编号 | 失败场景 | 回滚 | 数据影响 |
|---|---|---|---|
| F-063 | 字段映射不匹配 | 回退到 schema-level stub | 无 |
| F-064 | Smoke 失败 | 不进入 DDL/CANARY Gate | 无（零写入） |
| F-065 | Canary 数据异常 | delete_by_filter 清理脚本 | 可逆 |

---

## 8. T2 Design Allowlist 与不可修改路径

### 8.1 T2 Design 允许创建的文件

| 路径 | 说明 |
|---|---|
| `docs/design/03_data/DESIGN-03-014-p3a-sector-provider-activation.md` | 详细设计文档 |

### 8.2 T2 Design 需定义的内容

| 内容 | 说明 |
|---|---|
| SectorClient 接口签名 | `get_sector_snapshot()` / `get_sector_ranking()` 精确签名 |
| AKShareSectorClient 实现 | 真实 endpoint 调用逻辑（T2 设计，T3 实现） |
| FakeSectorClient 实现 | fixture DataFrame 构造、异常注入 |
| canonical mapping 函数 | AKShare 中文 DataFrame → list[dict]（SectorSnapshot.from_dict 兼容） |
| endpoint 选择逻辑 | `sector_type` → endpoint 路由（industry / concept） |
| AKShareProvider.fetch() sector 分支改造 | 从 stub 路径到真实 SectorClient 调用路径 |
| 测试计划 | 新增测试文件、fixture 覆盖、离线约束 |

### 8.3 T3 Implement 允许修改的文件（预期，T2 Design 最终裁定）

| 路径 | 允许操作 | 约束 |
|---|---|---|
| `providers/akshare.py` | sector 分支激活：从 `stub_dataframe_for` 到 SectorClient 调用 | 不改 kline_daily 路径；不改 capability set；不改 markets |
| `providers/sector_client.py`（新增） | AKShareSectorClient + FakeSectorClient + SectorClient Protocol | 不引入真实网络调用（AKShareSectorClient 延迟构造） |
| `tests/test_sector_provider_activation.py`（新增） | endpoint 选择、字段映射、空集、异常、sector_type 测试 | 零真实 I/O |
| `tests/fixtures/sector_activation_fixtures.py`（新增） | AKShare 中文 DataFrame fixture | 包含 industry + concept |

### 8.4 禁止修改路径

- ❌ `models/domain/sector.py`（SectorSnapshot 19 字段已冻结）
- ❌ `providers/_stub_columns.py` / `providers/__init__.py`（`_EXPECTED_SECTOR_*_FIELDS` / STUB_COLUMNS 已冻结）
- ❌ `router.py`（读路径不变）
- ❌ `client.py`（UnifiedDataClient 不变）
- ❌ `adapters/`（LocalMongoAdapter / P3PersistenceWriter 不变）
- ❌ `services/sector_service.py` 的 read path（`get_sector_snapshot` / `get_sector_ranking` 不变）
- ❌ `freshness.py`（PC-11 命名冲突冻结）
- ❌ 任何 `.env` / config / requirements / SKILL.md / README
- ❌ P3-B / P3-C 相关文件
- ❌ `providers/akshare.py` 的 `kline_daily` 路径（`_fetch_kline_daily` / `_akshare_df_to_daily_bars`）

---

## 9. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-P3A-001 | RFC 和 SPEC 两份独立文档存在且互相交叉引用 | 文件存在性检查 |
| A-P3A-002 | endpoint 选择契约定义完整（F-001 ~ F-005） | 静态检查 |
| A-P3A-003 | 字段映射表定义完整（F-006 ~ F-024） | 静态检查 |
| A-P3A-004 | 空集/异常/retry 契约可测试（F-030 ~ F-041） | 静态检查 |
| A-P3A-005 | 离线测试方式定义（SectorClient / FakeSectorClient / fixture） | 静态检查 |
| A-P3A-006 | 数据合理性规则禁止编造值（A-DRIFT-1） | 静态检查 |
| A-P3A-007 | 后续 smoke 最小参数和授权清单（F-054 ~ F-062） | 静态检查 |
| A-P3A-008 | T2 allowlist 和禁止路径明确（§8） | 静态检查 |
| A-P3A-009 | 不触发真实 I/O（无 `akshare.stock_*` 调用代码） | 静态 grep |
| A-P3A-010 | 不修改 SectorSnapshot schema / STUB_COLUMNS / 主文档 | `git diff --name-status` |
| A-P3A-011 | 与主 RFC/SPEC B2 裁决一致（offline stub → 待 smoke） | 交叉引用检查 |
| A-P3A-012 | `git diff --check` exit 0 | git 命令 |
| A-P3A-013 | `git diff --name-status` 仅含 RFC + SPEC 两份文档 | git 命令 |
| A-P3A-014 | 声明辅助研究数据，不构成交易指令或投资建议 | 静态 grep |

---

## 10. 测试要求

- **单元测试**（T3 阶段）：endpoint 选择、字段映射、空集、异常、sector_type 映射（全部离线，FakeSectorClient）。
- **集成测试**（T3 阶段）：AKShareProvider + FakeSectorClient → SectorService → DataResult 全链路（离线）。
- **回归测试**：现有 `test_sector_service.py` / `test_sector_snapshot.py` / `test_provider_phase3.py` / `test_mapping_sector.py` 在 T3 变更后继续 PASS。
- **不可自动化验证项**：真实 AKShare endpoint 返回结构（属后续 PR-2 smoke）。

---

## 11. 实现约束

- **禁止事项**：真实 AKShare 调用、真实 MongoDB、DDL/DML、Cache 写入、cron/systemd、Git commit/push、secrets 读取、修改主文档/schema/STUB_COLUMNS。
- **依赖限制**：不新增第三方依赖（AKShare 已在 requirements 中）。
- **性能/安全约束**：rate_limit_rpm=200、retry_max_attempts=3、零持久化写（T1~T3 阶段）。

---

## 12. 开放问题

- [x] ~~OQ-P3A-1~~（**V0.2 已解决**）：`stock_board_industry_cons_em` 返回的是**成分股列表**（个股粒度），不是板块级聚合。离线源码已确认。`sector.snapshot` 和 `sector.ranking` 共享 `stock_board_industry_name_em()` 作为板块级聚合主 endpoint。
- [ ] OQ-P3A-2：`concept` 类型是否在当前阶段一并激活？
- [ ] OQ-P3A-3：`region` / `style` 类型数据源待定。
- [ ] OQ-P3A-4：B2 SSL 网络诊断何时执行？
- [ ] OQ-P3A-5：`retry_max_attempts=3` 是否适用于 sector endpoint？
- [ ] OQ-P3A-6（V0.2 新增）：`name_em()` 返回的 `领涨股票` 列是代码还是名称？待 smoke 确认。
- [ ] OQ-P3A-7（V0.2 新增）：`name_em()` 是实时排名，无历史日期维度。`snapshot_date` 取 fetch 日期是否满足业务需求？

---

## 13. 声明

本 SPEC 中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。该声明通过静态 grep 验证。

本 SPEC 不修改主 SPEC-03-014 的任何已有内容。所有契约以交叉引用方式继承主 SPEC，冲突时以主 SPEC 为准。
