"""In-TUI approval gate hosting.

The pipeline worker calls ApprovalManager.request(job_id) (via the
approval_fn seam) and blocks; the app raises an approval modal; the boss
answers; resolve() unblocks the worker. Pipeline semantics unchanged.
"""

from __future__ import annotations

import queue
import threading

from textual import events
from textual.message import Message


class ApprovalRequested(Message):
    def __init__(self, job_id: str) -> None:
        super().__init__()
        self.job_id = job_id


class ApprovalManager:
    def __init__(self, app) -> None:
        self.app = app
        self._pending: dict[str, queue.Queue[bool]] = {}
        self._lock = threading.Lock()

    def request(self, job_id: str) -> bool:
        """Blocking call, runs on the pipeline worker thread."""
        q: queue.Queue[bool] = queue.Queue(maxsize=1)
        with self._lock:
            self._pending[job_id] = q
        self.app.post_message(ApprovalRequested(job_id))
        return q.get()

    def resolve(self, job_id: str, approve: bool) -> bool:
        """Answer a pending request from the UI thread. False if none pending."""
        with self._lock:
            q = self._pending.pop(job_id, None)
        if q is None:
            return False
        q.put(approve)
        return True

    def is_pending(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._pending

    def pending_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending.keys())