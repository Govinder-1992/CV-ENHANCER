"""Extract plain text from PDF and DOCX CV bytes.

Uses pypdf for PDFs and python-docx for DOCX. Both are pure-Python and ship in
the Lambda layer / deployment package so no native binaries are needed.
"""
import io

from .errors import TextExtractionError

MAX_EXTRACTED_CHARS = 60_000


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise TextExtractionError("pypdf is not available in the runtime.") from exc

    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            # Attempt to open with an empty password; raise if it stays locked.
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise TextExtractionError("The PDF is password protected.") from exc
        parts = [page.extract_text() or "" for page in reader.pages]
    except TextExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TextExtractionError(f"Could not read the PDF: {exc}") from exc

    return "\n".join(parts).strip()


def _extract_docx(raw: bytes) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover
        raise TextExtractionError("python-docx is not available in the runtime.") from exc

    try:
        document = docx.Document(io.BytesIO(raw))
        paragraphs = [p.text for p in document.paragraphs]
        # Include table cell text, which often holds contact details.
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text:
                        paragraphs.append(cell.text)
    except Exception as exc:  # noqa: BLE001
        raise TextExtractionError(f"Could not read the DOCX: {exc}") from exc

    return "\n".join(p for p in paragraphs if p).strip()


def extract_text(raw: bytes, file_ext: str) -> str:
    """Return extracted, length-bounded plain text for a supported file."""
    ext = file_ext.lower().lstrip(".")
    if ext == "pdf":
        text = _extract_pdf(raw)
    elif ext == "docx":
        text = _extract_docx(raw)
    else:
        raise TextExtractionError(f"Cannot extract text from '{ext}' files.")

    if not text:
        raise TextExtractionError(
            "No readable text found. The file may be scanned images or empty."
        )

    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS]
    return text
