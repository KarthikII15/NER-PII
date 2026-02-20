"""
main.py — Secure Doc AI FastAPI entrypoint (Phase 2).
Wires up: FileWatcher → Pipeline → API endpoints.
"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

# ── Logging setup ────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Settings ─────────────────────────────────────────────────────────────
# Import settings; this validates API_KEY is set
from config.settings import settings

# ── Pipeline + Watcher ───────────────────────────────────────────────────
from app.core.pipeline import Pipeline
from app.core.watcher import FileWatcher
from app.services.audit.logger import AuditLogger


# Shared instances (created in lifespan)
_pipeline: Optional[Pipeline] = None
_watcher: Optional[FileWatcher] = None
_auditor: Optional[AuditLogger] = None


def _pipeline_callback(job_id: str, file_path: Path, original_name: str):
    """Called by the file watcher when a new file is detected."""
    if _pipeline:
        _pipeline.run(job_id, file_path, original_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — initialise pipeline and watcher."""
    global _pipeline, _watcher, _auditor

    # Derive local paths (for dev) or container paths
    upload_dir = settings.upload_dir
    processed_dir = settings.processed_dir
    signed_dir = settings.signed_dir
    keys_dir = settings.keys_dir
    db_path = settings.db_path
    error_dir = str(Path(upload_dir).parent / "error")
    processing_dir = str(Path(upload_dir).parent / "processing")

    # Ensure directories exist
    for d in [upload_dir, processed_dir, signed_dir, keys_dir, error_dir, processing_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Init pipeline
    _pipeline = Pipeline(
        processed_dir=processed_dir,
        signed_dir=signed_dir,
        error_dir=error_dir,
        keys_dir=keys_dir,
        db_path=db_path,
        max_size_mb=settings.max_file_size_mb,
    )
    _auditor = _pipeline.auditor
    logger.info("Pipeline initialized")

    # Init watcher
    _watcher = FileWatcher(
        watch_dir=upload_dir,
        processing_dir=processing_dir,
        pipeline_callback=_pipeline_callback,
    )
    _watcher.start()

    yield  # ── App runs here ──

    # Shutdown
    if _watcher:
        _watcher.stop()
    logger.info("Shutdown complete")


# ── FastAPI App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Secure Doc AI",
    description="On-premise PII detection and redaction service.",
    version="0.2.0",
    lifespan=lifespan,
)


# ── Health endpoints (unchanged from Phase 1) ───────────────────────────

@app.get("/health/live", tags=["Health"])
async def liveness():
    """Kubernetes-style liveness probe."""
    return JSONResponse(content={
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/health/ready", tags=["Health"])
async def readiness():
    """Readiness probe — checks pipeline and DB are available."""
    checks = {
        "pipeline": "ready" if _pipeline else "not_ready",
        "watcher": "running" if _watcher else "stopped",
        "database": "connected" if _auditor else "not_connected",
    }
    status = "ready" if all(v in ("ready", "running", "connected") for v in checks.values()) else "not_ready"
    return JSONResponse(content={
        "status": status,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Processing endpoints ────────────────────────────────────────────────

@app.post("/api/v1/process", tags=["Processing"])
async def process_file(file: UploadFile = File(...)):
    """
    Upload a document for PII detection and redaction.
    Returns the processing result with detected entity counts.
    """
    if not _pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not ready")

    # Save uploaded file to the uploads dir
    upload_path = Path(settings.upload_dir) / file.filename
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info("API upload: %s (%d bytes)", file.filename, len(content))

    # Process synchronously (for MVP; background task in Phase 3)
    from uuid import uuid4
    job_id = uuid4().hex
    processing_dir = Path(settings.upload_dir).parent / "processing"
    processing_path = processing_dir / f"{job_id}{upload_path.suffix}"
    processing_dir.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.move(str(upload_path), str(processing_path))

    result = _pipeline.run(job_id, processing_path, file.filename)

    return JSONResponse(content={
        "job_id": result.job_id,
        "status": result.status.value,
        "filename": result.filename,
        "entity_count": result.entity_count,
        "duration_seconds": round(result.duration_seconds, 2),
        "output_path": result.output_path,
    })


@app.get("/api/v1/jobs/{job_id}", tags=["Processing"])
async def get_job(job_id: str):
    """Retrieve processing results for a specific job."""
    if not _auditor:
        raise HTTPException(status_code=503, detail="Audit DB not ready")

    job = _auditor.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(content=job)


@app.get("/api/v1/stats", tags=["Processing"])
async def get_stats():
    """Return aggregate processing statistics."""
    if not _auditor:
        raise HTTPException(status_code=503, detail="Audit DB not ready")

    stats = _auditor.get_stats()
    stats["timestamp"] = datetime.now(timezone.utc).isoformat()
    return JSONResponse(content=stats)


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Secure Doc AI — Phase 2 Core Pipeline Active"}
