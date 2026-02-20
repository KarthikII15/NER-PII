
# Phase 2 — Core Development: Detailed Execution Guide

> **Phase:** 2 of 6
> **Duration:** 10 Days (Week 2–3)
> **Exit Gate:** End-to-end processing of a test PDF. Latency < 15s/page.
> **Entry Gate:** Phase 1 complete. `secure-doc-ai` container running.

---

## Task PROC-01: Implement File Watcher & Ingestion

**Owner:** Backend Lead | **Day:** 6 | **Complexity:** Medium
**Goal:** Detect new files in `/app/storage/uploads` and move them to processing.

### Steps

**Step 1.1 — Create `app/core/watcher.py`**
*   **Dependency:** `watchdog`
*   **Logic:**
    *   Subclass `FileSystemEventHandler`.
    *   On `on_created`:
        1.  Wait 1s for write to finish (debounce).
        2.  Generate `job_id` (UUID4).
        3.  Move file to `/app/storage/processing/{job_id}.pdf`.
        4.  Trigger `Pipeline.process(job_id)`.
*   **Error Handling:** If move fails, log error and retry once.

**Step 1.2 — Update `app/main.py` startup event**
*   Initialize `Observer` in `@app.on_event("startup")`.
*   Start watcher thread on `settings.UPLOAD_DIR`.

### Verification Gate — PROC-01
```powershell
# 1. Drop a file
docker cp test.pdf pii_processor:/app/storage/uploads/
# 2. Check logs
docker logs pii_processor
# Expected: "INFO: Detected new file: test.pdf. Moved to processing/{uuid}..."
```

---

## Task PROC-02: Implement Validation Service (The 5-Gate Check)

**Owner:** Backend Lead | **Day:** 7 | **Complexity:** Low
**Goal:** Reject invalid/unsafe files before they touch the pipeline.

### Steps

**Step 2.1 — Create `app/core/validator.py`**
*   **Class:** `FileValidator`
*   **Method:** `validate(file_path: Path) -> bool`
*   **Gates:**
    1.  **Extension:** Must be `.pdf`, `.jpg`, `.png`.
    2.  **MIME (Magic):** Must be `application/pdf` or `image/...`.
    3.  **Size:** Must be < `settings.MAX_FILE_SIZE_MB` (50MB).
    4.  **Encryption:** PDF must not be password protected (using `pymupdf`).
    5.  **Page Count:** Must be < 50 pages (MVP limit).
*   **Action:** If fail, move to `/app/storage/error/` and log reason.

### Verification Gate — PROC-02
*   **Unit Test:** `tests/unit/test_validator.py`
    *   Test passing file.
    *   Test >50MB file (fail).
    *   Test `.exe` renamed to `.pdf` (fail Magic check).

---

## Task PROC-03: Implement Processing Pipeline (Orchestrator)

**Owner:** Backend Lead | **Day:** 8–9 | **Complexity:** High
**Goal:** The "Brain" that ties OCR, NER, and Redaction together.

### Steps

**Step 3.1 — Create `app/models/document.py`**
*   Pydantic models: `ProcessRequest`, `ProcessResult`, `DetectedEntity`.

**Step 3.2 — Create `app/core/pipeline.py`**
*   **Class:** `Pipeline`
*   **Method:** `run_pipeline(job_id: str, file_path: Path)`
*   **Flow:**
    1.  `Validator.validate()`
    2.  `Extractor.extract_text_and_images()`
    3.  `Detector.analyze(text)` → List[Entity]
    4.  `Redactor.apply(file_path, entities)` → Output Path
    5.  `Signer.sign(output_path)`
    6.  `Audit.log(job_id, entities)`
    7.  Move original to `/app/storage/archive` (or delete based on policy).

**Step 3.3 — Implement "No-Op" Stubs**
*   Create empty classes for `Extractor`, `Detector`, `Redactor` to allow Pipeline to run without ML yet.

### Verification Gate — PROC-03
*   Run pipeline with "No-Op" stubs.
*   Input file -> Output file (unchanged but moved).
*   Logs show full trace: `START -> VALIDATE -> EXTRACT -> DETECT -> REDACT -> SIGN -> END`.

---

## Task PROC-04: Connect ML Services (The "Smart" Parts)

**Owner:** ML Engineer | **Day:** 10–13 | **Complexity:** Very High

### Steps

**Step 4.1 — Extraction (`app/services/extraction/`)**
*   **Text:** Use `pymupdf` (`page.get_text("dict")`) to get text + existing bounding boxes.
*   **OCR:** Use `RapidOCR` (ONNX) if page text is empty/garbled.

**Step 4.2 — Detection (`app/services/detection/`)**
*   **Regex:** `regex_detector.py` (SSN, Email, Phone).
*   **NER:** `ner_detector.py` loads `distilbert-base-uncased-finetuned-ner`.
    *   **Optimization:** Quantize to INT8 using `optimum` (if not already done).
    *   **Logic:** Run inference on extracted text chunks. Map token indices back to bounding boxes.

**Step 4.3 — Redaction (`app/services/redaction/`)**
*   `text_redactor.py`: Use `pymupdf` → `page.add_redact_annot(rect)` → `page.apply_redactions()`.
    *   **Crucial:** Set `fill=(0, 0, 0)` (Black box).

### Verification Gate — PROC-04
*   **Golden Test:**
    *   Input: `sample_pii.pdf` (contains "John Doe" and "555-0199").
    *   Output: PDF with black boxes over "John Doe" and "555-0199".
    *   **Text Layer Check:** Copy-paste from redacted area must yield nothing.

---

## Task PROC-05 & QA-01: Audit, Signing & End-to-End Test

**Owner:** Security Lead | **Day:** 14–15 | **Complexity:** Medium

### Steps

**Step 5.1 — Digital Signing (`app/services/signing/`)**
*   Generate/Load P-256 private key.
*   Sign the Redacted PDF using `pyHanko` or `cryptography`.
*   Append visual signature stamp (optional for MVP, sticking to digital sig).

**Step 5.2 — Audit Logger (`app/services/audit/`)**
*   Write job details to `jobs` table in `audit.db`.
*   **Schema:** `job_id`, `timestamp_utc`, `filename`, `entity_counts` (JSON), `params_hash`.

**100-File Integration Loop**
*   Script: `tests/integration/soak_test.py`
*   Loop 100 times:
    *   Generate random invoice PDF (using `fpdf`).
    *   Copy to `/uploads`.
    *   Poll `/stats` or wait for `/processed`.
    *   Assert output exists and is valid PDF.
    *   Assert DB record exists.

### Verification Gate — Phase 2 Exit
*   **Latency:** Average < 10s per page on the 100-file loop.
*   **Accuracy:** Manually check 5 random output files.
*   **Stability:** No crash (OOM) during loop. `docker stats` shows RAM < 4GB.

---

## Phase 2 Exit Checklist

| Gate | Check | Verified By |
|---|---|---|
| G1 | Watcher picks up file < 2s | `logs` |
| G2 | Invalid file (password protected) rejected | `test_validator.py` |
| G3 | PII (SSN/Phone) redacted in output | Manual Review |
| G4 | Redacted text NOT copy-pasteable | Manual Review |
| G5 | Output PDF has valid digital signature | Acrobat Reader / `pdfsig` |
| G6 | Audit DB contains 1 record per job | `sqlite3` query |
| G7 | Latency p95 < 15s | `soak_test.py` |
