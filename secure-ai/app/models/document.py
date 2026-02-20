"""
document.py — Pydantic models for processing pipeline data objects.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    DETECTING = "detecting"
    REDACTING = "redacting"
    SIGNING = "signing"
    AUDITING = "auditing"
    COMPLETED = "completed"
    FAILED = "failed"


class DetectedEntity(BaseModel):
    """A single PII entity found in a document."""
    entity_type: str          # e.g. "SSN", "PHONE", "PERSON", "EMAIL"
    text: str                 # The raw PII text matched
    start: int                # Start char offset in extracted text
    end: int                  # End char offset in extracted text
    confidence: float = 1.0   # 0.0 – 1.0
    page: int = 0             # Page number (0-indexed)
    source: str = "regex"     # "regex" | "ner"

    # Bounding box for redaction (if available from OCR/text extraction)
    bbox: Optional[List[float]] = None  # [x0, y0, x1, y1]


class ProcessRequest(BaseModel):
    """A request to process a single document."""
    job_id: str = Field(default_factory=lambda: uuid4().hex)
    filename: str
    file_path: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ProcessResult(BaseModel):
    """The result of processing a single document."""
    job_id: str
    filename: str
    status: JobStatus = JobStatus.COMPLETED
    entity_count: int = 0
    entities: List[DetectedEntity] = Field(default_factory=list)
    output_path: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
