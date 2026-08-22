"""Pipeline host adapter.

`run_pipeline` is the thin entry point CLI and TUI call. It owns host concerns
(config load, DB wiring, session-health probe) and delegates the entire cycle
to the deep `PipelineCycleEngine`. All stage behaviour lives there — this
module must stay small.
"""

from __future__ import annotations

import subprocess
from typing import Any, Callable, Optional

from src.config import load_config
from src.db.store import get_session, init_db
from src.pipeline.engine import PipelineCycleEngine
from src.pipeline.types import CycleSummaryResult, SessionHealthError  # noqa: F401
from src.storage.document_store import DiskDocumentStore


def notify_user(title: str, message: str) -> None:
    try:
        subprocess.run(["notify-send", title, message], check=False)
    except Exception:
        print(f"[NOTIFICATION] {title}: {message}")


def prompt_user_approval(job) -> bool:
    print(f"Prompting user for job: {job.title} at {job.company}")
    notify_user("FlowJob: Job ready for approval!", f"{job.title} at {job.company}")
    try:
        response = input("Do you approve applying to this job? (y/n): ")
        return response.strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def save_draft_json(job_id: str, draft_data: dict, output_dir: str = "data/resumes") -> str:
    return DiskDocumentStore(base_dir=output_dir).save_draft(job_id, draft_data)


def load_draft_json(job_id: str, output_dir: str = "data/resumes") -> dict:
    return DiskDocumentStore(base_dir=output_dir).load_draft(job_id)


def run_pipeline(
    agents: dict,
    url: Optional[str] = None,
    dry_run: bool = False,
    config_path: str = "flowjob.yaml",
    db_path: Optional[str] = None,
    doc_store: Optional[Any] = None,
    approval_fn: Optional[Callable] = None,
    wait_fn: Optional[Callable] = None,
    notify_fn: Optional[Callable] = None,
) -> CycleSummaryResult:
    """Run one full pipeline cycle and return its summary.

    Raises SessionHealthError when the LinkedIn browser session fails its
    health probe before any work starts.
    """
    print(f"Pipeline started with url={url} and dry_run={dry_run}")

    from src.tools.browser import check_session_health

    if not check_session_health():
        raise SessionHealthError("LinkedIn session health check failed.")

    cfg = load_config(config_path)
    config = cfg.model_dump()
    if db_path is None:
        db_path = cfg.data.db_path
    engine_db = init_db(db_path)

    cycle_engine = PipelineCycleEngine(
        config=config,
        agents=agents,
        doc_store=doc_store or DiskDocumentStore(),
        approval_fn=approval_fn or prompt_user_approval,
        wait_fn=wait_fn,
        notify_fn=notify_fn or notify_user,
    )

    with get_session(engine_db) as session:
        return cycle_engine.run_cycle(session, url=url, dry_run=dry_run)
