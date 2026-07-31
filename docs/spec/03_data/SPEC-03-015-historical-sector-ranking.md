# SPEC-03-015: 简化历史行业 sector.ranking_history — 可执行契约

## 元数据

| 项 | 值 |
|---|----|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.5 修订：T2.11 文档修正 — 成功完整 ranking trace 显式化为 `completeness:complete, materialized:ok`（H-049/H-051c）；§7 测试矩阵新增 T-015-015 成功 source_trace 顺序与文本逐字断言；H-049/H-049a/H-050/T-015-006 的 trace 统一为冒号格式；元数据关联 Design 指针更新为 `DESIGN-03-015-historical-sector-ranking.md (V0.5)`，三层版本指针同步。V0.4 修订保留：T2.9 source_trace 枚举闭合 — H-069 `completeness` 枚举补齐为 `{complete|incomplete|empty}`，H-070 `materialized` 枚举收敛为 `{ok|miss}`，删除并明确禁止未使用的 `skipped`；§3.9 约束补充枚举封闭声明。V0.3 修订保留：T2.7 契约纠偏 — H-007/H-049a/H-050 消除"返回 empty 或 error / empty 或附带 warning"二选一措辞，统一引用 RFC §5.6.3 结果语义冻结表；新增 H-051a 明确 4 类情形的冻结 warning token 与 source_trace 顺序。V0.2 修订保留：G-01 H-049~H-051 完整性语义改为 100% exact-match，expected universe 显式传入不硬编码；G-02 收紧 T3 allowlist/测试矩阵/realtime fallback 实现时机。对齐 Design Gate REVISE 反馈。） |
| 版本号 | V0.5 |
|| 来源 RFC | RFC-03-015-historical-sector-ranking（V0.5） |
| 关联 RFC | RFC-03-014（Phase 3 主 RFC）、RFC-03-014-p3a-sector-provider-activation（V0.2）、RFC-03-007（Unified Data Layer 总纲） |
| 关联 SPEC | SPEC-03-014（Phase 3 主 SPEC）、SPEC-03-014-p3a-sector-provider-activation（V0.2） |
| 关联 Design | DESIGN-03-015-historical-sector-ranking.md（V0.5） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Principal（后续 Gate 阶段） |

---

## 0. 术语对齐与基线锚定

本 SPEC 为 RFC-03-015 的可执行契约，不重述 RFC 背景。以下锁定本 SPEC 必须一致的措辞：

- **sector.ranking_history** = 新增 capability，按 `trade_date` 查询某 `dataset` 下全行业板块的已收盘历史交易日涨跌幅排名。
- **历史 vs 实时**：本能力返回的是**已收盘的历史交易日**数据，不是实时/盘中数据。`trade_date` 必须为已收盘的历史交易日，禁止 `date=None`/实时 latest 语义。
- **新 namespace**：`03_data_ud_sector_ranking_daily`（9 字段行 schema，唯一键 `{dataset, trade_date, sector_code}`）。
- **旧 namespace（冻结）**：`03_data_ud_market_sector_snapshot`（P3-A `sector.snapshot`/`sector.ranking` 物化目标，fake-only stub，不改、不迁、不回填）。
- **固定口径**：`pct_chg = (close - pre_close) / pre_close * 100`，禁止 close-to-open，禁止取上游自带 pct_chg。
- **dataset 维度**：数据源与分类口径的稳定标识，严格禁止跨 dataset 混排或静默 fallback。
- **TA-CN 只读上游候选**：`index_daily_quotes`（申万行业指数日线）作为 `sw2021_ta_cn` dataset 的只读上游候选，未经生产 Mongo 验证不得宣称已可用。
- **第一版交付**：仅离线/fake/mongomock 可验证实现，所有真实 I/O 冻结。

### 0.1 本 SPEC 不重复定义的契约

| 契约 | 定义位置 | 本 SPEC 引用方式 |
|---|---|---|
| TA-CN adapter read-only 约束 | RFC-03-007 / `ta_cn_mongo_adapter.py` | TA-CN 作为只读上游候选时引用 |
| P3PersistenceWriter upsert/get | SPEC-03-014 §P1.4 | 新 collection 的写入器可参照此模式（T2 定义） |
| DataResult / source_trace 模式 | SPEC-03-014 / SPEC-03-008 | `sector.ranking_history` 返回的 DataResult 遵循同一模式 |
| SectorSnapshot 19 字段 schema | SPEC-03-014 §3.1 | **不引用为新 schema 基线**——新能力用独立 9 字段 schema |

---

## 1. 需求摘要

将 RFC-03-015 的需求落为可执行契约，核心交付 8 件事：

1. **Capability 定义契约**：精确定义 `sector.ranking_history` 的查询参数、返回类型、排序口径、禁止语义（§3.1）。
2. **Collection Schema 契约**：新 collection `03_data_ud_sector_ranking_daily` 的 9 字段行 schema、唯一键、upsert 语义（§3.2）。
3. **dataset 维度契约**：dataset 枚举、严格禁止混排规则、sector_code 隔离（§3.3）。
4. **固定收益口径契约**：close-to-pre_close 公式、pre_close 来源、rank 计算、禁止替代口径（§3.4）。
5. **trade_date 证明与 realtime fallback 排除契约**：trade_date 合法性校验、realtime fallback 检测与排除（§3.5）。
6. **缺数据 fail/empty 契约**：缺 pre_close、覆盖不足、空集的语义（§3.6）。
7. **TA-CN 只读上游映射契约**：字段映射、日期格式兼容、不可宣称已可用（§3.7）。
8. **迁移隔离契约**：旧 collection 冻结、旧 capability 冻结、新 capability 独立（§3.8）。

---

## 2. 范围

### 2.1 In Scope

- [x] Capability 定义契约（§3.1）
- [x] Collection Schema 契约（§3.2）
- [x] dataset 维度契约（§3.3）
- [x] 固定收益口径契约（§3.4）
- [x] trade_date 证明与 realtime fallback 排除契约（§3.5）
- [x] 缺数据 fail/empty 契约（§3.6）
- [x] TA-CN 只读上游映射契约（§3.7）
- [x] 迁移隔离契约（§3.8）
- [x] Source Trace / Provenance 最小可观测契约（§3.9）
- [x] 后续 Gate 授权清单（§4）
- [x] T2 Design allowlist 与禁止修改路径（§5）

### 2.2 Out of Scope

- ❌ 真实 Mongo collection / index creation（属后续 Gate-2）
- ❌ 真实 TA-CN Mongo 读取（属后续 Gate-1）
- ❌ 真实 AKShare / HTTP 调用
- ❌ 真实写入（mongomock 以外）
- ❌ Cache 写入 / cron / systemd / webhook
- ❌ `.env` 读取 / secrets 回显
- ❌ Git commit / push
- ❌ 修改 SectorSnapshot 19 字段 schema（P0 已冻结，属 P3-A）
- ❌ 修改 `_EXPECTED_SECTOR_*_FIELDS` / STUB_COLUMNS（P0 已冻结）
- ❌ 修改 `providers/akshare.py`（P3-A fake-only 基线）
- ❌ 修改 `services/sector_service.py`（属 T3）
- ❌ 修改 P3-A 的任何文件
- ❌ 迁移、回填旧 collection（`03_data_ud_market_sector_snapshot` 冻结）
- ❌ `concept` / `region` / `style` 类型（第一版仅 industry）
- ❌ 存储涨停家数、跌停家数、领涨股、资金流、成员列表、run_id、raw_payload、版本字段

---

## 3. 功能规格

### 3.1 Capability 定义契约

#### 3.1.1 Capability 字符串与查询参数（H-001 ~ H-005）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| H-001 | `sector.ranking_history` 查询 | `trade_date`（必填, `YYYY-MM-DD`）、`dataset`（必填）、`limit`（可选, 默认全部） | `list[dict]`（9 字段行 schema），按 `pct_chg` 降序排列 | `trade_date` 缺失或格式非法 → `ValueError`；`dataset` 缺失 → `ValueError` |
| H-002 | `trade_date` 合法性校验 | `trade_date` 字符串 | 校验通过 → 继续；校验失败 → `ValueError` | 必须为 `YYYY-MM-DD` 格式；必须为已收盘的历史交易日（非当日盘中） |
| H-003 | `dataset` 合法性校验 | `dataset` 字符串 | 校验通过 → 继续；校验失败 → `ValueError` | 必须为已知 dataset 枚举值（第一版仅 `sw2021_ta_cn`） |
| H-004 | `limit` 处理 | `limit`（可选） | `limit > 0` → 截取前 N；`limit <= 0` 或 `None` → 返回全部 | 非法类型 → `ValueError` |
| H-005 | 返回排序 | 排序后的 `list[dict]` | 按 `pct_chg` 降序；`pct_chg` 相同按 `sector_code` 升序 | — |

#### 3.1.2 禁止的查询语义（H-006 ~ H-008）

| 编号 | 禁止语义 | 说明 |
|---|---|---|
| H-006 | 禁止 `trade_date=None` | 不支持"查最新"语义。`trade_date` 必须是明确的、已收盘的历史交易日。 |
| H-007 | 禁止 `trade_date=当日盘中` | 如果 `trade_date` 是当前交易日且当前时间早于收盘时间，视为参数非法，抛出 `ValueError`（结果语义见 RFC §5.6.3 冻结表 Category 1）。 |
| H-008 | 禁止跨 dataset 混合查询 | 单次查询只能指定一个 `dataset`。不支持列表/多 dataset 参数。 |

### 3.2 Collection Schema 契约

#### 3.2.1 Collection 名称与行 Schema（H-009 ~ H-018）

| 编号 | 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|---|
| H-009 | `dataset` | str | 是 | 非空；已知 dataset 枚举值 |
| H-010 | `trade_date` | str | 是 | 非空；`YYYY-MM-DD` 格式；已收盘的历史交易日 |
| H-011 | `sector_code` | str | 是 | 非空；dataset 内唯一标识板块 |
| H-012 | `sector_name` | str | 是 | 非空 |
| H-013 | `pct_chg` | float | 是 | 非空；`(close - pre_close) / pre_close * 100`；缺 pre_close 时整行不入库 |
| H-014 | `rank` | int | 是 | 非空；1-based，1 = 涨幅最高 |
| H-015 | `close` | float | 是 | 非空；当日收盘价/收盘指数 |
| H-016 | `pre_close` | float | 是 | 非空；前一交易日收盘价/收盘指数 |
| H-017 | `updated_at` | str (ISO-8601) | 是 | 非空；行写入/更新时间戳 |
| H-018 | schema 校验 | — | — | 行入库前校验全部 9 字段；任何必填字段缺失 → 整行不入库（fail） |

#### 3.2.2 唯一键与 upsert 语义（H-019 ~ H-021）

| 编号 | 行为 | 说明 |
|---|---|---|
| H-019 | 唯一键定义 | `{dataset, trade_date, sector_code}`。同一 dataset + trade_date 下，每个 sector_code 最多一行。 |
| H-020 | upsert 语义 | 相同唯一键的行被覆盖更新（`updated_at` 刷新）。 |
| H-021 | 索引建议 | 唯一键字段建复合唯一索引；T2 Design 定义精确索引 DDL。第一版不执行真实 DDL。 |

#### 3.2.3 明确不存储的字段（H-022）

| 编号 | 禁止字段类别 | 说明 |
|---|---|---|
| H-022 | 涨停/跌停家数、领涨股、资金流、成分股列表、run_id、raw_payload、版本号、volume/amount/turnover_rate | 第一版不存储、不编造。缺失值不写 0/None；缺失即整行不入库。 |

### 3.3 dataset 维度契约

#### 3.3.1 dataset 枚举（H-023 ~ H-025）

| 编号 | dataset 标识 | 分类口径 | 第一版状态 |
|---|---|---|---|
| H-023 | `sw2021_ta_cn` | 申万 2021 一级行业分类（TA-CN 上游） | **第一版候选** |
| H-024 | `eastmoney_industry` | 东方财富行业板块 | 后续扩展 |
| H-025 | `ths_industry` / `sina_industry_eod` | 同花顺 / 新浪 | 后续扩展 |

#### 3.3.2 严格禁止混排规则（H-026 ~ H-029）

| 编号 | 规则 | 说明 |
|---|---|---|
| H-026 | 查询隔离 | 单次查询只能指定一个 `dataset`。不支持跨 dataset 联合查询。 |
| H-027 | 存储隔离 | 不同 dataset 的行存储在同一 collection，通过 `dataset` 字段严格隔离。查询必须按 `dataset` 过滤。 |
| H-028 | 禁止静默 fallback | `dataset=sw2021_ta_cn` 查询无数据 → 返回 empty，不得静默回退到其他 dataset。 |
| H-029 | sector_code 不跨 dataset 复用 | 不同 dataset 的 sector_code 通过 `dataset` 字段区分，不去重合并。 |

### 3.4 固定收益口径契约

#### 3.4.1 pct_chg 公式（H-030 ~ H-032）

| 编号 | 规则 | 说明 |
|---|---|---|
| H-030 | pct_chg 公式 | `pct_chg = (close - pre_close) / pre_close * 100`。`close` = 当日收盘；`pre_close` = 前一交易日收盘。 |
| H-031 | 禁止 close-to-open | 不得使用 `(close - open) / open * 100` 作为排名依据。 |
| H-032 | 禁止取上游自带 pct_chg | 不得直接使用上游（TA-CN/AKShare）返回的 `pct_chg` 字段。必须用 close/pre_close 重新计算。 |

#### 3.4.2 pre_close 来源（H-033 ~ H-035）

| 编号 | 场景 | 处理 |
|---|---|---|
| H-033 | 上游直接提供 `pre_close` | 校验 `pre_close ≈ 前一日 close`（容差由 T2 定义）；校验通过后使用上游值 |
| H-034 | 上游不提供 `pre_close` | 从历史日线取同一 `sector_code` 前一交易日的 `close` 作为 `pre_close` |
| H-035 | 前一交易日无 `close` 数据 | 该 `sector_code` 行**不入库**（fail 语义）。不写 0、不写 None、不用 open 替代。 |

#### 3.4.3 rank 计算（H-036 ~ H-038）

| 编号 | 规则 | 说明 |
|---|---|---|
| H-036 | rank 计算 | `rank = 按 pct_chg 降序排列后的位次（1-based）` |
| H-037 | pct_chg 相同的 tiebreaker | 按 `sector_code` 升序排列后分配连续 rank |
| H-038 | rank 计算范围 | 在整个 `dataset` + `trade_date` 的全量板块集合上计算，不对部分板块计算 rank |

### 3.5 trade_date 证明与 realtime fallback 排除契约

#### 3.5.1 trade_date 合法性校验（H-039 ~ H-041）

| 编号 | 规则 | 说明 |
|---|---|---|
| H-039 | 格式校验 | `trade_date` 必须为 `YYYY-MM-DD` 格式字符串 |
| H-040 | 已收盘校验 | 该交易日必须已收盘。如 `trade_date` 为当前交易日且当前时间早于收盘时间 → 不合法 |
| H-041 | 可证明性 | 该 `trade_date` 必须有对应的、已确认的历史日线记录（非 realtime fallback） |

#### 3.5.2 realtime fallback 排除策略（H-042 ~ H-046）

| 编号 | 检测信号 | 处理 |
|---|---|---|
| H-042 | `trade_date` 为当日且市场未收盘 | 该 `trade_date` 全部行不作为历史数据返回 |
| H-043 | 记录缺少 `close` 或 `close` 为 None | 该行不入库 |
| H-044 | 记录 `pct_chg`（如有）与公式计算偏差超容差 | 该行标记可疑；T2 定义容差阈值 |
| H-045 | 记录标记为 realtime/intraday（如有 source/type 字段） | 该行不入库 |
| H-046 | 设计原则 | 宁可拒绝（按 RFC §5.6.3 冻结表 Category 3/4 返回 empty + warning，不抛 error），不可将非最终记录作为历史排名。精确检测逻辑由 T2 Design 定义。 |

### 3.6 缺数据 fail/empty 契约

#### 3.6.1 单板块缺 pre_close（H-047 ~ H-048）

| 编号 | 场景 | 处理 |
|---|---|---|
| H-047 | 某 `sector_code` 有 `close` 但前一交易日无 `close` | 该板块行不入库；不影响同 `trade_date` 其他板块 |
| H-048 | 某 `sector_code` 既无 `close` 也无 `pre_close` | 该板块行不入库 |

#### 3.6.2 全行业覆盖完整性 — 100% exact-match（H-049 ~ H-051）

**完整性判定原则（严格）**：正式 ranking 仅当 `observed_sector_codes == expected_sector_codes` 时生成。不存在"部分覆盖即生成正式 ranking"的中间态。

| 编号 | 场景 | 处理 |
|---|---|---|
| H-049 | `observed_sector_codes == expected_sector_codes`（100% 覆盖、无重复、每行有效 close/pre_close） | 生成正式 ranking 并物化；`completeness:complete, materialized:ok`（成功 trace 逐字断言见 T-015-015；结果语义见 RFC §5.6.3 冻结表成功行） |
| H-049a | `observed_sector_codes ⊊ expected_sector_codes`（缺行业）或含 expected 之外/重复代码 | **不生成正式 ranking**；`BuildOutcome(status="incomplete")`，不物化（不写库、不返回部分榜单）。对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-incomplete"])`；`completeness:incomplete`（结果语义见 RFC §5.6.3 冻结表 Category 3） |
| H-050 | incomplete 的 `trade_date` 查询返回 | `DataResult.success(data=[], warnings=["historical-ranking-incomplete"])`（**不返回部分榜单**；warning token 冻结为 `historical-ranking-incomplete`，不得省略、不得替换）。source_trace `completeness:incomplete, materialized:miss` |
| H-051 | 某 `trade_date` 零个板块有完整数据（build 零有效行） | `BuildOutcome(status="empty")`，不物化。对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-empty"])`。empty ≠ error（结果语义见 RFC §5.6.3 冻结表 Category 4） |
| H-051a | 结果语义冻结（T2.7 契约纠偏） | 4 类情形（参数非法 / 读集合无记录 / build 完整性失败 / build 零有效行）的结果类型与稳定 warning token **唯一冻结**，完整定义见 RFC §5.6.3 结果语义冻结表。本 SPEC 不得出现"返回 error 或 empty"、"empty 或附带 warning"等二选一措辞。 |
| H-051b | 读集合无记录（trade_date 合法但物化集合零条） | `DataResult.success(data=[], warnings=["historical-ranking-empty"])`；source_trace `coverage:0/{expected}, completeness:empty, materialized:ok`（结果语义见 RFC §5.6.3 冻结表 Category 2） |
| H-051c | 成功完整 ranking（成功场景 trace） | `observed == expected`（100% 覆盖、无重复、每行有效 close/pre_close）且正式行已物化 → `DataResult.success(data=正式 ranking 列表, warnings=[])`；source_trace `completeness:complete, materialized:ok`，顺序 `dataset → trade_date → source → coverage → completeness → materialized`（RFC §5.6.3 冻结表成功行；离线测试 T-015-015 逐字断言成功 source_trace） |

**expected universe 来源契约（H-049u）**：

| 编号 | 规则 | 说明 |
|---|---|---|
| H-049u | expected universe 显式传入 | expected universe 必须由调用方/fixture 显式传入（`expected_sector_codes: frozenset[str]` 或等价结构）。**不得在 T3 硬编码**未经验证的"31 个 SW L1 常量表"。离线 fixture universe 仅证明逻辑正确，不代表生产真实 universe。生产真实 expected universe 确认为独立 Pascal Gate（Gate-1）。 |

### 3.7 TA-CN 只读上游映射契约

#### 3.7.1 TA-CN 字段映射（H-052 ~ H-058）

| 编号 | TA-CN 字段 | 新 schema 字段 | 转换 |
|---|---|---|---|
| H-052 | `sector_code`（如 `801120`） | `sector_code` | str 直传 |
| H-053 | `trade_date`（如 `20260713`） | `trade_date` | `YYYYMMDD` → `YYYY-MM-DD` |
| H-054 | `close` | `close` | float |
| H-055 | —（前一交易日 close） | `pre_close` | 从前一交易日同 `sector_code` 的 `close` 推导 |
| H-056 | —（计算） | `pct_chg` | `(close - pre_close) / pre_close * 100` |
| H-057 | —（计算） | `rank` | 按 `pct_chg` 降序排名 |
| H-058 | —（常量注入） | `dataset` | `sw2021_ta_cn`（调用方注入，不从 TA-CN 推断） |

#### 3.7.2 TA-CN 不可宣称已可用（H-059）

| 编号 | 规则 | 说明 |
|---|---|---|
| H-059 | TA-CN 覆盖率未验证 | TA-CN SW 历史日线的实际覆盖率和历史完整性未经生产 Mongo 验证。未经 Gate-1 smoke 前，不得宣称"已可用"或"已覆盖"。 |

#### 3.7.3 sector_name 来源（H-060）

| 编号 | 规则 | 说明 |
|---|---|---|
| H-060 | sector_name 映射 | TA-CN `index_daily_quotes` 无 `sector_name` 字段。sector_name 来源由 T2 Design 定义（候选：TA-CN `stock_sector_info.l1_name` / SW L1 预定义代码表）。缺 sector_name → 该行不入库。 |

### 3.8 迁移隔离契约

#### 3.8.1 旧 collection 与 capability 冻结（H-061 ~ H-064）

| 编号 | 对象 | 处理 |
|---|---|---|
| H-061 | `03_data_ud_market_sector_snapshot` | 不改、不迁、不回填、不删除 |
| H-062 | `sector.snapshot` | 冻结，不修改 |
| H-063 | `sector.ranking` | 冻结/暂缓，不修改。实时路径暂缓。 |
| H-064 | `sector.ranking_history` | 新增 capability，不替代/覆盖/合并 `sector.ranking`。独立 collection、schema、unique key。 |

### 3.9 Source Trace / Provenance 最小可观测契约（H-065 ~ H-070）

| 编号 | source_trace 条目 | 说明 |
|---|---|---|
| H-065 | `dataset:{dataset}` | 本次查询的 dataset 标识 |
| H-066 | `trade_date:{trade_date}` | 本次查询的交易日 |
| H-067 | `source:{upstream}` | 数据来源标识（如 `ta_cn:index_daily_quotes`） |
| H-068 | `coverage:{actual}/{expected}` | 实际覆盖板块数 / 期望板块数（冻结占位符，见 RFC §5.6.3） |
| H-069 | `completeness:{complete\|incomplete\|empty}` | 完整性判定（枚举封闭，见 RFC §5.6.3 冻结表） |
| H-070 | `materialized:{ok\|miss}` | 是否命中物化集合读取（`skipped` 已废弃禁用，不得作为对外值） |

**约束**：source_trace 不得仅包含 `provider=akshare`。必须包含 dataset、trade_date、source、coverage、completeness 最小信息。`completeness` 枚举封闭为 `complete|incomplete|empty`；`materialized` 枚举封闭为 `ok|miss`，`skipped` 已废弃禁用，不得作为对外可能值（RFC §5.6.3 冻结约束，T2.9）。

---

## 4. 后续 Gate 授权清单

| 编号 | Gate | 内容 | 授权方 | 前置条件 |
|---|---|---|---|---|
| G-015-1 | Gate-1 | TA-CN SW 历史数据真实可达性 smoke（只读 Mongo，验证覆盖率和完整性） | Pascal | T3 离线实现通过 |
| G-015-2 | Gate-2 | 新 collection `03_data_ud_sector_ranking_daily` 创建 + 索引（DDL） | Pascal | Gate-1 verdict ≥ conditional_pass |
| G-015-3 | Gate-3 | 历史 backfill（真实 TA-CN → 新 collection 批量写入） | Pascal | Gate-2 完成 |
| G-015-4 | Gate-4 | 生产读取激活（`sector.ranking_history` 真实查询路径上线） | Pascal | Gate-3 canary 通过 |

---

## 5. T2 Design Allowlist 与禁止修改路径

### 5.1 T2 Design 允许创建的文件

| 路径 | 说明 |
|---|---|
| `docs/design/03_data/DESIGN-03-015-historical-sector-ranking.md` | 详细设计文档 |

### 5.2 T2 Design 需定义的内容

| 内容 | 说明 |
|---|---|
| Collection schema 实现细节 | 9 字段行的 mongomock / pymongo 映射、索引 DDL（仅定义，不执行） |
| pre_close 推导逻辑 | 前一交易日 close 查询逻辑、链式缺失处理（**精确容差校验留待后续 Gate**） |
| ranking 计算逻辑 | pct_chg 降序、tiebreaker、连续 1-based rank |
| 完整性判定 | **100% exact-match**（`observed_sector_codes == expected_sector_codes` 才生成正式 ranking）；expected universe 由调用方/fixture 显式传入，**不硬编码** |
| mongomock repository | 注入式 mongomock repository，仅操作 `03_data_ud_sector_ranking_daily`，key `{dataset, trade_date, sector_code}` |
| 只读查询 service | 强制 dataset + trade_date，按稳定排序返回；直读物化集合，不经 router |
| UnifiedDataClient facade | **条件性**：仅当可从已注入 fake/mongomock db 端到端实测时追加；否则后置到未来 Gate |
| realtime fallback 检测 | **精确检测信号不在 T3 实现**；第一版由完整性约束（§3.6）覆盖安全边界。精确信号、容差阈值留待后续 Gate |
| TA-CN 读取适配 | `TA_CNMongoAdapter.get_index_daily_bars()` 调用参数、日期范围、sector_code 过滤（**不在 T3 实现**，Gate-3 backfill 参考） |
| sector_name 映射 | SW L1 代码 → 中文名称的来源与映射表（**不在 T3 硬编码全表**；Gate-1 权威验证；离线 fixture 可显式传入测试用名称） |
| mongomock 测试覆盖 | schema 校验、upsert、pct_chg 计算、rank 计算、缺 pre_close fail、完整性判定（complete/incomplete/empty）、dataset 隔离 |
| T3 Implement allowlist | 允许新增/修改的文件清单（收紧版，见 §5.3） |

### 5.3 T3 Implement 预期允许修改的文件（T2 最终裁定，收紧版）

T3 allowlist 最多为：domain、repository（mongomock）、service（只读查询）、一个新测试、一个 fixture，以及（仅如明确可测）`models/domain/__init__.py` / `client.py` 的最薄追加。**不含** provider client、SW 常量表、backfill 逻辑。

| 路径（预期） | 允许操作 | 约束 |
|---|---|---|
| `models/domain/sector_ranking.py`（新增） | `SectorRankingDaily` 9 字段 domain object + `from_dict()` | 不修改 `models/domain/sector.py`（SectorSnapshot 冻结） |
| `adapters/historical_ranking_writer.py`（新增） | 注入式 mongomock repository（get/upsert/delete） | 不修改 `p3_persistence_writer.py`；接受外部传入 mongomock db |
| `services/historical_sector_service.py`（新增） | 只读查询 service（`get_sector_ranking_history`） | 不修改现有 `sector_service.py` read path；不经 router；不含 backfill |
| `tests/test_sector_ranking_history.py`（新增） | 离线单元测试 | 零真实 I/O |
| `tests/fixtures/historical_ranking_fixtures.py`（新增） | 测试 fixture（含显式 expected_sector_codes） | 不含 SW L1 全表常量 |
| `models/domain/__init__.py`（追加） | 追加 export | 不修改现有 import/export |
| `client.py`（追加，条件性） | 追加 `get_sector_ranking_history()` facade | 仅当可从已注入 fake/mongomock db 端到端实测时；不修改现有方法 |

### 5.4 禁止修改路径

- ❌ `models/domain/sector.py`（SectorSnapshot 19 字段已冻结）
- ❌ `providers/_stub_columns.py` / `providers/__init__.py`（STUB_COLUMNS / `_EXPECTED_SECTOR_*_FIELDS` 已冻结）
- ❌ `providers/akshare.py`（P3-A fake-only 基线）
- ❌ `providers/sector_client.py`（P3-A 文件）
- ❌ `router.py`（除非新增 capability 注册，且不破坏现有 read path）
- ❌ `client.py`（除非新增 facade 方法，且不修改现有方法）
- ❌ `adapters/ta_cn_mongo_adapter.py`（TA-CN adapter 只读，不改）
- ❌ `adapters/p3_persistence_writer.py`（P3 writer 不改）
- ❌ `services/sector_service.py` 的现有 read path（`get_sector_snapshot`/`get_sector_ranking` 不变）
- ❌ 任何 `.env` / config / requirements / SKILL.md / README
- ❌ P3-A / P3-B / P3-C 相关的现有文件
- ❌ `tests/test_sector_provider_activation.py` / `tests/test_sector_service.py` / `tests/test_mapping_sector.py`（已有测试不改）

---

## 6. 数据合理性与 schema-drift 规则

| 编号 | 规则 | 说明 |
|---|---|---|
| A-015-DRIFT-1 | 禁止编造值 | 缺失字段保持 None/不入库，不通过计算/推断/别名编造。缺 pre_close → 整行不入库。 |
| A-015-DRIFT-2 | 字段名漂移容忍 | 上游返回的额外字段静默忽略（不抛异常） |
| A-015-DRIFT-3 | 字段缺失容忍 | expected 字段缺失 → 整行不入库（fail），不抛 KeyError |
| A-015-DRIFT-4 | 类型强转容错 | 数值字段返回字符串时容错转换，失败 → 整行不入库 |
| A-015-DRIFT-5 | 缺失值不写 0 | 未来扩展字段时，缺失值不写 0，保持 None 或不入库 |

---

## 7. 离线测试覆盖矩阵

| 编号 | 测试 | 覆盖 | 需网络 | 文件（预期） |
|---|---|---|---|---|
| T-015-001 | schema 校验 | 9 字段行 schema 全部必填字段校验 | 否 | `tests/test_sector_ranking_history.py` |
| T-015-002 | unique key upsert | 相同 `{dataset, trade_date, sector_code}` 覆盖更新 | 否 | 同上 |
| T-015-003 | pct_chg 计算 | `(close - pre_close) / pre_close * 100` 正确性 | 否 | 同上 |
| T-015-004 | rank 计算 | pct_chg 降序排名、tiebreaker | 否 | 同上 |
| T-015-005 | 缺 pre_close fail | 缺 pre_close 的板块行不入库 | 否 | 同上 |
| T-015-006 | 完整性判定 incomplete | observed != expected（缺行业/重复/多余）→ 不生成正式 ranking；`BuildOutcome(status="incomplete")`；对外查询 `DataResult.success([], warnings=["historical-ranking-incomplete"])`；source_trace `completeness:incomplete, materialized:miss`；**不写库**（RFC §5.6.3 Category 3） | 否 | `tests/test_sector_ranking_history.py` |
| T-015-007 | 零板块 empty | build 零有效行 → `BuildOutcome(status="empty")`；对外查询 `DataResult.success([], warnings=["historical-ranking-empty"])`；source_trace `completeness:empty, materialized:miss`（非 error；RFC §5.6.3 Category 4） | 否 | 同上 |
| T-015-008 | realtime fallback 排除（安全边界） | 缺行业/重复/非法 close/pre_close 的行不进入正式 ranking（由完整性约束覆盖）；**精确 realtime 信号检测不在 T3** | 否 | 同上 |
| T-015-009 | dataset 隔离 | 不同 dataset 不混排、不静默 fallback | 否 | 同上 |
| T-015-010 | trade_date 格式校验 | `YYYY-MM-DD` 格式校验、非法日期拒绝（ValueError；Category 1） | 否 | 同上 |
| T-015-011 | 禁止 date=None | `trade_date=None` → ValueError（Category 1） | 否 | 同上 |
| T-015-012 | TA-CN 字段映射 | `YYYYMMDD` → `YYYY-MM-DD`、close/pre_close 推导 | 否 | 同上 |
| T-015-013 | source_trace 完整性 | 返回的 DataResult 包含 dataset/trade_date/source/coverage/completeness/materialized；**warning token 与 source_trace 顺序逐字断言**（Category 2/3/4） | 否 | 同上 |
| T-015-014 | 读集合无记录 | trade_date 合法但物化集合零条 → `DataResult.success([], warnings=["historical-ranking-empty"])`；source_trace `coverage:0/{expected}, completeness:empty, materialized:ok`（Category 2） | 否 | 同上 |
| T-015-015 | 成功完整 ranking | observed == expected（100% 覆盖、无重复、每行有效 close/pre_close）→ 生成正式 ranking 并物化；对外查询返回完整榜单 `DataResult.success(data=[...], warnings=[])`；source_trace `completeness:complete, materialized:ok`；**成功 source_trace 顺序（dataset → trade_date → source → coverage → completeness → materialized）与文本逐字断言**（RFC §5.6.3 冻结表成功行） | 否 | `tests/test_sector_ranking_history.py` |

---

## 8. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-015-001 | RFC 和 SPEC 两份独立文档存在且互相交叉引用 | 文件存在性检查 |
| A-015-002 | Capability 定义契约完整（H-001 ~ H-008） | 静态检查 |
| A-015-003 | Collection Schema 契约完整（H-009 ~ H-022） | 静态检查 |
| A-015-004 | dataset 维度契约完整（H-023 ~ H-029） | 静态检查 |
| A-015-005 | 固定收益口径契约完整（H-030 ~ H-038） | 静态检查 |
| A-015-006 | trade_date 证明与 realtime fallback 排除契约完整（H-039 ~ H-046） | 静态检查 |
| A-015-007 | 缺数据 fail/empty 契约完整（H-047 ~ H-051） | 静态检查 |
| A-015-008 | TA-CN 只读上游映射契约完整（H-052 ~ H-060） | 静态检查 |
| A-015-009 | 迁移隔离契约完整（H-061 ~ H-064） | 静态检查 |
| A-015-010 | Source Trace 契约完整（H-065 ~ H-070） | 静态检查 |
| A-015-011 | Gate 授权清单完整（G-015-1 ~ G-015-4） | 静态检查 |
| A-015-012 | T2 allowlist 和禁止路径明确（§5） | 静态检查 |
| A-015-013 | 不触发真实 I/O | 静态 grep（本阶段无代码） |
| A-015-014 | 不修改 P3-A fake-only 基线 | `git diff --name-status` |
| A-015-015 | 不将 `date=None`/实时 latest 作为历史语义 | 静态检查 |
| A-015-016 | `git diff --check` exit 0 | git 命令 |
| A-015-017 | `git diff --name-status` 仅含 RFC + SPEC 两份文档 | git 命令 |
| A-015-018 | 声明辅助研究数据，不构成交易指令或投资建议 | 静态 grep |

---

## 9. 开放问题

- [ ] OQ-015-1：`sector_name` 来源（SW L1 代码 → 中文名称映射表）— **不在 T3 硬编码全表，留待 Gate-1 权威验证**
- [x] OQ-015-2：全行业覆盖不足阈值 — **已裁定（V0.2）**：100% exact-match（`observed == expected` 才生成正式 ranking）；expected universe 由调用方/fixture 显式传入
- [ ] OQ-015-3：pre_close 容差校验阈值 — **精确容差校验留待后续 Gate**
- [ ] OQ-015-4：TA-CN realtime fallback 精确检测信号 — **不在 T3 实现，留待后续 Gate**
- [ ] OQ-015-5：rank 写入 vs 查询时动态计算 — 查询时按稳定排序返回（pct_chg DESC, sector_code ASC）
- [ ] OQ-015-6：未来 dataset 扩展时 sector_code 共存策略（已通过 dataset 字段隔离解决）

---

## 10. 声明

本 SPEC 中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本 SPEC 不修改任何现有 RFC/SPEC/Design/代码/测试/配置。所有新定义为新增，不与 P3-A 冻结基线冲突。
