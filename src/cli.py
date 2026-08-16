import typer
import sys
from pathlib import Path
from src.config import load_config
from src.db.store import init_db
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
    from src.pipeline.orchestrator import run_pipeline
    typer.echo("👀 Starting FlowJob in watch mode...")
    agents = build_agents()
    while True:
        typer.echo("🚀 Running pipeline cycle...")
        
        run_pipeline(agents=agents)
        
        jitter_minutes = random.uniform(45, 90)
        typer.echo(f"⏳ Sleeping for {jitter_minutes:.2f} minutes before next cycle...")
        time.sleep(jitter_minutes * 60)

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
            statement = select(func.count(Job.id)).where(Job.state == state)
            return session.exec(statement).one()

        new_count = count_state(JobState.NEW)
        drafted_count = count_state(JobState.DRAFTED)
        needs_evidence_count = count_state(JobState.NEEDS_EVIDENCE)
        unfixable_count = count_state(JobState.UNFIXABLE)
        applied_count = count_state(JobState.APPLIED)
        pending_count = count_state(JobState.PENDING_APPROVAL)
        failed_count = count_state(JobState.FAILED)

        from src.db.models import PipelineRun
        statement = select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)
        last_run = session.exec(statement).first()
        last_cycle = last_run.timestamp if last_run else "Unknown (Never run or no record found)"

    typer.echo("📊 FlowJob Status:")
    typer.echo(f"  NEW: {new_count}")
    typer.echo(f"  DRAFTED: {drafted_count}")
    typer.echo(f"  NEEDS_EVIDENCE: {needs_evidence_count}")
    typer.echo(f"  UNFIXABLE: {unfixable_count}")
    typer.echo(f"  PENDING_APPROVAL: {pending_count}")
    typer.echo(f"  APPLIED: {applied_count}")
    typer.echo(f"  FAILED: {failed_count}")
    typer.echo(f"\n🕒 Last successful cycle: {last_cycle}")

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
            statement = select(Job).where(Job.state == JobState.NEEDS_EVIDENCE)
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
        run_grilling_session(
            session=session,
            job_id=job_id,
            interactive=True,
            model_name=grill_model,
            max_turns_per_gap=max_turns
        )

if __name__ == "__main__":
    app()
