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

if __name__ == "__main__":
    app()
