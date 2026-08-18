"""Render cockpit screenshots as SVG for the README.

Seeds a demo database (jobs across every state, LLM interactions, a transcript),
boots the real CockpitApp headless, and exports one SVG per tab plus the
approval-gate modal into docs/screenshots/.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FLOWJOB_DB"] = str(Path(tempfile.mkdtemp()) / "shots.db")

from textual.widgets import TabbedContent  # noqa: E402

from src.db.models import ErrorRecord, Job, JobState, LLMInteraction  # noqa: E402
from src.db.store import get_session, init_db  # noqa: E402
from src.tui.queries import reset_engine  # noqa: E402

JOB_IDS = [str(uuid.uuid4()) for _ in range(8)]


def seed() -> None:
    reset_engine()
    engine = init_db(os.environ["FLOWJOB_DB"])
    with get_session(engine) as session:
        jobs = [
            ("NEW", "Staff Data Engineer", "Acme", "San Francisco, CA", 62, None),
            ("ANALYZED", "Senior ML Platform Engineer", "Globex", "Remote", 81, None),
            ("DRAFTED", "Backend Engineer (Go)", "Umbrella Corp", "New York, NY", 74, None),
            ("PENDING_APPROVAL", "Principal AI Engineer", "Initech", "Remote", 88, 91),
            ("APPLIED", "ML Engineer — Search", "Stark Industries", "Menlo Park, CA", 79, 84),
            ("FAILED", "SRE / Platform", "Wayne Enterprises", "Gotham, NJ", 66, 58),
            ("NEEDS_EVIDENCE", "Staff Engineer — Infra", "Cyberdyne", "Remote", 71, 77),
            ("UNFIXABLE", "Crypto Quant Dev", "Tyrell Corp", "Remote", 23, None),
        ]
        for i, (state, title, company, location, fit, edit) in enumerate(jobs):
            jd = f"{title} — design and build {company.lower()} platform services..."
            session.add(
                Job(
                    id=JOB_IDS[i],
                    url=f"https://www.linkedin.com/jobs/view/{100000 + i}",
                    title=title,
                    company=company,
                    location=location,
                    posted_date="2026-08-17",
                    jd_text=jd,
                    state=JobState(state),
                    fit_score=fit,
                    edit_score=edit,
                    error="Playwright timeout while clicking Next (3 attempts)" if state == "FAILED" else None,
                    cv_path=f"data/resumes/{JOB_IDS[i]}/resume.pdf" if state == "APPLIED" else None,
                    transcript="Q: Show a time you scaled a data pipeline.\nA: At my last company I owned a 40TB batch pipeline that ran 12 hours nightly; I cut it to 3 with incremental loads and saw zero SLA misses over a quarter." if state == "NEEDS_EVIDENCE" else None,
                )
            )
        session.add(
            ErrorRecord(
                job_id=JOB_IDS[5],
                agent_name="ApplicatorAgent",
                error_type="PlaywrightTimeoutError",
                stack_trace="playwright._impl._errors.TimeoutError: Timeout 30000ms exceeded.",
                timestamp="2026-08-17 14:02",
                retry_count=2,
            )
        )
        for i, (agent, model, tokens, cost) in enumerate(
            [
                ("analyst", "gemini-3.1-flash-lite", (812, 240), 0.0004),
                ("tailor", "gemini-3.1-flash-lite", (1450, 512), 0.0008),
                ("editor", "gemini-3.1-flash-lite", (2301, 388), 0.0011),
                ("critic", "gemini-3.1-flash-lite", (1204, 96), 0.0005),
                ("writer", "gemini-3.1-flash-lite", (3102, 640), 0.0015),
                ("interviewer", "gemini-3.1-flash-lite", (522, 158), 0.0003),
            ]
        ):
            session.add(
                LLMInteraction(
                    timestamp=datetime.now(),
                    agent_name=agent,
                    job_id=JOB_IDS[3] if agent == "critic" else None,
                    provider="gemini",
                    model=model,
                    prompt=f"Analyze job fit for {agent}",
                    response="analysis output",
                    success=True,
                    prompt_tokens=tokens[0],
                    completion_tokens=tokens[1],
                    cached_tokens=0,
                    cost_usd=cost,
                    latency_ms=320 + i * 40,
                )
            )
        session.commit()


async def main() -> None:
    seed()

    from src.tui.app import CockpitApp
    from src.tui.widgets import ApprovalModal, GrillChat

    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    app = CockpitApp(agents={})
    async with app.run_test(size=(112, 34)) as pilot:
        await pilot.pause()
        await pilot.pause()
        app.refresh_all()
        await pilot.pause()

        watch_log = app.query_one("#watch-log")
        for line in [
            "cycle: 41.2s · 3 applied (+1) · spend $0.0041 (+0.0004)",
            "[Applicator] Found 'Submit application' button. Submitting...",
            "[Applicator] Application submitted successfully.",
        ]:
            watch_log.write(line)

        tabs = app.query_one(TabbedContent)
        for tab, name in [
            ("dashboard", "dashboard"),
            ("jobs", "jobs"),
            ("logs", "logs"),
            ("settings", "settings"),
            ("hitl", "hitl"),
        ]:
            tabs.active = tab
            await pilot.pause()
            await pilot.pause()
            if tab == "jobs":
                from textual.widgets import DataTable

                table = app.query_one(DataTable)
                table.move_cursor(row=3, column=0)
                await pilot.pause()
            if tab == "hitl":
                chat = app.query_one(GrillChat)
                for line in [
                    "You: I rebuilt our batch pipeline to incremental loads — cut runtime from 12h to 3h.",
                    "Interviewer: How did you keep correctness with late-arriving data?",
                    "You: Idempotent watermark-based reprocessing with a DLQ for out-of-order events.",
                    "Interviewer: Strong. Any SLA misses during the migration?",
                    "You: Zero over a quarter; we shadow-ran both paths for two weeks first.",
                ]:
                    chat.append_line(line)
            await pilot.pause()
            svg = app.export_screenshot(title=f"FlowJob Cockpit — {name}")
            (out / f"{name}.svg").write_text(svg)
            print(f"wrote {out / name}.svg ({len(svg)} bytes)")

        app.push_screen(ApprovalModal(JOB_IDS[3]))
        await pilot.pause()
        await pilot.pause()
        (out / "approval.svg").write_text(
            app.export_screenshot(title="FlowJob Cockpit — approval gate")
        )
        print(f"wrote {out / 'approval.svg'}")


asyncio.run(main())