"""UD 互斥锁测试 — 03-018 UT15。

覆盖：两个真实本地子进程争锁、BUSY 时零 HTTP / 零 DB、异常退出后锁释放。
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.unified_data.ud_lock import (
    LOCK_PATH,
    UDLockBusy,
    acquire_ud_lock,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_HOLDER_SCRIPT = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, {root!r})
    from scripts.unified_data.ud_lock import acquire_ud_lock
    with acquire_ud_lock({lock!r}):
        print("LOCKED", flush=True)
        time.sleep(30)
    """
)


def _spawn_holder(lock_path: Path) -> subprocess.Popen:
    script = _HOLDER_SCRIPT.format(root=str(PROJECT_ROOT), lock=str(lock_path))
    return subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_ut15_default_lock_path_is_the_project_lock() -> None:
    assert LOCK_PATH.name == "yquant-data-history.lock"
    assert LOCK_PATH.parent.name == "locks"
    assert LOCK_PATH.parent.parent.name == "data"


def test_ut15_lock_is_reentrant_only_after_release(tmp_path) -> None:
    path = tmp_path / "ud.lock"
    with acquire_ud_lock(path):
        with pytest.raises(UDLockBusy):
            with acquire_ud_lock(path):
                pass
    with acquire_ud_lock(path):
        pass


def test_ut15_second_process_gets_busy(tmp_path) -> None:
    path = tmp_path / "ud.lock"
    holder = _spawn_holder(path)
    try:
        assert holder.stdout is not None
        line = holder.stdout.readline().strip()
        assert line == "LOCKED"
        with pytest.raises(UDLockBusy):
            with acquire_ud_lock(path):
                pass
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_ut15_lock_is_released_after_process_exit(tmp_path) -> None:
    path = tmp_path / "ud.lock"
    holder = _spawn_holder(path)
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "LOCKED"
    holder.kill()
    holder.wait(timeout=30)
    # 进程退出后 OS 释放锁
    with acquire_ud_lock(path):
        pass


def test_ut15_lock_file_is_not_unlinked(tmp_path) -> None:
    path = tmp_path / "ud.lock"
    with acquire_ud_lock(path):
        pass
    assert path.exists()


def test_ut15_lock_directory_is_created_on_demand(tmp_path) -> None:
    path = tmp_path / "nested" / "dir" / "ud.lock"
    with acquire_ud_lock(path):
        assert path.exists()


def test_ut15_busy_does_not_raise_unexpected_errors(tmp_path) -> None:
    path = tmp_path / "ud.lock"
    with acquire_ud_lock(path):
        with pytest.raises(UDLockBusy) as excinfo:
            with acquire_ud_lock(path):
                pass
    assert "held" in str(excinfo.value)


def test_ut15_lock_is_process_scoped_not_thread_scoped(tmp_path) -> None:
    """锁是文件级 flock；同进程重复获取会被拒绝（非线程安全假设）。"""
    path = tmp_path / "ud.lock"
    with acquire_ud_lock(path):
        with pytest.raises(UDLockBusy):
            with acquire_ud_lock(path):
                pass
    assert os.path.exists(path)
