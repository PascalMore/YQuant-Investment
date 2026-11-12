"""项目级 UD 互斥锁 — 03-018 §7.3。

单一 ``flock`` 锁文件 ``data/locks/yquant-data-history.lock``，供迁移 /
历史 apply / audit smoke / sector 写入口共享。

语义：

* ``fcntl.flock(fd, LOCK_EX | LOCK_NB)`` — 拿不到立即抛
  :class:`UDLockBusy`（退出码 30），**零 HTTP / 零 DB**。
* 文件**不 unlink**（避免 inode 竞态）；异常 / 进程退出由 OS 释放。
* 无租约、无分布式协调、无后台服务。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

#: 项目根（本文件位于 ``<root>/scripts/unified_data/ud_lock.py``）。
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 唯一锁文件路径。
LOCK_PATH = PROJECT_ROOT / "data" / "locks" / "yquant-data-history.lock"


class UDLockBusy(RuntimeError):
    """锁已被占用（BUSY）。

    捕获方必须以退出码 30 结束，且不得发出任何 HTTP / DB 请求。
    """


@contextmanager
def acquire_ud_lock(path: Path | str | None = None) -> Iterator[Path]:
    """获取项目级 UD 互斥锁。

    Args:
        path: 可选锁文件路径（测试用）；默认 :data:`LOCK_PATH`。

    Yields:
        锁文件路径。

    Raises:
        UDLockBusy: 锁已被其他进程占用。
    """
    lock_path = Path(path) if path is not None else LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise UDLockBusy(
                "ud lock is held by another process"
            ) from exc
        try:
            yield lock_path
        finally:
            # 释放锁但**不** unlink 文件。
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


__all__ = ["LOCK_PATH", "PROJECT_ROOT", "UDLockBusy", "acquire_ud_lock"]
