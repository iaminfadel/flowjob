"""Unit tests for pipeline.watch_loop — timing/stop/skip with fake clocks."""

from src.config import FlowJobConfig, WatchConfig
from src.pipeline.watch_loop import run_watch_loop


class FakeEvent:
    """threading.Event stand-in with controllable wait()."""

    def __init__(self):
        self.set_flag = False

    def is_set(self):
        return self.set_flag

    def set(self):
        self.set_flag = True

    def clear(self):
        self.set_flag = False

    def wait(self, timeout=None):
        return self.set_flag  # if set during wait -> skip


def test_loop_runs_until_stop():
    cfg = FlowJobConfig(watch=WatchConfig(min_wait_minutes=1, max_wait_minutes=2))
    calls = []
    sleeps = []

    def cycle():
        calls.append(1)
        return len(calls)

    def should_stop():
        return len(calls) >= 2

    n = run_watch_loop(cfg, cycle, should_stop=should_stop, sleep_fn=sleeps.append)
    assert n == 2
    assert len(calls) == 2
    # one jittered sleep happened between the two cycles, within config bounds (seconds)
    assert len(sleeps) == 1
    for s in sleeps:
        assert 60 <= s <= 120


def test_skip_event_short_circuits_the_wait():
    cfg = FlowJobConfig()
    calls = []
    sleeps = []
    ev = FakeEvent()

    def cycle():
        calls.append(1)
        if len(calls) == 1:
            ev.set()  # user pressed "run now" during the wait
        return None

    run_watch_loop(
        cfg,
        cycle,
        should_stop=lambda: len(calls) >= 2,
        skip_event=ev,
        sleep_fn=sleeps.append,
    )
    assert len(calls) == 2
    assert all(s == 0.0 for s in sleeps), "no real sleep when skipped"


def test_on_cycle_receives_cycle_result():
    cfg = FlowJobConfig()
    seen = []

    run_watch_loop(
        cfg,
        lambda: "summary",
        on_cycle=seen.append,
        should_stop=lambda: True,
    )
    assert seen == ["summary"]


def test_before_wait_can_adjust_interval():
    cfg = FlowJobConfig(watch=WatchConfig(min_wait_minutes=10, max_wait_minutes=20))
    calls = []
    sleeps = []
    observed = {}
    stop_after = {"n": 2}

    def before_wait(minutes):
        observed["m"] = minutes
        return 0.001  # shrink to ~0ms

    def should_stop():
        return len(calls) >= stop_after["n"]

    run_watch_loop(
        cfg,
        lambda: calls.append(1) or None,
        should_stop=should_stop,
        before_wait=before_wait,
        sleep_fn=sleeps.append,
    )
    # before_wait saw the jittered interval (within config bounds) and shrank it
    assert 10 <= observed["m"] <= 20
    assert sleeps == [0.001 * 60], "sleep used the adjusted interval"


def test_lock_not_owned_by_loop():
    """The loop never touches the watch lock — host owns it (documented contract)."""
    import inspect

    from src.pipeline import watch_loop

    src = inspect.getsource(watch_loop)
    assert "acquire_watch_lock" not in src
