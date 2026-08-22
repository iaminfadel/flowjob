"""Watch-loop hosting inside the TUI.

One worker thread runs pipeline cycles with stdout capture, a jittered
countdown, per-cycle summary, and the watch lockfile. Manual start / graceful
stop / restart; never auto-starts on launch.

The loop discipline (jitter, stop, skip) lives in pipeline.watch_loop; this
module supplies only TUI-specific callbacks.
"""

from __future__ import annotations

import threading

from textual.message import Message

from src.tui.queries import state_counts, spend_summary


class WatchOutput(Message):
    def __init__(self, line: str) -> None:
        super().__init__()
        self.line = line


class WatchStateChanged(Message):
    def __init__(self, state: str, detail: str = "") -> None:
        super().__init__()
        self.state = state  # idle | running | countdown | error
        self.detail = detail


class CycleSummary(Message):
    def __init__(self, duration_s: float, counts: dict, spend_delta: float, cost: float, jobs_applied: int) -> None:
        super().__init__()
        self.duration_s = duration_s
        self.counts = counts
        self.spend_delta = spend_delta
        self.cost = cost
        self.jobs_applied = jobs_applied


class WatchManager:
    def __init__(self, app, approval_manager, agents=None, wait_fn=None) -> None:
        self.app = app
        self.approval = approval_manager
        self._wait_fn = wait_fn
        self._agent_map = agents
        self._stop = threading.Event()
        self._skip = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = "idle"
        self._detail = ""
        self._lock = threading.Lock()
        self._spend_before = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def detail(self) -> str:
        return self._detail

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.is_running():
            return False
        self._stop.clear()
        self._skip.clear()
        self._thread = threading.Thread(
            target=self._run, name="watch-loop", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        self._skip.set()

    def run_now(self) -> None:
        self._skip.set()

    def _set_state(self, state: str, detail: str = "") -> None:
        self._state = state
        self._detail = detail
        self.app.post_message(WatchStateChanged(state, detail))

    def _pump(self, line: str) -> None:
        self.app.post_message(WatchOutput(line))

    def _get_agents(self):
        if self._agent_map is None:
            from src.cli import build_agents

            self._agent_map = build_agents()
        return self._agent_map

    def _run_one_cycle(self):
        from src.pipeline.orchestrator import run_pipeline
        from src.tui.output import StdoutCapture

        self._spend_before = spend_summary()["cost_usd"]
        with StdoutCapture(self._pump):
            return run_pipeline(
                agents=self._get_agents(),
                approval_fn=self.approval.request,
                wait_fn=self._wait_fn,
            )

    def _run(self) -> None:
        from src.config import load_config
        from src.pipeline.orchestrator import SessionHealthError
        from src.pipeline.watch_loop import run_watch_loop
        from src.pipeline.watch_lock import acquire_watch_lock, WatchLockHeldError

        try:
            cfg = load_config("flowjob.yaml")

            def on_cycle(summary) -> None:
                spend_after = spend_summary()["cost_usd"]
                counts = state_counts()
                self._set_state("running")
                self.app.post_message(
                    CycleSummary(
                        duration_s=summary.duration_s,
                        counts=counts,
                        spend_delta=spend_after - self._spend_before,
                        cost=spend_after,
                        jobs_applied=summary.jobs_applied,
                    )
                )

            def before_wait(interval_minutes: float) -> float:
                # Show the TUI countdown for the wait the loop is about to do.
                self._set_state("countdown", f"{interval_minutes:.0f}")
                return interval_minutes

            with acquire_watch_lock():
                self._set_state("running")
                run_watch_loop(
                    cfg,
                    self._run_one_cycle,
                    on_cycle=on_cycle,
                    should_stop=self._stop.is_set,
                    skip_event=self._skip,
                    before_wait=before_wait,
                )
        except SessionHealthError as exc:
            self._set_state("error", str(exc))
        except WatchLockHeldError as exc:
            self._set_state("error", str(exc))
        except Exception as exc:  # noqa: BLE001 — surface any worker failure
            self._set_state("error", f"{type(exc).__name__}: {exc}")
        finally:
            if self._state != "error":
                self._set_state("idle")
