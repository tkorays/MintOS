"""Tests for core/lock.py: PID file locking."""
from __future__ import annotations

import os

from mos.core.lock import acquire_lock, release_lock


def test_acquire_first_time(tmp_path):
    pid_path = tmp_path / "watch.pid"
    assert acquire_lock(pid_path) is True
    assert pid_path.exists()
    assert pid_path.read_text().strip() == str(os.getpid())


def test_release_removes_pid_file(tmp_path):
    pid_path = tmp_path / "watch.pid"
    acquire_lock(pid_path)
    release_lock(pid_path)
    assert not pid_path.exists()


def test_second_acquire_fails_while_live(tmp_path, monkeypatch):
    """Simulate another process holding the lock."""
    pid_path = tmp_path / "watch.pid"

    # 写入一个假的 PID（我们自己的 PID，但 monkeypatch os.kill 让它返回 "活着"）
    fake_pid = os.getpid()
    pid_path.write_text(str(fake_pid))

    # 让 os.kill(pid, 0) 不抛异常 → 进程存活
    monkeypatch.setattr(os, "kill", lambda _pid, _sig: None)

    assert acquire_lock(pid_path) is False


def test_stale_pid_is_overwritten(tmp_path, monkeypatch):
    """Stale PID file (process no longer exists) should be overwritten."""
    pid_path = tmp_path / "watch.pid"

    # 写入一个假的 PID
    fake_pid = 999999
    pid_path.write_text(str(fake_pid))

    # 让 os.kill(pid, 0) 抛 ProcessLookupError → 进程已死
    def fake_kill(_pid, _sig):
        raise ProcessLookupError()

    monkeypatch.setattr(os, "kill", fake_kill)

    assert acquire_lock(pid_path) is True  # stale, overwritten
    assert pid_path.read_text().strip() == str(os.getpid())


def test_release_only_if_owner(tmp_path, monkeypatch):
    """release_lock should not delete a PID file owned by another process."""
    pid_path = tmp_path / "watch.pid"

    # 写入另一个进程的 PID
    other_pid = 999999
    pid_path.write_text(str(other_pid))

    release_lock(pid_path)
    assert pid_path.exists()  # 不删除，因为不是我们的


def test_release_no_file_is_safe(tmp_path):
    """Calling release_lock when no PID file exists should not raise."""
    pid_path = tmp_path / "watch.pid"
    release_lock(pid_path)  # should not raise
