"""Pilot (headless) integration tests for the cockpit TUI.

Each test boots the real CockpitApp against a temp DB and drives it with
Textual's Pilot, patching only the expensive boundaries: pipeline run,
grilling session, and settings file I/O.
"""

import os
import threading
import time
import uuid
from datetime import datetime

import pytest
from textual.widgets import DataTable, Input, TabbedContent

from src.db.models import Job, JobState, LLMInteraction
from src.db.store import get_session, init_db


@pytest.fixture
def cockpit_env(tmp_path, monkeypatch):
    db_path = tmp_path / "cockpit.db"
    monkeypatch.setenv("FLOWJOB_DB", str(db_path))
    from src.tui.queries import reset_engine

    reset_engine()
    engine = init_db(str(db_path))
    with get_session(engine) as session:
        seed = [
            ("NEW", "Data Engineer", "Acme"),
            ("PENDING_APPROVAL", "ML Engineer", "Globex"),
            ("FAILED", "SRE", "Initech"),
            ("NEEDS_EVIDENCE", "Backend Dev", "Umbrella"),
        ]
        for state, title, company in seed:
            session.add(
                Job(
                    id=str(uuid.uuid4()),
                    url=f"https://example.com/job/{title.lower().replace(' ', '-')}",
                    title=title,
                    company=company,
                    location="Remote",
                    posted_date="2026-08-01",
                    jd_text=f"{title} job description",
                    state=JobState(state),
                    fit_score=70,
                )
            )
        session.add(
            LLMInteraction(
                timestamp=datetime.now(),
                agent_name="analyst",
                job_id=None,
                provider="openrouter",
                model="qwen/qwen3.8-27b",
                prompt="p",
                response="r",
                success=True,
                prompt_tokens=10,
                completion_tokens=5,
                cached_tokens=0,
                cost_usd=0.0001,
                latency_ms=300,
            )
        )
        session.commit()
    return engine


@pytest.fixture
def app(cockpit_env):
    from src.tui.app import CockpitApp

    return CockpitApp(agents={})


async def wait_until(pilot, cond, timeout=8.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await pilot.pause()
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


async def test_mount_tabs_and_jobs_table(app, cockpit_env):
    from src.tui.queries import total_jobs

    assert total_jobs() == 4
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        tabs = app.query_one(TabbedContent)
        assert tabs.active == "dashboard"

        tabs.active = "jobs"
        await pilot.pause()
        table = app.query_one(DataTable)
        assert table.row_count == 4

        table.move_cursor(row=0, column=0)
        await pilot.pause()
        from src.tui import queries
        from src.tui.widgets import JobDetailPane

        first = queries.jobs("ALL")[0]
        title = app.query_one(JobDetailPane).query_one("#detail-title")
        assert first["title"] in str(title.content)
        assert first["company"] in str(title.content)

        tabs.active = "logs"
        await pilot.pause()
        from src.tui.widgets import LogsPane

        stats = app.query_one(LogsPane).query_one("#logs-stats")
        assert "analyst" in str(stats.content) or "$0.0001" in str(stats.content)

        tabs.active = "hitl"
        await pilot.pause()
        assert app.query_one("#approve-" + _pending_id())


def _pending_id():
    from src.tui import queries

    jobs = queries.jobs("PENDING_APPROVAL")
    assert jobs, "seed must contain a pending-approval job"
    return jobs[0]["id"]


async def test_approval_modal_approve_flow(app):
    job_id = _pending_id()
    results = []

    def _requester():
        results.append(app.approval.request(job_id))

    async with app.run_test(size=(140, 40)) as pilot:
        from src.tui.widgets import ApprovalModal

        thread = threading.Thread(target=_requester, daemon=True)
        thread.start()
        await wait_until(pilot, lambda: isinstance(app.screen, ApprovalModal), what="approval modal")

        await pilot.press("y")
        thread.join(timeout=3)
        assert results == [True], "pipeline worker must unblock with True"
        assert not isinstance(app.screen, ApprovalModal), "modal must close"
        assert not app.approval.is_pending(job_id)


async def test_approval_modal_reject_flow(app):
    job_id = _pending_id()
    results = []

    def _requester():
        results.append(app.approval.request(job_id))

    async with app.run_test(size=(140, 40)) as pilot:
        from src.tui.widgets import ApprovalModal

        thread = threading.Thread(target=_requester, daemon=True)
        thread.start()
        await wait_until(pilot, lambda: isinstance(app.screen, ApprovalModal), what="approval modal")
        await pilot.press("n")
        thread.join(timeout=3)
        assert results == [False]


async def test_approve_without_active_cycle_warns(app, monkeypatch):
    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.query_one(TabbedContent).active = "hitl"
        await pilot.pause()
        await pilot.click(f"#approve-{_pending_id()}")
        await pilot.pause()
        assert any("No active cycle is awaiting approval" in n for n in notes)


async def test_grill_chat_flow(app, monkeypatch, cockpit_env):
    from src.tui import queries

    job_id = queries.jobs("NEEDS_EVIDENCE")[0]["id"]
    answers: list[str] = []

    def fake_session(job_id, **kwargs):
        input_fn = kwargs["input_fn"]
        answers.append(input_fn("Q1: walk me through your resume"))
        print("captured answer one")
        answers.append(input_fn("Q2: what were your metrics?"))
        return True

    monkeypatch.setattr("src.agents.interviewer.run_grilling_session", fake_session)
    monkeypatch.setattr("src.agents.llm_factory.load_providers", lambda: [])
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)

    async with app.run_test(size=(140, 40)) as pilot:
        app.start_grill(job_id)
        await wait_until(
            pilot, lambda: app.grill.is_active(), what="grill worker to start"
        )

        inp = app.query_one("#grill-input", Input)
        inp.value = "I architected data pipelines at scale."
        await pilot.click("#grill-send")
        await pilot.pause()
        await wait_until(pilot, lambda: len(answers) == 1, what="first answer to land")
        assert answers[0] == "I architected data pipelines at scale."

        inp.value = "We cut query latency by 40%."
        await pilot.click("#grill-send")

        await wait_until(
            pilot,
            lambda: not app.grill.is_active() and app.grill.active_job is None,
            what="grill session to end",
        )
        assert len(answers) == 2, "both questions must have been answered"

        chat = "\n".join(str(strip.text) for strip in app.query_one("#grill-chat").lines)
        assert "You: I architected data pipelines at scale." in chat
        assert "captured answer one" in chat


async def test_grill_send_without_session_warns(app, monkeypatch):
    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.query_one(TabbedContent).active = "hitl"
        await pilot.pause()
        inp = app.query_one("#grill-input", Input)
        inp.value = "hello"
        await pilot.click("#grill-send")
        await pilot.pause()
        assert any("No active grilling session" in n for n in notes)


async def test_watch_start_cycle_and_stop(app, monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake_run_pipeline(*, agents, approval_fn, wait_fn=None):
        calls["n"] += 1
        print("fake cycle ran")

    monkeypatch.setattr("src.pipeline.orchestrator.run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.click("#watch-start")
        await wait_until(pilot, lambda: calls["n"] >= 1, what="first cycle")
        await wait_until(
            pilot,
            lambda: "Watch: countdown" in str(app.query_one("#watch-status").content),
            what="countdown state",
        )

        app.watch_manager.run_now()
        await wait_until(pilot, lambda: calls["n"] >= 2, what="second cycle (run now)")

        app.watch_manager.stop()
        await wait_until(
            pilot,
            lambda: app.watch_manager.state == "idle" and not app.watch_manager.is_running(),
            what="watch to stop",
        )
        log = "\n".join(str(strip.text) for strip in app.query_one("#watch-log").lines)
        assert "fake cycle ran" in log
        assert "cycle:" in log


async def test_watch_lock_conflict_shows_error(app, monkeypatch):
    from src.pipeline.watch_lock import acquire_watch_lock

    def fake_run_pipeline(*, agents, approval_fn, wait_fn=None):
        raise AssertionError("must not run when lock is held")

    monkeypatch.setattr("src.pipeline.orchestrator.run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)

    with acquire_watch_lock():
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.click("#watch-start")
            await wait_until(
                pilot,
                lambda: "Watch: error" in str(app.query_one("#watch-status").content),
                what="watch error state from lock conflict",
            )


async def test_settings_save_wires_collect_to_save(app, monkeypatch, tmp_path):
    import yaml as pyyaml

    from src.tui import settings as settings_mod

    saved = {}

    def fake_save(raw, path="flowjob.yaml"):
        saved.update(raw)

    monkeypatch.setattr(settings_mod, "save_settings", fake_save)
    monkeypatch.setattr(settings_mod, "round_trip_load", settings_mod.round_trip_load)

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "settings"
        await pilot.pause()

        field = app.query_one("#cfg-scout-max_scrape_per_run", Input)
        field.value = "33"
        save_btn = app.query_one("#settings-save")
        save_btn.scroll_visible()
        await pilot.pause()
        save_btn.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert saved.get("scout", {}).get("max_scrape_per_run") == 33


async def test_settings_env_banner(app, monkeypatch):
    from src.tui import settings as settings_mod

    monkeypatch.setenv("FLOWJOB_MODEL", "anthropic/claude-x")
    monkeypatch.setattr(
        settings_mod, "env_overrides_active", lambda: {"FLOWJOB_MODEL": "anthropic/claude-x"}
    )

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "settings"
        await pilot.pause()
        banner = app.query_one("#env-banner")
        assert banner.display is True
        assert "FLOWJOB_MODEL" in str(banner.content)


async def test_settings_save_validation_error_notifies(app, monkeypatch, tmp_path):
    import yaml as pyyaml

    from src.tui import settings as settings_mod

    cfg_file = tmp_path / "flowjob.yaml"
    cfg_file.write_text(
        pyyaml.safe_dump(
            {"scout": {"max_scrape_per_run": 10}, "analyst": {"min_fit_score": 70}}
        )
    )
    notes = []
    real_save = settings_mod.save_settings
    monkeypatch.setattr(
        settings_mod, "save_settings", lambda raw, path="flowjob.yaml": real_save(raw, path=str(cfg_file))
    )
    monkeypatch.setattr(settings_mod, "round_trip_load", settings_mod.round_trip_load)
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "settings"
        await pilot.pause()

        field = app.query_one("#cfg-scout-max_scrape_per_run", Input)
        field.value = "999"
        save_btn = app.query_one("#settings-save")
        save_btn.scroll_visible()
        await pilot.pause()
        save_btn.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert any("Settings invalid" in n and "max_scrape_per_run" in n for n in notes)
        assert "max_scrape_per_run: 10" in cfg_file.read_text(), "file must be untouched"


async def test_watch_pause_blocks_worker_until_continue(app, monkeypatch):
    calls = {"n": 0}

    def fake_run_pipeline(*, agents, approval_fn, wait_fn=None):
        calls["n"] += 1
        if calls["n"] == 1:
            wait_fn("Fill the experience field, then click Next")

    monkeypatch.setattr("src.pipeline.orchestrator.run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.click("#watch-start")
        from src.tui.widgets import PauseModal

        await wait_until(
            pilot,
            lambda: isinstance(app.screen, PauseModal),
            what="pause modal",
        )
        modal_body = app.screen.query_one("#modal-body")
        assert "Fill the experience field" in str(modal_body.content)
        assert app.pause.pending() == ["Fill the experience field, then click Next"]

        await pilot.click(app.screen.query_one("#modal-pause-continue"))
        app.watch_manager.run_now()
        await wait_until(pilot, lambda: calls["n"] >= 2, what="worker resumed after continue")

        app.watch_manager.stop()
        await wait_until(
            pilot,
            lambda: app.watch_manager.state == "idle" and not app.watch_manager.is_running(),
            what="watch to stop",
        )
        assert app.pause.pending() == []