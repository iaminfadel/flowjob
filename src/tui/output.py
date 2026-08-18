"""Thread-safe stdout capture for pipeline workers running inside the TUI.

The pipeline reports progress exclusively via print(); hosting it in-process
means redirecting sys.stdout to a pump that forwards complete lines to the
app's message loop (Textual post_message is thread-safe).
"""

from __future__ import annotations

import sys
import threading


class StdoutCapture:
    """Context manager swapping sys.stdout with a line-pumping stream.

    Lines (and partial writes) are forwarded to `pump(line)` exactly as they
    become complete, so the UI tails progress live.
    """

    def __init__(self, pump):
        self._pump = pump
        self._buffer = ""
        self._lock = threading.Lock()
        self._old_stdout = None

    def write(self, text: str) -> int:
        with self._lock:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self._pump(line.rstrip("\r"))
        return len(text)

    def flush(self) -> None:
        pass

    def __enter__(self):
        self._old_stdout = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, *exc):
        if self._buffer.strip():
            self._pump(self._buffer.rstrip("\r"))
        self._buffer = ""
        sys.stdout = self._old_stdout
        return False