# DESIGN-03-015: 简化历史行业 sector.ranking_history — 离线实现设计（V0.2 收紧版）

## 元数据

| 项 | 值 |
|---|----|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.5 修订：T2.11 文档修正 — §5.1 测试矩阵新增 UT-015-021 成功完整 ranking trace 顺序与文本逐字断言；§6.2 warning 表新增成功行（`completeness:complete, materialized:ok`、warnings=[]）；§3.4 关键约束补成功处理项；UT-015-006 的 trace 统一为冒号格式；元数据来源 RFC/SPEC 指针同步 V0.5。V0.4 修订保留：T2.9 source_trace 枚举闭合 — §5.1 测试矩阵补齐四类 trace exact assertions（UT-015-006/007 收紧为 Category 3/4 精确断言、UT-015-013 补充 warning token 与 source_trace 顺序逐字断言、新增 UT-015-020 对应 SPEC T-015-014 Category 2 读集合无记录）；§6.2 禁止段补充 `materialized` 枚举封闭 `{ok|miss}`、`skipped` 废弃禁用；BuildOutcome 内部 `skipped_*` 计数注明不进入 source_trace/materialized。V0.3 修订保留：T2.7 契约纠偏 — §3.4 完整性判定与 §6.2 warning 表消除"返回 empty 或附带 warning"二选一措辞，统一引用 RFC §5.6.3 结果语义冻结表 Category 1~4；source_trace coverage 占位符统一为 `{actual}/{expected}`；§9.1 交接守则补充冻结 warning token 逐字使用要求。V0.2 修订保留：G-01 完整性语义改为 100% exact-match，expected universe 显式传入不硬编码 31 常量；G-02 将 HistoricalRankingClient Protocol/Fake、backfill、SW L1 全表、realtime 精确检测、TA-CN 聚合逻辑全部移至附录 A（Future Gate 参考），T3 收紧为 domain + 确定性纯函数 + 注入式 mongomock repository + 只读查询 service + 条件性 facade。） |
| 版本号 | V0.5 |
| 来源 RFC | RFC-03-015-historical-sector-ranking（V0.5） |
| 来源 SPEC | SPEC-03-015-historical-sector-ranking（V0.5） |
| 关联 Design | DESIGN-03-014-p3a-sector-provider-activation（V0.2，P3-A 离线基线参考） |
| 关联 Design | DESIGN-03-014（Phase 3 主设计 V0.21） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

---

## 0. V0.1 → V0.2 修订摘要（Design Gate REVISE 响应）

本版响应 Orchestrator Design Gate 的两项阻断性反馈：

| Gate Finding | 严重度 | V0.2 修订 |
|---|---|---|
| **G-01 完整性语义冲突** | BLOCKING | RFC/SPEC/Design 同时写"覆盖不足不能生成正式 ranking"和">=90% complete"。V0.2 统一改为：正式 ranking 仅当 `observed_sector_codes == expected_sector_codes`（100% exact-match）时生成；expected universe 由调用方/fixture 显式传入，**不在 T3 硬编码 31 常量表**；任何缺行业/重复/非法 close/pre_close 均不物化，按 RFC §5.6.3 冻结表返回 empty + warning（Category 3/4），不抛 error、不返回部分榜单。 |
| **G-02 实现结构超出用户要求的最小范围** | MAJOR | 用户已否决 run+item 复杂模型，但 V0.1 Design 又引入 `HistoricalRankingClient` Protocol+Fake、硬编码 SW L1 常量表、RT-1~5 侦测、writer+backfill+service+facade 组合，且 `backfill` 本身已明确不在 T3。V0.2 将 T3 收紧为：最小 9 字段 domain + 确定性纯函数构建/校验/排序 + 注入式 mongomock repository（单集合/唯一键）+ 只读查询 service；真实 TA-CN fetch、realtime-origin 判别、SW 名称全表、生产 backfill/DDL 全部移动到附录 A（Future Gate 参考）。facade 仅在可从已注入 fake/mongomock db 端到端实测时实现，否则后置。 |

---

## 1. 设计摘要

本设计将 RFC-03-015 V0.2 / SPEC-03-015 V0.2 定义的新增 capability `sector.ranking_history` 落为**最小离线实现设计**。核心交付物是一套围绕新 collection `03_data_ud_sector_ranking_daily` 的可纯函数测试的读取/校验/排序基础设施，全部在 mongomock + 显式 fixture 上可验证，零真实 I/O。

### 1.1 与 P3-A 的关系

| 维度 | P3-A（`sector.snapshot` / `sector.ranking`） | 本设计（`sector.ranking_history`） |
|---|---|---|
| 数据性质 | 实时快照（AKShare `name_em`） | 已收盘历史日线排名 |
| Collection | `03_data_ud_market_sector_snapshot`（冻结） | `03_data_ud_sector_ranking_daily`（新建） |
| Schema | `SectorSnapshot` 19 字段 | `SectorRankingDaily` 9 字段 |
| Unique Key | `{market, sector_code, snapshot_date}` | `{dataset, trade_date, sector_code}` |
| 上游 | AKShare（外部 provider） | TA-CN `index_daily_quotes`（只读候选，**不在 T3 接入**） |
| Router 路径 | Step 4 外部 fallback | 直读物化集合（不经 router Step 1/4） |
| 文件重叠 | 零重叠：不修改 P3-A 的任何文件 | 全新文件，不触碰 P3-A 基线 |

**隔离原则**：本设计不导入、不修改、不引用 P3-A 的 `providers/akshare.py` / `providers/sector_client.py` / `SectorSnapshot` / `_EXPECTED_SECTOR_*_FIELDS` / STUB_COLUMNS。两套实现在代码层面完全独立。

### 1.2 核心设计决策（V0.2 收紧版）

| 决策点 | 选择 | 理由 |
|---|---|---|
| Domain 对象 | 新建 `SectorRankingDaily`（独立文件） | SPEC 禁止修改 `models/domain/sector.py`（SectorSnapshot 冻结） |
| 构建/校验/排序 | **确定性纯函数**（输入 rows + expected sector codes） | 可纯函数测试；100% exact-match 完整性校验 |
| 读路径 | 直读物化集合（不经 router） | 历史排名是预计算物化数据，无需 provider fallback；避免修改 router 风险 |
| Repository | 注入式 mongomock repository（`HistoricalRankingWriter`） | 接受外部传入 mongomock db；不修改 `P3PersistenceWriter` |
| Service | 新建 `HistoricalSectorService`（**只读查询，不含 backfill**） | 避免在 `SectorService` 中混入历史逻辑；backfill 移至附录 A |
| Client facade | **条件性**追加 `get_sector_ranking_history()` | 仅当可从已注入 fake/mongomock db 端到端实测时；否则后置 |
| sector_name 来源 | **不在 T3 硬编码 SW L1 全表** | 留待 Gate-1 权威验证；离线 fixture 显式传入测试用名称 |
| 完整性判定 | **100% exact-match**（`observed == expected`） | V0.2 G-01 修订；expected 由调用方/fixture 显式传入 |
| rank 计算 | 查询时按稳定排序返回（pct_chg DESC, sector_code ASC） | 不依赖存储顺序 |

---

## 2. 现状分析

### 2.1 相关目录与文件

| 路径 | 现状 | 本设计关系 |
|---|---|---|
| `models/domain/sector.py` | `SectorSnapshot` 19 字段 + `SectorClassification` | **禁止修改**（P0 冻结） |
| `models/domain/__init__.py` | 导出 domain dataclasses | T3 新增 export（追加一行） |
| `adapters/p3_persistence_writer.py` | P3 collection/key 映射 + upsert/get/delete | **禁止修改**（SPEC §5.4） |
| `adapters/ta_cn_mongo_adapter.py` | TA-CN 只读 adapter | **禁止修改**；**不在 T3 引用**（Gate-3 backfill 参考） |
| `services/sector_service.py` | P3-A read path + P1 refresh path | **禁止修改** |
| `router.py` | capability 路由 | **不修改**（T3 直读物化集合，不经 router） |
| `client.py` | `UnifiedDataClient` facade | T3 **条件性**追加方法（仅如可测） |
| `providers/akshare.py` | P3-A provider | **禁止修改** |
| `providers/sector_client.py` | P3-A SectorClient | **禁止修改** |
| `tests/fixtures/ta_cn_mock_docs.py` | `sw_industry_daily_quotes()` fixture | **禁止修改**；T3 新 fixture 独立 |

### 2.2 SW L1 行业体系参考

申万 2021 一级行业分类约 31 个 L1 行业。**V0.2 明确：完整代码表不在 T3 硬编码**，expected universe 由调用方/fixture 显式传入。生产真实 universe 的权威校验为 Gate-1。

---

## 3. T3 方案设计（最小离线范围）

### 3.1 模块/文件改动（T3 Implement allowlist — 收紧版）

#### 3.1.1 新建文件

| 文件 | 内容 | 说明 |
|---|---|---|
| `models/domain/sector_ranking.py` | `SectorRankingDaily` dataclass + `from_dict()` | 9 字段最小行 domain 对象 |
| `services/historical_sector_service.py` | `HistoricalSectorService` 类（**只读查询**） | 历史排名查询 service；**不含 backfill** |
| `adapters/historical_ranking_writer.py` | `HistoricalRankingWriter` 类 | 注入式 mongomock repository（get/upsert/delete） |
| `tests/test_sector_ranking_history.py` | 离线单元测试 | 覆盖 SPEC §7 测试矩阵（收紧版） |
| `tests/fixtures/historical_ranking_fixtures.py` | 测试 fixture | **显式传入** expected_sector_codes；不含 SW L1 全表常量 |

#### 3.1.2 修改文件（追加，不修改现有内容）

| 文件 | 改动 | 约束 |
|---|---|---|
| `models/domain/__init__.py` | 追加 `from .sector_ranking import SectorRankingDaily` + `__all__` 追加 | 不修改现有 import/export |
| `client.py` | **条件性**追加 `get_sector_ranking_history()` facade + lazy accessor | 仅当可从已注入 fake/mongomock db 端到端实测时；不修改现有方法 |

#### 3.1.3 精确禁止修改路径

- ❌ `models/domain/sector.py`（SectorSnapshot 19 字段冻结）
- ❌ `models/domain/market_data.py`（IndexDailyBar 冻结）
- ❌ `providers/_stub_columns.py`（STUB_COLUMNS / `_EXPECTED_SECTOR_*_FIELDS` 冻结）
- ❌ `providers/__init__.py`（twin 定义冻结）
- ❌ `providers/akshare.py`（P3-A 基线）
- ❌ `providers/sector_client.py`（P3-A 文件）
- ❌ `providers/historical_ranking_client.py`（**V0.2：不在 T3 创建**；HistoricalRankingClient Protocol/Fake 移至附录 A）
- ❌ `router.py`（T3 不经 router）
- ❌ `adapters/ta_cn_mongo_adapter.py`（TA-CN adapter 只读不改；**不在 T3 引用**）
- ❌ `adapters/p3_persistence_writer.py`（P3 writer 不改）
- ❌ `services/sector_service.py`（现有 read path 不变）
- ❌ `services/__init__.py`（现有 service 注册不变）
- ❌ 任何 `.env` / config / requirements / SKILL.md / README
- ❌ P3-A / P3-B / P3-C 的任何现有文件
- ❌ 已有测试/fixture 文件（见 SPEC §5.4）

### 3.2 数据流/控制流

#### 3.2.1 查询路径（T3 离线：直读物化集合）

```text
UnifiedDataClient.get_sector_ranking_history(trade_date, dataset, limit)
  │  （条件性 facade — 仅如可测）
  ▼
HistoricalSectorService.get_sector_ranking_history(trade_date, dataset, limit)
  │
  ├── validate trade_date: 非空、YYYY-MM-DD 格式
  ├── validate dataset: 非空、已知枚举值（第一版仅 sw2021_ta_cn）
  │
  ▼
HistoricalRankingWriter.get(
    collection="03_data_ud_sector_ranking_daily",
    filter={"dataset": dataset, "trade_date": trade_date},
)
  │
  ▼ 返回 list[dict]（9 字段行）
  │
  ├── sort: pct_chg DESC → sector_code ASC（稳定排序）
  ├── apply limit（limit > 0 时截取前 N）
  ├── coerce: list[dict] → list[SectorRankingDaily]
  │
  ▼
DataResult.success(
    data=list[SectorRankingDaily],   # complete 时非空；Category 2/3/4 时为 []
    source_trace=[
        "dataset:{dataset}",
        "trade_date:{trade_date}",
        "source:ta_cn:index_daily_quotes",
        "coverage:{actual}/{expected}",          # actual=命中板块数, expected=expected_sector_codes 大小
        "completeness:{complete|incomplete|empty}",  # 见 RFC §5.6.3 冻结表
        "materialized:{ok|miss}",                 # 成功=ok(正式行已物化); Category 2=ok(读命中但空); Category 3/4=miss(build 未写)
    ],
    warnings=[                                    # 冻结 token, 逐字使用 (RFC §5.6.3)
        # complete → []
        # Category 2/4 → ["historical-ranking-empty"]
        # Category 3   → ["historical-ranking-incomplete"]
    ],
)
```

**关键约束**：
1. **不经 router**——直读物化集合，无 provider fallback、无外部 HTTP。
2. **dataset + trade_date 双必填**——缺失任一 → `ValueError`。
3. **单 dataset 查询**——禁止跨 dataset 列表参数。
4. **排序在 service 层**——查询时重新排序确保稳定（pct_chg DESC → sector_code ASC）。

#### 3.2.2 构建/校验路径（确定性纯函数，T3 核心）

```text
build_ranking_rows(
    rows: list[dict],              # 已有 close/pre_close/sector_code/sector_name 的候选行
    expected_sector_codes: frozenset[str],  # 由调用方/fixture 显式传入
    dataset: str,
    trade_date: str,
) -> BuildOutcome
  │
  ├── 1. 过滤非法行：close/pre_close 为 None 或缺字段 → 剔除
  ├── 2. 去重：同 sector_code 多行 → 剔除（重复不 materialize）
  ├── 3. 计算 pct_chg: (close - pre_close) / pre_close * 100
  ├── 4. 完整性校验：
  │      observed = {row.sector_code for valid rows}
  │      if observed != expected_sector_codes:
  │          → 不生成正式 ranking，返回 incomplete/empty outcome
  ├── 5. 排序：pct_chg DESC → sector_code ASC
  ├── 6. 连续 rank 分配（1-based）
  ├── 7. 构建 9 字段行（含 updated_at）
  │
  ▼
BuildOutcome(status=complete|incomplete|empty, rows=list[SectorRankingDaily], ...)
```

**关键约束**：
- `expected_sector_codes` **由调用方/fixture 显式传入**，不硬编码。
- 100% exact-match 才生成正式 ranking（`observed == expected`）。
- 缺行业/重复/非法行 → 不 materialize 部分榜单。

### 3.3 接口与数据结构

#### 3.3.1 SectorRankingDaily dataclass（`models/domain/sector_ranking.py`）

```python
@dataclass
class SectorRankingDaily:
    """历史行业日涨跌幅排名行 — 03_data_ud_sector_ranking_daily canonical。

    9 字段最小行 schema（SPEC-03-015 V0.2 §3.2.1 H-009 ~ H-017）。
    每条记录表示某 dataset 下某 sector_code 在某已收盘交易日的
    日涨跌幅排名。消费方通过 sector.ranking_history capability 访问。

    本数据为辅助研究数据，不构成交易指令或投资建议。
    """

    dataset: str          # (必填) 数据源与分类口径标识，如 "sw2021_ta_cn"
    trade_date: str       # (必填) 交易日，格式 "YYYY-MM-DD"，已收盘历史交易日
    sector_code: str      # (必填) 板块代码，dataset 内唯一
    sector_name: str      # (必填) 板块名称
    pct_chg: float        # (必填) 日涨跌幅 %，口径 (close-pre_close)/pre_close*100
    rank: int             # (必填) 当日涨跌幅排名（1=涨幅最高）
    close: float          # (必填) 当日收盘价/收盘指数
    pre_close: float      # (必填) 前一交易日收盘价/收盘指数
    updated_at: str       # (必填) 行写入/更新时间戳，ISO-8601

    @classmethod
    def from_dict(cls, d: dict) -> "SectorRankingDaily":
        """从字典构造。全部 9 字段必填——缺失任一 → ValueError。

        不做默认值填充、不做 None 容忍。
        """
        ...
```

**字段校验规则（SPEC H-009 ~ H-018 对齐）**：

| 字段 | 校验 | 失败处理 |
|---|---|---|
| `dataset` | 非空 str；必须为已知枚举值（`_KNOWN_DATASETS`） | `ValueError` |
| `trade_date` | 非空 str；`YYYY-MM-DD` 格式 | `ValueError` |
| `sector_code` | 非空 str | `ValueError` |
| `sector_name` | 非空 str | `ValueError` |
| `pct_chg` | 非空 float（int 输入容错转 float） | `ValueError` |
| `rank` | 非空 int（≥1） | `ValueError` |
| `close` | 非空 float | `ValueError` |
| `pre_close` | 非空 float（≠ 0，防除零） | `ValueError` |
| `updated_at` | 非空 str | `ValueError` |

#### 3.3.2 HistoricalRankingWriter（`adapters/historical_ranking_writer.py`）— 注入式 mongomock repository

```python
class HistoricalRankingWriter:
    """03_data_ud_sector_ranking_daily 的注入式 mongomock repository。

    与 P3PersistenceWriter 平行但独立。接受外部传入的 mongomock db。
    不接受真实 pymongo 连接（离线 guard）。

    Args:
        mongo_db: mongomock Database（由调用方/测试注入）。
            真实 pymongo 连接被拒绝。
    """

    COLLECTION = "03_data_ud_sector_ranking_daily"
    UNIQUE_KEY: frozenset[str] = frozenset({"dataset", "trade_date", "sector_code"})

    def __init__(self, mongo_db: Any) -> None:
        self._db = mongo_db
        self._assert_fake_db(mongo_db)

    @staticmethod
    def _assert_fake_db(mongo_db: Any) -> None:
        """拒绝真实 pymongo（同 P3PersistenceWriter guard 逻辑）。"""
        ...

    def get(
        self,
        collection: str | None = None,
        filter: Mapping[str, Any] | None = None,
    ) -> list[dict]:
        """读取 ranking 行。默认查本 collection。返回 list[dict]。"""
        ...

    def upsert(
        self,
        records: Sequence[Mapping[str, Any]],
        unique_key: Iterable[str] | None = None,
    ) -> "UpsertOutcome":
        """upsert ranking 行。默认按 {dataset, trade_date, sector_code}。

        返回 UpsertOutcome（复用 P3PersistenceWriter.UpsertOutcome frozen dataclass）。
        """
        ...

    def delete(self, filter: Mapping[str, Any]) -> int:
        """按 filter 删除行。空 filter 被拒绝。"""
        ...
```

**设计决策**：
1. **不复用 P3PersistenceWriter**——SPEC 禁止修改 P3 writer。新 writer 是独立类。
2. **UpsertOutcome 复用**——直接 import `from ..adapters.p3_persistence_writer import UpsertOutcome`。
3. **db 由外部注入**——mongomock db 由调用方/测试传入，不在 writer 内部创建。

#### 3.3.3 HistoricalSectorService（`services/historical_sector_service.py`）— 只读查询

```python
# 已知 dataset 枚举（SPEC H-023 ~ H-025）
_KNOWN_DATASETS: frozenset[str] = frozenset({
    "sw2021_ta_cn",
    # 后续扩展：
    # "eastmoney_industry",
    # "ths_industry",
    # "sina_industry_eod",
})


class HistoricalSectorService:
    """历史行业排名域服务（只读查询）。

    V0.2 收紧版：仅提供 get_sector_ranking_history()。
    backfill 逻辑移至附录 A（Future Gate 参考）。

    构造签名：
        HistoricalSectorService(writer: HistoricalRankingWriter)

    writer 是必填依赖（物化集合 reader/writer）。router 不注入
    （历史排名不经 router Step 1/4）。
    """

    DOMAIN = "sector"
    OPERATION = "ranking_history"
    CAPABILITY = "sector.ranking_history"

    def __init__(self, writer: HistoricalRankingWriter) -> None:
        self._writer = writer

    @property
    def capability(self) -> str:
        return self.CAPABILITY

    def get_sector_ranking_history(
        self,
        trade_date: str,
        dataset: str,
        limit: int = 0,
    ) -> DataResult:
        """从物化集合读取历史行业排名。

        Args:
            trade_date: 已收盘历史交易日（YYYY-MM-DD，必填）。
            dataset: dataset 标识（必填，第一版仅 sw2021_ta_cn）。
            limit: 返回前 N 个板块；0 或负数 → 返回全部。

        Returns:
            DataResult，data 为 list[SectorRankingDaily]（按 pct_chg
            降序排列）或 [] （empty）。空集 ≠ error。

        Raises:
            ValueError: trade_date 缺失/格式非法；dataset 缺失/未知枚举。
        """
        ...
        # 1. 校验 trade_date（非空、YYYY-MM-DD）
        # 2. 校验 dataset（非空、已知枚举）
        # 3. 直读物化集合：writer.get(filter={dataset, trade_date})
        # 4. 排序：pct_chg DESC → sector_code ASC
        # 5. limit 截取
        # 6. coerce → list[SectorRankingDaily]
        # 7. 构建 source_trace + DataResult
```

**V0.2 关键变更**：`backfill_sector_ranking()` **不在本类实现**，移至附录 A。

#### 3.3.4 确定性构建/校验纯函数

```python
def build_ranking_rows(
    rows: list[dict],
    expected_sector_codes: frozenset[str],
    dataset: str,
    trade_date: str,
) -> BuildOutcome:
    """从候选行 + expected universe 构建正式 ranking（确定性纯函数）。

    100% exact-match 完整性校验（V0.2 G-01）：
    - observed_sector_codes == expected_sector_codes → complete
    - observed ⊊ expected（缺行业）或含重复/多余 → incomplete（不 materialize 正式 ranking）
    - 零有效行 → empty

    expected_sector_codes 由调用方/fixture 显式传入，不硬编码。
    """
    ...
```

**`BuildOutcome` dataclass**：

```python
@dataclass
class BuildOutcome:
    status: str  # "complete" | "incomplete" | "empty"
    rows: list[SectorRankingDaily]  # complete 时为正式 ranking；否则为空
    observed_sector_codes: frozenset[str]
    expected_sector_codes: frozenset[str]
    coverage_ratio: float  # len(observed) / len(expected)
    skipped_invalid: int  # 因非法 close/pre_close 剔除的行数（内部诊断计数，不进入 source_trace / materialized）
    skipped_duplicates: int  # 因重复 sector_code 剔除的行数（内部诊断计数，不进入 source_trace / materialized）
```

#### 3.3.5 UnifiedDataClient facade（`client.py` 条件性追加）

```python
# 仅当可从已注入 fake/mongomock db 端到端实测时才追加：

@property
def _historical_sector(self) -> HistoricalSectorService:
    """Lazy accessor for HistoricalSectorService."""
    if self._historical_sector_service is None:
        # mongomock db 来源：T3 实现时确定（从构造参数复用或新增可选参数）
        # 如无法复用则 T3 先跳过 facade 集成，仅交付 service+writer
        ...
        self._historical_sector_service = HistoricalSectorService(
            writer=HistoricalRankingWriter(self._mongomock_db),
        )
    return self._historical_sector_service

def get_sector_ranking_history(
    self,
    trade_date: str,
    dataset: str,
    limit: int = 0,
) -> DataResult:
    """查询历史行业日涨跌幅排名。"""
    return self._historical_sector().get_sector_ranking_history(
        trade_date=trade_date, dataset=dataset, limit=limit,
    )
```

**条件性约束**：如 T3 实现时无法从已注入 fake/mongomock db 端到端实测，则 facade 后置到未来 Gate，T3 仅交付 service + writer。

### 3.4 完整性判定（SPEC H-049 ~ H-051 V0.2 — 100% exact-match）

**第一版完整性判定规则（严格）**：

```python
# expected: 由调用方/fixture 显式传入（不硬编码）
expected = expected_sector_codes  # frozenset[str]

# observed: 候选行中有效（close + pre_close + sector_name 非空）且去重后的 sector_codes
observed = frozenset(valid_unique_sector_codes)

# 完整性判定（100% exact-match）
if len(valid_rows) == 0:
    completeness = "empty"  # H-051
elif observed == expected:
    completeness = "complete"  # H-049 — 生成正式 ranking
else:
    completeness = "incomplete"  # H-049a — 不生成正式 ranking
```

**关键约束（V0.2 G-01）**：
1. **expected 由调用方/fixture 显式传入**——不在 T3 硬编码"31 个 SW L1 常量表"。
2. **100% exact-match**——`observed == expected` 才生成正式 ranking。不允许部分覆盖 materialize。
3. **incomplete 处理**（Category 3）：`BuildOutcome(status="incomplete")`，不物化；对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-incomplete"])`，source_trace `completeness:incomplete, materialized:miss`。不返回部分榜单，warning token 冻结（见 RFC §5.6.3）。
4. **empty 处理**（H-051 / Category 4）：build 零有效行 → `BuildOutcome(status="empty")`，不物化；对外查询返回 `DataResult.success(data=[], warnings=["historical-ranking-empty"])`，source_trace `completeness:empty, materialized:miss`。
5. **读集合无记录**（Category 2）：trade_date 合法但物化集合零条 → `DataResult.success(data=[], warnings=["historical-ranking-empty"])`，source_trace `coverage:0/{expected}, completeness:empty, materialized:ok`。
6. **参数非法**（Category 1）：trade_date/dataset/limit 非法 → `ValueError`（service 入口抛出，不构造 DataResult）。
7. **成功处理**（RFC §5.6.3 冻结表成功行）：`observed == expected`（100% 覆盖、无重复、每行有效 close/pre_close）且正式行已物化 → `BuildOutcome(status="complete")`，正式 ranking 行物化；对外查询返回完整榜单 `DataResult.success(data=[...], warnings=[])`，source_trace `completeness:complete, materialized:ok`。

### 3.5 pct_chg 与 rank 计算

#### 3.5.1 pct_chg（SPEC H-030 ~ H-032）

```
pct_chg = (close - pre_close) / pre_close * 100
```

- **固定口径**：close-to-pre_close。
- **禁止** close-to-open。
- **禁止** 取上游 TA-CN 自带 `pct_chg`。
- 精度：float，不四舍五入。

#### 3.5.2 rank（SPEC H-036 ~ H-038）

```python
# 稳定排序：pct_chg DESC → sector_code ASC
sorted_rows = sorted(valid_rows, key=lambda r: (-r["pct_chg"], r["sector_code"]))

# 连续 rank 分配（1-based，不跳号，无并列）
for i, row in enumerate(sorted_rows, start=1):
    row["rank"] = i
```

### 3.6 mongomock 映射

```python
# mongomock Database 中，collection 按需自动创建
db = mongomock.MongoClient().get_database("unified_data_test")
coll = db["03_data_ud_sector_ranking_daily"]

# 文档结构（9 字段 + MongoDB 自动 _id）
{
    "_id": ObjectId(...),
    "dataset": "sw2021_ta_cn",
    "trade_date": "2026-07-13",
    "sector_code": "801120",
    "sector_name": "食品饮料",
    "pct_chg": 0.85,
    "rank": 1,
    "close": 5545.0,
    "pre_close": 5498.16,
    "updated_at": "2026-07-31T19:30:00.123456",
}
```

### 3.7 生产 collection / index 创建（附录，不在 T3）

**以下 DDL 不在 T3 范围。Gate-2（Pascal 授权）执行。** 见附录 A.4。

---

## 4. 实现计划（T3 Implement worker 按 §4.1 ~ §4.6 顺序实现）

### Step 1: 新建 `models/domain/sector_ranking.py`

- [ ] 定义 `SectorRankingDaily` dataclass（9 字段，全部必填，无默认值）
- [ ] 定义 `from_dict()` classmethod（严格校验，缺失任一字段 → ValueError）
- [ ] 定义 `__all__ = ["SectorRankingDaily"]`

**验证**：模块可独立 import，无第三方依赖。
**符号级变更**：新增文件，新增 1 个 dataclass + 1 个 classmethod。

### Step 2: 修改 `models/domain/__init__.py`

- [ ] 追加 `from .sector_ranking import SectorRankingDaily`
- [ ] 追加 `"SectorRankingDaily"` 到 `__all__`（如 `__all__` 存在）

**验证**：`from skills.data.unified_data.models.domain import SectorRankingDaily` 可 import。
**符号级变更**：追加 1 行 import + 1 个 `__all__` 条目。

### Step 3: 新建 `adapters/historical_ranking_writer.py`

- [ ] 定义 `HistoricalRankingWriter` 类（COLLECTION / UNIQUE_KEY 常量）
- [ ] 实现 `_assert_fake_db()` guard（与 P3PersistenceWriter 一致）
- [ ] 实现 `get(collection, filter)` — 返回 list[dict]
- [ ] 实现 `upsert(records, unique_key)` — 返回 UpsertOutcome（复用 P3PersistenceWriter.UpsertOutcome）
- [ ] 实现 `delete(filter)` — 返回 int
- [ ] 定义 `__all__`

**验证**：mongomock db 上 get/upsert/delete 正常工作；真实 pymongo 被拒绝。
**符号级变更**：新增文件，新增 1 个类 + 3 个方法 + 2 个常量。

### Step 4: 新建 `services/historical_sector_service.py`

- [ ] 定义常量：`_KNOWN_DATASETS`
- [ ] 定义 `build_ranking_rows()` 纯函数 + `BuildOutcome` dataclass
- [ ] 定义 `HistoricalSectorService` 类
- [ ] 实现 `get_sector_ranking_history()` — 校验 + 直读物化 + 排序 + source_trace
- [ ] 实现 `_validate_trade_date()` — 格式校验
- [ ] 实现 `_validate_dataset()` — 枚举检查
- [ ] 定义 `__all__`

**V0.2 关键**：**不实现 `backfill_sector_ranking()`**（移至附录 A）。

**验证**：注入 HistoricalRankingWriter(mongomock) 后，get 全链路离线通过。
**符号级变更**：新增文件，新增 1 个纯函数 + 1 个 dataclass + 1 个类 + 3 个方法 + 1 个常量。

### Step 5: 修改 `client.py`（条件性）

- [ ] **仅当**可从已注入 fake/mongomock db 端到端实测时：
  - [ ] 追加 `self._historical_sector_service: HistoricalSectorService | None = None`
  - [ ] 追加 `_historical_sector()` lazy accessor property
  - [ ] 追加 `get_sector_ranking_history()` facade 方法
- [ ] 否则跳过 facade，T3 仅交付 service + writer

**验证**：如实现，`UnifiedDataClient.get_sector_ranking_history(...)` 可调用且现有方法不受影响。
**符号级变更**（如实现）：追加 1 个 instance attribute + 1 个 property + 1 个方法。

### Step 6: 新建测试 + fixture

- [ ] 新建 `tests/fixtures/historical_ranking_fixtures.py`
  - `_make_valid_ranking_rows()` — 完整有效行（含显式 expected_sector_codes）
  - `_make_incomplete_rows()` — 缺行业（observed ⊊ expected）
  - `_make_duplicate_rows()` — 重复 sector_code
  - `_make_empty_rows()` — 零有效行
- [ ] 新建 `tests/test_sector_ranking_history.py`（覆盖 §5 测试矩阵）

**验证**：全部测试离线通过，零真实 I/O。

### Step 7: 回归测试

- [ ] `pytest skills/data/unified_data/tests/ -x -q` 全部 PASS
- [ ] 确认 P3-A 测试不变

---

## 5. 测试策略

### 5.1 单元测试矩阵（收紧版）

| 测试 ID | SPEC 编号 | 覆盖 | 需网络 | 描述 |
|---|---|---|---|---|
| UT-015-001 | T-015-001 | schema 校验 | 否 | SectorRankingDaily.from_dict 9 字段全部必填；缺失任一 → ValueError |
| UT-015-002 | T-015-002 | unique key upsert | 否 | 相同 {dataset, trade_date, sector_code} 覆盖更新；updated_at 刷新 |
| UT-015-003 | T-015-003 | pct_chg 计算 | 否 | (close - pre_close) / pre_close * 100 正确性 |
| UT-015-004 | T-015-004 | rank 计算 | 否 | pct_chg 降序排名、tiebreaker（sector_code ASC）、连续 rank |
| UT-015-005 | T-015-005 | 缺 pre_close fail | 否 | 缺 pre_close 的 sector 行不入库 |
| UT-015-006 | T-015-006 | 完整性判定 incomplete（Category 3） | 否 | observed != expected（缺行业/重复/多余）→ 不生成正式 ranking；`BuildOutcome(status="incomplete")`；对外查询 `DataResult.success([], warnings=["historical-ranking-incomplete"])`；source_trace `completeness:incomplete, materialized:miss`；**不写库**（RFC §5.6.3 Category 3） |
| UT-015-007 | T-015-007 | 零板块 empty（Category 4） | 否 | build 零有效行 → `BuildOutcome(status="empty")`；对外查询 `DataResult.success([], warnings=["historical-ranking-empty"])`；source_trace `completeness:empty, materialized:miss`（非 error；RFC §5.6.3 Category 4） |
| UT-015-008 | T-015-008 | 完整性安全边界 | 否 | 非法 close/pre_close 的行不进入正式 ranking（由完整性约束覆盖） |
| UT-015-009 | T-015-009 | dataset 隔离 | 否 | 不同 dataset 不混排；无静默 fallback |
| UT-015-010 | T-015-010 | trade_date 格式校验 | 否 | YYYY-MM-DD 格式校验；非法日期 → ValueError |
| UT-015-011 | T-015-011 | 禁止 date=None | 否 | trade_date=None → ValueError |
| UT-015-012 | T-015-012 | build_ranking_rows 纯函数 | 否 | 输入 rows + expected → 正确排序/rank/完整性判定 |
| UT-015-013 | T-015-013 | source_trace 完整性 | 否 | 返回的 DataResult 包含 dataset/trade_date/source/coverage/completeness/materialized；**warning token 与 source_trace 顺序逐字断言**（Category 2/3/4） |
| UT-015-014 | — | dataset 校验 | 否 | dataset=None → ValueError；未知 dataset → ValueError |
| UT-015-015 | — | 禁止跨 dataset | 否 | dataset=["a","b"] → ValueError（不接受列表） |
| UT-015-016 | — | Writer fake-db guard | 否 | HistoricalRankingWriter 拒绝真实 pymongo |
| UT-015-017 | — | limit 截取 | 否 | limit > 0 → 返回前 N；limit ≤ 0 → 全部 |
| UT-015-018 | — | 排序稳定性 | 否 | pct_chg 相同时 sector_code ASC 确定性排序 |
| UT-015-019 | — | expected universe 显式传入 | 否 | expected_sector_codes 由 fixture 显式传入；不硬编码 |
| UT-015-020 | T-015-014 | 读集合无记录（Category 2） | 否 | trade_date 合法但物化集合零条 → `DataResult.success([], warnings=["historical-ranking-empty"])`；source_trace `coverage:0/{expected}, completeness:empty, materialized:ok`（RFC §5.6.3 Category 2） |
| UT-015-021 | T-015-015 | 成功完整 ranking（成功场景 trace） | 否 | observed == expected → `BuildOutcome(status="complete")`；对外查询返回完整榜单 `DataResult.success(data=[...], warnings=[])`；source_trace `completeness:complete, materialized:ok`；**成功 source_trace 顺序（dataset → trade_date → source → coverage → completeness → materialized）与文本逐字断言**（RFC §5.6.3 冻结表成功行） |

**V0.2 移除的测试项**（移至附录 A，不在 T3）：
- ~~backfill 全链路~~
- ~~backfill 覆盖率不足~~
- ~~backfill 异常处理~~
- ~~pct_chg 容差校验（RT-3）~~
- ~~realtime fallback 精确检测（RT-1~5）~~
- ~~sector_name 未找到（SW 常量表）~~

### 5.2 回归测试范围

| 测试文件 | 回归原因 |
|---|---|
| `test_sector_service.py` | SectorService 不变 |
| `test_mapping_sector.py` | SectorSnapshot mapping 不变 |
| `test_sector_provider_activation.py` | P3-A provider 不变 |
| `test_sector_client.py` | facade 委托现有方法不变 |
| `test_router_p3_readonly.py` | router 不变 |

### 5.3 运行命令

```bash
# T3 新增测试
cd /home/pascal/workspace/yquant-investment
python -m pytest skills/data/unified_data/tests/test_sector_ranking_history.py -v

# 回归测试
python -m pytest skills/data/unified_data/tests/ -x -q
```

---

## 6. source_trace 与 dataset 表达契约

### 6.1 source_trace 条目

```python
source_trace = [
    f"dataset:{dataset}",                     # H-065
    f"trade_date:{trade_date}",               # H-066
    "source:ta_cn:index_daily_quotes",        # H-067
    f"coverage:{actual}/{expected}",          # H-068
    f"completeness:{complete|incomplete|empty}",  # H-069
    f"materialized:{ok|miss}",                # H-070
]
```

### 6.2 warning 表达（冻结 token — RFC §5.6.3 对齐）

**warning token 为契约冻结值，T3 实现须逐字使用**（不得使用自由文本、不得省略）。描述性信息放在 source_trace，不放在 warning。

| 场景 | Category | warning（冻结 token） | source_trace 补充 |
|---|---|---|---|
| 参数非法 | 1 | —（抛 `ValueError`，无 warning） | — |
| 读集合无记录 | 2 | `["historical-ranking-empty"]` | `coverage:0/{expected}, completeness:empty, materialized:ok` |
| build 完整性失败（incomplete） | 3 | `["historical-ranking-incomplete"]` | `coverage:{actual}/{expected}, completeness:incomplete, materialized:miss` |
| build 零有效行（empty） | 4 | `["historical-ranking-empty"]` | `coverage:0/{expected}, completeness:empty, materialized:miss` |
| 成功完整 ranking（complete） | 成功 | `[]`（无 warning） | `coverage:{actual}/{expected}, completeness:complete, materialized:ok` |

**禁止**：不得使用 `"completeness incomplete: observed ... != expected ... sectors"`、`"empty: no valid rows for ..."` 等自由文本作为 warning。这类描述性信息如需保留，放入 source_trace 的 `coverage`/`completeness` 条目，warning 仅承载冻结 token。`materialized` 枚举封闭为 `ok|miss`，`skipped` 已废弃禁用，不得作为对外可能值（RFC §5.6.3 冻结约束，T2.9）。

---

## 7. 风险、降级与回滚

| 风险 | 概率 | 影响 | 应对 | 降级/回滚 |
|---|---|---|---|---|
| expected universe 真实来源未验证 | 中 | 中 | 离线 fixture 显式传入；Gate-1 权威验证 | 离线仅证明逻辑 |
| mongomock 与真实 Mongo 行为差异 | 低 | 低 | HistoricalRankingWriter 接口与 pymongo 协议一致；Gate-2 后真实 Mongo 验证 | T3 仅离线验证 |
| client.py facade 无法端到端实测 | 中 | 低 | facade 条件性；无法测则后置 | T3 仅交付 service + writer |
| T3 后发现完整性判定过严（100% 无法满足） | 低 | 中 | 留待 Gate-1 评估是否引入宽容阈值 | 返回 incomplete + empty |

### 7.1 回滚策略

T3 实现后如发现设计缺陷：
1. 新增文件全部保留为设计资产（不删除）。
2. `client.py` 追加的方法可注释掉（一行），不影响现有功能。
3. `models/domain/__init__.py` 追加的 export 可注释掉。
4. 回退后全部已有测试 PASS（零侵入设计保证）。

---

## 8. 后续 Gate（SPEC §4 对齐）

| Gate | 内容 | 授权方 | 前置条件 | 本设计定义的 Gate 动作 |
|---|---|---|---|---|
| G-015-1 | TA-CN SW 历史数据真实可达性 smoke（只读 Mongo） | Pascal | T3 离线实现通过 | 验证 `index_daily_quotes` 中 SW L1 sector_code 覆盖率、历史完整性、source 字段分布；**权威校验 expected universe** |
| G-015-2 | 新 collection 创建 + 索引（DDL） | Pascal | Gate-1 verdict ≥ conditional_pass | 执行附录 A.4 的 createCollection + createIndex |
| G-015-3 | 历史 backfill（真实 TA-CN → 新 collection） | Pascal | Gate-2 完成 | 注入真实 TA-CN client（附录 A.1），运行 backfill（附录 A.2） |
| G-015-4 | 生产读取激活 | Pascal | Gate-3 canary 通过 | UnifiedDataClient.get_sector_ranking_history() 上线 |

---

## 9. 交接给实现者

### 9.1 必须遵守

1. **9 字段全部必填**——SectorRankingDaily.from_dict 缺失任一字段 → ValueError。
2. **pct_chg 必须用 (close - pre_close) / pre_close * 100**。
3. **trade_date + dataset 双必填**——get_sector_ranking_history 无默认值。
4. **禁止 trade_date=None**。
5. **禁止跨 dataset 混读**。
6. **空集 ≠ error**——完整性失败 / 读集合无记录 / build 零有效行均返回 `DataResult.success(data=[], warnings=[<冻结 token>])`，**不抛 error**。4 类失败情形与成功完整 ranking 的结果类型与冻结 warning token 见 RFC §5.6.3 结果语义冻结表（Category 1~4 + 成功行）；warning token 逐字使用（`historical-ranking-empty` / `historical-ranking-incomplete`），成功情形 `warnings=[]`、trace 为 `completeness:complete, materialized:ok`。
7. **排序：pct_chg DESC → sector_code ASC**——查询时重新排序。
8. **rank 连续分配**——1-based，不跳号，tiebreaker 为 sector_code ASC。
9. **完整性 100% exact-match**——`observed == expected` 才生成正式 ranking（V0.2 G-01）。
10. **expected_sector_codes 由调用方/fixture 显式传入**——不硬编码（V0.2 G-01）。
11. **不经 router**——直读物化集合。
12. **不修改 P3-A 的任何文件**。
13. **不触发真实 I/O**——T3 仅 mongomock + 显式 fixture。
14. **不实现 backfill**——移至附录 A（V0.2 G-02）。
15. **不硬编码 SW L1 全表**——sector_name 来源留待 Gate-1（V0.2 G-02）。
16. **facade 条件性**——仅当可端到端实测时实现（V0.2 G-02）。
17. **source_trace 包含 6 条最小信息**。
18. **完成后**：验收标准全 PASS → `kanban_complete(status="done")`；任何 FAIL → `kanban_block(reason="...")`。

### 9.2 可自行判断

- `BuildOutcome` 的字段命名。
- client.py 中 mongomock db handle 的获取方式（复用 vs 新增参数 vs 跳过 facade）。
- ~~warning 信息的具体措辞~~ **（V0.3 撤销：warning token 已冻结为 `historical-ranking-empty` / `historical-ranking-incomplete`，不得自行措辞；描述性信息放入 source_trace。）**

### 9.3 遇到以下情况退回 Principal

- 发现完整性 100% exact-match 在真实数据下无法满足（需评估宽容阈值）。
- 发现需要修改 router.py。
- 发现 `client.py` 的 lazy accessor 与现有 `_sector()` 冲突。
- 发现需要新增第三方依赖。
- 发现 P3-A 文件需要修改。

---

## 10. SPEC 开放问题解决汇总（V0.2）

| OQ 编号 | 问题 | V0.2 解决方案 | 章节 |
|---|---|---|---|
| OQ-015-1 | sector_name 来源 | **不在 T3 硬编码全表**；留待 Gate-1 权威验证；离线 fixture 显式传入 | §3.3.4, 附录 A.3 |
| OQ-015-2 | 覆盖率阈值 | **100% exact-match**（`observed == expected`）；expected 由调用方/fixture 显式传入 | §3.4 |
| OQ-015-3 | pre_close 容差 | **精确容差校验留待后续 Gate**（附录 A.2） | 附录 A.2 |
| OQ-015-4 | realtime fallback 检测信号 | **不在 T3 实现**；第一版由完整性约束覆盖安全边界；精确信号留待后续 Gate（附录 A.5） | §3.4, 附录 A.5 |
| OQ-015-5 | rank 写入 vs 查询时计算 | 查询时按稳定排序返回（pct_chg DESC, sector_code ASC） | §3.5.2 |
| OQ-015-6 | sector_code 跨 dataset 共存 | dataset 字段隔离 | §6 |

---

## 附录 A：Future Gate 参考设计（不在 T3 实现）

> **本附录内容为后续 Gate（Gate-1 ~ Gate-4）的参考设计，T3 Implement worker 不得实现以下任何内容。**
> V0.1 Design 中这些内容曾位于正文，V0.2 根据用户"简化"要求和 Design Gate G-02 反馈移至此附录。

### A.1 HistoricalRankingClient Protocol + Fake（Gate-3 backfill 注入参考）

```python
# providers/historical_ranking_client.py — Gate-3 创建，不在 T3

@runtime_checkable
class HistoricalRankingClient(Protocol):
    """上游历史排名数据 client（Gate-3 注入模式）。

    两个实现：
    * FakeHistoricalRankingClient — 测试 fixture（Gate-3 离线验证）
    * TA_CNHistoricalRankingClient — Gate-3 生产实现，只读 TA-CN index_daily_quotes
    """

    def get_daily_bars_for_ranking(
        self, *, trade_date: str, prev_trade_date: str,
    ) -> list[dict]:
        """返回目标日 + 前一日的全部 SW L1 行业指数日线文档。"""
        ...


class FakeHistoricalRankingClient:
    """Test-only 实现（Gate-3 离线验证用）。"""
    ...
```

### A.2 backfill 逻辑（Gate-3 真实 TA-CN → 新 collection）

```python
# HistoricalSectorService.backfill_sector_ranking() — Gate-3 实现，不在 T3

def backfill_sector_ranking(
    self, trade_date: str, dataset: str = "sw2021_ta_cn",
    *, upstream_client: HistoricalRankingClient,
    prev_trade_date: str | None = None,
    expected_sector_codes: frozenset[str] | None = None,
) -> BackfillOutcome:
    """从上游 client 读取 TA-CN 日线并计算/写入历史排名。

    Gate-3 注入真实 TA-CN client。包含：
    - pre_close 推导（前一交易日 close）
    - pct_chg 容差校验（0.05 个百分点，附录参考值）
    - realtime fallback 排除（附录 A.5）
    - sector_name 解析（附录 A.3）
    - 完整性校验（100% exact-match）
    - rank 计算 + upsert
    """
    ...
```

### A.3 SW L1 sector_name 映射（Gate-1 权威验证）

```python
# SW L1 代码→名称常量表 — Gate-1 权威校验后填充，不在 T3 硬编码

_SW_L1_CODE_TO_NAME: dict[str, str] = {
    # 完整 31 个代码在 Gate-1 以权威来源（申万官方网站或 TA-CN index_basic_info）校验填充
    # 示例（未经权威验证，仅供参考）：
    # "801120": "食品饮料",
    # "801780": "银行",
    ...
}

def _resolve_sector_name(sector_code: str) -> str | None:
    """从 SW L1 常量表查找 sector_name。未找到 → None。"""
    return _SW_L1_CODE_TO_NAME.get(sector_code)
```

### A.4 生产 collection / index DDL（Gate-2）

```javascript
// Gate-2: 创建 collection（如不存在）
db.createCollection("03_data_ud_sector_ranking_daily")

// Gate-2: 创建唯一复合索引
db["03_data_ud_sector_ranking_daily"].createIndex(
    {"dataset": 1, "trade_date": -1, "sector_code": 1},
    {"unique": true, "name": "uniq_dataset_date_sector"}
)

// Gate-2: 创建查询辅助索引
db["03_data_ud_sector_ranking_daily"].createIndex(
    {"dataset": 1, "trade_date": -1},
    {"name": "idx_dataset_date"}
)
```

### A.5 realtime fallback 精确检测信号（后续 Gate）

| 编号 | 检测信号 | 检测逻辑 | 处理 |
|---|---|---|---|
| RT-1 | `trade_date` 为当日且市场未收盘 | `trade_date == today and now < market_close_time` | 该 trade_date 全部行不作为历史数据 |
| RT-2 | 记录缺少 `close` 或 `close` 为 None | `doc.get("close") is None` | 该行不入库 |
| RT-3 | 记录 `pct_chg`（上游自带）与计算值偏差超容差 | `abs(upstream_pct - computed_pct) > tolerance` | 该行仍入库但标记 warning（容差 0.05% 为附录参考值） |
| RT-4 | 记录的 `source` 字段标记为 realtime/intraday | `doc.get("source") in ("realtime", "intraday", "rt")` | 该行不入库 |
| RT-5 | `trade_date` 格式不兼容 | 非 `YYYYMMDD` 格式 | 该行不入库 |

**V0.2 说明**：第一版由完整性约束（§3.4，100% exact-match）覆盖安全边界——缺行业/重复/非法 close/pre_close 的行均不进入正式 ranking。精确 realtime 信号检测（RT-1~5）留待后续 Gate 以权威数据定义。

### A.6 TA-CN index_daily_quotes 聚合逻辑（Gate-3 backfill 参考）

```text
HistoricalRankingClient.get_daily_bars_for_ranking(trade_date, prev_trade_date)
  │
  ▼ 返回 list[dict]（TA-CN index_daily_quotes 原始文档）
  │
  每个 TA-CN 文档：
    sector_code: "801120"（str）
    trade_date: "20260713"（YYYYMMDD）
    close: 5545.0
    source: "sw"
    pct_chg: 0.85（TA-CN 自带，不使用）
    ...

日期格式兼容：
  - 公开参数：YYYY-MM-DD
  - TA-CN 内部：YYYYMMDD
  - 转换在 backfill service 层完成

data_source 映射：
  TA-CN source="sw" → dataset="sw2021_ta_cn"（常量注入，不从 TA-CN 推断）
```

### A.7 pre_close 容差校验（附录参考值，后续 Gate 确认）

```python
# 附录参考值：0.05 个百分点（绝对值）
# 理由：TA-CN pct_chg 可能基于不同精度；0.05% 可容忍四舍五入差异
# 超标不阻止入库（使用计算值），但标记 warning
_PCT_CHG_TOLERANCE: float = 0.05  # 后续 Gate 确认
```

---

## 声明

本设计中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本设计不修改 RFC-03-015 V0.2 / SPEC-03-015 V0.2 的任何内容。所有引用以交叉引用方式继承，冲突时以 RFC/SPEC 为准。

本设计与 P3-A（DESIGN-03-014-p3a）在代码层面完全隔离：不共享 collection、不共享 schema、不共享 client、不共享 provider、不共享 service 方法。两套实现各自独立。

附录 A 内容为 Future Gate 参考设计，T3 Implement worker 不得实现附录 A 的任何内容。
