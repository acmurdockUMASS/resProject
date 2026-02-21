from fastapi import UploadFile, HTTPException
from docx import Document
import pdfplumber
import tempfile
import os


def extract_text_from_pdf_bytes(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    finally:
        os.unlink(path)
def extract_text_from_docx_bytes(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        d = Document(path)
        return "\n".join(p.text for p in d.paragraphs).strip()
    finally:
        os.unlink(path)


async def extract_text(upload: UploadFile) -> tuple[str, bytes]:
    filename = (upload.filename or "").lower()
    data = await upload.read()

    if filename.endswith(".pdf"):
        return extract_text_from_pdf_bytes(data), data
    if filename.endswith(".docx"):
        return extract_text_from_docx_bytes(data), data

    raise HTTPException(status_code=400, detail="Unsupported file type. Upload PDF or DOCX.")