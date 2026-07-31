"""HistoricalSectorService — 历史行业日涨跌幅排名只读查询服务（RFC-03-015 T3）。

新增 capability ``sector.ranking_history`` 的离线最小实现（DESIGN-03-015
V0.5 §3.3）：直读物化集合 ``03_data_ud_sector_ranking_daily``，不经
router / provider，无真实 I/O。

核心部件：

* :func:`build_ranking_rows` — 确定性纯函数（输入候选行 + 显式 expected
  universe），100% exact-match 完整性校验，pct_chg DESC / sector_code ASC
  稳定排序 + 连续 1-based rank（SPEC H-030 ~ H-038 / H-049 ~ H-051）。
* :class:`BuildOutcome` — 构建结果（complete / incomplete / empty）。
* :class:`HistoricalSectorService` — 只读查询 service：校验参数 → 直读物化
  集合 → 重新校验完整性 → 稳定排序 → 构造 ``DataResult``（source_trace /
  warning token 与 RFC §5.6.3 冻结表逐字一致）。

result 语义冻结（RFC §5.6.3 冻结表）：

| Category | 触发 | 结果 |
|---|---|---|
| 1 参数非法 | trade_date/dataset/limit 非法 | ``ValueError``（不构造 DataResult） |
| 2 读集合无记录 | {dataset, trade_date} 零条 | empty + ``historical-ranking-empty``，trace ``completeness:empty, materialized:ok`` |
| 3 build 完整性失败 | observed != expected | empty + ``historical-ranking-incomplete``，trace ``completeness:incomplete, materialized:miss`` |
| 4 build 零有效行 | 零个有效行 | empty + ``historical-ranking-empty``，trace ``completeness:empty, materialized:miss`` |
| 成功 | observed == expected 且已物化 | 完整榜单 + warnings=[]，trace ``completeness:complete, materialized:ok`` |

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from ..adapters.historical_ranking_writer import HistoricalRankingWriter
from ..models import DataResult, Market, SecurityId
from ..models.domain.sector_ranking import (
    KNOWN_DATASETS,
    SectorRankingDaily,
    coerce_float,
    is_valid_trade_date,
)

# DESIGN §3.3.3 常量名对齐：domain 模块持有权威枚举，此处别名导出。
_KNOWN_DATASETS: frozenset[str] = KNOWN_DATASETS

# Capability 常量（RFC §5.1.1）。
DOMAIN = "sector"
OPERATION = "ranking_history"
CAPABILITY = "sector.ranking_history"

# DataResult.provider 标签（本 service 直读物化集合，非 provider fetch）。
PROVIDER = "historical_sector"

# source_trace 数据来源标识（RFC §5.8.2 H-067：如 ``ta_cn:index_daily_quotes``）。
SOURCE = "ta_cn:index_daily_quotes"

# 冻结 warning token（RFC §5.6.3）—— 逐字使用，不得改写。
WARNING_EMPTY = "historical-ranking-empty"
WARNING_INCOMPLETE = "historical-ranking-incomplete"

# 枚举封闭（RFC §5.6.3 冻结约束 / SPEC H-069 ~ H-070）。
_COMPLETENESS_VALUES = ("complete", "incomplete", "empty")
_MATERIALIZED_VALUES = ("ok", "miss")


def _now_iso() -> str:
    """Naive UTC ISO-8601 timestamp (matches the repo's Phase 0 default)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _placeholder_security_id(dataset: str, trade_date: str) -> SecurityId:
    """Synthesise a market-level placeholder ``SecurityId`` for DataResult."""
    return SecurityId(
        market=Market.INDEX,
        symbol=f"sector_ranking:{dataset}:{trade_date}",
    )


@dataclass
class BuildOutcome:
    """:func:`build_ranking_rows` 的构建结果。

    ``status`` 仅 ``complete | incomplete | empty``。``rows`` 仅在
    ``complete`` 时携带正式 ranking（按 pct_chg DESC / sector_code ASC
    排序、rank 连续）；否则为 ``[]``。

    ``skipped_invalid`` / ``skipped_duplicates`` 为**内部诊断计数**，
    不进入对外 source_trace / materialized（DESIGN §6.2 禁止段）。
    """

    status: str
    rows: list[SectorRankingDaily] = field(default_factory=list)
    observed_sector_codes: frozenset[str] = frozenset()
    expected_sector_codes: frozenset[str] = frozenset()
    coverage_ratio: float = 0.0
    skipped_invalid: int = 0
    skipped_duplicates: int = 0


def build_ranking_rows(
    rows: Sequence[Mapping[str, Any]],
    expected_sector_codes: Iterable[str],
    dataset: str,
    trade_date: str,
    *,
    updated_at: str | None = None,
) -> BuildOutcome:
    """从候选行 + expected universe 构建正式 ranking（确定性纯函数，无 I/O）。

    100% exact-match 完整性校验（SPEC H-049 ~ H-051 / DESIGN §3.4）：

    * ``observed == expected`` → ``status="complete"``，rows 为正式
      ranking（pct_chg DESC → sector_code ASC 稳定排序，rank 从 1 连续）。
    * 缺行业 / 多余代码 / 重复 sector_code / 非法 close/pre_close →
      ``status="incomplete"``，rows=[]（不生成、不物化部分榜单）。
    * 零有效行 → ``status="empty"``，rows=[]。

    ``expected_sector_codes`` 由调用方 / fixture **显式传入**，不硬编码
    SW L1 全表（H-049u）。

    Args:
        rows: 候选行（已有 close / pre_close / sector_code / sector_name
            的 dict；dataset / trade_date 由本函数注入）。
        expected_sector_codes: 期望板块代码集合（显式 universe）。
        dataset: dataset 标识（调用方已校验合法）。
        trade_date: 交易日 ``YYYY-MM-DD``（调用方已校验合法）。
        updated_at: 行时间戳；``None`` 时由本函数生成（便于测试注入
            固定值保持确定性）。

    Returns:
        :class:`BuildOutcome`。参数非法（dataset/trade_date 非法）会在
        构造行时经 :meth:`SectorRankingDaily.from_dict` 抛出 ``ValueError``
        —— 调用方（service）在调用前已完成参数校验。
    """
    expected = frozenset(expected_sector_codes)
    stamp = updated_at if updated_at is not None else _now_iso()

    # 1. 过滤非法行：sector_code/sector_name 非空、close/pre_close 为
    #    有限数值且 pre_close != 0（SPEC H-043 / A-015-DRIFT-4）。
    candidates: list[dict[str, Any]] = []
    skipped_invalid = 0
    for row in rows:
        if not isinstance(row, Mapping):
            skipped_invalid += 1
            continue
        sector_code = row.get("sector_code")
        sector_name = row.get("sector_name")
        close = coerce_float(row.get("close"))
        pre_close = coerce_float(row.get("pre_close"))
        if not isinstance(sector_code, str) or not sector_code:
            skipped_invalid += 1
            continue
        if not isinstance(sector_name, str) or not sector_name:
            skipped_invalid += 1
            continue
        if close is None or pre_close is None or pre_close == 0:
            skipped_invalid += 1
            continue
        candidates.append(
            {
                "dataset": dataset,
                "trade_date": trade_date,
                "sector_code": sector_code,
                "sector_name": sector_name,
                "close": close,
                "pre_close": pre_close,
            }
        )

    # 2. 去重：同 sector_code 多行 → 该代码全部行剔除（重复不
    #    materialize，SPEC H-049a / DESIGN §3.2.2 step 2）。
    counts = Counter(c["sector_code"] for c in candidates)
    duplicate_codes = {code for code, n in counts.items() if n > 1}
    valid_rows: list[dict[str, Any]] = []
    skipped_duplicates = 0
    for candidate in candidates:
        if candidate["sector_code"] in duplicate_codes:
            skipped_duplicates += 1
            continue
        valid_rows.append(candidate)

    observed = frozenset(c["sector_code"] for c in valid_rows)

    # 3. 完整性判定（100% exact-match）。
    if not valid_rows:
        return BuildOutcome(
            status="empty",
            rows=[],
            observed_sector_codes=observed,
            expected_sector_codes=expected,
            coverage_ratio=0.0,
            skipped_invalid=skipped_invalid,
            skipped_duplicates=skipped_duplicates,
        )
    if observed != expected:
        coverage_ratio = len(observed) / len(expected) if expected else 0.0
        return BuildOutcome(
            status="incomplete",
            rows=[],
            observed_sector_codes=observed,
            expected_sector_codes=expected,
            coverage_ratio=coverage_ratio,
            skipped_invalid=skipped_invalid,
            skipped_duplicates=skipped_duplicates,
        )

    # 4. complete：pct_chg 固定口径 → 稳定排序 → 连续 rank → 9 字段行。
    for candidate in valid_rows:
        candidate["pct_chg"] = (candidate["close"] - candidate["pre_close"]) / candidate["pre_close"] * 100
    valid_rows.sort(key=lambda r: (-r["pct_chg"], r["sector_code"]))

    ranking: list[SectorRankingDaily] = []
    for i, candidate in enumerate(valid_rows, start=1):
        candidate["rank"] = i
        candidate["updated_at"] = stamp
        ranking.append(SectorRankingDaily.from_dict(candidate))

    coverage_ratio = len(observed) / len(expected) if expected else 0.0
    return BuildOutcome(
        status="complete",
        rows=ranking,
        observed_sector_codes=observed,
        expected_sector_codes=expected,
        coverage_ratio=coverage_ratio,
        skipped_invalid=skipped_invalid,
        skipped_duplicates=skipped_duplicates,
    )


class HistoricalSectorService:
    """历史行业排名域服务（只读查询，不含 backfill）。

    构造签名：``HistoricalSectorService(writer, *, expected_universe_by_dataset=None)``。
    ``writer`` 是必填依赖（物化集合 reader/writer）。router 不注入
    （历史排名不经 router Step 1/4，DESIGN §1.2）。

    ``expected_universe_by_dataset`` 将 dataset → 期望板块代码集合的映射
    注入 service，供完整性判定与 coverage trace 使用。未注入的 dataset
    按 ``frozenset()`` 处理（fail-closed：任何物化行都无法通过
    100% exact-match，查询返回 incomplete / empty，绝不宣称 complete）。
    生产真实 universe 由 Gate-1 权威校验后注入（H-049u）。
    """

    DOMAIN = DOMAIN
    OPERATION = OPERATION
    CAPABILITY = CAPABILITY

    def __init__(
        self,
        writer: HistoricalRankingWriter,
        *,
        expected_universe_by_dataset: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        if writer is None:
            raise TypeError(
                "HistoricalSectorService requires a HistoricalRankingWriter "
                "(mongomock-backed)."
            )
        self._writer = writer
        self._expected_universe: dict[str, frozenset[str]] = {
            dataset: frozenset(codes)
            for dataset, codes in (expected_universe_by_dataset or {}).items()
        }

    @property
    def capability(self) -> str:
        """The canonical ``sector.ranking_history`` capability string."""
        return self.CAPABILITY

    @property
    def writer(self) -> HistoricalRankingWriter:
        """The injected repository (read path)."""
        return self._writer

    # ------------------------------------------------------------------
    # Parameter validation (Category 1 — ValueError, no DataResult)
    # ------------------------------------------------------------------

    def _validate_trade_date(self, trade_date: Any) -> None:
        if not is_valid_trade_date(trade_date):
            raise ValueError(
                f"trade_date must be a valid YYYY-MM-DD string, got {trade_date!r}"
            )

    def _validate_dataset(self, dataset: Any) -> None:
        if not isinstance(dataset, str) or not dataset:
            raise ValueError(f"dataset is required (known: {sorted(_KNOWN_DATASETS)})")
        if dataset not in _KNOWN_DATASETS:
            raise ValueError(
                f"dataset {dataset!r} is not a known dataset; "
                f"known datasets: {sorted(_KNOWN_DATASETS)}"
            )

    def _validate_limit(self, limit: Any) -> int:
        if limit is None:
            return 0  # None → 返回全部（SPEC H-004）
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError(f"limit must be an int, got {limit!r}")
        return limit

    # ------------------------------------------------------------------
    # Query path
    # ------------------------------------------------------------------

    def get_sector_ranking_history(
        self,
        trade_date: str,
        dataset: str,
        limit: int = 0,
    ) -> DataResult:
        """从物化集合读取历史行业日涨跌幅排名。

        完整 trace 顺序固定（RFC §5.6.3 / SPEC H-051c）：``dataset →
        trade_date → source → coverage → completeness → materialized``。

        Args:
            trade_date: 已收盘历史交易日（``YYYY-MM-DD``，必填）。
            dataset: dataset 标识（必填，第一版仅 ``sw2021_ta_cn``）。
            limit: 返回前 N 个板块；``0`` / 负数 / ``None`` → 返回全部。

        Returns:
            ``DataResult``，``data`` 为 ``list[SectorRankingDaily]``
            （按 pct_chg 降序、sector_code 升序）或 ``[]``（empty）。
            空集 ≠ error。

        Raises:
            ValueError: ``trade_date`` 缺失/格式非法；``dataset`` 缺失/
                未知枚举；``limit`` 类型非法（Category 1，不构造
                ``DataResult``）。
        """
        # Category 1 — 参数非法：抛 ValueError，不构造 trace / DataResult。
        self._validate_trade_date(trade_date)
        self._validate_dataset(dataset)
        limit_n = self._validate_limit(limit)

        expected = self._expected_universe.get(dataset, frozenset())
        expected_count = len(expected)

        rows = self._writer.get(
            filter={"dataset": dataset, "trade_date": trade_date}
        )

        trace_prefix = [
            f"dataset:{dataset}",
            f"trade_date:{trade_date}",
            f"source:{SOURCE}",
        ]

        # Category 2 — 读集合无记录：trace completeness:empty,
        # materialized:ok（命中物化集合读取但空）。
        if not rows:
            trace = trace_prefix + [
                f"coverage:0/{expected_count}",
                "completeness:empty",
                "materialized:ok",
            ]
            return DataResult.success(
                data=[],
                security_id=_placeholder_security_id(dataset, trade_date),
                domain=self.DOMAIN,
                operation=self.OPERATION,
                provider=PROVIDER,
                source_trace=trace,
                warnings=[WARNING_EMPTY],
            )

        # 读到的行重新走完整性校验：仅 complete 被视为正式 ranking。
        outcome = build_ranking_rows(rows, expected, dataset, trade_date)
        actual = len(outcome.observed_sector_codes)

        if outcome.status == "complete":
            data = outcome.rows
            if limit_n > 0:
                data = data[:limit_n]
            trace = trace_prefix + [
                f"coverage:{actual}/{expected_count}",
                "completeness:complete",
                "materialized:ok",
            ]
            return DataResult.success(
                data=data,
                security_id=_placeholder_security_id(dataset, trade_date),
                domain=self.DOMAIN,
                operation=self.OPERATION,
                provider=PROVIDER,
                source_trace=trace,
                warnings=[],
            )

        if outcome.status == "incomplete":
            # Category 3 — build 完整性失败：不返回部分榜单、不写库。
            trace = trace_prefix + [
                f"coverage:{actual}/{expected_count}",
                "completeness:incomplete",
                "materialized:miss",
            ]
            return DataResult.success(
                data=[],
                security_id=_placeholder_security_id(dataset, trade_date),
                domain=self.DOMAIN,
                operation=self.OPERATION,
                provider=PROVIDER,
                source_trace=trace,
                warnings=[WARNING_INCOMPLETE],
            )

        # Category 4 — build 零有效行。
        trace = trace_prefix + [
            f"coverage:0/{expected_count}",
            "completeness:empty",
            "materialized:miss",
        ]
        return DataResult.success(
            data=[],
            security_id=_placeholder_security_id(dataset, trade_date),
            domain=self.DOMAIN,
            operation=self.OPERATION,
            provider=PROVIDER,
            source_trace=trace,
            warnings=[WARNING_EMPTY],
        )


__all__ = [
    "BuildOutcome",
    "HistoricalSectorService",
    "build_ranking_rows",
    "PROVIDER",
    "SOURCE",
    "WARNING_EMPTY",
    "WARNING_INCOMPLETE",
]
