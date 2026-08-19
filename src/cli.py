import typer
import sys
from src.config import load_config
from src.db.store import init_db, pipeline_only
from src.db.models import JobState
from scripts.validate_resume import validate_resume as do_validate_resume

app = typer.Typer(help="FlowJob: Agentic Job Application Pipeline", no_args_is_help=True)

@app.callback()
def main():
    pass

@app.command()
def validate(
    resume: str = typer.Option("master_resume.md", help="Path to the master resume"),
    config: str = typer.Option("flowjob.yaml", help="Path to the configuration file")
):
    """Parse master_resume.md, validate flowjob.yaml, and initialize the DB."""
    typer.echo(f"Validating configuration...")
    
    # Validate YAML Config
    try:
        conf = load_config(config)
        typer.echo("✅ flowjob.yaml is valid.")
    except Exception as e:
        typer.echo(f"❌ Config validation failed: {e}")
        sys.exit(1)
        
    # Validate Master Resume
    typer.echo(f"\nValidating master resume...")
    is_valid = do_validate_resume(resume)
    if not is_valid:
        sys.exit(1)
        
    # Initialize SQLite Database
    typer.echo(f"\nInitializing database...")
    try:
        engine = init_db(conf.data.db_path)
        typer.echo(f"✅ Database initialized at {conf.data.db_path}.")
    except Exception as e:
        typer.echo(f"❌ Database initialization failed: {e}")
        sys.exit(1)
        
    typer.echo("\n🚀 Validation complete. FlowJob is ready.")

@app.command()
def login():
    """Launch headed browser to authenticate with LinkedIn and save state."""
    from src.tools.browser import login_linkedin
    typer.echo("Launching browser... Please log in to LinkedIn.")
    login_linkedin()
    typer.echo("✅ State saved!")

def build_agents():
    import os
    from src.config import load_config
    from src.agents.analyst import AnalystAgent
    from src.agents.tailor import TailorAgent
    from src.agents.editor import EditorAgent
    from src.agents.applicator import ApplicatorAgent
    from src.agents.coverage_critic import CoverageCriticAgent
    from src.agents.writer import WriterAgent
    
    cfg = load_config("flowjob.yaml")
    
    default_model = getattr(cfg.llm, "default_model", "google/gemini-2.5-pro")
    openrouter_base_url = getattr(cfg.llm, "openrouter_base_url", "https://openrouter.ai/api/v1")
    openrouter_api_key = getattr(cfg.llm, "openrouter_api_key", None)
    
    analyst_model = getattr(cfg.analyst, "model", default_model)
    tailor_model = getattr(cfg.tailor, "model", default_model)
    editor_model = getattr(cfg.editor, "model", default_model)
    critic_model = getattr(cfg.critic, "model", default_model)
    writer_model = getattr(cfg.writer, "model", default_model)
    
    return {
        "analyst": AnalystAgent(model_name=analyst_model, openrouter_base_url=openrouter_base_url, openrouter_api_key=openrouter_api_key),
        "tailor": TailorAgent(model_name=tailor_model, openrouter_base_url=openrouter_base_url, openrouter_api_key=openrouter_api_key),
        "critic": CoverageCriticAgent(model_name=critic_model, openrouter_base_url=openrouter_base_url, openrouter_api_key=openrouter_api_key),
        "writer": WriterAgent(model_name=writer_model, openrouter_base_url=openrouter_base_url, openrouter_api_key=openrouter_api_key),
        "editor": EditorAgent(model_name=editor_model, openrouter_base_url=openrouter_base_url, openrouter_api_key=openrouter_api_key),
        "applicator": ApplicatorAgent()
    }

@app.command()
def run(url: str = typer.Option(None, help="Process a single job URL instead of running Scout"), 
        dry_run: bool = typer.Option(False, help="Do not apply, save PDF and form answers to disk")):
    """Run the FlowJob pipeline."""
    from src.pipeline.orchestrator import run_pipeline
    typer.echo("🚀 Running FlowJob pipeline...")
    agents = build_agents()
    run_pipeline(agents=agents, url=url, dry_run=dry_run)

@app.command()
def watch():
    """Run the FlowJob pipeline continuously with jitter."""
    import time
    import random
    from src.config import load_config
    from src.pipeline.orchestrator import run_pipeline
    from src.pipeline.watch_lock import acquire_watch_lock, WatchLockHeldError
    from src.db.store import init_db

    cfg = load_config("flowjob.yaml")
    init_db(cfg.data.db_path)

    typer.echo("👀 Starting FlowJob in watch mode...")
    agents = build_agents()
    try:
        with acquire_watch_lock():
            while True:
                typer.echo("🚀 Running pipeline cycle...")
                
                run_pipeline(agents=agents)
                
                jitter_minutes = random.uniform(cfg.watch.min_wait_minutes, cfg.watch.max_wait_minutes)
                typer.echo(f"⏳ Sleeping for {jitter_minutes:.2f} minutes before next cycle...")
                time.sleep(jitter_minutes * 60)
    except WatchLockHeldError as e:
        typer.echo(f"❌ {e}")
        raise typer.Exit(code=1)

@app.command()
def status(config: str = typer.Option("flowjob.yaml", help="Path to the configuration file")):
    """Display basic DB summary counts and the last successful cycle timestamp."""
    from src.config import load_config
    from src.db.store import init_db, get_session
    from sqlmodel import select, func
    from src.db.models import Job, JobState
    
    try:
        conf = load_config(config)
        engine = init_db(conf.data.db_path)
    except Exception as e:
        typer.echo(f"❌ Failed to load config or DB: {e}")
        raise typer.Exit(code=1)

    with get_session(engine) as session:
        def count_state(state):
            statement = pipeline_only(select(func.count(Job.id)).where(Job.state == state))
            return session.exec(statement).one()

        new_count = count_state(JobState.NEW)
        analyzed_count = count_state(JobState.ANALYZED)
        drafted_count = count_state(JobState.DRAFTED)
        needs_evidence_count = count_state(JobState.NEEDS_EVIDENCE)
        unfixable_count = count_state(JobState.UNFIXABLE)
        skipped_count = count_state(JobState.SKIPPED)
        applied_count = count_state(JobState.APPLIED)
        pending_count = count_state(JobState.PENDING_APPROVAL)
        failed_count = count_state(JobState.FAILED)

        from src.db.models import PipelineRun
        statement = select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)
        last_run = session.exec(statement).first()
        last_cycle = last_run.timestamp if last_run else "Unknown (Never run or no record found)"

    typer.echo("📊 FlowJob Status:")
    typer.echo(f"  NEW: {new_count}")
    typer.echo(f"  ANALYZED: {analyzed_count}")
    typer.echo(f"  DRAFTED: {drafted_count}")
    typer.echo(f"  NEEDS_EVIDENCE: {needs_evidence_count}")
    typer.echo(f"  UNFIXABLE: {unfixable_count}")
    typer.echo(f"  SKIPPED: {skipped_count}")
    typer.echo(f"  PENDING_APPROVAL: {pending_count}")
    typer.echo(f"  APPLIED: {applied_count}")
    typer.echo(f"  FAILED: {failed_count}")
    typer.echo(f"\n🕒 Last successful cycle: {last_cycle}")

@app.command()
def add(
    title: str = typer.Option("", help="Job title"),
    company: str = typer.Option("", help="Company name"),
    url: str = typer.Option("", help="Job posting URL"),
    jd: str = typer.Option("", "--jd", help="Job description (pasted; no URL fetching)"),
    notes: str = typer.Option("", help="Free-form notes for this application"),
    cv: str = typer.Option(None, help="Path to a resume/CV file; copied into the resume store"),
    state: JobState = typer.Option(JobState.APPLIED, help="Initial state"),
    date_applied: str = typer.Option(None, help="Date applied (defaults to today)"),
    config: str = typer.Option("flowjob.yaml", help="Path to the configuration file"),
):
    """Log a manual application — filed by hand, outside the pipeline."""
    from src.config import load_config
    from src.db.store import init_db, create_manual_job, find_jobs_by_url

    conf = load_config(config)
    engine = init_db(conf.data.db_path)

    try:
        job_id, _, saved = create_manual_job(
            engine,
            title=title,
            company=company,
            url=url,
            jd_text=jd,
            notes=notes,
            cv=cv,
            state=state,
            date_applied=date_applied,
        )
    except ValueError as e:
        typer.echo(f"❌ {e}")
        raise typer.Exit(code=1)

    new_id = job_id
    new_state = state.value
    label = f"{title} at {company}" if title or company else ""
    if not saved:
        typer.echo(f"❌ A job with id {new_id} already exists — nothing saved.")
        raise typer.Exit(code=1)

    if url:
        existing = find_jobs_by_url(engine, url)
        if existing:
            ids = ", ".join(j.id for j in existing)
            typer.echo(f"⚠️  A job with this URL already exists ({ids}) — creating a separate row.")

    typer.echo(f"✅ Logged manual application [{new_id}] {label} — {new_state} (source: manual)")

@app.command()
def update(
    job_id: str = typer.Argument(..., help="Job ID to update"),
    state: JobState = typer.Option(..., help="New state (e.g. REJECTED to track rejections)"),
    config: str = typer.Option("flowjob.yaml", help="Path to the configuration file"),
):
    """Flip any job's state (manual or pipeline) — e.g. mark a rejection."""
    from src.config import load_config
    from src.db.store import init_db, get_session
    from src.db.models import Job

    conf = load_config(config)
    engine = init_db(conf.data.db_path)

    with get_session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            typer.echo(f"❌ No job with id {job_id}.")
            raise typer.Exit(code=1)
        old = job.state
        job.state = state
        session.commit()
        label = f"{job.title} at {job.company}" if job.title or job.company else job.id
        typer.echo(f"✅ {label}: {old.value} → {state.value} (source: {job.source})")

@app.command("audit-bank")
def audit_bank(resume: str = typer.Option("master_resume.md", help="Path to the master resume")):
    """Audit the master resume bullet bank for hygiene and metrics."""
    from src.agents.auditor import audit_master_resume
    from src.config import load_config
    
    cfg = load_config("flowjob.yaml")
    auditor_model = getattr(cfg.auditor, "model", "google/gemini-2.5-pro")
    
    typer.echo(f"🔍 Auditing bullet bank in {resume}...")
    report = audit_master_resume(master_resume_path=resume, model_name=auditor_model)
    
    typer.echo("\n--- Audit Results ---")
    for item in report.audited:
        status = "✅ PASS" if item.passed else "❌ FAIL"
        preview = item.bullet.replace("\n", " ")[:60]
        typer.echo(f"{status} | {preview}...")
        if not item.passed:
            for issue in item.issues:
                typer.echo(f"  - {issue}")
                
    typer.echo(f"\nTotal Passed: {report.passed_count}")
    typer.echo(f"Total Failed: {report.failed_count}")
    
    if report.failed_count > 0:
        raise typer.Exit(code=1)

@app.command()
def grill(
    job_id: str = typer.Argument(None, help="Job ID to grill candidate on"),
    config: str = typer.Option("flowjob.yaml", help="Path to configuration file")
):
    """Start or resume an interactive grilling session for a job needing evidence."""
    from src.config import load_config
    from src.db.store import init_db, get_session
    from sqlmodel import select
    from src.db.models import Job, JobState
    from src.agents.interviewer import run_grilling_session
    
    conf = load_config(config)
    engine = init_db(conf.data.db_path)
    
    with get_session(engine) as session:
        if not job_id:
            statement = pipeline_only(select(Job).where(Job.state == JobState.NEEDS_EVIDENCE))
            pending_jobs = session.exec(statement).all()
            if not pending_jobs:
                typer.echo("ℹ️ No jobs currently waiting for evidence.")
                return
            typer.echo("📋 Jobs waiting for grilling evidence:")
            for j in pending_jobs:
                typer.echo(f"  - [{j.id}] {j.title} at {j.company}")
            typer.echo("\nRun: flowjob grill <job_id>")
            return
            
        grill_model = getattr(conf.grilling, "model", "google/gemini-2.5-pro")
        max_turns = getattr(conf.grilling, "max_turns_per_gap", 5)
        from src.agents.llm_factory import load_providers
        run_grilling_session(
            session=session,
            job_id=job_id,
            interactive=True,
            model_name=grill_model,
            max_turns_per_gap=max_turns,
            providers=load_providers()
        )

@app.command()
def logs(
    job_id: str = typer.Option(None, help="Filter by job ID"),
    agent: str = typer.Option(None, help="Filter by agent name"),
    limit: int = typer.Option(30, help="Number of records to show"),
    cost_summary: bool = typer.Option(False, "--cost", help="Show token/cost summary instead of records"),
    config: str = typer.Option("flowjob.yaml", help="Path to the configuration file"),
    raw: bool = typer.Option(False, help="Print full prompt/response text"),
):
    """Show persisted LLM request/response logs (every prompt, response, provider, cost)."""
    from src.config import load_config
    from src.db.store import init_db, get_session
    from sqlmodel import select
    from src.db.models import LLMInteraction

    conf = load_config(config)
    engine = init_db(conf.data.db_path)

    with get_session(engine) as session:
        statement = select(LLMInteraction)
        if job_id:
            statement = statement.where(LLMInteraction.job_id == job_id)
        if agent:
            statement = statement.where(LLMInteraction.agent_name == agent)

        if cost_summary:
            from sqlmodel import func
            rows = session.exec(statement).all()
            total_cost = sum(r.cost_usd for r in rows)
            total_tokens = sum(r.prompt_tokens + r.completion_tokens for r in rows)
            cached = sum(r.cached_tokens for r in rows)
            failures = sum(1 for r in rows if not r.success)
            by_provider: dict[str, dict] = {}
            for r in rows:
                p = by_provider.setdefault(r.provider or "?", {"calls": 0, "cost": 0.0, "tokens": 0, "cached": 0})
                p["calls"] += 1
                p["cost"] += r.cost_usd
                p["tokens"] += r.prompt_tokens + r.completion_tokens
                p["cached"] += r.cached_tokens
            typer.echo(f"💸 LLM Spend Summary ({len(rows)} calls):")
            typer.echo(f"  Total cost: ${total_cost:.6f}")
            typer.echo(f"  Total tokens: {total_tokens} (cached: {cached})")
            typer.echo(f"  Failures: {failures}")
            typer.echo("  By provider:")
            for name, p in sorted(by_provider.items(), key=lambda kv: -kv[1]["cost"]):
                typer.echo(f"    {name}: {p['calls']} calls, ${p['cost']:.6f}, {p['tokens']} tokens, {p['cached']} cached")
            return

        statement = statement.order_by(LLMInteraction.id.desc()).limit(limit)
        records = session.exec(statement).all()

    if not records:
        typer.echo("ℹ️ No LLM interactions logged yet. Run `flowjob run` first.")
        return

    typer.echo(f"📜 LLM Interaction Logs (last {len(records)}):")
    for r in records:
        status = "✅" if r.success else "❌"
        cost = f"${r.cost_usd:.5f}" if r.cost_usd else "$0"
        typer.echo(f"\n[{r.id}] {status} {r.timestamp} | {r.agent_name} | {r.provider}/{r.model} | job={r.job_id or '-'}")
        typer.echo(f"    tokens: in={r.prompt_tokens} out={r.completion_tokens} cached={r.cached_tokens} | cost={cost} | {r.latency_ms}ms")
        if not r.success:
            typer.echo(f"    ERROR: {r.error[:200]}")
        if raw:
            typer.echo(f"    PROMPT: {r.prompt[:2000]}")
            typer.echo(f"    RESPONSE: {r.response[:2000]}")

@app.command()
def tui(
    config: str = typer.Option("flowjob.yaml", help="Path to the configuration file"),
):
    """Launch the cockpit TUI (five tabs: Dashboard / Jobs / LLM Logs / Settings / HITL)."""
    from src.config import load_config
    from src.db.store import init_db

    conf = load_config(config)
    init_db(conf.data.db_path)

    from src.tui.app import CockpitApp

    CockpitApp(agents=build_agents(), db_path=conf.data.db_path).run()


if __name__ == "__main__":
    app()
