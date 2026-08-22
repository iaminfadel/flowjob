import os
import json
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod

from jinja2 import Environment, FileSystemLoader

from src.utils.latex_utils import build_render_context
from src.utils.resume_parser import parse_master_resume


class DocumentGenerator(ABC):
    @abstractmethod
    def generate(self, resume_data: dict, metadata, output_dir: str = "output") -> str:
        pass

    @staticmethod
    def validate_ats(pdf_path: str, metadata) -> None:
        """Raise if the compiled PDF fails ATS parseability (name + contact)."""
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text()
        doc.close()

        name = getattr(metadata, "name", "") if metadata else ""
        full_name = getattr(metadata, "full_name", "") if metadata else ""
        email = getattr(metadata, "email", "") if metadata else ""
        phone = getattr(metadata, "phone", "") if metadata else ""
        # The email may be hidden behind a mailto link label ("Email"), exactly
        # like the hand-made gold resumes; phone is always plain text.
        name_found = any(n and n in extracted_text for n in (full_name, name))
        contact_found = (bool(email) and email in extracted_text) or (
            bool(phone) and phone in extracted_text
        )
        if not name_found or not contact_found:
            raise ValueError(
                f"Generated PDF at {pdf_path} failed ATS validation: contact info not found in extracted text."
            )


class LatexDocumentGenerator(DocumentGenerator):
    """Renders the tailored draft through the Jake's Resume LaTeX template.

    Pipeline: draft JSON -> normalize + escape -> Jinja2 (.tex) -> pdflatex x2
    -> resume.pdf -> PyMuPDF ATS validation. Contact info and header extras
    come from locally parsed master metadata, never from LLM output.
    """

    def __init__(self, template_dir=None, compiler: str = "pdflatex"):
        if template_dir is None:
            self.template_dir = os.path.dirname(__file__)
        else:
            self.template_dir = template_dir
        self.compiler = compiler

    def _render_tex(self, resume_data: dict, metadata) -> str:
        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            block_start_string="\\BLOCK{",
            block_end_string="}",
            variable_start_string="\\VAR{",
            variable_end_string="}",
            comment_start_string="\\#{",
            comment_end_string="}",
            line_statement_prefix="%%-",
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )
        template = env.get_template("resume_template.tex")
        try:
            _, master_md = parse_master_resume("master_resume.md")
        except Exception:
            master_md = ""
        context = build_render_context(resume_data, metadata, master_experience_md=master_md)
        return template.render(**context)

    def _compile_pdf(self, tex_path: str) -> str:
        output_dir = os.path.dirname(tex_path)
        env = dict(os.environ)
        for _ in range(2):  # two passes for stable layout/refs
            result = subprocess.run(
                [self.compiler, "-interaction=nonstopmode", "-halt-on-error", os.path.basename(tex_path)],
                cwd=output_dir,
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )
            if result.returncode != 0:
                log_path = os.path.join(output_dir, "resume.log")
                log_tail = ""
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        log_tail = "\n".join(f.read().splitlines()[-30:])
                raise RuntimeError(
                    f"LaTeX compilation failed (exit {result.returncode}). Log tail:\n{log_tail}"
                )
        return os.path.join(output_dir, "resume.pdf")

    @staticmethod
    def _cleanup_aux(output_dir: str) -> None:
        for ext in (".aux", ".log", ".out"):
            path = os.path.join(output_dir, f"resume{ext}")
            if os.path.exists(path):
                os.remove(path)

    def generate(self, resume_data: dict, metadata, output_dir: str = "output") -> str:
        """Renders the .tex and compiles the PDF for the given tailored resume dict."""
        os.makedirs(output_dir, exist_ok=True)

        # 1. Save JSON (audit trail of what was rendered)
        json_path = os.path.join(output_dir, "resume.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(resume_data, f, indent=2)

        # 2. Render .tex via Jinja2
        tex_content = self._render_tex(resume_data, metadata)
        tex_path = os.path.join(output_dir, "resume.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)

        # 3. Compile PDF (pdflatex x2)
        pdf_path = self._compile_pdf(tex_path)

        # 4. Validate ATS parseability; clean aux files either way (keep .tex
        # for debugging on failure).
        try:
            self.validate_ats(pdf_path, metadata)
        finally:
            self._cleanup_aux(output_dir)
        return pdf_path


class PlaywrightDocumentGenerator(DocumentGenerator):
    """Legacy HTML->Chromium renderer. Kept for fallback; pipeline defaults to LaTeX."""

    def __init__(self, template_dir=None):
        if template_dir is None:
            self.template_dir = os.path.dirname(__file__)
        else:
            self.template_dir = template_dir

    def generate(self, resume_data: dict, metadata, output_dir: str = "output") -> str:
        """Renders the HTML and PDF for the given tailored resume dict."""
        os.makedirs(output_dir, exist_ok=True)

        # 1. Save JSON
        json_path = os.path.join(output_dir, "resume.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(resume_data, f, indent=2)

        # 2. Render HTML using Jinja2
        env = Environment(loader=FileSystemLoader(self.template_dir))
        template = env.get_template("resume_template.html")
        html_content = template.render(**resume_data)

        html_path = os.path.join(output_dir, "resume.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 3. Print PDF using Playwright
        from playwright.sync_api import sync_playwright

        pdf_path = os.path.join(output_dir, "resume.pdf")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            abs_html_path = Path(html_path).absolute()
            page.goto(f"file:///{abs_html_path}", wait_until="networkidle")
            page.pdf(path=pdf_path, format="A4", margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            browser.close()

        # 4. Validate ATS parseability with PyMuPDF
        self.validate_ats(pdf_path, metadata)

        return pdf_path


class InMemoryDocumentGenerator(DocumentGenerator):
    def generate(self, resume_data: dict, metadata, output_dir: str = "output") -> str:
        """Creates fake output files without external dependencies for testing."""
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, "resume.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(resume_data, f, indent=2)

        pdf_path = os.path.join(output_dir, "resume.pdf")
        with open(pdf_path, "w") as f:
            f.write("FAKE PDF CONTENT")

        return pdf_path
