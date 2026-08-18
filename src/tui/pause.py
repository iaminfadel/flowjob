"""Application-form pause hosting.

The applicator's wait_fn seam blocks inside the Easy Apply modal while the
browser stays open; the TUI raises a pause modal so the boss can fill the
field, click Continue, and let the worker resume.
"""

from __future__ import annotations

import queue
import threading

from textual.message import Message


class PauseRequested(Message):
    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt


class PauseManager:
    def __init__(self, app) -> None:
        self.app = app
        self._queue: queue.Queue[None] = queue.Queue()
        self._pending: list[str] = []
        self._lock = threading.Lock()

    def request(self, prompt: str) -> None:
        """Blocking call, runs on the pipeline worker thread."""
        with self._lock:
            self._pending.append(prompt)
        self.app.post_message(PauseRequested(prompt))
        self._queue.get()

    def continue_(self, prompt: str) -> bool:
        """Dismiss a pending pause from the UI thread. False if none pending."""
        with self._lock:
            if prompt not in self._pending:
                return False
            self._pending.remove(prompt)
        self._queue.put(None)
        return True

    def pending(self) -> list[str]:
        with self._lock:
            return list(self._pending)
