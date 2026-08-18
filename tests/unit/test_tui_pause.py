import threading
import time

from src.tui.pause import PauseManager, PauseRequested


class FakeApp:
    def __init__(self):
        self.posted = []

    def post_message(self, message):
        self.posted.append(message)


def test_request_blocks_until_continue():
    app = FakeApp()
    manager = PauseManager(app)

    result = {}
    def worker():
        manager.request("fill the field")
        result["unblocked"] = True

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.1)

    assert thread.is_alive(), "request() must block the worker"
    assert app.posted and isinstance(app.posted[0], PauseRequested)
    assert app.posted[0].prompt == "fill the field"
    assert manager.pending() == ["fill the field"]

    assert manager.continue_("fill the field") is True
    thread.join(timeout=2)
    assert result.get("unblocked") is True
    assert manager.pending() == []


def test_continue_missing_prompt_returns_false():
    app = FakeApp()
    manager = PauseManager(app)
    assert manager.continue_("nope") is False
    assert manager.pending() == []


def test_multiple_pauses_resolve_in_order():
    app = FakeApp()
    manager = PauseManager(app)

    events = []
    def worker_a():
        manager.request("first")
        events.append("a")

    def worker_b():
        manager.request("second")
        events.append("b")

    ta = threading.Thread(target=worker_a)
    tb = threading.Thread(target=worker_b)
    ta.start()
    tb.start()
    time.sleep(0.1)

    assert manager.pending() == ["first", "second"]
    assert manager.continue_("first") is True
    ta.join(timeout=2)
    assert events == ["a"]
    assert manager.pending() == ["second"]
    assert manager.continue_("second") is True
    tb.join(timeout=2)
    assert events == ["a", "b"]