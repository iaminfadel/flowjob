"""Shared fixture: point the watch lock at a tmp path so tests never collide
with a live CLI/TUI watcher (or each other)."""

import pytest


@pytest.fixture(autouse=True)
def isolated_watch_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWJOB_WATCH_LOCK", str(tmp_path / "watch.lock"))
    yield
