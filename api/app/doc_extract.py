"""PDF, DOCX, and plain-text extraction for Knowledge Base ingestion (N13).

Zero heavy external dependencies:
  - DOCX: stdlib zipfile + XML parser (word/document.xml) with zip-bomb size cap (10 MB).
  - PDF: uses `pypdf` if installed, otherwise a pure-Python zlib + BT/ET Tj/TJ stream extractor.
  - TXT / MD: UTF-8 decode with replacement.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_DECOMPRESSED_BYTES = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


def extract_docx(data: bytes) -> str:
    """Extract paragraph and table text from a .docx zip archive safely."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("DOCX exceeds 10 MB limit")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid DOCX file") from exc
    with zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("DOCX missing word/document.xml")
        info = zf.getinfo("word/document.xml")
        if info.file_size > MAX_DECOMPRESSED_BYTES:
            raise ValueError("DOCX document.xml exceeds size limit")
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for p in root.iter():
        if p.tag.endswith("}p") or p.tag == "p":
            texts = [el.text for el in p.iter() if (el.tag.endswith("}t") or el.tag == "t") and el.text]
            line = "".join(texts).strip()
            if line:
                paragraphs.append(line)
    return "\n\n".join(paragraphs)


def _unescape_pdf_literal(raw: bytes) -> str:
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == 92 and i + 1 < n:  # backslash
            nxt = raw[i + 1]
            mapping = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12,
                       ord("("): 40, ord(")"): 41, ord("\\"): 92}
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
        out.append(ch)
        i += 1
    return out.decode("latin-1", errors="ignore")


def _extract_pdf_text_blocks(stream: bytes) -> list[str]:
    pieces: list[str] = []
    # Match (...) Tj and [(...) -20 (...)] TJ inside content streams
    for block in re.findall(rb"BT(.*?)ET", stream, re.S):
        for m in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(.*?)\]\s*TJ", block, re.S):
            if m.group(1) is not None:
                parts = re.findall(rb"\((?:\\.|[^\\()])*\)", m.group(1))
                text = "".join(_unescape_pdf_literal(p[1:-1]) for p in parts).strip()
            else:
                lit = m.group(0)
                inner = lit[1:lit.rfind(b")")]
                text = _unescape_pdf_literal(inner).strip()
            if text:
                pieces.append(text)
    return pieces


def extract_pdf(data: bytes) -> str:
    """Extract text from a PDF file. Uses pypdf when installed, else pure-Python stream parser."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("PDF exceeds 10 MB limit")
    if not data.lstrip().startswith(b"%PDF-"):
        raise ValueError("Invalid PDF header")
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        joined = "\n\n".join(p for p in pages if p)
        if joined:
            return joined
    except ImportError:
        pass
    except Exception:
        pass

    # Pure-Python fallback: inspect uncompressed & FlateDecode streams
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw_stream = match.group(1)
        candidates = [raw_stream]
        try:
            candidates.append(zlib.decompress(raw_stream))
        except zlib.error:
            pass
        for stream in candidates:
            if b"BT" in stream and b"ET" in stream:
                chunks.extend(_extract_pdf_text_blocks(stream))
    if not chunks and b"BT" in data:
        chunks.extend(_extract_pdf_text_blocks(data))
    return "\n".join(chunks).strip()


def extract_document(filename: str, data: bytes) -> str:
    """Dispatch document extraction by filename extension."""
    name = (filename or "").strip().lower()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds 10 MB limit")
    if name.endswith(".pdf"):
        text = extract_pdf(data)
    elif name.endswith(".docx"):
        text = extract_docx(data)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace").strip()
    else:
        raise ValueError("Unsupported file type. Upload PDF, DOCX, TXT, or MD.")
    if len(text.strip()) < 10:
        raise ValueError("Could not extract readable text from document")
    return text.strip()
