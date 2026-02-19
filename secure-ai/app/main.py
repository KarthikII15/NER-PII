"""
main.py — Secure Doc AI FastAPI entrypoint.
Phase 1: Hello World only. Business logic added in Phase 2.
"""
import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Secure Doc AI",
    description="On-premise PII detection and redaction service.",
    version="0.1.0",
)

logger = logging.getLogger(__name__)


@app.get("/health/live", tags=["Health"])
async def liveness():
    """Kubernetes-style liveness probe. Always returns 200 if container is running."""
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/health/ready", tags=["Health"])
async def readiness():
    """Readiness probe. Phase 1: always ready. Phase 2+: checks model + DB."""
    return JSONResponse(
        content={
            "status": "ready",
            "checks": {
                "model": "not_loaded",   # Updated in Phase 2
                "database": "not_checked",  # Updated in Phase 2
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Secure Doc AI — Phase 1 Foundation"}
