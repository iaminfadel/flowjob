# Research: Textual API Landscape for the Cockpit TUI

> Resolves [#83](https://github.com/iaminfadel/flowjob/issues/83) — part of [#82](https://github.com/iaminfadel/flowjob/issues/82)
>
> Question: facts for building the FlowJob cockpit (dashboard, jobs table with filters, job detail pane, LLM log viewer, settings forms, HITL chat/approval panes) on Textual, with blocking pipeline Python running in background threads on Python 3.12.

## Primary Sources

- Official docs: [https://textual.textualize.io/](https://textual.textualize.io/) (widget reference, guide chapters)
- PyPI project page: [https://pypi.org/project/textual/](https://pypi.org/project/textual/)
- GitHub repo: [https://github.com/Textualize/textual](https://github.com/Textualize/textual) (+ [CHANGELOG.md](https://github.com/Textualize/textual/blob/main/CHANGELOG.md), GitHub API for repo stats)

---

## 1. Version & Python 3.12 Support — ✅ Safe

| Fact | Value | Source |
|------|-------|--------|
| Latest stable | **8.2.8** (released 2026-06-30) | PyPI JSON (`info.version`); CHANGELOG `## [8.2.8] - 2026-06-30` |
| Python requirement | `>=3.9,<4.0` | PyPI JSON (`requires_python`) |
| Python 3.12 | Explicitly supported (classifier `Programming Language :: Python :: 3.12`), and the version Textual itself recommends for demos (`uvx --python 3.12 textual-demo`) | PyPI JSON; GitHub README |
| Python history | 8.2.x dropped nothing recent; **6.3.0 (2025-10-11) dropped Python 3.8 and added Python 3.14** | CHANGELOG `## [6.3.0]` |

Docs state "Textual requires Python 3.9 or later" ([Getting started](https://textual.textualize.io/getting_started/)). Python 3.12 is squarely in the supported window — no compatibility concerns for the cockpit.

### Version milestones relevant to the cockpit

| Version | When | What |
|---------|------|------|
| 0.3.0 | 2022-10-31 | `App.run_test` (Pilot) added |
| 0.14.0 | 2023-03-09 | `ContentSwitcher` added |
| 0.16.0 | 2023-03-22 | `TabbedContent` added |
| 0.18.0 | 2023-04-04 | Worker API added (`run_worker`, `@work`) |

Sources: [CHANGELOG](https://github.com/Textualize/textual/blob/main/CHANGELOG.md) entries `## [0.3.0]`, `## [0.14.0]`, `## [0.16.0]`, `## [0.18.0]`; widget docs mark "Added in version 0.16.0" ([TabbedContent](https://textual.textualize.io/widgets/tabbed_content/), [Workers guide](https://textual.textualize.io/guide/workers/), [Testing guide](https://textual.textualize.io/guide/testing/)).

## 2. Widget Inventory for the Cockpit Surfaces

Full widget list (37 widgets): Button, Checkbox, Collapsible, ContentSwitcher, DataTable, Digits, DirectoryTree, Footer, Header, Input, Label, Link, ListItem, ListView, LoadingIndicator, Log, MarkdownViewer, Markdown, MaskedInput, OptionList, Placeholder, Pretty, ProgressBar, RadioButton, RadioSet, RichLog, Rule, Select, SelectionList, Sparkline, Static, Switch, TabbedContent, Tabs, TextArea, Toast, Tree — [Widget index](https://textual.textualize.io/widget_gallery/).

### Dashboard / jobs table → `DataTable`

- Add rows/columns with `add_columns` / `add_rows`; rows and columns carry **keys** (use the DB primary key as row key so rows survive sorting/removal); coordinates → keys via `coordinate_to_cell_key`. ([DataTable guide](https://textual.textualize.io/widgets/data_table/))
- **Per-cell styling**: cells accept Rich `Text` renderables (`Text(str, style="italic #03AC13", justify="right")`) — per-cell color/emphasis/justification, plus `zebra_stripes`, `fixed_columns`/`fixed_rows`, `cursor_type` (cell/row/column/none). Same source.
- **Sorting**: built-in `sort(*columns, key=None, reverse=False)` — sort by column keys (natural order) or a key function over multiple columns (`sort("hours", "rate", key=lambda h, r: h*r)`), `reverse` supported. Same source.
- **Filtering**: **no built-in filter**. Docs explicitly hand filtering to the app: "Applications may have custom rules for … repopulating tables after searching or filtering". Pattern: filter in Python, then `clear()` + `add_rows`, or `remove_row(key)` per row; incremental updates via `update_cell` / `update_cell_at`. Same source.
- Row/col selection messages: `RowSelected`, `CellSelected`, `ColumnSelected`, `HeaderSelected` etc. — basis for the job-detail pane binding. Same source.
- **Alternatives**: no separate "DataTable 2" exists in Textual. For log-like streams use `RichLog`; for simple lists `ListView` / `OptionList` / `SelectionList` (all in the widget index). DataTable is *the* table widget — the docs describe it as "an efficiently displayed and updated table capable for most applications".

### Navigation → `TabbedContent` (not Tabs alone, StackedContent is gone)

- **`TabbedContent`** (added 0.16.0) combines `Tabs` + `ContentSwitcher`: "Switch between mutually exclusive content panes via a row of tabs". Compose with `TabPane("Title", id=...)`, switch programmatically via the `active` reactive, initial tab via `initial=`, hide/disable tabs at runtime (`hide_tab`, `disable_tab`, `enable_tab`, `show_tab`, `add_pane`, `remove_pane`). Emits `TabActivated`. ([TabbedContent](https://textual.textualize.io/widgets/tabbed_content/))
- **`Tabs`** standalone if you want the tab strip without panes; **`ContentSwitcher`** (added 0.14.0) for programmatic pane switching with no visible tabs ([widget index](https://textual.textualize.io/widget_gallery/)).
- ⚠️ **`StackedContent` no longer exists** — absent from the current widget index and from `src/textual/containers.py` at HEAD. Use `ContentSwitcher` (its successor role) or `TabbedContent`.
- Recommendation for cockpit: `TabbedContent` for main areas (Dashboard / Jobs / LLM Logs / Settings / HITL), `ContentSwitcher` inside panes where the app switches views programmatically (e.g. HITL chat ↔ approval).

### Forms → `Input`, `Select`, `TextArea`, `Checkbox`, `Button` (+ friends)

All present in the widget index: `Input` (text; `Input.Changed` message; `placeholder`, `restrict` — used in the [Workers guide](https://textual.textualize.io/guide/workers/) example), `Select` (dropdown of options), `TextArea` (multi-line editor; gained `placeholder`/`suggestion`/`update_suggestion` in 6.0.0), `Checkbox`, `Button` (variants success/error — for Approve/Reject), plus `Switch`, `RadioSet`, `OptionList`, `MaskedInput` where useful. ([widget index](https://textual.textualize.io/widget_gallery/), CHANGELOG `## [6.0.0]`)

### Chrome → `Header`, `Footer`, `BINDINGS`

- **`Header`**: "A header widget with icon and clock" — `show_clock`, `tall` (single-cell vs tall, toggled by clicking), `time_format`, `icon`, `screen_title`/`screen_sub_title`; title format overridable via `App.format_title` / `Header.format_title` (added 6.0.0). ([Header](https://textual.textualize.io/widgets/header/), CHANGELOG `## [6.0.0]`)
- **`Footer`**: displays "the bindings for the currently focused widget" — i.e. it auto-renders `BINDINGS` (key → action → description) as a bottom bar; reactives `combine_groups`, `compact`, `show_command_palette`. ([Footer](https://textual.textualize.io/widgets/footer/))
- `BINDINGS` class attribute + `action_*` methods = the standard keybinding mechanism (see the TabbedContent example binding `l`/`j`/`p` to tab switching).

### Log viewer → `RichLog` (or `Log`)

- **`RichLog`**: "A widget for logging Rich renderables and text" — `write()` for streaming lines, `auto_scroll`, `wrap`, `max_lines`/`lines` (retention cap — keeps unbounded LLM output bounded), `markup`, `highlighter`, `clear()`. Ideal for the LLM log viewer + HITL chat transcript. ([RichLog](https://textual.textualize.io/widgets/rich_log/))
- `Log` widget also exists (simpler plain-text log) — [widget index](https://textual.textualize.io/widget_gallery/).

### Detail pane / lists / misc

- `Static` (fixed text/rich content; note `renderable` renamed to `content` in 6.0.0 — see §6), `ListView`/`ListItem`, `Tree`/`TreeNode` (hierarchies; `expand_all`/`collapse_all` since 0.11.0), `Markdown`/`MarkdownViewer` (for LLM markdown output), `ProgressBar`, `LoadingIndicator`, `Toast` (transient notifications). ([widget index](https://textual.textualize.io/widget_gallery/), CHANGELOG `## [0.11.0]`)

## 3. Worker / Thread Patterns for the Blocking Pipeline

Worker API added in 0.18.0; everything below from the [Workers guide](https://textual.textualize.io/guide/workers/) unless noted.

| Pattern | What it does |
|---------|--------------|
| `self.run_worker(coro_or_fn, exclusive=True)` | Runs a function in the background, returns a `Worker`. `exclusive=True` cancels previous workers (good for filter-as-you-type). |
| `@work` decorator | Same as `run_worker`, applied to a method; calling the method starts the worker (no `await` needed). Same args as `run_worker`. |
| `@work(thread=True)` (or `run_worker(..., thread=True)`) | Runs a **plain synchronous function on a real OS thread** — exactly the pattern for FlowJob's blocking pipeline (urllib/requests-style, CPU-bound, sync libs). ⚠️ Textual **raises an exception** if you put `@work` on a sync function without `thread=True`. |
| `run_in_thread` | ⚠️ **Does not exist** in Textual (checked against the whole CHANGELOG) — the ticket's tentative name; the actual API is `run_worker(..., thread=True)` / `@work(thread=True)` above. |
| `get_current_worker()` | Inside a worker: returns the `Worker` so you can check `worker.is_cancelled` between pipeline steps. Threads can't be force-cancelled (unlike coroutines) — cooperative cancellation is the only option. |
| `self.call_from_thread(fn, *args)` | From inside a thread worker, runs `fn` back on the main thread — the sanctioned way to touch UI/reactives from a thread. |
| `post_message(...)` | **Thread-safe** — the one UI API you may call directly from a thread worker. |

**Streaming progress from the pipeline into the UI (the docs' recommended pattern):** "If your worker needs to make multiple updates to the UI, it is a good idea to send custom messages and let the message handler update the state of the UI." I.e. the thread worker defines a custom `Message` subclass (e.g. `PipelineProgress(Message)`), calls `self.post_message(...)` (thread-safe) for each progress tick, and a handler on the widget/app updates `ProgressBar`, `RichLog`, `Static`, or `DataTable` accordingly. See §4 for the message mechanics.

**Worker lifecycle:** states `PENDING → RUNNING → CANCELLED | ERROR | SUCCESS` (`worker.state`, `worker.result`, `worker.error`); each state change posts `Worker.StateChanged` to the creating DOM node → handle via `on_worker_state_changed`. Workers are owned by their DOM node: removing the widget/screen or exiting the app cancels them. Default on exception: app exits with traceback; opt out with `exit_on_error=False`. To await from a handler: `await worker.wait()` (blocks the widget, so prefer events).

## 4. Event / Message System Basics

From the [Events and Messages guide](https://textual.textualize.io/guide/events/):

- Every widget has a **message queue** processed by an asyncio Task started at mount; messages are dispatched to handlers in order — this is why the UI stays responsive and why `post_message` from a thread is safe (it enqueues; the main thread processes).
- Messages with `bubble=True` (input events, widget messages like `Button.Pressed`) propagate from widget → parent → … → App; handlers can stop it with `stop()`; `prevent_default()` stops base-class handlers.
- **Custom messages**: subclass `Message`, attach data in the constructor, send with `post_message()` ("To send a message call the `post_message()` method. This will place a message on the widget's message queue and run any message handlers."). Common pattern: widget posts to itself and lets it bubble so ancestors handle it.
- **Handlers**: naming convention `on_<namespace>_<message>` (e.g. `on_input_changed` for `Input.Changed`) **or** the `@on(...)` decorator — `@on(Button.Pressed)`, `@on(TabbedContent.TabActivated, pane="#home")` (CSS-selector filtering via `ALLOW_SELECTOR_MATCH` attributes). Handlers may be `async def`.

This is the full loop for streaming pipeline output: thread worker → `post_message(custom_msg)` → bubbling handler → mutate `RichLog`/`ProgressBar`/`DataTable`/`Static`.

## 5. Pilot Testing API

- **`App.run_test()`** — async context manager, runs the app **headless**, returns a **`Pilot`**. Added in **0.3.0 (2022-10-31)** ("Added App.run_test context manager", "Added auto_pilot to App.run") — [CHANGELOG](https://github.com/Textualize/textual/blob/main/CHANGELOG.md). Requires an async test framework; docs use pytest + **pytest-asyncio** (`asyncio_mode = auto`). ([Testing guide](https://textual.textualize.io/guide/testing/))
- **Driving the app** (all from the [Testing guide](https://textual.textualize.io/guide/testing/)):
  - `await pilot.press("h", "e", "l", "l", "o")` — keys, non-printable names (`"enter"`), `"ctrl+"` modifiers
  - `await pilot.click("#approve")` — CSS selector or widget; `offset=(x, y)`, `times=2/3` for double/triple clicks, `shift`/`meta`/`control` modifiers
  - `await pilot.hover("#widget")`, `await pilot.pause()` — drain pending messages before asserting (essential for message-bubbling timing)
  - `await pilot.resize_terminal(...)` (added 0.53.0), `run_test(size=(100, 50))` for terminal size; `pilot.mouse_down`/`mouse_up` (0.42.0)
  - Asserting state = plain asserts on widgets: `assert app.screen.styles.background == Color.parse("red")`, or query widgets (`query_one`) and check reactives/values.
- **Typing into inputs**: `pilot.press("a","b","c")` simulates keystrokes into the focused `Input`/`TextArea` (HITL answers, grill replies); click the input first if focus isn't there.
- **Threaded workers in tests**: no special API. Thread workers run on real OS threads during `run_test`; the docs' advice applies — after triggering a worker, `await pilot.pause()` (or `await worker.wait()`; the Workers guide documents `Worker.wait()`) so posted messages get processed before asserting. `message_hook` on `run_test` (added 0.27.0) can observe every message for stricter assertions.
- **Snapshot testing**: official `pytest-textual-snapshot` plugin renders the app to an SVG screenshot per test and diffs against a stored baseline (`snap_compare("app.py", press=[...], terminal_size=(100,50), run_before=...)`) — good for catching visual regressions in the cockpit layouts. ([Testing guide](https://textual.textualize.io/guide/testing/), [pytest-textual-snapshot repo](https://github.com/Textualize/pytest-textual-snapshot))

## 6. License, Maintenance Status, Breaking Changes

### License & health — ✅ No red flags

| Item | Value | Source |
|------|-------|--------|
| License | **MIT** | PyPI (`info.license`); GitHub API (`license: MIT`) |
| Repo | ~36.9k stars, ~1.3k forks, 352 open issues | GitHub API (queried 2026-08-18) |
| Activity | `pushed_at 2026-07-11`; 8.2.8 released 2026-06-30 | GitHub API; CHANGELOG |
| Backing | Textualize, Inc. (Will McGugan), active Discord; commercial products (Textual Web) share the framework | PyPI author metadata; repo description ("Run your apps in the terminal and a web browser") |
| Archived? | No | GitHub API |

### Breaking changes in the last major versions (5.0.0 → 8.x)

| Version | Date | Breaking changes that could hit the cockpit |
|---------|------|---------------------------------------------|
| 5.0.0 | 2025-07-25 | tree-sitter dep for `syntax` extras requires Python 3.10+; `Visual.render_strips` signature; Markdown component classes moved to `MarkdownBlock` |
| 6.0.0 | 2025-08-31 | `Static.renderable` → `content`; `Label(renderable=...)` → `content`; `HeaderTitle` is now static (no `text`/`sub_text` reactives); background-style line API change |
| 7.0.0 | 2026-01-03 | Minor: `update_node_styles` grew an `animate` param (effectively internal) |
| 8.0.0 | 2026-02-16 | `Select.BLANK` → `Select.NULL`; 50ms screen-switch delay; dismiss semantics for non-active screens |

Sources: [CHANGELOG](https://github.com/Textualize/textual/blob/main/CHANGELOG.md) sections `## [5.0.0]`, `## [6.0.0]`, `## [7.0.0]`, `## [8.0.0]` (plus 8.2.x entries).

**Verdict**: the two most recent majors (7.0.0, 8.0.0) are small and low-risk; the last genuinely disruptive majors were 5.0.0/6.0.0 (renames: `renderable`→`content` on `Static`/`Label`, `Select.BLANK`→`Select.NULL`). Version churn is steady (7.0.0 → 8.2.8 in ~6 months), so **pin `textual>=8.2,<9` in requirements** and re-run the Pilot test suite on upgrades. No deprecation-warning obligation upstream — rename-type breaks land without notice periods, so a changelog review is part of every upgrade.

## Recommendation Summary (surface → widget/API)

| Cockpit surface | Widgets / APIs |
|-----------------|----------------|
| Dashboard | `Header` + `DataTable` + `Static` widgets + `Footer` |
| Jobs table + filters | `DataTable` (`add_rows` w/ row keys, `sort()`, app-side filter + `clear()`/`remove_row`; `RowSelected` → detail pane) |
| Job detail pane | `ContentSwitcher` (or `TabbedContent` tab) + `Static`/`Markdown` |
| LLM log viewer | `RichLog` (`write`, `auto_scroll`, `max_lines`) |
| Settings forms | `Input`, `Select`, `TextArea`, `Checkbox`, `Button`, `Switch` |
| HITL chat / approval | `RichLog` (transcript) + `Input` + `Button(variant="success"/"error")`; `Toast` for notices |
| Navigation | `TabbedContent` w/ `TabPane(id=...)` + `BINDINGS`; `Footer` shows keys |
| Blocking pipeline | `@work(thread=True)` + `get_current_worker()` + `post_message` (thread-safe) → custom `Message` → handler updates UI |
| Tests | `App.run_test()` + `Pilot` (`press`, `click`, `pause`) + pytest-asyncio; `pytest-textual-snapshot` for visual regression |
