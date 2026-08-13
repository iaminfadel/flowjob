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

@app.command()
def run(url: str = typer.Option(None, help="Process a single job URL instead of running Scout"), 
        dry_run: bool = typer.Option(False, help="Do not apply, save PDF and form answers to disk")):
    """Run the FlowJob pipeline."""
    from src.pipeline.orchestrator import run_pipeline
    typer.echo("🚀 Running FlowJob pipeline...")
    run_pipeline(url=url, dry_run=dry_run)

@app.command()
def watch():
    """Run the FlowJob pipeline continuously with jitter."""
    import time
    import random
    from src.pipeline.orchestrator import run_pipeline
    typer.echo("👀 Starting FlowJob in watch mode...")
    while True:
        typer.echo("🚀 Running pipeline cycle...")
        run_pipeline()
        
        jitter_minutes = random.uniform(45, 90)
        typer.echo(f"⏳ Sleeping for {jitter_minutes:.2f} minutes before next cycle...")
        time.sleep(jitter_minutes * 60)

if __name__ == "__main__":
    app()
