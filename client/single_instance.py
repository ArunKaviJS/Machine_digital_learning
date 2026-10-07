"""Single-instance lock (SKILL §20): a lock file holding the owner's PID.

Stale locks (owner process no longer running) are reclaimed automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

import psutil


class SingleInstanceLock:
    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self._acquired = False

    def acquire(self) -> bool:
        """True if this process now owns the lock; False if another is running."""
        if self.lock_path.exists():
            try:
                owner_pid = int(self.lock_path.read_text().strip())
            except (ValueError, OSError):
                owner_pid = None
            if owner_pid is not None and owner_pid != os.getpid() and psutil.pid_exists(owner_pid):
                return False
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(str(os.getpid()))
        self._acquired = True
        return True

    def release(self) -> None:
        if self._acquired and self.lock_path.exists():
            try:
                if int(self.lock_path.read_text().strip()) == os.getpid():
                    self.lock_path.unlink()
            except (ValueError, OSError):
                pass
        self._acquired = False
