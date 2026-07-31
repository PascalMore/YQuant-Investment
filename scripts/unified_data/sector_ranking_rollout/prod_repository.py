"""03-016 rollout production repository — real-pymongo-capable writer + read path.

DESIGN-03-016 V0.4 §3.6.1 / §3.7。与 03-015 冻结的
:class:`~skills.data.unified_data.adapters.historical_ranking_writer.HistoricalRankingWriter`
平行但**允许真实 pymongo**：每个操作先过 ``_assert_namespace``（拒绝目标集合外
的一切读写，G3-S-009 / G2-D-004 同纪律）。

* :class:`ProdRankingWriter` — Gate-3 真实 backfill 写入器
  （``03_data_ud_sector_ranking_daily`` 唯一集合，业务唯一键
  ``{dataset, trade_date, sector_code}``，返回冻结 ``UpsertOutcome``）。
* :class:`BindingState` — Gate-4 binding 开关（``binding_state.json``，
  fail-closed：缺失 → ``{"enabled": False}``）。
* :class:`ProdRankingReader` — Gate-4 生产只读路径（duck-typed ``.get()``，
  可注入冻结 ``HistoricalSectorService``；binding 未启用 / policy 不可用 →
  fail-closed 拒绝读）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from skills.data.unified_data.adapters.p3_persistence_writer import UpsertOutcome
from skills.data.unified_data.models.domain.sector_ranking import is_valid_trade_date

from .common import PolicyUnavailableError


class NamespaceViolation(Exception):
    """尝试操作目标集合外（G3-S-009 / G2-D-004 → 退出码 2）。"""


class BindingDisabledError(Exception):
    """生产读 binding 未启用（fail-closed，G4-R-006 / G4-V-104）。"""


# ---------------------------------------------------------------------------
# ProdRankingWriter（DESIGN §3.6.1）
# ---------------------------------------------------------------------------


class ProdRankingWriter:
    """真实 pymongo 生产写入器（仅限 ``03_data_ud_sector_ranking_daily``）。

    与 :class:`HistoricalRankingWriter` 平行但允许真实 db；每个操作先过
    :meth:`_assert_namespace`（拒绝目标集合外的一切读写）。写入只应在
    ``BuildOutcome.status == \"complete\"`` 时发生（G3-B-012 由调用方保证）。
    """

    COLLECTION = "03_data_ud_sector_ranking_daily"
    UNIQUE_KEY: frozenset[str] = frozenset({"dataset", "trade_date", "sector_code"})

    def __init__(self, db: Any) -> None:
        if db is None:
            raise TypeError("ProdRankingWriter requires a db (pymongo / mongomock)")
        self._db = db

    def _assert_namespace(self, collection: str | None) -> None:
        if collection is not None and collection != self.COLLECTION:
            raise NamespaceViolation(
                f"collection {collection!r} is outside the allowlist "
                f"(only {self.COLLECTION})"
            )

    def get(
        self,
        collection: str | None = None,
        filter: Mapping[str, Any] | None = None,
    ) -> list[dict]:
        """读取 ranking 行，返回 ``list[dict]``（与冻结 writer 同形态）。"""
        self._assert_namespace(collection)
        coll = self._db[collection or self.COLLECTION]
        cursor = coll.find(dict(filter or {}))
        return [dict(doc) for doc in cursor]

    def upsert(
        self,
        records: Sequence[Mapping[str, Any]],
        unique_key: Iterable[str] | None = None,
    ) -> UpsertOutcome:
        """按唯一键 upsert（update_one upsert=True）；单条失败捕获进 outcome。"""
        self._assert_namespace(None)
        outcome = UpsertOutcome()
        records_list = list(records)
        if not records_list:
            return outcome

        unique_key_set = set(unique_key) if unique_key is not None else set(self.UNIQUE_KEY)
        if not unique_key_set:
            outcome.failed = len(records_list)
            outcome.errors.append("unique_key must be a non-empty set of field names")
            return outcome

        coll = self._db[self.COLLECTION]
        for record in records_list:
            try:
                if not isinstance(record, Mapping):
                    raise TypeError(
                        f"record must be a Mapping, got {type(record).__name__}"
                    )
                key_filter: dict[str, Any] = {}
                missing: list[str] = []
                for key in unique_key_set:
                    if key in record:
                        key_filter[key] = record[key]
                    else:
                        missing.append(key)
                if missing:
                    raise ValueError(
                        f"record missing unique-key field(s): {sorted(missing)}"
                    )
                coll.update_one(key_filter, {"$set": dict(record)}, upsert=True)
            except Exception as exc:  # noqa: BLE001 — capture into outcome
                outcome.failed += 1
                outcome.failed_keys.append(
                    {k: record.get(k) for k in unique_key_set if k in record}
                )
                outcome.errors.append(f"{type(exc).__name__}: {exc}")
                continue
            outcome.persisted += 1
        return outcome

    def count(self, filter: Mapping[str, Any]) -> int:
        """写后读回行数统计。"""
        self._assert_namespace(None)
        coll = self._db[self.COLLECTION]
        return int(coll.count_documents(dict(filter)))

    def estimated_document_count(self) -> int:
        """越权扫描：目标集合行数快照。"""
        self._assert_namespace(None)
        return int(self._db[self.COLLECTION].estimated_document_count())


# ---------------------------------------------------------------------------
# BindingState（DESIGN §3.7.1）
# ---------------------------------------------------------------------------

BINDING_FILE = "binding_state.json"
BINDING_CAPABILITY = "sector.ranking_history"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_binding(report_dir: str) -> dict[str, Any]:
    """读取 binding 状态；缺失 → ``{"enabled": False}``（fail-closed）。"""
    path = Path(report_dir) / BINDING_FILE
    if not path.exists():
        return {"enabled": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"enabled": False}
    if not isinstance(data, dict):
        return {"enabled": False}
    return data


def write_binding(report_dir: str, enabled: bool) -> dict[str, Any]:
    """写 binding 状态文件并返回完整记录（幂等；previous 记录旧值）。"""
    previous = load_binding(report_dir)
    payload = {
        "capability": BINDING_CAPABILITY,
        "enabled": bool(enabled),
        "gate": 4,
        "updated_at": _now_iso(),
        "previous": previous.get("enabled"),
    }
    path = Path(report_dir) / BINDING_FILE
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# ProdRankingReader（DESIGN §3.7.2 / SPEC G4-P-001~010）
# ---------------------------------------------------------------------------


class ProdRankingReader:
    """生产只读路径：与冻结 writer ``.get()`` 同形态，可注入冻结 service。

    fail-closed（DESIGN §3.7.2）：

    * binding 未启用 → :class:`BindingDisabledError`（G4-R-006 / G4-V-104）。
    * ``policy=None``（无受控交易日历证据）→ :class:`PolicyUnavailableError`
      （G4-P-008/009，不猜测交易日状态）。
    * filter 强制含 ``dataset``（G4-V-005：跨 dataset 混读拒绝）。
    * filter 中 ``trade_date`` 经注入 ``CompletedSessionPolicy`` 判定；
      FUTURE / TODAY_UNCLOSED → ``ValueError``（G4-P-004/005，Category 1
      语义，由 policy 抛出——不是修改冻结 service）。
    """

    COLLECTION = "03_data_ud_sector_ranking_daily"

    def __init__(
        self,
        db: Any,
        *,
        binding: Callable[[], bool],
        policy: Any | None = None,
    ) -> None:
        self._db = db
        self._binding = binding
        self._policy = policy

    def _assert_namespace(self, collection: str | None) -> None:
        if collection is not None and collection != self.COLLECTION:
            raise NamespaceViolation(
                f"collection {collection!r} is outside the allowlist "
                f"(only {self.COLLECTION})"
            )

    def get(
        self,
        collection: str | None = None,
        filter: Mapping[str, Any] | None = None,
    ) -> list[dict]:
        """读取物化行（``list[dict]``），带 binding / policy / dataset 门禁。"""
        if not self._binding():
            raise BindingDisabledError(
                "sector.ranking_history production read binding is disabled"
            )
        if self._policy is None:
            raise PolicyUnavailableError(
                "trade-calendar evidence unavailable; fail-closed (G4-P-008/009)"
            )
        self._assert_namespace(collection)
        f = dict(filter or {})
        if "dataset" not in f:
            raise ValueError(
                "reader requires a dataset filter; cross-dataset reads are "
                "refused (G4-V-005)"
            )
        trade_date = f.get("trade_date")
        if trade_date is not None:
            # FUTURE / TODAY_UNCLOSED → ValueError（G4-P-004/005）
            self._policy.classify(str(trade_date))
        coll = self._db[collection or self.COLLECTION]
        cursor = coll.find(f)
        return [dict(doc) for doc in cursor]


__all__ = [
    "BINDING_CAPABILITY",
    "BINDING_FILE",
    "BindingDisabledError",
    "NamespaceViolation",
    "ProdRankingReader",
    "ProdRankingWriter",
    "load_binding",
    "write_binding",
]
