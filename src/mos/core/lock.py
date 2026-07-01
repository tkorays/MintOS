"""Single-instance lock via a PID file.

The lock is advisory: ``acquire_lock`` writes the current PID and refuses if a
live process is already recorded. Stale PID files (where ``os.kill(pid, 0)``
raises ``ProcessLookupError``) are overwritten so a crashed process can be
restarted.

This is a generic utility that can be used by any plugin or component that
needs to ensure only one instance is running at a time.
"""
from __future__ import annotations

import os
from pathlib import Path


def acquire_lock(pid_path: Path) -> bool:
    """Try to acquire the lock.

    Returns ``True`` if acquired (PID file written), ``False`` if another
    live process already holds the lock.
    """
    if pid_path.exists():
        try:
            existing = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(existing, 0)  # 仅检测存活，不杀
            return False  # 活的
        except (ProcessLookupError, ValueError, OverflowError, OSError):
            pass  # stale / 不可读 / PID 越界，覆盖
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock(pid_path: Path) -> None:
    """Release the lock if (and only if) we still own it."""
    try:
        if pid_path.exists() and pid_path.read_text(encoding="utf-8").strip() == str(
            os.getpid()
        ):
            pid_path.unlink()
    except OSError:
        pass
