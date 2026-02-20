"""
extractor.py — Text + bounding-box extraction from PDF and image files.
Uses PyMuPDF for native PDF text and RapidOCR for scanned/image-based pages.

Key design: Each TextBlock records its character offset range within the
full page text. This enables mapping detected PII entities (which have
character offsets) back to exact bounding boxes for precise redaction.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # pymupdf

logger = logging.getLogger(__name__)

# Minimum characters on a page before we fall back to OCR
_MIN_TEXT_THRESHOLD = 20


@dataclass
class TextBlock:
    """A block of text with its bounding box and character offset range."""
    text: str
    bbox: List[float]       # [x0, y0, x1, y1]
    page_number: int
    char_start: int = 0     # Start offset in full page text
    char_end: int = 0       # End offset in full page text


@dataclass
class PageContent:
    """Extracted content for one page."""
    page_number: int
    text: str
    blocks: List[TextBlock] = field(default_factory=list)
    ocr_used: bool = False

    def get_bboxes_for_range(
        self, start: int, end: int
    ) -> List[List[float]]:
        """
        Return bounding boxes covering the character range [start, end).
        An entity may span multiple TextBlocks, so this can return
        multiple bboxes.
        """
        bboxes = []
        for block in self.blocks:
            # Check if block overlaps with the requested range
            if block.char_end <= start:
                continue
            if block.char_start >= end:
                break  # blocks are sorted by offset, no more overlaps
            bboxes.append(block.bbox)
        return bboxes


class TextExtractor:
    """Extracts text (+ bounding boxes) from PDFs and images."""

    def __init__(self):
        self._ocr_engine = None  # Lazy-loaded RapidOCR

    def extract(self, file_path: Path) -> List[PageContent]:
        """Extract text from all pages of a PDF or from a single image."""
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_pdf(file_path)
        elif suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif"):
            return [self._extract_image(file_path)]
        else:
            logger.warning("Unsupported file type for extraction: %s", suffix)
            return []

    # ── PDF extraction ───────────────────────────────────────────────────

    def _extract_pdf(self, pdf_path: Path) -> List[PageContent]:
        doc = fitz.open(str(pdf_path))
        pages: List[PageContent] = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text_dict = page.get_text("dict")
            blocks: List[TextBlock] = []
            line_texts: List[str] = []
            current_offset = 0

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # type 0 = text block
                    continue
                for line in block.get("lines", []):
                    span_texts = []
                    for span in line.get("spans", []):
                        txt = span.get("text", "").strip()
                        if not txt:
                            continue
                        bbox = list(span.get("bbox", [0, 0, 0, 0]))

                        # Record the character offset range for this span
                        # within the full page text, accounting for the
                        # position it will have after joining lines with \n
                        # We'll compute final offsets after building the text
                        blocks.append(TextBlock(
                            text=txt,
                            bbox=bbox,
                            page_number=page_idx,
                            char_start=0,  # placeholder
                            char_end=0,    # placeholder
                        ))
                        span_texts.append(txt)
                    if span_texts:
                        line_texts.append(" ".join(span_texts))

            # Build the full text with line breaks
            full_text = "\n".join(line_texts)

            # Now compute the exact char offsets for each block
            # by finding each block's text in the full_text sequentially
            search_from = 0
            for blk in blocks:
                idx = full_text.find(blk.text, search_from)
                if idx >= 0:
                    blk.char_start = idx
                    blk.char_end = idx + len(blk.text)
                    search_from = idx  # don't advance past, overlaps possible
                else:
                    # If exact match not found, approximate
                    blk.char_start = search_from
                    blk.char_end = search_from + len(blk.text)

            # Fall back to OCR if page has very little native text
            if len(full_text.strip()) < _MIN_TEXT_THRESHOLD:
                logger.info(
                    "Page %d has < %d chars — using OCR",
                    page_idx, _MIN_TEXT_THRESHOLD,
                )
                ocr_page = self._ocr_page(page, page_idx)
                ocr_page.ocr_used = True
                pages.append(ocr_page)
            else:
                pages.append(PageContent(
                    page_number=page_idx,
                    text=full_text,
                    blocks=blocks,
                ))

        doc.close()
        return pages

    # ── OCR for scanned pages ────────────────────────────────────────────

    def _ocr_page(self, page: fitz.Page, page_idx: int) -> PageContent:
        """Render page to image and run Tesseract OCR."""
        try:
            import pytesseract
            from PIL import Image
            import io
        except ImportError:
            logger.warning("Tesseract/PIL not installed — returning empty text")
            return PageContent(page_number=page_idx, text="", ocr_used=True)

        # Render high-res image (300 DPI)
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))

        # Run Tesseract
        try:
            # Output dict has keys: 'left', 'top', 'width', 'height', 'text', 'conf'
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractNotFoundError:
            logger.error("Tesseract binary not found in PATH")
            return PageContent(page_number=page_idx, text="", ocr_used=True)

        blocks: List[TextBlock] = []
        text_parts: List[str] = []
        current_offset = 0
        
        # Scaling factor: PyMuPDF bbox is in PDF points (72 DPI usually),
        # but our image was rendered at 300 DPI. We need to scale back.
        scale = 72 / 300

        n_boxes = len(data["text"])
        for i in range(n_boxes):
            text = data["text"][i].strip()
            # Tesseract returns empty strings for layout blocks, skip them
            # Also skip low confidence matched noise if needed (conf usually 0-100)
            if not text:
                continue
            
            # Tesseract Coords (pixels at 300 DPI)
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            
            # Convert to PDF Points
            x0 = x * scale
            y0 = y * scale
            x1 = (x + w) * scale
            y1 = (y + h) * scale
            bbox = [x0, y0, x1, y1]

            blocks.append(TextBlock(
                text=text,
                bbox=bbox,
                page_number=page_idx,
                char_start=current_offset,
                char_end=current_offset + len(text),
            ))
            text_parts.append(text)
            current_offset += len(text) + 1  # Space

        return PageContent(
            page_number=page_idx,
            text=" ".join(text_parts),
            blocks=blocks,
            ocr_used=True,
        )

    # ── Single image extraction ──────────────────────────────────────────

    def _extract_image(self, img_path: Path) -> PageContent:
        """OCR a standalone image file."""
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            logger.warning("Tesseract/PIL not installed — returning empty text")
            return PageContent(page_number=0, text="", ocr_used=True)

        try:
            image = Image.open(str(img_path))
            # Output dict has keys: 'left', 'top', 'width', 'height', 'text', 'conf'
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception:
            logger.error("Tesseract processing failed for %s", img_path)
            return PageContent(page_number=0, text="", ocr_used=True)

        blocks: List[TextBlock] = []
        text_parts: List[str] = []
        current_offset = 0

        # For standalone images, we treat pixels as points (1:1), 
        # unless we want to try to infer DPI. For now, 1:1 is safest.
        
        n_boxes = len(data["text"])
        for i in range(n_boxes):
            text = data["text"][i].strip()
            if not text:
                continue

            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            bbox = [float(x), float(y), float(x + w), float(y + h)]

            blocks.append(TextBlock(
                text=text, bbox=bbox, page_number=0,
                char_start=current_offset,
                char_end=current_offset + len(text),
            ))
            text_parts.append(text)
            current_offset += len(text) + 1

        return PageContent(
            page_number=0,
            text=" ".join(text_parts),
            blocks=blocks,
            ocr_used=True,
        )
