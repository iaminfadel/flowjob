"""Unit tests for the in-TUI approval gate (ApprovalManager)."""

import threading
import time

import pytest

from src.tui.approval import ApprovalManager, ApprovalRequested


class FakeApp:
    def __init__(self) -> None:
        self.messages = []

    def post_message(self, message) -> None:
        self.messages.append(message)


def request_in_thread(manager, job_id, results):
    def _run():
        results.append(manager.request(job_id))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def test_request_blocks_and_posts_message():
    app = FakeApp()
    manager = ApprovalManager(app)
    results = []

    t = request_in_thread(manager, "job-1", results)
    time.sleep(0.1)

    assert t.is_alive(), "request() must block the caller"
    assert manager.is_pending("job-1")
    assert manager.pending_ids() == ["job-1"]
    assert isinstance(app.messages[0], ApprovalRequested)
    assert app.messages[0].job_id == "job-1"

    assert manager.resolve("job-1", True)
    t.join(timeout=2)
    assert results == [True]
    assert not manager.is_pending("job-1")


def test_resolve_reject_returns_false():
    app = FakeApp()
    manager = ApprovalManager(app)
    results = []

    t = request_in_thread(manager, "job-1", results)
    time.sleep(0.1)
    assert manager.resolve("job-1", False)
    t.join(timeout=2)
    assert results == [False]


def test_resolve_without_pending_request_returns_false():
    manager = ApprovalManager(FakeApp())
    assert manager.resolve("nope", True) is False


def test_two_requests_resolve_independently():
    app = FakeApp()
    manager = ApprovalManager(app)
    results = []

    t1 = request_in_thread(manager, "job-a", results)
    t2 = request_in_thread(manager, "job-b", results)
    time.sleep(0.1)

    assert manager.pending_ids() == ["job-a", "job-b"]
    assert manager.resolve("job-b", True)
    assert manager.resolve("job-a", False)
    t1.join(timeout=2)
    t2.join(timeout=2)
    assert sorted(results) == [False, True]