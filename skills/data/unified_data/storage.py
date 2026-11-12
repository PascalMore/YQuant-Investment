"""UD 双库边界 — 03-018 §3.1 / §4。

UD 自有对象（物化、缓存、审计、质量汇总、ranking、历史与检查点）只允许
落在业务库 ``yquant-data``；TA-CN 原始读源固定 ``tradingagents`` 只读。

认证来源不变：本模块不拼 URI、不改 ``MONGODB_DATABASE``、不修改通用
``MongoReader`` 默认库。两个库必须来自**同一个** client 实例（同一连接、
同一认证来源）。

``assert_ud_database`` 只对**真实** ``pymongo.database.Database`` 检查
``name``；显式注入的 fake / mongomock 句柄继续跑离线历史测试，不把
``hasattr(name)`` 当成真实类型判定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: UD 自有数据的业务库（生产固定）。
UD_DATABASE = "yquant-data"

#: TA-CN 原始读源（只读）。
TA_CN_DATABASE = "tradingagents"


class UDDatabaseError(RuntimeError):
    """UD 库边界违规（库名不符 / 类型无法判定）。"""


@dataclass(frozen=True)
class UDDatabases:
    """UD 目标库与 TA-CN 只读源的两个句柄。

    Attributes:
        ud: ``yquant-data`` 库句柄（UD 自有对象的唯一目标）。
        ta_cn: ``tradingagents`` 库句柄（只读源）。
    """

    ud: Any
    ta_cn: Any


def _is_real_pymongo_database(db: Any) -> bool:
    """Return ``True`` when ``db`` is a genuine pymongo ``Database``.

    mongomock / 自造 fake 不满足该类型检查，因此不会触发库名 guard。
    """
    try:
        from pymongo.database import Database
    except Exception:  # pragma: no cover — pymongo 缺失时不误判
        return False
    return isinstance(db, Database)


def assert_ud_database(db: Any, *, expected: str = UD_DATABASE) -> None:
    """确保 ``db`` 是目标 UD 库；不匹配时 fail-fast 抛错。

    Args:
        db: 待校验的数据库句柄。
        expected: 期望的库名，默认 ``yquant-data``。

    Raises:
        UDDatabaseError: 真实 pymongo 库名与 ``expected`` 不符，或句柄为空。
    """
    if db is None:
        raise UDDatabaseError("database handle is required")
    if not _is_real_pymongo_database(db):
        # fake / mongomock：允许离线测试继续；不冒充真实类型判定。
        return
    name = getattr(db, "name", None)
    if name != expected:
        raise UDDatabaseError(
            f"expected database {expected!r}, got {name!r}"
        )


def select_databases(client: Any) -> UDDatabases:
    """从**同一个** client 派生 UD 目标库与 TA-CN 只读源。

    Args:
        client: 任意 ``client[database]`` 风格的 Mongo client
            （pymongo 或 mongomock）。

    Returns:
        :class:`UDDatabases`。

    Raises:
        UDDatabaseError: client 不支持按名取库。
    """
    try:
        ud = client[UD_DATABASE]
        ta_cn = client[TA_CN_DATABASE]
    except Exception as exc:  # noqa: BLE001 — 统一为边界错误
        raise UDDatabaseError(
            f"cannot select databases from client ({type(exc).__name__})"
        ) from exc
    assert_ud_database(ud)
    return UDDatabases(ud=ud, ta_cn=ta_cn)


def open_databases() -> UDDatabases:
    """复用既有合法连接选择规则打开两个库。

    延迟 import ``MongoReader``（避免包级导入触发 env 读取 / 连接），
    复用其原认证语义与原 ``authSource``；不拼新 URI、不改
    ``MongoReader._client``、不修改通用默认库。
    """
    from skills.data.data_interface.mongo_reader import MongoReader

    reader = MongoReader(database=TA_CN_DATABASE)
    return select_databases(reader.db.client)


__all__ = [
    "UD_DATABASE",
    "TA_CN_DATABASE",
    "UDDatabaseError",
    "UDDatabases",
    "assert_ud_database",
    "select_databases",
    "open_databases",
]
