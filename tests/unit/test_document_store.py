import pytest
from src.storage.document_store import InMemoryDocumentStore, DiskDocumentStore


def test_in_memory_document_store_save_and_load():
    store = InMemoryDocumentStore()
    draft = {"basics": {"name": "Alice Developer", "email": "alice@example.com"}, "work": []}
    
    uri = store.save_draft("job123", draft)
    assert "memory://" in uri
    assert store.has_draft("job123") is True

    loaded = store.load_draft("job123")
    assert loaded["basics"]["name"] == "Alice Developer"

    # Test markdown projection
    md = store.project_markdown("job123")
    assert "# Alice Developer" in md
    assert "alice@example.com" in md


def test_in_memory_document_store_compile_and_text():
    store = InMemoryDocumentStore()
    draft = {"basics": {"name": "Bob Smith", "email": "bob@example.com"}, "work": []}
    
    pdf_uri = store.compile_document("job456", metadata=None, draft_data=draft)
    assert pdf_uri == "memory://resumes/job456/resume.pdf"
    assert store.get_cv_path("job456") == pdf_uri

    extracted = store.extract_text("job456")
    assert "Bob Smith" in extracted
