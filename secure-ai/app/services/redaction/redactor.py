"""
redactor.py — Applies black-box redactions to PDF documents.
Uses PyMuPDF redact annotations with fill=(0,0,0) to permanently remove PII.
"""
import logging
from pathlib import Path
from typing import List

import fitz  # pymupdf

from app.models.document import DetectedEntity

logger = logging.getLogger(__name__)


class Redactor:
    """Applies pixel-level redactions to PDFs based on detected PII entities."""

    def redact(
        self,
        input_path: Path,
        entities: List[DetectedEntity],
        output_path: Path,
    ) -> Path:
        """
        Create a redacted copy of the input PDF.
        Returns the output path.
        """
        doc = fitz.open(str(input_path))
        redaction_count = 0

        for entity in entities:
            page_idx = entity.page
            if page_idx >= len(doc):
                logger.warning(
                    "Entity refers to page %d but doc has %d pages — skipping",
                    page_idx, len(doc),
                )
                continue

            page = doc[page_idx]

            if entity.bbox:
                # PRIMARY: Use exact bounding box from offset→bbox mapping
                rect = fitz.Rect(entity.bbox)
                page.add_redact_annot(rect, fill=(0, 0, 0))
                redaction_count += 1
                logger.debug(
                    "REDACT bbox [%.0f,%.0f,%.0f,%.0f]: \"%s\"",
                    *entity.bbox, entity.text,
                )
            else:
                # FALLBACK: Text search — only if bbox mapping failed.
                # Limit to FIRST match only to avoid redacting unrelated text.
                if len(entity.text) < 4:
                    logger.debug(
                        "Skipping short entity (no bbox): \"%s\" (%s)",
                        entity.text, entity.entity_type,
                    )
                    continue
                rects = page.search_for(entity.text)
                if rects:
                    page.add_redact_annot(rects[0], fill=(0, 0, 0))
                    redaction_count += 1
                    logger.debug(
                        "REDACT search (1st match): \"%s\"", entity.text,
                    )
                else:
                    logger.debug(
                        "No match on page %d for: \"%s\"",
                        page_idx, entity.text,
                    )

        # Apply all redactions at once (permanent removal)
        for page in doc:
            page.apply_redactions()

        doc.save(str(output_path), garbage=4, deflate=True)
        doc.close()

        logger.info(
            "Redacted %d regions in %s → %s",
            redaction_count, input_path.name, output_path.name,
        )
        return output_path
