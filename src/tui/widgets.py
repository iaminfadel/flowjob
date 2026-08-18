"""Cockpit widgets: dashboard, jobs browser + detail pane, LLM logs,
settings forms, HITL inbox + grill chat, and the approval modal."""

from __future__ import annotations

import time
from typing import Protocol, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Rule,
    Select,
    Static,
)

from src.db.models import JobState
from src.tui import queries
from src.tui.approval import ApprovalManager
from src.tui.grill import GrillManager
from src.tui.pause import PauseManager
from src.tui.watch import WatchManager


class CockpitProtocol(Protocol):
    approval: ApprovalManager
    grill: GrillManager
    watch_manager: WatchManager
    pause: PauseManager

    def refresh_all(self) -> None: ...

    def start_grill(self, job_id: str) -> None: ...

    def focus_chat_input(self) -> None: ...

    def notify(self, message: str, *, severity: str = "information", title: str | None = None) -> None: ...


def as_cockpit(app) -> CockpitProtocol:
    return cast(CockpitProtocol, app)
from src.tui import settings as settings_mod

LOGO = r""" _____ _     _____        __  _  ___  ____
|  ___| |   / _ \ \      / / | |/ _ \| __ )
| |_  | |  | | | \ \ /\ / /  | | | | |  _ \
|  _| | |__| |_| |\ V  V / |_| | |_| | |_) |
|_|   |_____\___/  \_/\_/ \___/ \___/|____/"""

STATES = [s.value for s in JobState]

FAIL_STATES = {s.value for s in JobState if s.value in {"FAILED", "TAILOR_FAIL", "EDIT_FAIL"}}


def state_style(state: str) -> str:
    if state == "PENDING_APPROVAL":
        return "bold #FFB454"
    if state == "APPLIED":
        return "green"
    if state in FAIL_STATES:
        return "red"
    if state == "NEEDS_EVIDENCE":
        return "bold #7AA2F7"
    return "default"


class RefreshAll(Message):
    pass


class DashboardPane(Vertical):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._countdown_end: float | None = None
        self._countdown_total: float = 0
        self._countdown_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Static(LOGO, id="logo")
        yield Static("", id="dash-stats")
        yield Static("", id="dash-counts")
        yield Rule()
        yield Label("Watch")
        yield Static("", id="watch-status", classes="watch-status")
        yield ProgressBar(id="watch-countdown", show_eta=False)
        with Horizontal(id="watch-buttons"):
            yield Button("Start", id="watch-start", variant="primary")
            yield Button("Stop", id="watch-stop", variant="error")
            yield Button("Run now", id="watch-runnow")
        yield RichLog(id="watch-log", auto_scroll=True, highlight=True, markup=True)

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        counts = queries.state_counts()
        spend = queries.spend_summary()
        last = queries.last_cycle() or "never"
        total = sum(counts.values())
        stats = self.query_one("#dash-stats", Static)
        stats.update(
            f"[bold]Total jobs:[/] {total}   [bold]Last cycle:[/] {last}   "
            f"[bold]LLM spend:[/] ${spend['cost_usd']:.4f} ({spend['calls']} calls, "
            f"{spend['tokens']:,} tokens, {spend['failures']} failures)"
        )
        cards = "   ".join(
            f"[{state_style(s)}]{s}: {counts[s]}[/]" for s in STATES
        )
        self.query_one("#dash-counts", Static).update(cards)

    def set_watch_status(self, state: str, detail: str = "") -> None:
        self.query_one("#watch-status", Static).update(
            f"Watch: {state}" + (f" ({detail})" if detail else "")
        )
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer = None
        bar = self.query_one("#watch-countdown", ProgressBar)
        if state == "countdown":
            minutes = float(detail or 0)
            self._countdown_total = max(minutes * 60, 1.0)
            self._countdown_end = time.monotonic() + self._countdown_total
            bar.update(progress=0.0, total=1.0)
            self._countdown_timer = self.set_interval(1.0, self._tick_countdown)
        else:
            self._countdown_end = None
            bar.update(progress=0.0, total=1.0)

    def _tick_countdown(self) -> None:
        if self._countdown_end is None:
            return
        remaining = self._countdown_end - time.monotonic()
        elapsed_frac = 1.0 - max(remaining, 0.0) / self._countdown_total
        bar = self.query_one("#watch-countdown", ProgressBar)
        bar.update(progress=elapsed_frac, total=1.0)
        status = self.query_one("#watch-status", Static)
        mm, ss = divmod(int(max(remaining, 0)), 60)
        status.update(f"Watch: countdown ({mm:02d}:{ss:02d} remaining)")
        if remaining <= 0:
            if self._countdown_timer is not None:
                self._countdown_timer.stop()
                self._countdown_timer = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        watch = as_cockpit(self.app).watch_manager
        if event.button.id == "watch-start":
            if not watch.start():
                self.app.notify("Watch already running")
            else:
                self.app.notify("Watch started")
        elif event.button.id == "watch-stop":
            watch.stop()
            self.app.notify("Watch stopping…")
        elif event.button.id == "watch-runnow":
            if watch.is_running():
                watch.run_now()
                self.app.notify("Running a cycle now")
            else:
                self.app.notify("Watch is not running")


class JobsTable(DataTable):
    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.add_column("Title", key="title", width=28)
        self.add_column("Company", key="company", width=18)
        self.add_column("Location", key="location", width=15)
        self.add_column("State", key="state", width=16)
        self.add_column("Fit", key="fit", width=5)
        self.add_column("Edit", key="edit", width=5)
        self.row_job_ids: list[str] = []

    def refresh_rows(self, state_filter: str = "ALL") -> None:
        self.clear()
        self.row_job_ids = []
        for job in queries.jobs(state_filter):
            self.row_job_ids.append(job["id"])
            self.add_row(
                Text(job["title"]),
                job["company"],
                job["location"],
                Text(job["state"], style=state_style(job["state"])),
                str(job["fit_score"] or "-"),
                str(job["edit_score"] or "-"),
                key=job["id"],
            )

    @property
    def selected_id(self) -> str | None:
        if self.cursor_row is None:
            return None
        if self.cursor_row >= len(self.row_job_ids):
            return None
        return self.row_job_ids[self.cursor_row]


class JobDetailPane(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static("", id="detail-title")
        yield Static("", id="detail-meta")
        yield Static("", id="detail-scores")
        yield Static("", id="detail-cv")
        yield Static("", id="detail-errors", classes="error-block")
        yield Static("", id="detail-actions")
        yield Rule()
        yield Label("Job description")
        yield Static("", id="detail-jd", classes="jd")
        yield Rule()
        yield Label("Grilling transcript")
        yield Static("", id="detail-transcript", classes="jd")

    def show(self, job: dict) -> None:
        state = job["state"]
        style = state_style(state)
        self.query_one("#detail-title", Static).update(
            Text(f"{job['title']} — {job['company']}", style="bold")
        )
        self.query_one("#detail-meta", Static).update(
            f"{job['location']} · posted {job['posted_date']} · {job['url']}"
        )
        self.query_one("#detail-scores", Static).update(
            f"State: {Text(state, style=style)}   Fit: {job['fit_score'] or '-'}/100   "
            f"Edit: {job['edit_score'] or '-'}/100"
        )
        cv = job["cv_path"] or ""
        self.query_one("#detail-cv", Static).update(
            f"CV: {cv if cv else '(not generated yet)'}"
        )

        err_widget = self.query_one("#detail-errors", Static)
        if state in FAIL_STATES:
            err = queries.error_record(job["id"])
            if err:
                err_widget.update(
                    f"[red]Error:[/] {err['agent_name']} — {err['error_type']} "
                    f"(retries: {err['retry_count']})\n{err['stack_trace'][:600]}"
                )
                err_widget.display = True
            else:
                err_widget.update("")
                err_widget.display = False
        else:
            err_widget.update("")
            err_widget.display = False

        hints = []
        if state == "PENDING_APPROVAL":
            hints = ["[a] approve", "[r] reject"]
        elif state == "NEEDS_EVIDENCE":
            hints = ["[g] open grill"]
        elif state in FAIL_STATES:
            hints = ["[t] retry"]
        hints.append("[o] open url")
        if cv:
            hints.append("[d] open resume dir")
        self.query_one("#detail-actions", Static).update("   ".join(hints))

        self.query_one("#detail-jd", Static).update(job["jd_text"])

        gaps = job["grilling_transcript"].get("gaps", {})
        if gaps:
            lines = []
            for req, gap in gaps.items():
                badge = gap.get("status", "pending")
                badge_style = {"completed": "green", "dropped": "dim", "pending": "bold #FFB454"}.get(badge, "default")
                turns = gap.get("turns", [])
                n = len([t for t in turns if t.get("role") == "candidate"])
                lines.append(f"[{badge_style}]{badge}[/] {req} ({n} answers)")
            self.query_one("#detail-transcript", Static).update("\n".join(lines))
            self.query_one("#detail-transcript", Static).display = True
        else:
            self.query_one("#detail-transcript", Static).update("")
            self.query_one("#detail-transcript", Static).display = False


class JobsWorkspace(Horizontal):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical(id="jobs-col"):
            yield Select(
                [(s, s) for s in ["ALL", *STATES]],
                value="ALL",
                prompt="State filter",
                id="state-filter",
            )
            yield JobsTable(id="jobs-table")
        yield JobDetailPane(id="job-detail")

    @property
    def selected_job(self) -> dict | None:
        table = self.query_one(JobsTable)
        job_id = table.selected_id
        if job_id is None:
            return None
        return queries.job_detail(job_id)

    def on_mount(self) -> None:
        self.query_one(JobsTable).refresh_rows()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "state-filter":
            value = str(event.value) if event.value is not None else "ALL"
            self.query_one(JobsTable).refresh_rows(value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._show_row(event.row_key.value)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_row(event.row_key.value)

    def _show_row(self, job_id: object) -> None:
        job = queries.job_detail(str(job_id))
        if job:
            self.query_one(JobDetailPane).show(job)


class LogsPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("", id="logs-stats")
        yield Rule()
        yield RichLog(id="log-stream", auto_scroll=False, highlight=True, markup=True)

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        spend = queries.spend_summary()
        self.query_one("#logs-stats", Static).update(
            f"LLM interactions — total ${spend['cost_usd']:.4f} · "
            f"{spend['tokens']:,} tokens ({spend['cached_tokens']:,} cached) · "
            f"{spend['failures']} failures"
        )
        log = self.query_one("#log-stream", RichLog)
        log.clear()
        for r in reversed(queries.llm_logs()):
            flag = "ok" if r["success"] else "ERROR"
            style = "green" if r["success"] else "red"
            log.write(
                Text(
                    f"[{r['timestamp']}] {r['agent_name']:<12} {r['provider']}/{r['model']:<18} "
                    f"{r['tokens']:>6} tok  ${r['cost_usd']:<8.4f} {r['latency_ms']:>5}ms  ",
                    style=style,
                )
                + Text(flag)
            )


class SettingsPane(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static("", id="env-banner", classes="error-block")
        for section, fields in settings_mod.SECTION_FIELDS.items():
            yield Label(f"[bold]  {section}[/]", id=f"cfg-head-{section}")
            for key, (label, ftype) in fields.items():
                widget_id = f"cfg-{section}-{key}"
                if ftype == "bool":
                    yield Checkbox(label, id=widget_id)
                else:
                    secret = key.endswith("_key") or key == "openrouter_api_key"
                    yield Input(placeholder=label, id=widget_id, password=secret)
            yield Rule()
        yield Static(
            "Providers chain: edited manually in flowjob.yaml (out of TUI scope).",
            classes="note",
        )
        with Horizontal():
            yield Button("Save", id="settings-save", variant="primary")
            yield Button("Re-validate", id="settings-validate")

    def on_mount(self) -> None:
        self.load_values()
        self.refresh_banner()

    def load_values(self) -> None:
        doc = settings_mod.round_trip_load()
        effective = None
        if settings_mod.env_overrides_active():
            from src.config import load_config

            effective = load_config("flowjob.yaml")
        for section, fields in settings_mod.SECTION_FIELDS.items():
            section_data = doc.get(section) or {}
            for key, (label, ftype) in fields.items():
                widget_id = f"cfg-{section}-{key}"
                value = section_data.get(key)
                if effective is not None:
                    eff = getattr(getattr(effective, section, None), key, None)
                    if eff is not None and str(eff) != str(value):
                        value = eff
                if value is None:
                    continue
                if ftype == "bool":
                    self.query_one(f"#{widget_id}", Checkbox).value = bool(value)
                else:
                    self.query_one(f"#{widget_id}", Input).value = str(value)

    def refresh_banner(self) -> None:
        active = settings_mod.env_overrides_active()
        banner = self.query_one("#env-banner", Static)
        if active:
            names = ", ".join(active)
            banner.update(
                f"[yellow]Env override active ({names}) — edits to overridden "
                "fields won't take effect until unset.[/]"
            )
            banner.display = True
        else:
            banner.display = False

    def collect(self) -> dict:
        raw: dict = {}
        for section, fields in settings_mod.SECTION_FIELDS.items():
            section_data: dict = {}
            for key, (label, ftype) in fields.items():
                widget_id = f"cfg-{section}-{key}"
                if ftype == "bool":
                    section_data[key] = self.query_one(f"#{widget_id}", Checkbox).value
                else:
                    text = self.query_one(f"#{widget_id}", Input).value
                    if ftype == "int":
                        try:
                            section_data[key] = int(text)
                        except ValueError:
                            section_data[key] = text  # guardrail reports non-int
                    else:
                        section_data[key] = text
            raw[section] = section_data
        return raw

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save":
            raw = self.collect()
            try:
                settings_mod.save_settings(raw)
            except settings_mod.SettingsValidationError as exc:
                self.app.notify("Settings invalid: " + "; ".join(exc.errors), severity="error")
                return
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Save failed: {exc}", severity="error")
                return
            self.app.notify("Settings saved")
            self.load_values()
        elif event.button.id == "settings-validate":
            errors = settings_mod.run_full_validation()
            if errors:
                self.app.notify("Validation failed: " + "; ".join(errors), severity="error")
            else:
                self.app.notify("Validation OK — config, resume, and DB all good")


class ApprovalList(VerticalScroll):
    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        for child in list(self.children):
            child.remove()
        pending = queries.jobs("PENDING_APPROVAL")
        if not pending:
            yield_label = Label("(none)", classes="dim-row")
            self.mount(yield_label)
        for job in pending:
            row = Horizontal(
                Label(f"{job['title']} — {job['company']}", classes="approval-label"),
                Button("Approve", id=f"approve-{job['id']}", variant="success"),
                Button("Reject", id=f"reject-{job['id']}", variant="error"),
                classes="approval-row",
            )
            self.mount(row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith(("approve-", "reject-")):
            event.stop()
            job_id = event.button.id.split("-", 1)[1]
            approve = event.button.id.startswith("approve-")
            if not as_cockpit(self.app).approval.resolve(job_id, approve):
                as_cockpit(self.app).notify(
                    "No active cycle is awaiting approval for this job — start the watch first.",
                    severity="warning",
                )
            else:
                as_cockpit(self.app).notify("Approved — applying…" if approve else "Rejected — job skipped")
                self.post_message(RefreshAll())


class NeedsEvidenceList(VerticalScroll):
    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        for child in list(self.children):
            child.remove()
        jobs = queries.jobs("NEEDS_EVIDENCE")
        if not jobs:
            self.mount(Label("(none)", classes="dim-row"))
            return
        for job in jobs:
            row = Horizontal(
                Label(f"{job['title']} — {job['company']}", classes="approval-label"),
                Button("Open grill", id=f"grill-{job['id']}", variant="primary"),
                classes="approval-row",
            )
            self.mount(row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("grill-"):
            event.stop()
            job_id = event.button.id.split("-", 1)[1]
            as_cockpit(self.app).start_grill(job_id)


class PauseList(VerticalScroll):
    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        for child in list(self.children):
            child.remove()
        pending = as_cockpit(self.app).pause.pending()
        if not pending:
            self.mount(Label("(none)", classes="dim-row"))
            return
        for idx, prompt in enumerate(pending):
            row = Horizontal(
                Label(prompt[:80], classes="approval-label"),
                Button("Continue", id=f"pauseresume-{idx}", variant="primary"),
                classes="approval-row",
            )
            self.mount(row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("pauseresume-"):
            event.stop()
            idx = int(event.button.id.split("-", 1)[1])
            pending = as_cockpit(self.app).pause.pending()
            if idx >= len(pending):
                return
            if as_cockpit(self.app).pause.continue_(pending[idx]):
                as_cockpit(self.app).notify("Pause cleared — applicator resumed")
                self.post_message(RefreshAll())


class GrillChat(Vertical):
    def compose(self) -> ComposeResult:
        yield RichLog(id="grill-chat", auto_scroll=True, highlight=True, markup=True)
        with Horizontal(id="grill-input-row"):
            yield Input(placeholder="Reply to the interviewer…", id="grill-input")
            yield Button("Send", id="grill-send", variant="primary")

    def _send(self) -> None:
        inp = self.query_one("#grill-input", Input)
        text = inp.value.strip()
        if not text:
            return
        log = self.query_one("#grill-chat", RichLog)
        if not as_cockpit(self.app).grill.send_answer(text):
            self.app.notify("No active grilling session", severity="warning")
            return
        log.write(Text(f"You: {text}"))
        inp.value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "grill-send":
            self._send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "grill-input":
            self._send()

    def append_line(self, line: str) -> None:
        self.query_one("#grill-chat", RichLog).write(line)


class HitlWorkspace(Horizontal):
    def compose(self) -> ComposeResult:
        with Vertical(id="hitl-left"):
            yield Label("Approval inbox")
            yield ApprovalList(id="approval-list")
            yield Rule()
            yield Label("Needs evidence — open a grilling session")
            yield NeedsEvidenceList(id="evidence-list")
            yield Rule()
            yield Label("Paused applications — browser is open")
            yield PauseList(id="pause-list")
            yield Rule()
            yield Label("Unfixable")
            yield Static("", id="unfixable-list", classes="jd")
        with Vertical(id="grill-col"):
            yield Label("Grilling session")
            yield GrillChat(id="grill-chat-pane")

    def refresh_data(self) -> None:
        self.query_one("#approval-list", ApprovalList).refresh_data()
        self.query_one("#evidence-list", NeedsEvidenceList).refresh_data()
        self.query_one("#pause-list", PauseList).refresh_data()
        unfixable = queries.jobs("UNFIXABLE")
        text = "\n".join(f"{j['title']} — {j['company']}" for j in unfixable) or "(none)"
        self.query_one("#unfixable-list", Static).update(text)

    def on_grill_output(self, message) -> None:
        self.query_one("#grill-chat-pane", GrillChat).append_line(message.line)

    def on_grill_ended(self, message) -> None:
        chat = self.query_one("#grill-chat-pane", GrillChat)
        chat.append_line("— session ended —")
        if message.note:
            as_cockpit(self.app).notify(f"Grill ended with error: {message.note}", severity="error")
        else:
            as_cockpit(self.app).notify("Grilling session ended")
        as_cockpit(self.app).refresh_all()
        as_cockpit(self.app).focus_chat_input()


class ApprovalModal(ModalScreen[None]):
    BINDINGS = [
        Binding("y", "approve", "Approve"),
        Binding("n", "reject", "Reject"),
        Binding("escape", "reject", "Reject"),
    ]

    def __init__(self, job_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.job_id = job_id

    def compose(self) -> ComposeResult:
        job = queries.job_detail(self.job_id) or {}
        yield Static(
            "[bold]Application ready for approval[/]",
            id="modal-title",
            classes="modal-box",
        )
        yield Static(
            f"{job.get('title', '?')} — {job.get('company', '?')}\n"
            f"{job.get('location', '')} · fit {job.get('fit_score') or '-'} · "
            f"edit {job.get('edit_score') or '-'}\n"
            f"{job.get('jd_text', '')[:400]}",
            id="modal-body",
            classes="modal-box",
        )
        with Horizontal(classes="modal-box"):
            yield Button("Approve (y)", id="modal-approve", variant="success")
            yield Button("Reject (n)", id="modal-reject", variant="error")

    def _resolve(self, approve: bool) -> None:
        as_cockpit(self.app).approval.resolve(self.job_id, approve)
        as_cockpit(self.app).notify("Approved — applying…" if approve else "Rejected — job skipped")
        as_cockpit(self.app).refresh_all()
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-approve":
            self._resolve(True)
        elif event.button.id == "modal-reject":
            self._resolve(False)

    def action_approve(self) -> None:
        self._resolve(True)

    def action_reject(self) -> None:
        self._resolve(False)


class PauseModal(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Dismiss"),
    ]

    def __init__(self, prompt: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Form paused — browser is open[/]",
            id="modal-title",
            classes="modal-box",
        )
        yield Static(
            f"Fill the field in the browser, then continue:\n\n{self.prompt}",
            id="modal-body",
            classes="modal-box",
        )
        with Horizontal(classes="modal-box"):
            yield Button("Continue", id="modal-pause-continue", variant="primary")

    def _continue(self) -> None:
        as_cockpit(self.app).pause.continue_(self.prompt)
        as_cockpit(self.app).refresh_all()
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-pause-continue":
            self._continue()

    def action_dismiss_modal(self) -> None:
        self._continue()
