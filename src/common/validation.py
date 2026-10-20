"""Input validation for the incoming CV + job details payload."""
import base64
import re
from typing import Any

from .errors import FileTooLargeError, UnsupportedFileTypeError, ValidationError

# Magic-byte signatures used to confirm the declared file type.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # DOCX is a zip container.

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

ALLOWED_EXTENSIONS = {"pdf", "docx"}
MAX_JOB_DESCRIPTION_CHARS = 20_000
MAX_JOB_ROLE_CHARS = 200


def _require_str(payload: dict, key: str, *, min_len: int = 1, max_len: int | None = None) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or len(value.strip()) < min_len:
        raise ValidationError(f"Field '{key}' is required.")
    value = value.strip()
    if max_len is not None and len(value) > max_len:
        raise ValidationError(f"Field '{key}' exceeds the maximum length of {max_len}.")
    return value


def decode_file_content(payload: dict, max_bytes: int) -> bytes:
    """Decode the base64 CV content and enforce the size limit."""
    b64 = payload.get("fileContentBase64")
    if not isinstance(b64, str) or not b64:
        raise ValidationError("Field 'fileContentBase64' is required.")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise ValidationError("fileContentBase64 is not valid base64.") from exc
    if not raw:
        raise ValidationError("The uploaded file is empty.")
    if len(raw) > max_bytes:
        raise FileTooLargeError(
            f"File is {len(raw)} bytes; the maximum allowed is {max_bytes} bytes."
        )
    return raw


def _detect_and_verify_type(raw: bytes, declared_ext: str) -> str:
    """Confirm the declared extension matches the file's magic bytes."""
    declared_ext = declared_ext.lower().lstrip(".")
    if declared_ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{declared_ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if declared_ext == "pdf" and not raw.startswith(_PDF_MAGIC):
        raise UnsupportedFileTypeError("File does not appear to be a valid PDF.")
    if declared_ext == "docx" and not raw.startswith(_ZIP_MAGIC):
        raise UnsupportedFileTypeError("File does not appear to be a valid DOCX.")
    return declared_ext


def validate_payload(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """Validate the full request and return a normalized, safe dict."""
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")

    file_name = _require_str(payload, "fileName", max_len=255)
    job_role = _require_str(payload, "jobRole", max_len=MAX_JOB_ROLE_CHARS)
    job_description = _require_str(
        payload, "jobDescription", min_len=20, max_len=MAX_JOB_DESCRIPTION_CHARS
    )
    email = _require_str(payload, "email", max_len=320)
    if not EMAIL_RE.match(email):
        raise ValidationError("A valid email address is required.")

    declared_ext = (payload.get("fileType") or file_name.rsplit(".", 1)[-1]).lower()
    raw = decode_file_content(payload, max_bytes)
    ext = _detect_and_verify_type(raw, declared_ext)

    return {
        "fileName": file_name,
        "fileExt": ext,
        "fileBytes": raw,
        "fileSize": len(raw),
        "jobRole": job_role,
        "jobDescription": job_description,
        "email": email,
    }
