from sqlmodel import SQLModel, create_engine, Session

def init_db(db_path: str):
    """Initialize the SQLite database with the required schema."""
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    
    # Create all tables
    import src.db.models  # Ensure models are registered
    SQLModel.metadata.create_all(engine)
    
    return engine

def get_session(engine) -> Session:
    """Return a database session."""
    return Session(engine)
