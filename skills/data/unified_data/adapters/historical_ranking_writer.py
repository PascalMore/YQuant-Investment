"""HistoricalRankingWriter — 注入式 mongomock repository（RFC-03-015 T3）。

仅操作 ``03_data_ud_sector_ranking_daily``（新 namespace），业务唯一键
``{dataset, trade_date, sector_code}``（SPEC H-019 ~ H-020）。与
:class:`~skills.data.unified_data.adapters.p3_persistence_writer.P3PersistenceWriter`
平行但独立：不修改 P3 writer，接受外部传入的 mongomock / FakeDatabase db。

离线 guard（RFC §6.1 / DESIGN §3.3.2）：

* 拒绝真实 ``pymongo`` 连接 —— 构造函数只接受 mongomock / FakeDatabase。
* 不做真实 DDL / 索引创建（Gate-2 执行）。

写入守则（RFC §5.6.3 冻结表 / DESIGN §3.3.2）：本 writer 是哑 repository，
**只应在 :class:`BuildOutcome.status == "complete"` 时被调用写入正式
ranking**；incomplete / empty 不得物化。该不变式由调用方（Gate-3
backfill 或测试流程）负责，本模块在 docstring 与测试中显式声明。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .p3_persistence_writer import UpsertOutcome


class HistoricalRankingWriter:
    """``03_data_ud_sector_ranking_daily`` 的注入式 mongomock repository。

    Args:
        mongo_db: mongomock ``MongoClient().get_database(...)``（或同
            ``db[name]`` 协议的 FakeDatabase shim）。真实 ``pymongo``
            连接被 :meth:`_assert_fake_db` 拒绝。
    """

    COLLECTION = "03_data_ud_sector_ranking_daily"
    UNIQUE_KEY: frozenset[str] = frozenset({"dataset", "trade_date", "sector_code"})

    def __init__(self, mongo_db: Any) -> None:
        self._db = mongo_db
        self._assert_fake_db(mongo_db)

    @property
    def db(self) -> Any:
        """The injected fake database handle (test/consumer inspection)."""
        return self._db

    # ------------------------------------------------------------------
    # Internal guard — refuse a real pymongo connection
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_fake_db(mongo_db: Any) -> None:
        """Reject real pymongo Database objects (mirrors P3PersistenceWriter)."""
        if mongo_db is None:
            raise TypeError(
                "HistoricalRankingWriter requires a mongo_db (mongomock / FakeDatabase)."
            )
        cls_name = type(mongo_db).__name__
        module = type(mongo_db).__module__ or ""
        if "pymongo" in module and "mongomock" not in module:
            raise TypeError(
                "HistoricalRankingWriter refuses real pymongo connections "
                "(RFC-03-015 offline guard). Pass a mongomock or FakeDatabase."
            )
        if cls_name == "Database" and "mongomock" not in module:
            raise TypeError(
                "HistoricalRankingWriter refuses real pymongo connections "
                "(RFC-03-015 offline guard)."
            )

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def get(
        self,
        collection: str | None = None,
        filter: Mapping[str, Any] | None = None,
    ) -> list[dict]:
        """读取 ranking 行，返回 ``list[dict]``。

        Args:
            collection: 集合名；``None`` 默认本 writer 的
                :attr:`COLLECTION`。
            filter: Mongo filter；空 filter 返回全部行。

        Returns:
            匹配 ``filter`` 的行（浅拷贝 dict），无匹配时 ``[]``。
        """
        coll = self._db[collection or self.COLLECTION]
        cursor = coll.find(dict(filter or {}))
        return [dict(doc) for doc in cursor]

    # ------------------------------------------------------------------
    # Write path — only for complete builds (see module docstring)
    # ------------------------------------------------------------------

    def upsert(
        self,
        records: Sequence[Mapping[str, Any]],
        unique_key: Iterable[str] | None = None,
    ) -> UpsertOutcome:
        """按唯一键 upsert ranking 行。

        默认按 :attr:`UNIQUE_KEY`（``{dataset, trade_date, sector_code}``）；
        相同唯一键的行被覆盖更新（``updated_at`` 刷新，SPEC H-020）。
        单条失败被捕获进 :class:`UpsertOutcome`，整个调用不抛异常。

        Args:
            records: 9 字段行字典序列。
            unique_key: 唯一键字段集合；``None`` 使用
                :attr:`UNIQUE_KEY`。

        Returns:
            :class:`UpsertOutcome`（复用 ``P3PersistenceWriter.UpsertOutcome``）。
        """
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

    # ------------------------------------------------------------------
    # Stop / rollback helper
    # ------------------------------------------------------------------

    def delete(self, filter: Mapping[str, Any]) -> int:
        """按 ``filter`` 删除行，返回删除数。空 filter 被拒绝。"""
        if not filter:
            raise ValueError("delete requires a non-empty filter to prevent full wipes")
        coll = self._db[self.COLLECTION]
        result = coll.delete_many(dict(filter))
        if hasattr(result, "deleted_count"):
            return int(result.deleted_count)
        if isinstance(result, int):
            return int(result)
        return 0


__all__ = ["HistoricalRankingWriter"]
