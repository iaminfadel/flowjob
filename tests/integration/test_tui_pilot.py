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
from textual.widgets import DataTable, Input, Select, TabbedContent, TextArea

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
            ("NEW", "Data Engineer", "Acme", "pipeline"),
            ("PENDING_APPROVAL", "ML Engineer", "Globex", "pipeline"),
            ("FAILED", "SRE", "Initech", "pipeline"),
            ("NEEDS_EVIDENCE", "Backend Dev", "Umbrella", "pipeline"),
            ("APPLIED", "Manual Role", "BossCorp", "manual"),
        ]
        for idx, (state, title, company, source) in enumerate(seed):
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
                    source=source,
                    notes="referred by a friend" if source == "manual" else "",
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


async def wait_modal_widget(pilot, app, widget_id, what="modal widget"):
    await wait_until(
        pilot,
        lambda: len(app.screen.query(f"#{widget_id}").nodes) > 0,
        what=what,
    )


async def test_mount_tabs_and_jobs_table(app, cockpit_env):
    from src.tui.queries import total_jobs

    assert total_jobs() == 5
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        tabs = app.query_one(TabbedContent)
        assert tabs.active == "dashboard"

        tabs.active = "jobs"
        await pilot.pause()
        table = app.query_one(DataTable)
        assert table.row_count == 5

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

async def test_source_badge_and_source_filter(app, cockpit_env):
    from src.tui.widgets import JobsTable

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "jobs"
        await pilot.pause()

        table = app.query_one(JobsTable)
        assert table.row_count == 5
        cells = [str(table.get_cell_at((r, 4))) for r in range(table.row_count)]
        assert "manual" in cells, f"source column must carry a manual badge, got {cells}"
        assert "pipeline" in cells

        src_filter = app.query_one("#source-filter", Select)
        src_filter.value = "manual"
        await pilot.pause()
        assert table.row_count == 1
        assert str(table.get_cell_at((0, 0))) == "Manual Role"

        src_filter.value = "pipeline"
        await pilot.pause()
        assert table.row_count == 4

        src_filter.value = "ALL"
        await pilot.pause()
        assert table.row_count == 5


async def test_source_filter_combines_with_state_filter(app, cockpit_env):
    from src.tui.widgets import JobsTable

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "jobs"
        await pilot.pause()

        app.query_one("#state-filter", Select).value = "APPLIED"
        app.query_one("#source-filter", Select).value = "manual"
        await pilot.pause()

        table = app.query_one(JobsTable)
        assert table.row_count == 1
        assert str(table.get_cell_at((0, 0))) == "Manual Role"


async def test_manual_job_detail_shows_notes_and_jd(app, cockpit_env):
    from src.tui import queries
    from src.tui.widgets import JobDetailPane, JobsTable

    manual = queries.jobs(source_filter="manual")[0]

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "jobs"
        await pilot.pause()

        table = app.query_one(JobsTable)
        idx = table.row_job_ids.index(manual["id"])
        table.move_cursor(row=idx, column=0)
        await pilot.pause()

        pane = app.query_one(JobDetailPane)
        title = str(pane.query_one("#detail-title").content)
        assert "[manual]" in title
        notes = pane.query_one("#detail-notes")
        assert notes.display is True
        assert "referred by a friend" in str(notes.content)
        jd = str(pane.query_one("#detail-jd").content)
        assert "Manual Role job description" in jd


async def test_add_manual_form_saves_row(app, monkeypatch, cockpit_env, tmp_path):
    from src.tui import queries
    from src.tui.widgets import AddJobModal, JobsTable

    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))

    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"fake-pdf")

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "jobs"
        await pilot.pause()

        await pilot.press("m")
        await wait_modal_widget(pilot, app, "add-title", "add form fields")

        modal = app.screen
        assert isinstance(modal, AddJobModal)
        modal.query_one("#add-title", Input).value = "TUI Added Job"
        modal.query_one("#add-company", Input).value = "NewCo"
        modal.query_one("#add-url", Input).value = "https://example.com/tui-added"
        modal.query_one("#add-jd", TextArea).text = "pasted jd in the TUI"
        modal.query_one("#add-notes", TextArea).text = "logged from cockpit"
        modal.query_one("#add-cv", Input).value = str(cv)
        await pilot.click("#add-save")
        await pilot.pause()

        assert not isinstance(app.screen, AddJobModal), "modal must close after save"
        assert any("Logged manual application" in n for n in notes)

        added = queries.jobs(source_filter="manual")
        assert len(added) == 2
        row = next(j for j in added if j["title"] == "TUI Added Job")
        assert row["company"] == "NewCo"
        assert row["jd_text"] == "pasted jd in the TUI"
        assert row["notes"] == "logged from cockpit"
        assert row["state"] == "APPLIED"
        assert row["date_applied"]
        assert row["cv_path"] and os.path.exists(row["cv_path"])

        table = app.query_one(JobsTable)
        assert any("TUI Added Job" in str(table.get_cell_at((r, 0))) for r in range(table.row_count))


async def test_add_manual_form_requires_identifying_field(app, monkeypatch, cockpit_env):
    from src.tui.widgets import AddJobModal

    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("m")
        await wait_modal_widget(pilot, app, "add-title", "add form fields")

        await pilot.click("#add-save")
        await pilot.pause()

        assert isinstance(app.screen, AddJobModal), "modal stays open on invalid input"
        assert any("at least one" in n for n in notes)


async def test_add_manual_form_bad_cv_path_notifies(app, monkeypatch, cockpit_env):
    from src.tui.widgets import AddJobModal

    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("m")
        await wait_modal_widget(pilot, app, "add-title", "add form fields")

        modal = app.screen
        modal.query_one("#add-title", Input).value = "Bad Cv Job"
        modal.query_one("#add-cv", Input).value = "/nonexistent/cv.pdf"
        await pilot.click("#add-save")
        await pilot.pause()

        assert isinstance(app.screen, AddJobModal), "modal stays open on bad cv path"
        assert any("not found" in n for n in notes)


async def test_change_state_modal_flips_state(app, monkeypatch, cockpit_env):
    from src.tui import queries
    from src.tui.widgets import ChangeStateModal, JobsTable

    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "jobs"
        await pilot.pause()

        table = app.query_one(JobsTable)
        table.move_cursor(row=0, column=0)
        await pilot.pause()
        target = queries.jobs("ALL")[0]

        await pilot.press("s")
        await wait_modal_widget(pilot, app, "change-state-select", "change-state modal")

        modal = app.screen
        assert isinstance(modal, ChangeStateModal)
        modal.query_one("#change-state-select", Select).value = "REJECTED"
        await pilot.click("#change-save")
        await pilot.pause()

        assert not isinstance(app.screen, ChangeStateModal)
        assert queries.job_detail(target["id"])["state"] == "REJECTED"
        assert any("→ REJECTED" in n for n in notes)


async def test_change_state_without_selection_warns(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    monkeypatch.setenv("FLOWJOB_DB", str(db_path))
    from src.db.store import init_db

    init_db(str(db_path))
    from src.tui.queries import reset_engine

    reset_engine()

    from src.tui.app import CockpitApp

    app = CockpitApp(agents={})
    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("s")
        await pilot.pause()
        assert any("Select a job" in n for n in notes)


def _seed_extra_job(state: str, title: str, source: str):
    from src.tui import queries

    with get_session(queries.engine()) as session:
        session.add(
            Job(
                id=uuid.uuid4().hex[:12],
                url=f"https://example.com/{source}-{title.lower().replace(' ', '-')}",
                title=title,
                company="ExtraCorp",
                location="",
                posted_date="",
                jd_text=f"{title} job description",
                state=JobState(state),
                source=source,
            )
        )
        session.commit()


async def test_manual_failed_row_has_no_retry_hint(app, cockpit_env):
    from src.tui import queries
    from src.tui.widgets import JobsTable

    _seed_extra_job("FAILED", "Manual Fail", "manual")

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "jobs"
        await pilot.pause()

        table = app.query_one(JobsTable)
        idx = next(
            i for i, jid in enumerate(table.row_job_ids)
            if (queries.job_detail(jid) or {}).get("title") == "Manual Fail"
        )
        table.move_cursor(row=idx, column=0)
        await pilot.pause()

        actions = str(app.query_one("#detail-actions").content)
        assert "[t] retry" not in actions, f"manual rows must not invite retry, got: {actions}"


async def test_hitl_inboxes_exclude_manual_rows(app, cockpit_env):
    from src.tui import queries
    from src.tui.widgets import ApprovalList, NeedsEvidenceList
    from textual.widgets import Label

    _seed_extra_job("PENDING_APPROVAL", "Manual Pending", "manual")
    _seed_extra_job("NEEDS_EVIDENCE", "Manual Evidence", "manual")

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "hitl"
        await pilot.pause()

        approval = app.query_one("#approval-list", ApprovalList)
        approval_text = "\n".join(str(w.content) for w in approval.query(Label))
        assert "ML Engineer" in approval_text
        assert "Manual Pending" not in approval_text

        evidence = app.query_one("#evidence-list", NeedsEvidenceList)
        evidence_text = "\n".join(str(w.content) for w in evidence.query(Label))
        assert "Backend Dev" in evidence_text
        assert "Manual Evidence" not in evidence_text

        assert queries.jobs("PENDING_APPROVAL", source_filter="manual")[0]["title"] == "Manual Pending"


async def test_retry_action_refuses_manual_row(app, monkeypatch, cockpit_env):
    from src.tui import queries
    from src.tui.widgets import JobsTable

    _seed_extra_job("FAILED", "Manual Fail", "manual")
    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))

    async with app.run_test(size=(140, 40)) as pilot:
        tabs = app.query_one(TabbedContent)
        tabs.active = "jobs"
        await pilot.pause()

        table = app.query_one(JobsTable)
        idx = next(
            i for i, jid in enumerate(table.row_job_ids)
            if (queries.job_detail(jid) or {}).get("title") == "Manual Fail"
        )
        table.move_cursor(row=idx, column=0)
        await pilot.pause()

        await pilot.press("t")
        await pilot.pause()

        assert any("never pipeline work" in n for n in notes), notes
        assert queries.job_detail(table.row_job_ids[idx])["state"] == "FAILED"
