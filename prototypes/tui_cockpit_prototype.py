"""PROTOTYPE — FlowJob cockpit screen model (throwaway, not production).

Question: what should the `flowjob tui` cockpit look and behave like?
Three radically different layout/navigation variants of the same six
surfaces (dashboard, jobs, LLM logs, settings, HITL). Cycle with `v`.
The boss reacts to the artifact, not to prose.

    uv run --with "textual>=8.2,<9" python prototypes/tui_cockpit_prototype.py

Variant A — Tabs:        TabbedContent across the top, jobs split side-by-side.
Variant B — Sidebar:     nav rail on the left, jobs stacked vertically.
Variant C — Keys:        full-screen stacked surfaces, key-bound, approval modal.

No persistence, no pipeline calls — everything is in-memory mock data.
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    DataTable,
    Header,
    Input,
    Label,
    OptionList,
    ProgressBar,
    RichLog,
    Rule,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from textual.widgets._option_list import Option

STATES = [
    "NEW",
    "ANALYZED",
    "SKIPPED",
    "DRAFTED",
    "EDITED",
    "PENDING_APPROVAL",
    "APPLIED",
    "FAILED",
    "TAILOR_FAIL",
    "EDIT_FAIL",
    "REJECTED",
    "NEEDS_EVIDENCE",
    "UNFIXABLE",
]

MOCK_JOBS = [
    {
        "id": "a1b2c3d4e5f6",
        "url": "https://linkedin.com/jobs/view/1",
        "title": "Senior Backend Engineer",
        "company": "Nimbus Robotics",
        "location": "Remote (US)",
        "posted_date": "2026-08-14",
        "state": "PENDING_APPROVAL",
        "fit_score": 82,
        "edit_score": 91,
        "cv_path": "output/nimbus-robotics/senior-backend-engineer/cv.pdf",
        "jd_text": (
            "Design and operate the orchestration layer of a warehouse robot fleet.\n"
            "You will own scheduling, failure recovery and observability for 40+ brokers."
        ),
        "transcript": [],
    },
    {
        "id": "b2c3d4e5f6a1",
        "url": "https://linkedin.com/jobs/view/2",
        "title": "Staff ML Engineer",
        "company": "Halcyon AI",
        "location": "San Francisco, CA",
        "posted_date": "2026-08-13",
        "state": "PENDING_APPROVAL",
        "fit_score": 74,
        "edit_score": 88,
        "cv_path": "output/halcyon-ai/staff-ml-engineer/cv.pdf",
        "jd_text": (
            "Own the training platform behind our reasoning models.\n"
            "Scale data pipelines, eval harnesses and infra for multi-cluster training."
        ),
        "transcript": [],
    },
    {
        "id": "c3d4e5f6a1b2",
        "url": "https://linkedin.com/jobs/view/3",
        "title": "Platform Engineer",
        "company": "Cobalt Fintech",
        "location": "Remote (EU)",
        "posted_date": "2026-08-12",
        "state": "APPLIED",
        "fit_score": 79,
        "edit_score": 90,
        "cv_path": "output/cobalt-fintech/platform-engineer/cv.pdf",
        "jd_text": "Build the internal developer platform for a payments scale-up: CI, CD, k8s golden paths.",
        "transcript": [],
    },
    {
        "id": "d4e5f6a1b2c3",
        "url": "https://linkedin.com/jobs/view/4",
        "title": "Data Engineer",
        "company": "Fern Labs",
        "location": "Berlin, DE",
        "posted_date": "2026-08-11",
        "state": "DRAFTED",
        "fit_score": 66,
        "edit_score": 84,
        "cv_path": "output/fern-labs/data-engineer/cv.pdf",
        "jd_text": "Own batch + streaming pipelines (Airflow, Kafka) feeding a dbt warehouse at a biotech scale-up.",
        "transcript": [],
    },
    {
        "id": "e5f6a1b2c3d4",
        "url": "https://linkedin.com/jobs/view/5",
        "title": "Backend Engineer",
        "company": "Kepler Systems",
        "location": "Amsterdam, NL",
        "posted_date": "2026-08-10",
        "state": "EDITED",
        "fit_score": 88,
        "edit_score": 93,
        "cv_path": "output/kepler-systems/backend-engineer/cv.pdf",
        "jd_text": "Ship the distributed ledger backend of a freight settlement network. Go, Postgres, Kafka.",
        "transcript": [],
    },
    {
        "id": "f6a1b2c3d4e5",
        "url": "https://linkedin.com/jobs/view/6",
        "title": "Site Reliability Engineer",
        "company": "Beacon Energy",
        "location": "Houston, TX",
        "posted_date": "2026-08-09",
        "state": "ANALYZED",
        "fit_score": 61,
        "edit_score": None,
        "cv_path": "",
        "jd_text": "Keep the SCADA backbone of a grid-scale battery operator at four-nines uptime. On-call rotation.",
        "transcript": [],
    },
    {
        "id": "a2b3c4d5e6f7",
        "url": "https://linkedin.com/jobs/view/7",
        "title": "Python Developer",
        "company": "Orion Labs",
        "location": "Remote",
        "posted_date": "2026-08-08",
        "state": "NEW",
        "fit_score": None,
        "edit_score": None,
        "cv_path": "",
        "jd_text": "Maintain the data capture platform of an IoT observability vendor. Django, Postgres, some Vue.",
        "transcript": [],
    },
    {
        "id": "b3c4d5e6f7a2",
        "url": "https://linkedin.com/jobs/view/8",
        "title": "ML Ops Engineer",
        "company": "Lumen Health",
        "location": "New York, NY",
        "posted_date": "2026-08-07",
        "state": "FAILED",
        "fit_score": 54,
        "edit_score": None,
        "cv_path": "",
        "jd_text": "Run inference + fine-tuning infra for clinical NLP. Kubernetes, Triton, HIPAA context.",
        "transcript": [],
    },
    {
        "id": "c4d5e6f7a2b3",
        "url": "https://linkedin.com/jobs/view/9",
        "title": "Senior Fullstack Engineer",
        "company": "Aurora Commerce",
        "location": "Remote (US)",
        "posted_date": "2026-08-06",
        "state": "NEEDS_EVIDENCE",
        "fit_score": 58,
        "edit_score": None,
        "cv_path": "",
        "jd_text": "Own the checkout funnel of a DTC brand house. React + Rails, high-traffic Black Friday loads.",
        "transcript": [
            ("agent", "Gap 'high-traffic checkout' — resume shows web apps but no scale numbers. Must-have: yes."),
            ("boss", "We did 3.2k orders in one hour on Black Friday 2025; I owned the cart service."),
            ("agent", "Bullet synthesized: 'Owned cart service sustaining 3.2k orders/hour at peak.' Accept? y/n"),
            ("boss", "y"),
        ],
    },
    {
        "id": "d5e6f7a2b3c4",
        "url": "https://linkedin.com/jobs/view/10",
        "title": "Product Engineer",
        "company": "Vesper",
        "location": "Remote",
        "posted_date": "2026-08-05",
        "state": "REJECTED",
        "fit_score": 49,
        "edit_score": None,
        "cv_path": "",
        "jd_text": "Build delightful onboarding flows for a B2B analytics tool. Full-stack generalist wanted.",
        "transcript": [],
    },
]

MOCK_LOGS = [
    ("09:41:02", "scout", "gemini-3.1-flash-lite", 1_842, 0.0031, 312, True),
    ("09:41:40", "analyst", "gemini-3.1-flash-lite", 2_310, 0.0042, 448, True),
    ("09:42:12", "tailor", "gemini-3.1-flash-lite", 3_120, 0.0058, 511, True),
    ("09:42:55", "editor", "gemini-3.1-flash-lite", 2_870, 0.0051, 390, True),
    ("09:43:21", "critic", "gemini-3.1-flash-lite", 1_990, 0.0037, 275, True),
    ("09:44:05", "interviewer", "gemini-3.1-flash-lite", 4_400, 0.0088, 833, True),
    ("09:45:10", "applicator", "qwen/qwen3.8-27b", 1_205, 0.0090, 1_240, False),
    ("09:46:02", "applicator", "gemini-3.5-flash", 1_315, 0.0064, 466, True),
]

MOCK_CONFIG = {
    "scout": {"max_scrape_per_run": 2, "time_filter": "past_24_hours"},
    "analyst": {"model": "gemini-3.1-flash-lite", "min_fit_score": 50},
    "tailor": {"model": "gemini-3.1-flash-lite"},
    "editor": {"model": "gemini-3.1-flash-lite", "min_keyword_coverage": 75},
    "critic": {"model": "gemini-3.1-flash-lite"},
    "writer": {"model": "gemini-3.1-flash-lite", "max_writer_rounds": 3},
    "grilling": {"model": "gemini-3.1-flash-lite", "max_turns_per_gap": 5},
    "auditor": {"model": "gemini-3.1-flash-lite", "max_attempts": 3},
    "applicator": {"max_apps_per_day": 100, "max_apps_per_hour": 10, "dry_run": False, "require_approval": True},
    "llm": {
        "default_model": "gemini-3.1-flash-lite",
        "llm_timeout_seconds": 60,
        "max_retries": 3,
        "openrouter_base_url": "https://openrouter.ai/api/v1",
    },
    "data": {"data_retention_days": 90, "db_path": "flowjob.db", "output_dir": "output/", "browser_data_dir": "browser_data/"},
}

CANNED_REPLIES = [
    "Bullet synthesized: 'Scaled the service to X.' Accept? y/n",
    "Good. Next gap: 'Distributed systems at scale' — tell me about your last incident.",
    "Noted. I'll fold that into the evidence bullet.",
    "One more question: what was your role in the multi-region migration?",
]


def jobs_by_state(state: str) -> list[dict]:
    return [j for j in MOCK_JOBS if state == "ALL" or j["state"] == state]


def set_state(job_id: str, state: str) -> None:
    for job in MOCK_JOBS:
        if job["id"] == job_id:
            job["state"] = state


class ApprovalRequested(Message):
    def __init__(self, job_id: str, approve: bool) -> None:
        self.job_id = job_id
        self.approve = approve
        super().__init__()


class DashboardPane(Vertical):
    def compose(self) -> ComposeResult:
        total = len(MOCK_JOBS)
        pending = len(jobs_by_state("PENDING_APPROVAL"))
        spend = sum(cost for _, _, _, _, cost, _, _ in MOCK_LOGS)
        tokens = sum(t for _, _, _, t, _, _, _ in MOCK_LOGS)
        with Horizontal(id="stat-row"):
            yield Static(f"Last cycle\n09:46 · 3 jobs · 1 applied", classes="stat-card")
            yield Static(f"LLM spend\n${spend:.4f} · {tokens:,} tok", classes="stat-card")
            yield Static(f"Jobs tracked\n{total}", classes="stat-card")
            yield Static(f"Awaiting approval\n{pending}", classes="stat-card")
        yield Label("State counts")
        table = DataTable(id="state-counts", cursor_type="none", zebra_stripes=True)
        table.add_column("State", key="state")
        table.add_column("Count", key="count")
        table.add_rows([(s, len(jobs_by_state(s))) for s in STATES if jobs_by_state(s)])
        yield table
        yield Rule()
        with Horizontal(id="watch-row"):
            yield Label("Watch loop")
            yield ProgressBar(id="watch-bar", total=100, show_percentage=False)
            yield Button("Start", id="watch-start", variant="primary")
            yield Button("Stop", id="watch-stop")

    def on_mount(self) -> None:
        self.running = False

    async def _watch_loop(self) -> None:
        bar = self.query_one("#watch-bar", ProgressBar)
        while self.running and bar.progress < bar.total:
            bar.advance(5)
            await asyncio.sleep(0.15)
        if self.running:
            bar.update(progress=0)
            self.app.notify("Mock cycle complete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "watch-start":
            self.running = True
            self.run_worker(self._watch_loop(), exclusive=True)
        elif event.button.id == "watch-stop":
            self.running = False


class JobsTable(DataTable):
    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.add_column("Title", key="title", width=24)
        self.add_column("Company", key="company", width=16)
        self.add_column("Location", key="location", width=13)
        self.add_column("State", key="state", width=16)
        self.add_column("Fit", key="fit", width=5)
        self.add_column("Edit", key="edit", width=5)

    def on_mount(self) -> None:
        self.current_filter = "ALL"
        self.refresh_rows()

    def apply_filter(self, state: str) -> None:
        self.current_filter = state
        self.refresh_rows()

    def refresh_rows(self) -> None:
        self.clear()
        for job in jobs_by_state(self.current_filter):
            state_style = {"PENDING_APPROVAL": "bold #FFB454", "FAILED": "red", "APPLIED": "green"}.get(
                job["state"], "default"
            )
            self.add_row(
                Text(job["title"]),
                job["company"],
                job["location"],
                Text(job["state"], style=state_style),
                str(job["fit_score"] or "-"),
                str(job["edit_score"] or "-"),
                key=job["id"],
            )


class JobDetailPane(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static("", id="detail-title")
        yield Static("", id="detail-meta")
        yield Static("", id="detail-scores")
        yield Static("", id="detail-cv")
        yield Rule()
        yield Label("Job description")
        yield Static("", id="detail-jd", classes="jd")
        yield Rule()
        yield Label("Grilling transcript")
        yield RichLog(id="detail-transcript", auto_scroll=False, highlight=True, markup=True)

    def show(self, job: dict) -> None:
        state = job["state"]
        style = "bold #FFB454" if state == "PENDING_APPROVAL" else "green" if state == "APPLIED" else "red" if state == "FAILED" else "default"
        self.query_one("#detail-title", Static).update(Text(f"{job['title']} — {job['company']}", style="bold"))
        self.query_one("#detail-meta", Static).update(f"{job['location']} · posted {job['posted_date']} · {job['url']}")
        self.query_one("#detail-scores", Static).update(
            f"State: {Text(state, style=style)}   Fit: {job['fit_score'] or '-'}/100   Edit: {job['edit_score'] or '-'}/100"
        )
        self.query_one("#detail-cv", Static).update(f"CV: {job['cv_path'] or '(not generated yet)'}")
        self.query_one("#detail-jd", Static).update(job["jd_text"])
        log = self.query_one("#detail-transcript", RichLog)
        log.clear()
        for role, text in job["transcript"]:
            who = "Interviewer" if role == "agent" else "You"
            log.write(Text(f"{who}: {text}"))


class JobsWorkspace(Vertical):
    def __init__(self, mode: str = "side", **kwargs) -> None:
        self.mode = mode
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Select(
            [(s, s) for s in ["ALL", *STATES]],
            value="ALL",
            prompt="State filter",
            id="state-filter",
        )
        if self.mode == "side":
            with Horizontal(id="jobs-split"):
                yield JobsTable(id="jobs-table")
                yield JobDetailPane(id="job-detail")
        else:
            with Vertical(id="jobs-stacked"):
                yield JobsTable(id="jobs-table")
                yield JobDetailPane(id="job-detail")

    def on_mount(self) -> None:
        self.query_one(JobsTable).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "state-filter":
            self.query_one(JobsTable).apply_filter(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.show_detail(event.row_key.value)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_detail(event.row_key.value)

    def show_detail(self, job_id: object) -> None:
        job = next(j for j in MOCK_JOBS if j["id"] == job_id)
        self.query_one(JobDetailPane).show(job)


class LogsPane(Vertical):
    def compose(self) -> ComposeResult:
        total = sum(cost for _, _, _, _, cost, _, _ in MOCK_LOGS)
        tokens = sum(t for _, _, _, t, _, _, _ in MOCK_LOGS)
        yield Static(f"LLM interaction log — session total ${total:.4f} · {tokens:,} tokens")
        yield Rule()
        yield RichLog(id="log-stream", auto_scroll=False, highlight=True, markup=True)

    def on_mount(self) -> None:
        log = self.query_one("#log-stream", RichLog)
        for ts, agent, model, tokens, cost, latency, ok in MOCK_LOGS:
            flag = "ok" if ok else "ERROR"
            style = "green" if ok else "red"
            log.write(Text(f"[{ts}] {agent:<12} {model:<24} {tokens:>6} tok  ${cost:<8.4f} {latency:>5}ms  ", style=style) + Text(flag))


class SettingsForm(VerticalScroll):
    def compose(self) -> ComposeResult:
        for section, fields in MOCK_CONFIG.items():
            yield Label(f"[bold]  {section}[/]", id=f"cfg-head-{section}")
            for key, value in fields.items():
                widget_id = f"cfg-{section}-{key}"
                if isinstance(value, bool):
                    yield Checkbox(key, value=value, id=widget_id)
                else:
                    yield Input(value=str(value), placeholder=key, id=widget_id)
            yield Rule()
        yield Static("Providers chain: edited manually in flowjob.yaml (out of TUI scope).", classes="note")
        yield Button("Save", id="settings-save", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save":
            self.app.notify("Settings saved (mock) — no persistence in prototype")


class ApprovalList(VerticalScroll):
    def compose(self) -> ComposeResult:
        self.scroll = VerticalScroll(id="approval-scroll")
        yield self.scroll

    def on_mount(self) -> None:
        self.build_rows()

    def build_rows(self) -> None:
        pending = jobs_by_state("PENDING_APPROVAL")
        if not pending:
            self.app.notify("Approval inbox empty")
            return
        for job in pending:
            self.scroll.mount(
                Horizontal(
                    Label(f"{job['title']} — {job['company']}", classes="approval-label"),
                    Button("Approve", id=f"approve-{job['id']}", variant="success"),
                    Button("Reject", id=f"reject-{job['id']}", variant="error"),
                    classes="approval-row",
                )
            )

    def rebuild(self) -> None:
        for child in list(self.scroll.children):
            child.remove()
        self.build_rows()


class GrillChat(Vertical):
    def compose(self) -> ComposeResult:
        yield RichLog(id="grill-chat", auto_scroll=True, highlight=True, markup=True)
        with Horizontal(id="grill-input-row"):
            yield Input(placeholder="Reply to the interviewer…", id="grill-input")
            yield Button("Send", id="grill-send", variant="primary")

    def on_mount(self) -> None:
        log = self.query_one("#grill-chat", RichLog)
        log.write(Text("Interviewer: Evidence session for 'Senior Fullstack Engineer' (Aurora Commerce).", style="bold"))

    def _send(self) -> None:
        inp = self.query_one("#grill-input", Input)
        text = inp.value.strip()
        if not text:
            return
        log = self.query_one("#grill-chat", RichLog)
        log.write(Text(f"You: {text}"))
        log.write(Text(f"Interviewer: {CANNED_REPLIES[len(log.lines) % len(CANNED_REPLIES)]}"))
        inp.value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "grill-send":
            self._send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "grill-input":
            self._send()


class HitlWorkspace(Vertical):
    def __init__(self, mode: str = "side", **kwargs) -> None:
        self.mode = mode
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        if self.mode == "side":
            with Horizontal(id="hitl-split"):
                with Vertical(id="approval-col"):
                    yield Label("Approval inbox")
                    yield ApprovalList(id="approval-list")
                with Vertical(id="grill-col"):
                    yield Label("Grilling session")
                    yield GrillChat(id="grill-chat-pane")
        else:
            with Vertical(id="hitl-stacked"):
                yield Label("Approval inbox")
                yield ApprovalList(id="approval-list")
                yield Rule()
                yield Label("Grilling session")
                yield GrillChat(id="grill-chat-pane")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith(("approve-", "reject-")):
            event.stop()
            job_id = event.button.id.split("-", 1)[1]
            self.post_message(ApprovalRequested(job_id, approve=event.button.id.startswith("approve-")))


class VariantBar(Static):
    def __init__(self, label: str, hint: str) -> None:
        super().__init__(f"  Variant {label} — {hint}   [v] next variant", id="variant-bar")


class VariantTabs(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Dashboard", id="dashboard"):
                yield DashboardPane()
            with TabPane("Jobs", id="jobs"):
                yield JobsWorkspace(mode="side")
            with TabPane("LLM Logs", id="logs"):
                yield LogsPane()
            with TabPane("Settings", id="settings"):
                yield SettingsForm()
            with TabPane("HITL", id="hitl"):
                yield HitlWorkspace(mode="side")
        yield VariantBar("A — Tabs", "click tabs · jobs split side-by-side")

    def on_approval_requested(self, message: ApprovalRequested) -> None:
        set_state(message.job_id, "APPLIED" if message.approve else "REJECTED")
        self.app.notify("Approved — job applied (mock)" if message.approve else "Rejected (mock)")
        self.query_one(ApprovalList).rebuild()


class VariantSidebar(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            nav = OptionList(id="nav")
            nav.add_option(Option("Dashboard", id="nav-dashboard"))
            nav.add_option(Option("Jobs", id="nav-jobs"))
            nav.add_option(Option("LLM Logs", id="nav-logs"))
            nav.add_option(Option("Settings", id="nav-settings"))
            nav.add_option(Option("HITL", id="nav-hitl"))
            yield nav
            with ContentSwitcher(initial="dashboard"):
                yield DashboardPane(id="dashboard")
                yield JobsWorkspace(mode="stack", id="jobs")
                yield LogsPane(id="logs")
                yield SettingsForm(id="settings")
                yield HitlWorkspace(mode="stack", id="hitl")
        yield VariantBar("B — Sidebar", "left rail nav · jobs stacked vertically")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.query_one(ContentSwitcher).active = event.option.id.removeprefix("nav-")

    def on_approval_requested(self, message: ApprovalRequested) -> None:
        set_state(message.job_id, "APPLIED" if message.approve else "REJECTED")
        self.app.notify("Approved — job applied (mock)" if message.approve else "Rejected (mock)")
        self.query_one(ApprovalList).rebuild()


class StackScreen(Screen):
    BINDINGS = [
        Binding("d", "stack_dashboard", "Dashboard"),
        Binding("j", "stack_jobs", "Jobs"),
        Binding("l", "stack_logs", "LLM Logs"),
        Binding("s", "stack_settings", "Settings"),
        Binding("h", "stack_hitl", "HITL"),
    ]

    def action_stack_dashboard(self) -> None:
        self.app.switch_screen("dashboard")

    def action_stack_jobs(self) -> None:
        self.app.switch_screen("jobs")

    def action_stack_logs(self) -> None:
        self.app.switch_screen("logs")

    def action_stack_settings(self) -> None:
        self.app.switch_screen("settings")

    def action_stack_hitl(self) -> None:
        self.app.switch_screen("hitl")


class StackDashboard(StackScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DashboardPane()
        yield VariantBar("C — Keys", "d/j/l/s/h switch surfaces · watch loop here")


class StackJobs(StackScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield JobsWorkspace(mode="side")
        yield VariantBar("C — Keys", "d/j/l/s/h switch surfaces · jobs full-screen")


class StackLogs(StackScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield LogsPane()
        yield VariantBar("C — Keys", "d/j/l/s/h switch surfaces · logs full-screen")


class StackSettings(StackScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield SettingsForm()
        yield VariantBar("C — Keys", "d/j/l/s/h switch surfaces · settings full-screen")


class StackHitl(StackScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield HitlWorkspace(mode="stack")
        yield VariantBar("C — Keys", "d/j/l/s/h switch surfaces · approvals + chat")

    def on_approval_requested(self, message: ApprovalRequested) -> None:
        job = next(j for j in MOCK_JOBS if j["id"] == message.job_id)
        self.app.run_worker(self._open_modal(job))

    async def _open_modal(self, job: dict) -> None:
        result = await self.app.push_screen(ApprovalModal(job), wait_for_dismiss=True)
        if result == "approve":
            set_state(job["id"], "APPLIED")
            self.app.notify("Approved — job applied (mock)")
        elif result == "reject":
            set_state(job["id"], "REJECTED")
            self.app.notify("Rejected (mock)")
        self.query_one(ApprovalList).rebuild()


class ApprovalModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss_modal", "Close")]

    def __init__(self, job: dict) -> None:
        self.job = job
        super().__init__()

    def compose(self) -> ComposeResult:
        with Container(id="approval-dialog"):
            yield Label(f"[bold]{self.job['title']}[/] — {self.job['company']}", id="modal-title")
            yield Static(f"Fit {self.job['fit_score']}/100 · Edit {self.job['edit_score']}/100", id="modal-scores")
            yield Static(self.job["jd_text"], id="modal-jd", classes="jd")
            yield Static(f"CV ready at: {self.job['cv_path']}", id="modal-cv")
            with Horizontal(id="modal-buttons"):
                yield Button("Approve & apply", id="modal-approve", variant="success")
                yield Button("Reject", id="modal-reject", variant="error")
                yield Button("Close", id="modal-close")

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-approve":
            self.dismiss("approve")
        elif event.button.id == "modal-reject":
            self.dismiss("reject")
        elif event.button.id == "modal-close":
            self.dismiss(None)


class CockpitPrototype(App):
    TITLE = "FlowJob Cockpit"
    SUB_TITLE = "prototype — v cycles layout variants"
    BINDINGS = [Binding("v", "next_variant", "Next variant")]

    SCREENS = {
        "dashboard": StackDashboard,
        "jobs": StackJobs,
        "logs": StackLogs,
        "settings": StackSettings,
        "hitl": StackHitl,
    }

    VARIANTS = [VariantTabs, VariantSidebar]

    CSS = """
    #stat-row { height: 5; }
    .stat-card { width: 1fr; border: round $primary; padding: 0 1; }
    #state-counts { height: 8; }
    #watch-row { height: 3; }
    #watch-bar { width: 1fr; }
    #jobs-split { height: 1fr; }
    #jobs-split JobsTable { width: 2fr; }
    #jobs-split JobDetailPane { width: 3fr; }
    #jobs-stacked { height: 1fr; }
    #jobs-stacked JobsTable { height: 3fr; }
    #jobs-stacked JobDetailPane { height: 2fr; }
    #nav { width: 22; }
    #hitl-split { height: 1fr; }
    #approval-col { width: 2fr; }
    #grill-col { width: 3fr; }
    #hitl-stacked { height: 1fr; }
    #approval-list { height: 1fr; }
    #grill-chat-pane { height: 1fr; }
    #grill-chat { height: 1fr; }
    #grill-input-row { height: 3; }
    #grill-input { width: 1fr; }
    #log-stream { height: 1fr; }
    .approval-row { height: 3; }
    .approval-label { width: 1fr; }
    .jd { height: auto; }
    #variant-bar { height: 1; background: $accent; color: $text; }
    #approval-dialog {
        width: 72; height: 16; border: thick $primary; background: $surface; padding: 1 2;
    }
    #modal-buttons { height: 3; }
    """

    def on_mount(self) -> None:
        self.variant_index = 0
        self.push_screen(VariantTabs())

    def action_next_variant(self) -> None:
        self.variant_index = (self.variant_index + 1) % 3
        if self.variant_index == 0:
            self.switch_screen(VariantTabs())
        elif self.variant_index == 1:
            self.switch_screen(VariantSidebar())
        else:
            self.switch_screen("dashboard")


if __name__ == "__main__":
    CockpitPrototype().run()
