import os
import json
from pathlib import Path
import fitz  # PyMuPDF
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

import os
import json
from pathlib import Path
from abc import ABC, abstractmethod
import fitz  # PyMuPDF
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

class DocumentGenerator(ABC):
    @abstractmethod
    def generate(self, resume_data: dict, metadata, output_dir: str = "output") -> str:
        pass

class PlaywrightDocumentGenerator(DocumentGenerator):
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
        pdf_path = os.path.join(output_dir, "resume.pdf")
        with sync_playwright() as p:
            # Playwright print-to-pdf requires headless=True
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # use absolute path for file:// url
            abs_html_path = Path(html_path).absolute()
            page.goto(f"file:///{abs_html_path}", wait_until="networkidle")
            page.pdf(path=pdf_path, format="A4", margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            browser.close()
            
        # 4. Validate ATS parseability with PyMuPDF
        doc = fitz.open(pdf_path)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text()
        doc.close()
        
        if metadata.name not in extracted_text or metadata.email not in extracted_text:
            raise ValueError(f"Generated PDF at {pdf_path} failed ATS validation: contact info not found in extracted text.")
            
        return pdf_path

class InMemoryDocumentGenerator(DocumentGenerator):
    def generate(self, resume_data: dict, metadata, output_dir: str = "output") -> str:
        """Creates fake output files without Playwright for testing."""
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, "resume.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(resume_data, f, indent=2)
            
        pdf_path = os.path.join(output_dir, "resume.pdf")
        with open(pdf_path, "w") as f:
            f.write("FAKE PDF CONTENT")
            
        return pdf_path

