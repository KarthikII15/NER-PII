"""
pipeline.py — Central orchestrator for the document processing pipeline.
Ties together: Validator → Extractor → Detector → Redactor → Signer → Auditor.
"""
import logging
import time
from pathlib import Path
from typing import List

from app.core.validator import FileValidator, ValidationError
from app.models.document import (
    DetectedEntity,
    JobStatus,
    ProcessResult,
)
from app.services.extraction.extractor import TextExtractor, PageContent
from app.services.detection.detector import PIIDetector
from app.services.redaction.redactor import Redactor
from app.services.signing.signer import DocumentSigner
from app.services.audit.logger import AuditLogger

logger = logging.getLogger(__name__)


class Pipeline:
    """
    End-to-end document processing pipeline.

    Flow:
        VALIDATE → EXTRACT → DETECT → RESOLVE BBOXES → REDACT → SIGN → AUDIT
    """

    def __init__(
        self,
        processed_dir: str,
        signed_dir: str,
        error_dir: str,
        keys_dir: str,
        db_path: str,
        max_size_mb: int = 50,
    ):
        self.processed_dir = Path(processed_dir)
        self.signed_dir = Path(signed_dir)
        self.error_dir = Path(error_dir)

        # Ensure directories exist
        for d in [self.processed_dir, self.signed_dir, self.error_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Sub-components
        self.validator = FileValidator(max_size_mb=max_size_mb, error_dir=error_dir)
        self.extractor = TextExtractor()
        self.detector = PIIDetector()
        self.redactor = Redactor()
        self.signer = DocumentSigner(keys_dir=keys_dir)
        self.auditor = AuditLogger(db_path=db_path)

    def run(self, job_id: str, file_path: Path, original_name: str) -> ProcessResult:
        """Execute the full pipeline on a single document."""
        start = time.time()
        logger.info("[%s] START → %s", job_id, original_name)

        # ── 1. Validate ──────────────────────────────────────────────────
        try:
            self.validator.validate(file_path)
            logger.info("[%s] VALIDATE ✓", job_id)
        except ValidationError as exc:
            logger.warning("[%s] VALIDATE FAILED: %s", job_id, exc)
            self.validator.reject(file_path, str(exc))
            return ProcessResult(
                job_id=job_id,
                filename=original_name,
                status=JobStatus.FAILED,
                error=str(exc),
                duration_seconds=time.time() - start,
            )

        # ── 2. Extract ───────────────────────────────────────────────────
        logger.info("[%s] EXTRACT …", job_id)
        pages = self.extractor.extract(file_path)
        logger.info("[%s] EXTRACT ✓ — %d pages", job_id, len(pages))

        # ── 3. Detect PII ────────────────────────────────────────────────
        logger.info("[%s] DETECT …", job_id)
        all_entities: List[DetectedEntity] = []
        for page in pages:
            entities = self.detector.detect(page.text, page.page_number)
            all_entities.extend(entities)
        logger.info("[%s] DETECT ✓ — %d entities found", job_id, len(all_entities))

        # ── 3b. Resolve bounding boxes ───────────────────────────────────
        # Map each entity's character offset back to the extraction
        # bounding boxes. This enables position-aware redaction.
        page_map = {p.page_number: p for p in pages}
        resolved = 0
        for entity in all_entities:
            if entity.bbox:
                resolved += 1
                continue  # Already has a bbox (e.g. from OCR)
            page_content = page_map.get(entity.page)
            if page_content is None:
                continue
            bboxes = page_content.get_bboxes_for_range(entity.start, entity.end)
            if bboxes:
                # Use the first bbox (most entities fit in one span)
                # For multi-span entities, merge into one encompassing rect
                if len(bboxes) == 1:
                    entity.bbox = bboxes[0]
                else:
                    # Merge: take min x0/y0, max x1/y1
                    x0 = min(b[0] for b in bboxes)
                    y0 = min(b[1] for b in bboxes)
                    x1 = max(b[2] for b in bboxes)
                    y1 = max(b[3] for b in bboxes)
                    entity.bbox = [x0, y0, x1, y1]
                resolved += 1
        logger.info(
            "[%s] BBOX ✓ — %d/%d entities resolved to bounding boxes",
            job_id, resolved, len(all_entities),
        )

        # ── 4. Redact ────────────────────────────────────────────────────
        logger.info("[%s] REDACT …", job_id)
        redacted_path = self.processed_dir / f"{job_id}_redacted.pdf"
        self.redactor.redact(file_path, all_entities, redacted_path)
        logger.info("[%s] REDACT ✓ → %s", job_id, redacted_path.name)

        # ── 5. Sign ──────────────────────────────────────────────────────
        logger.info("[%s] SIGN …", job_id)
        signed_path = self.signed_dir / f"{job_id}_signed.pdf"
        self.signer.sign(redacted_path, signed_path)
        logger.info("[%s] SIGN ✓ → %s", job_id, signed_path.name)

        # ── 6. Audit ─────────────────────────────────────────────────────
        logger.info("[%s] AUDIT …", job_id)
        duration = time.time() - start
        result = ProcessResult(
            job_id=job_id,
            filename=original_name,
            status=JobStatus.COMPLETED,
            entity_count=len(all_entities),
            entities=all_entities,
            output_path=str(signed_path),
            duration_seconds=duration,
        )
        self.auditor.log(result)
        logger.info("[%s] AUDIT ✓", job_id)

        logger.info(
            "[%s] END ✓ — %d entities, %.2fs", job_id, len(all_entities), duration
        )
        return result
