import fitz

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts all text from a given PDF file."""
    doc = fitz.open(pdf_path)
    extracted_text = ""
    for page in doc:
        extracted_text += page.get_text()
    doc.close()
    return extracted_text
