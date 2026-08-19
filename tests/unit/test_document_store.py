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


def test_disk_store_manual_cv_copies_into_job_dir(tmp_path):
    src = tmp_path / "my_tailored_cv.pdf"
    src.write_bytes(b"%PDF-1.4 fake")

    store = DiskDocumentStore(base_dir=str(tmp_path / "resumes"))
    dest = store.store_manual_cv("manual1", str(src))

    assert dest == str(tmp_path / "resumes" / "manual1" / "cv.pdf")
    assert (tmp_path / "resumes" / "manual1" / "cv.pdf").read_bytes() == b"%PDF-1.4 fake"


def test_disk_store_manual_cv_preserves_any_extension(tmp_path):
    src = tmp_path / "notes.md"
    src.write_text("# cv")

    store = DiskDocumentStore(base_dir=str(tmp_path / "resumes"))
    dest = store.store_manual_cv("manual2", str(src))

    assert dest == str(tmp_path / "resumes" / "manual2" / "cv.md")


def test_in_memory_store_manual_cv_uri():
    store = InMemoryDocumentStore()
    assert store.store_manual_cv("m3", "/tmp/resume.pdf") == "memory://resumes/m3/cv.pdf"
