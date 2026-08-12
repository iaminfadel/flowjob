# Research: PDF Text Extraction & JSON Resume Evaluation

> Resolves [#8](https://github.com/iaminfadel/flowjob/issues/8)

## 1. PDF Text Extraction Libraries (C013 Mitigation)

To verify that the Playwright-generated PDF is actually ATS-parseable (the "Notepad test"), we need a library to extract the raw text from the PDF. If the text comes out garbled or empty, the ATS will fail.

### Candidates

| Library | Pros | Cons | Verdict |
|---------|------|------|---------|
| **PyMuPDF** (`pymupdf`) | Extremely fast. Pure `pip install` (wheels include C binaries). Industry standard for text extraction. | Focuses on raw extraction, not exact visual layout (but we don't need layout, just text stream). | ⭐ **RECOMMENDED** |
| **pdfplumber** | Excellent at preserving layout and extracting tables. Built on `pdfminer.six`. | Much slower than PyMuPDF. Heavy dependency for just a simple text stream check. | Overkill |
| **pdftotext** (`poppler`) | Simple CLI tool, very reliable. | Requires installing system binaries (`apt-get install poppler-utils`), which ruins our pure Python distribution strategy. | Rejected |

**Implementation Strategy:**
Use `pymupdf`. After the Tailor agent generates the PDF via Playwright, the Editor agent runs a quick check:
```python
import fitz # PyMuPDF
doc = fitz.open("tailored_cv.pdf")
text = chr(12).join([page.get_text() for page in doc])
# If len(text.strip()) < 100, fail the validation (likely rendered as an image).
# Pass this extracted text to the Editor LLM to verify keyword coverage.
```
By passing the *extracted* text to the Editor Agent (rather than the original HTML), we prove that the ATS will actually see the keywords.

---

## 2. JSON Resume Evaluation

The user requested a look at [jsonresume.org](https://jsonresume.org).

### What it is
A standardized JSON schema for resumes, backed by a large ecosystem of open-source themes and a CLI tool (`resume-cli`) to export them to HTML/PDF.

### How it impacts FlowJob

**Pros:**
- It is the industry standard for programmatic resumes.
- If the Tailor agent outputs a valid `resume.json`, the user can use any of the 50+ community themes to render their CV.
- It decouples the data generation from the presentation layer perfectly.

**Cons:**
- **ATS Danger:** Many JSON Resume themes use complex multi-column layouts, icons, and skill bars that fail ATS parsers. We would have to strictly force an ATS-friendly theme (like `jsonresume-theme-dev-ats`).
- **Dependency bloat:** Requires Node.js and `npm install -g resume-cli` to render the PDFs, whereas our current design uses pure Python (Jinja2 + Playwright).

### Decision for FlowJob
We should **adopt the JSON Resume Schema** as the internal data structure for the Tailored CV, but **render it ourselves** via Python/Jinja2 instead of requiring the Node.js CLI.

**Updated Flow:**
1. Tailor Agent reads Master Resume and JD.
2. Tailor Agent outputs a subset of data conforming to the **JSON Resume schema** (`resume.json`).
3. FlowJob uses Jinja2 to render this JSON into our ATS-friendly HTML template.
4. Playwright prints to PDF.
5. PyMuPDF validates the text extraction.

This gives us the best of both worlds: standard JSON structure (cool and interoperable) without the Node.js dependency bloat.
