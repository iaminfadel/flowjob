"""Grilling session hosting.

A worker thread runs run_grilling_session with an input_fn that blocks on a
queue; the boss answers in the HITL chat. stdout (interviewer questions,
proposed bullets) is captured and pumped to the chat pane.
"""

from __future__ import annotations

import queue
import threading

from textual.message import Message


class GrillOutput(Message):
    def __init__(self, line: str) -> None:
        super().__init__()
        self.line = line


class GrillEnded(Message):
    def __init__(self, job_id: str, ok: bool, note: str = "") -> None:
        super().__init__()
        self.job_id = job_id
        self.ok = ok
        self.note = note


class GrillManager:
    def __init__(self, app) -> None:
        self.app = app
        self._answers: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._active_job: str | None = None
        self._lock = threading.Lock()

    @property
    def active_job(self) -> str | None:
        return self._active_job

    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, job_id: str) -> bool:
        with self._lock:
            if self.is_active():
                return False
            self._active_job = job_id
        self._thread = threading.Thread(
            target=self._run, args=(job_id,), name=f"grill-{job_id}", daemon=True
        )
        self._thread.start()
        return True

    def send_answer(self, text: str) -> bool:
        if not self.is_active():
            return False
        self._answers.put(text)
        return True

    def _pump(self, line: str) -> None:
        self.app.post_message(GrillOutput(line))

    def _run(self, job_id: str) -> None:
        from src.config import load_config
        from src.db.store import get_session
        from src.agents.llm_factory import load_providers
        from src.agents.interviewer import run_grilling_session
        from src.tui.queries import engine

        ok = False
        note = ""
        try:
            cfg = load_config("flowjob.yaml")
            with get_session(engine()) as session:
                from src.tui.output import StdoutCapture

                with StdoutCapture(self._pump):
                    ok = run_grilling_session(
                        session=session,
                        job_id=job_id,
                        input_fn=lambda prompt: self._answers.get(),
                        interactive=True,
                        model_name=cfg.grilling.model,
                        max_turns_per_gap=cfg.grilling.max_turns_per_gap,
                        providers=load_providers(),
                    )
        except Exception as exc:  # noqa: BLE001 — surface any worker failure
            note = f"{type(exc).__name__}: {exc}"
        finally:
            self._active_job = None
            self.app.post_message(GrillEnded(job_id, ok, note))