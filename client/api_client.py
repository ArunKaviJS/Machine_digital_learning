"""HTTP client to the backend (SKILL §20): calls run off the UI thread.

M11 only needs simple fire-and-forget calls for the context menu; the
richer request/response + WebSocket wiring for panels is M12.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger("arun.client.api")


class _Worker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, base_url: str, token: str, method: str, path: str, kwargs: dict):
        super().__init__()
        self.base_url = base_url
        self.token = token
        self.method = method
        self.path = path
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            headers = {"X-Arun-Token": self.token}
            resp = httpx.request(
                self.method, f"{self.base_url}{self.path}",
                headers=headers, timeout=10.0, **self.kwargs,
            )
            resp.raise_for_status()
            self.finished.emit(resp.json() if resp.content else {})
        except Exception as exc:  # noqa: BLE001 - surfaced via signal, never crashes the UI thread
            self.failed.emit(str(exc))


class ApiClient(QObject):
    """base_url + token from config; each .call() runs on its own QThread."""

    def __init__(self, config: dict[str, Any]):
        super().__init__()
        self.base_url = f"http://{config['backendHost']}:{config['backendPort']}"
        self.token = config.get("apiToken", "")
        # (thread, worker) pairs: the worker must be referenced too — PyQt does
        # not keep a QObject alive through `thread.started.connect(worker.run)`,
        # so a worker held only by a local variable is garbage-collected when
        # call() returns and the request silently never runs.
        self._jobs: list[tuple[QThread, _Worker]] = []

    def call(self, method: str, path: str, on_done=None, on_error=None, **kwargs) -> None:
        thread = QThread()
        worker = _Worker(self.base_url, self.token, method, path, kwargs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        job = (thread, worker)

        def _cleanup(*_a):
            thread.quit()
            thread.wait()
            if job in self._jobs:
                self._jobs.remove(job)

        worker.finished.connect(lambda result: (on_done(result) if on_done else None))
        worker.failed.connect(lambda err: (logger.warning("api call failed: %s %s: %s",
                                                           method, path, err),
                                           on_error(err) if on_error else None))
        worker.finished.connect(_cleanup)
        worker.failed.connect(_cleanup)
        self._jobs.append(job)
        thread.start()
