"""Watch-loop hosting inside the TUI.

One worker thread runs pipeline cycles with stdout capture, a jittered
countdown, per-cycle summary, and the watch lockfile. Manual start / graceful
stop / restart; never auto-starts on launch.
"""

from __future__ import annotations

import random
import threading
import time

from textual.message import Message

from src.tui.queries import state_counts, spend_summary, last_cycle


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

    def _run(self) -> None:
        from src.config import load_config
        from src.pipeline.orchestrator import run_pipeline, SessionHealthError
        from src.pipeline.watch_lock import acquire_watch_lock, WatchLockHeldError
        from src.tui.output import StdoutCapture

        try:
            cfg = load_config("flowjob.yaml")
            with acquire_watch_lock():
                self._set_state("running")
                while not self._stop.is_set():
                    counts_before = state_counts()
                    spend_before = spend_summary()["cost_usd"]
                    t0 = time.monotonic()
                    try:
                        with StdoutCapture(self._pump):
                            run_pipeline(
                                agents=self._get_agents(),
                                approval_fn=self.approval.request,
                                wait_fn=self._wait_fn,
                            )
                    except SessionHealthError as exc:
                        self._set_state("error", str(exc))
                        return
                    duration = time.monotonic() - t0
                    spend_after = spend_summary()["cost_usd"]
                    counts_after = state_counts()
                    self._set_state("running")
                    self.app.post_message(
                        CycleSummary(
                            duration_s=duration,
                            counts=counts_after,
                            spend_delta=spend_after - spend_before,
                            cost=spend_after,
                            jobs_applied=counts_after.get("APPLIED", 0) - counts_before.get("APPLIED", 0),
                        )
                    )

                    if self._stop.is_set():
                        break
                    interval = random.uniform(
                        cfg.watch.min_wait_minutes, cfg.watch.max_wait_minutes
                    )
                    self._set_state("countdown", f"{interval:.0f}")
                    if self._skip.wait(interval * 60):
                        self._skip.clear()
                        continue
        except WatchLockHeldError as exc:
            self._set_state("error", str(exc))
        except Exception as exc:  # noqa: BLE001 — surface any worker failure
            self._set_state("error", f"{type(exc).__name__}: {exc}")
        finally:
            if self._state != "error":
                self._set_state("idle")