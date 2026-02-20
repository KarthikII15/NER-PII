"""
detector.py — PII detection engine combining regex patterns and NER.

Document-agnostic: works for resumes, invoices, contracts, medical records, etc.
No document-type-specific heuristics or blocklists.
"""
import logging
import re
from typing import List

from app.models.document import DetectedEntity

logger = logging.getLogger(__name__)

# ── Regex Patterns (universal PII patterns) ──────────────────────────────
_PATTERNS = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE_US": re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "PHONE_IN": re.compile(
        r"(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b"
    ),
    "EMAIL": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    ),
    "AADHAAR": re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"),
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "DATE_OF_BIRTH": re.compile(
        r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b"
    ),
    "IP_ADDRESS": re.compile(
        r"\b(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)){3}\b"
    ),
    "URL_LINKEDIN": re.compile(
        r"\b(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+\b"
    ),
    "URL_GITHUB": re.compile(
        r"\b(?:https?://)?(?:www\.)?github\.com/[\w-]+\b"
    ),
}

# Minimum NER confidence to accept an entity
_NER_CONFIDENCE_THRESHOLD = 0.90

# Minimum entity text length (filters out sub-word fragments)
_MIN_ENTITY_LENGTH = 3


class PIIDetector:
    """Detect PII in text using regex + optional NER model."""

    def __init__(self, use_ner: bool = True):
        self._ner = None
        self._use_ner = use_ner

        if use_ner:
            self._load_ner()

    def detect(self, text: str, page_number: int = 0) -> List[DetectedEntity]:
        """Run all detectors on text and return a deduplicated entity list."""
        entities: List[DetectedEntity] = []

        # 1. Regex detection (fast, high precision)
        entities.extend(self._detect_regex(text, page_number))

        # 2. NER detection (catches PERSON, ORG, LOCATION)
        if self._ner is not None:
            entities.extend(self._detect_ner(text, page_number))

        # Deduplicate overlapping entities (prefer higher confidence)
        entities = self._deduplicate(entities)

        # Log final entities for debugging
        for e in entities:
            logger.info(
                "  ENTITY: %-14s | conf=%.2f | src=%-10s | \"%s\"",
                e.entity_type, e.confidence, e.source, e.text,
            )

        return entities

    # ── Regex ─────────────────────────────────────────────────────────────

    def _detect_regex(self, text: str, page: int) -> List[DetectedEntity]:
        found = []
        for entity_type, pattern in _PATTERNS.items():
            for match in pattern.finditer(text):
                found.append(DetectedEntity(
                    entity_type=entity_type,
                    text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    confidence=1.0,
                    page=page,
                    source="regex",
                ))
        return found

    # ── NER ───────────────────────────────────────────────────────────────

    def _load_ner(self):
        """Lazy-load the HuggingFace NER pipeline."""
        try:
            from transformers import pipeline as hf_pipeline
            self._ner = hf_pipeline(
                "ner",
                model="elastic/distilbert-base-uncased-finetuned-conll03-english",
                aggregation_strategy="simple",
                device=-1,  # CPU
            )
            logger.info("NER model loaded: elastic/distilbert-base-uncased")
        except Exception:
            logger.warning("NER model not available — regex-only detection")
            self._ner = None

    def _detect_ner(self, text: str, page: int) -> List[DetectedEntity]:
        """Run NER model on text chunks (max 512 tokens per chunk)."""
        if self._ner is None:
            return []

        found = []
        chunk_size = 450
        for chunk_start in range(0, len(text), chunk_size):
            chunk = text[chunk_start: chunk_start + chunk_size]
            try:
                results = self._ner(chunk)
            except Exception:
                logger.exception("NER inference failed on chunk at %d", chunk_start)
                continue

            for ent in results:
                label = ent.get("entity_group", "").upper()
                if label not in ("PER", "LOC", "ORG"):
                    continue

                text_content = ent["word"].strip()

                # Filter 1: Too short (sub-word fragments)
                if len(text_content) < _MIN_ENTITY_LENGTH:
                    continue

                # Filter 2: Confidence threshold
                if ent["score"] < _NER_CONFIDENCE_THRESHOLD:
                    logger.debug(
                        "NER SKIP (conf=%.2f): %s = \"%s\"",
                        ent["score"], label, text_content,
                    )
                    continue

                mapped_type = {
                    "PER": "PERSON",
                    "LOC": "LOCATION",
                    "ORG": "ORGANIZATION",
                }.get(label, label)

                found.append(DetectedEntity(
                    entity_type=mapped_type,
                    text=text_content,
                    start=chunk_start + ent["start"],
                    end=chunk_start + ent["end"],
                    confidence=round(ent["score"], 4),
                    page=page,
                    source="ner",
                ))

        return found

    # ── Dedup ─────────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(entities: List[DetectedEntity]) -> List[DetectedEntity]:
        """Remove overlapping entities, keeping the highest-confidence match."""
        if not entities:
            return []

        entities.sort(key=lambda e: (e.start, -e.confidence))
        deduped = [entities[0]]

        for ent in entities[1:]:
            prev = deduped[-1]
            if ent.start < prev.end:
                continue
            deduped.append(ent)

        return deduped
