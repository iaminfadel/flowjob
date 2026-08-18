"""Deep DocumentStore module providing a clean storage and document compilation seam.

Encapsulates draft JSON persistence, Markdown projection, PDF compilation via
Playwright/Jinja2, and text extraction for ATS/QA auditing.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union

import fitz  # PyMuPDF
from jinja2 import Environment, FileSystemLoader

from src.utils.projection import project_resume_to_markdown


class DocumentStore(ABC):
    """Abstract interface for draft resume persistence, projection, and document rendering."""

    @abstractmethod
    def save_draft(self, job_id: str, draft_data: dict) -> str:
        """Save draft JSON and return storage URI or path."""
        pass

    @abstractmethod
    def load_draft(self, job_id: str) -> dict:
        """Load draft JSON. Return empty dict if not found."""
        pass

    @abstractmethod
    def has_draft(self, job_id: str) -> bool:
        """Check if a draft exists for the job."""
        pass

    @abstractmethod
    def project_markdown(self, target: Union[str, dict]) -> str:
        """Render a markdown projection of a draft (by job_id or raw draft dict)."""
        pass

    @abstractmethod
    def compile_document(self, job_id: str, metadata: Any, draft_data: Optional[dict] = None) -> str:
        """Render HTML, compile PDF, validate ATS parseability. Returns path to PDF."""
        pass

    @abstractmethod
    def extract_text(self, target: Union[str, Path]) -> str:
        """Extract text from a compiled PDF (path or job_id) for verification."""
        pass

    @abstractmethod
    def get_cv_path(self, job_id: str) -> Optional[str]:
        """Return the path/URI to the compiled PDF if it exists, else None."""
        pass


class DiskDocumentStore(DocumentStore):
    """Production filesystem adapter using Playwright, Jinja2, and PyMuPDF."""

    def __init__(self, base_dir: str = "data/resumes", template_dir: Optional[str] = None):
        self.base_dir = base_dir
        if template_dir is None:
            self.template_dir = os.path.join(os.path.dirname(__file__), "..", "utils")
        else:
            self.template_dir = template_dir

    def _job_dir(self, job_id: str) -> str:
        return os.path.join(self.base_dir, job_id)

    def _json_path(self, job_id: str) -> str:
        return os.path.join(self._job_dir(job_id), "resume.json")

    def _html_path(self, job_id: str) -> str:
        return os.path.join(self._job_dir(job_id), "resume.html")

    def _pdf_path(self, job_id: str) -> str:
        return os.path.join(self._job_dir(job_id), "resume.pdf")

    def save_draft(self, job_id: str, draft_data: dict) -> str:
        job_dir = self._job_dir(job_id)
        os.makedirs(job_dir, exist_ok=True)
        file_path = self._json_path(job_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, indent=2)
        return file_path

    def load_draft(self, job_id: str) -> dict:
        file_path = self._json_path(job_id)
        if not os.path.exists(file_path):
            return {}
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def has_draft(self, job_id: str) -> bool:
        return os.path.exists(self._json_path(job_id))

    def project_markdown(self, target: Union[str, dict]) -> str:
        if isinstance(target, str):
            draft = self.load_draft(target)
        else:
            draft = target
        return project_resume_to_markdown(draft)

    def compile_document(self, job_id: str, metadata: Any, draft_data: Optional[dict] = None) -> str:
        job_dir = self._job_dir(job_id)
        os.makedirs(job_dir, exist_ok=True)

        if draft_data is None:
            draft_data = self.load_draft(job_id)
        else:
            self.save_draft(job_id, draft_data)

        # 1. Render HTML using Jinja2
        env = Environment(loader=FileSystemLoader(self.template_dir))
        template = env.get_template("resume_template.html")
        html_content = template.render(**draft_data)

        html_path = self._html_path(job_id)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 2. Print PDF using Playwright headless
        pdf_path = self._pdf_path(job_id)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            abs_html_path = Path(html_path).absolute()
            page.goto(f"file:///{abs_html_path}", wait_until="networkidle")
            page.pdf(path=pdf_path, format="A4", margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            browser.close()

        # 3. Validate ATS parseability with PyMuPDF
        if metadata:
            extracted_text = self.extract_text(pdf_path)
            name = getattr(metadata, "name", "")
            email = getattr(metadata, "email", "")
            if name and name not in extracted_text or (email and email not in extracted_text):
                raise ValueError(
                    f"Generated PDF at {pdf_path} failed ATS validation: contact info not found in extracted text."
                )

        return pdf_path

    def extract_text(self, target: Union[str, Path]) -> str:
        target_str = str(target)
        if not target_str.endswith(".pdf"):
            target_str = self._pdf_path(target_str)

        if not os.path.exists(target_str):
            return ""

        doc = fitz.open(target_str)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text()
        doc.close()
        return extracted_text

    def get_cv_path(self, job_id: str) -> Optional[str]:
        pdf_path = self._pdf_path(job_id)
        if os.path.exists(pdf_path):
            return pdf_path
        json_path = self._json_path(job_id)
        if os.path.exists(json_path):
            return json_path
        return None


class InMemoryDocumentStore(DocumentStore):
    """Pure in-memory test adapter with zero disk I/O and zero external dependencies."""

    def __init__(self):
        self._drafts: dict[str, dict] = {}
        self._pdfs: dict[str, str] = {}
        self._custom_texts: dict[str, str] = {}

    def save_draft(self, job_id: str, draft_data: dict) -> str:
        self._drafts[job_id] = json.loads(json.dumps(draft_data))
        return f"memory://resumes/{job_id}/resume.json"

    def load_draft(self, job_id: str) -> dict:
        return json.loads(json.dumps(self._drafts.get(job_id, {})))

    def has_draft(self, job_id: str) -> bool:
        return job_id in self._drafts

    def project_markdown(self, target: Union[str, dict]) -> str:
        if isinstance(target, str):
            draft = self.load_draft(target)
        else:
            draft = target
        return project_resume_to_markdown(draft)

    def compile_document(self, job_id: str, metadata: Any, draft_data: Optional[dict] = None) -> str:
        if draft_data is not None:
            self.save_draft(job_id, draft_data)
        pdf_path = f"memory://resumes/{job_id}/resume.pdf"
        self._pdfs[job_id] = pdf_path
        return pdf_path

    def extract_text(self, target: Union[str, Path]) -> str:
        target_str = str(target)
        if target_str in self._custom_texts:
            return self._custom_texts[target_str]
        job_id = target_str.replace("memory://resumes/", "").replace("/resume.pdf", "").replace("/resume.json", "")
        draft = self.load_draft(job_id)
        if draft:
            return self.project_markdown(draft)
        return "FAKE EXTRACTED PDF TEXT"

    def set_custom_text(self, target: str, text: str):
        self._custom_texts[target] = text

    def get_cv_path(self, job_id: str) -> Optional[str]:
        if job_id in self._pdfs:
            return self._pdfs[job_id]
        if job_id in self._drafts:
            return f"memory://resumes/{job_id}/resume.json"
        return None
