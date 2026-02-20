"""
validator.py — 5-gate file validation before pipeline processing.
"""
import logging
import magic
import shutil
from pathlib import Path

import fitz  # pymupdf

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}

_ALLOWED_MIMES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}

_MAX_PDF_PAGES = 50  # MVP limit


class ValidationError(Exception):
    """Raised when a file fails validation."""
    pass


class FileValidator:
    """Runs 5 sequential validation gates on an incoming file."""

    def __init__(self, max_size_mb: int = 50, error_dir: str | Path = "/app/storage/error"):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.error_dir = Path(error_dir)

    def validate(self, file_path: Path) -> bool:
        """
        Run all 5 validation gates. Returns True on pass.
        Raises ValidationError with a descriptive message on failure.
        """
        self._check_extension(file_path)
        self._check_mime(file_path)
        self._check_size(file_path)

        # PDF-specific checks
        if file_path.suffix.lower() == ".pdf":
            self._check_encryption(file_path)
            self._check_page_count(file_path)

        logger.info("Validation PASSED: %s", file_path.name)
        return True

    def reject(self, file_path: Path, reason: str):
        """Move a failed file to the error directory."""
        self.error_dir.mkdir(parents=True, exist_ok=True)
        dest = self.error_dir / file_path.name
        shutil.move(str(file_path), str(dest))
        logger.warning("File REJECTED → %s | Reason: %s", dest.name, reason)

    # ── gates ────────────────────────────────────────────────────────────

    def _check_extension(self, fp: Path):
        """Gate 1: Extension whitelist."""
        if fp.suffix.lower() not in _ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Extension '{fp.suffix}' not allowed. Accepted: {_ALLOWED_EXTENSIONS}"
            )

    def _check_mime(self, fp: Path):
        """Gate 2: MIME type via libmagic (content-sniffing, not trust-extension)."""
        try:
            mime = magic.from_file(str(fp), mime=True)
        except Exception as exc:
            raise ValidationError(f"MIME detection failed: {exc}") from exc

        if mime not in _ALLOWED_MIMES:
            raise ValidationError(
                f"MIME type '{mime}' not allowed. Accepted: {_ALLOWED_MIMES}"
            )

    def _check_size(self, fp: Path):
        """Gate 3: File must be under max size."""
        size = fp.stat().st_size
        if size > self.max_size_bytes:
            raise ValidationError(
                f"File too large: {size / 1024 / 1024:.1f}MB > {self.max_size_bytes / 1024 / 1024}MB limit"
            )

    def _check_encryption(self, fp: Path):
        """Gate 4: PDF must not be password-protected."""
        try:
            doc = fitz.open(str(fp))
            if doc.is_encrypted:
                doc.close()
                raise ValidationError("PDF is encrypted / password-protected")
            doc.close()
        except fitz.FileDataError as exc:
            raise ValidationError(f"Cannot open PDF: {exc}") from exc

    def _check_page_count(self, fp: Path):
        """Gate 5: PDF must not exceed page limit."""
        doc = fitz.open(str(fp))
        count = len(doc)
        doc.close()
        if count > _MAX_PDF_PAGES:
            raise ValidationError(
                f"PDF has {count} pages, exceeds {_MAX_PDF_PAGES}-page limit"
            )
