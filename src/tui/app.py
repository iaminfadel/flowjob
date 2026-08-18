"""CockpitApp — the FlowJob TUI entry point."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from typing import TypeVar, cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Footer, Header, Input, RichLog, TabbedContent, TabPane

from src.tui.approval import ApprovalManager, ApprovalRequested
from src.tui.grill import GrillEnded, GrillManager, GrillOutput
from src.tui.pause import PauseManager, PauseRequested
from src.tui import queries
from src.tui.watch import CycleSummary, WatchManager, WatchOutput, WatchStateChanged
from src.tui.widgets import (
    ApprovalModal,
    DashboardPane,
    HitlWorkspace,
    JobDetailPane,
    JobsTable,
    JobsWorkspace,
    LogsPane,
    PauseModal,
    RefreshAll,
    SettingsPane,
    FAIL_STATES,
)

_T = TypeVar("_T", bound=Widget)


def _first_mounted(app: "CockpitApp", widget_type: type[_T]) -> _T | None:
    nodes = app.query(widget_type).nodes
    return cast(_T, nodes[0]) if nodes else None


CSS = """
Screen {
    background: $surface;
}

#logo {
    color: $primary;
    text-style: bold;
    height: auto;
}

#watch-status {
    color: $text-muted;
}

.watch-status {
    height: auto;
}

#watch-buttons {
    height: auto;
    margin-bottom: 1;
}

#watch-countdown {
    margin-bottom: 1;
}

#watch-log {
    height: 1fr;
    border: round $panel;
}

#jobs-col {
    width: 1fr;
    height: 100%;
}

#state-filter {
    margin-bottom: 1;
}

#jobs-table {
    height: 1fr;
}

#job-detail {
    width: 2fr;
    height: 100%;
    border: round $panel;
    padding: 0 1;
}

#detail-title {
    color: $text;
    text-style: bold;
}

#detail-meta {
    color: $text-muted;
}

#detail-cv {
    color: $text-muted;
}

#detail-actions {
    color: $primary;
}

.error-block {
    color: $error;
    background: $surface;
}

.jd {
    color: $text;
}

#detail-transcript, #detail-jd {
    height: auto;
    overflow-y: auto;
    max-height: 40%;
}

.note {
    color: $text-muted;
    margin: 0 0 1 0;
}

#env-banner {
    height: auto;
}

#hitl-left {
    width: 1fr;
    height: 100%;
}

#grill-col {
    width: 2fr;
    height: 100%;
    border-left: solid $primary;
    padding: 0 1;
}

.approval-row {
    height: auto;
    margin: 1 0;
}

.approval-label {
    width: 1fr;
}

.dim-row {
    color: $text-muted;
}

#grill-chat {
    height: 1fr;
    border: round $panel;
}

#grill-input-row {
    height: auto;
    margin-top: 1;
}

#grill-input {
    width: 1fr;
}

#logs-stats {
    color: $text-muted;
}

#log-stream {
    height: 1fr;
    border: round $panel;
}

.modal-box {
    width: 80%;
    margin: 1 2;
    height: auto;
}

#modal-title {
    color: $primary;
    text-style: bold;
}

#modal-body {
    height: auto;
}

#modal-actions {
    height: auto;
}
"""


class CockpitApp(App):
    """Five-tab cockpit: Dashboard / Jobs / LLM Logs / Settings / HITL."""

    TITLE = "FlowJob Cockpit"
    SUB_TITLE = "the agentic job-application pipeline"
    CSS = CSS

    BINDINGS = [
        Binding("1", "go_tab('dashboard')", "Dashboard", show=True),
        Binding("2", "go_tab('jobs')", "Jobs", show=True),
        Binding("3", "go_tab('logs')", "LLM Logs", show=True),
        Binding("4", "go_tab('settings')", "Settings", show=True),
        Binding("5", "go_tab('hitl')", "HITL", show=True),
        Binding("a", "approve", "Approve", show=False),
        Binding("r", "reject", "Reject", show=False),
        Binding("g", "grill", "Open grill", show=False),
        Binding("t", "retry", "Retry", show=False),
        Binding("o", "open_url", "Open URL", show=False),
        Binding("d", "open_dir", "Open resume dir", show=False),
        Binding("ctrl+r", "refresh", "Refresh", show=False),
    ]

    def __init__(self, agents=None, db_path: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._agent_map = agents
        if db_path:
            os.environ["FLOWJOB_DB"] = db_path
        self.approval = ApprovalManager(self)
        self.grill = GrillManager(self)
        self.pause = PauseManager(self)
        self.watch_manager = WatchManager(self, self.approval, agents=agents, wait_fn=self.pause.request)
        self._notified_counts: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="dashboard"):
            with TabPane("Dashboard", id="dashboard"):
                yield DashboardPane()
            with TabPane("Jobs", id="jobs"):
                yield JobsWorkspace()
            with TabPane("LLM Logs", id="logs"):
                yield LogsPane()
            with TabPane("Settings", id="settings"):
                yield SettingsPane()
            with TabPane("HITL", id="hitl"):
                yield HitlWorkspace()
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(5, self.refresh_all)

    def action_go_tab(self, tab_id: str) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

    def action_refresh(self) -> None:
        self.refresh_all()

    def refresh_all(self) -> None:
        dashboard = _first_mounted(self, DashboardPane)
        if dashboard:
            dashboard.refresh_data()
        workspace = _first_mounted(self, JobsWorkspace)
        if workspace:
            workspace.query_one(JobsTable).refresh_rows()
            selected = workspace.selected_job
            if selected:
                workspace.query_one(JobDetailPane).show(selected)
        logs = _first_mounted(self, LogsPane)
        if logs:
            logs.refresh_data()
        hitl = _first_mounted(self, HitlWorkspace)
        if hitl:
            hitl.refresh_data()
        settings = _first_mounted(self, SettingsPane)
        if settings:
            settings.refresh_banner()
        for state in ("NEEDS_EVIDENCE", "UNFIXABLE"):
            count = queries.state_counts().get(state, 0)
            if count > self._notified_counts.get(state, 0):
                self.notify(f"{count} job(s) in {state} — check the HITL tab", severity="warning")
            self._notified_counts[state] = count

    def on_refresh_all(self, message: RefreshAll) -> None:
        self.refresh_all()

    def on_watch_output(self, message: WatchOutput) -> None:
        self.query_one("#watch-log", RichLog).write(message.line)

    def on_watch_state_changed(self, message: WatchStateChanged) -> None:
        self.query_one(DashboardPane).set_watch_status(message.state, message.detail)
        if message.state == "error":
            self.notify(f"Watch error: {message.detail}", severity="error")
        self.refresh_all()

    def on_cycle_summary(self, message: CycleSummary) -> None:
        self.query_one("#watch-log", RichLog).write(
            f"cycle: {message.duration_s:.1f}s · {message.counts.get('APPLIED', 0)} applied "
            f"(+{message.jobs_applied}) · spend ${message.cost:.4f} ({message.spend_delta:+.4f})"
        )
        self.notify(
            f"Cycle done: {message.jobs_applied} applied, ${message.spend_delta:+.4f} spend"
        )

    def on_approval_requested(self, message: ApprovalRequested) -> None:
        self._notify_send(f"FlowJob: application ready for approval — {message.job_id}")
        self.push_screen(ApprovalModal(message.job_id))

    def on_pause_requested(self, message: PauseRequested) -> None:
        self._notify_send(f"FlowJob: form paused — {message.prompt}")
        self.push_screen(PauseModal(message.prompt))

    @staticmethod
    def _notify_send(text: str) -> None:
        try:
            subprocess.run(["notify-send", text], check=False)
        except OSError:
            pass

    def on_grill_output(self, message: GrillOutput) -> None:
        self.query_one(HitlWorkspace).on_grill_output(message)

    def on_grill_ended(self, message: GrillEnded) -> None:
        self.query_one(HitlWorkspace).on_grill_ended(message)

    def focus_chat_input(self) -> None:
        self.query_one("#grill-input", Input).focus()

    def _selected(self) -> dict | None:
        return self.query_one(JobsWorkspace).selected_job

    def action_approve(self) -> None:
        self._resolve_selected(True)

    def action_reject(self) -> None:
        self._resolve_selected(False)

    def _resolve_selected(self, approve: bool) -> None:
        job = self._selected()
        if not job:
            self.notify("Select a job in the Jobs tab first", severity="warning")
            return
        if job["state"] != "PENDING_APPROVAL":
            self.notify(f"Job is {job['state']} — approval applies to pending-approval jobs only", severity="warning")
            return
        if not self.approval.resolve(job["id"], approve):
            self.notify(
                "No active cycle is awaiting approval for this job — start the watch first.",
                severity="warning",
            )
            return
        self.notify("Approved — applying…" if approve else "Rejected — job skipped")
        self.refresh_all()

    def action_grill(self) -> None:
        job = self._selected()
        if not job:
            self.notify("Select a job in the Jobs tab first", severity="warning")
            return
        if job["state"] != "NEEDS_EVIDENCE":
            self.notify(f"Job is {job['state']} — grilling applies to needs-evidence jobs only", severity="warning")
            return
        self.start_grill(job["id"])

    def start_grill(self, job_id: str) -> None:
        if not self.grill.start(job_id):
            self.notify("A grilling session is already running", severity="warning")
            return
        self.action_go_tab("hitl")
        self.notify("Grilling session started — answer the interviewer in the chat")
        self.focus_chat_input()

    def action_retry(self) -> None:
        from src.tui import queries

        job = self._selected()
        if not job:
            self.notify("Select a job in the Jobs tab first", severity="warning")
            return
        if job["state"] not in FAIL_STATES:
            self.notify(f"Job is {job['state']} — retry applies to failed jobs only", severity="warning")
            return
        target = queries.requeue_job(job["id"])
        if target:
            self.notify(f"Re-queued to {target}")
        else:
            self.notify("Re-queue failed", severity="error")
        self.refresh_all()

    def action_open_url(self) -> None:
        job = self._selected()
        if not job or not job["url"]:
            self.notify("No URL for this job", severity="warning")
            return
        webbrowser.open(job["url"])

    def action_open_dir(self) -> None:
        import os

        job = self._selected()
        if not job:
            self.notify("Select a job in the Jobs tab first", severity="warning")
            return
        path = os.path.dirname(job["cv_path"] or "")
        if not path or not os.path.isdir(path):
            self.notify("No resume directory for this job yet", severity="warning")
            return
        webbrowser.open(f"file://{path}")
