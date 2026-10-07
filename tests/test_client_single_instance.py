"""single_instance.py: lock-file guard, stale-lock reclamation (SKILL §20)."""

from __future__ import annotations

import os
from pathlib import Path

from client.single_instance import SingleInstanceLock


def test_acquire_creates_lock_with_own_pid(tmp_path: Path):
    lock = SingleInstanceLock(tmp_path / "arun.lock")
    assert lock.acquire() is True
    assert int((tmp_path / "arun.lock").read_text()) == os.getpid()


def test_second_acquire_in_same_process_still_succeeds(tmp_path: Path):
    path = tmp_path / "arun.lock"
    lock1 = SingleInstanceLock(path)
    lock1.acquire()
    lock2 = SingleInstanceLock(path)
    assert lock2.acquire() is True  # same pid owns it


def test_release_removes_lock_file(tmp_path: Path):
    path = tmp_path / "arun.lock"
    lock = SingleInstanceLock(path)
    lock.acquire()
    lock.release()
    assert not path.exists()


def test_stale_lock_from_dead_pid_is_reclaimed(tmp_path: Path):
    path = tmp_path / "arun.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("999999999")  # a pid that (almost certainly) doesn't exist
    lock = SingleInstanceLock(path)
    assert lock.acquire() is True
    assert int(path.read_text()) == os.getpid()


def test_live_other_process_blocks_acquire(tmp_path: Path, monkeypatch):
    path = tmp_path / "arun.lock"
    path.write_text("4321")

    import client.single_instance as mod
    monkeypatch.setattr(mod.psutil, "pid_exists", lambda pid: pid == 4321)

    lock = SingleInstanceLock(path)
    assert lock.acquire() is False
