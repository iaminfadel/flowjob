"""The watch loop: one implementation hosting both the CLI watcher and the TUI.

Owns the jittered wait between cycles and the stop/skip discipline. The
cross-process lock stays at the host layer (each host acquires it around the
loop). Hosts customise behaviour through callbacks only — the loop never
branches on who is running it.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Optional

from src.config import FlowJobConfig


def run_watch_loop(
    cfg: FlowJobConfig,
    run_cycle: Callable[[], object],
    *,
    on_cycle: Optional[Callable[[object], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    skip_event: Optional[object] = None,
    before_wait: Optional[Callable[[float], float]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[float, float], float] = random.uniform,
) -> int:
    """Run pipeline cycles until asked to stop; returns the cycle count.

    run_cycle: executes one pipeline cycle (host provides the closure over
        agents/approval/stdout capture) — may raise to abort the loop.
    on_cycle: called after each cycle with the cycle's return value.
    should_stop: polled between phases; True ends the loop.
    skip_event: object with wait(timeout) -> bool (e.g. threading.Event);
        when set during the jitter wait, the next cycle starts immediately.
    before_wait: called with the chosen interval in minutes right before the
        wait begins; may return a replacement interval (e.g. the TUI shows a
        countdown). Return value is ignored unless positive.
    """
    cycles = 0
    while True:
        if cycles > 0 and should_stop and should_stop():
            break
        result = run_cycle()
        cycles += 1
        if on_cycle is not None:
            on_cycle(result)
        if should_stop and should_stop():
            break
        interval_minutes = jitter_fn(cfg.watch.min_wait_minutes, cfg.watch.max_wait_minutes)
        if before_wait is not None:
            adjusted = before_wait(interval_minutes)
            if isinstance(adjusted, (int, float)) and adjusted > 0:
                interval_minutes = adjusted
        if skip_event is not None and skip_event.wait(interval_minutes * 60):
            skip_event.clear()
            continue
        sleep_fn(interval_minutes * 60)
    return cycles
