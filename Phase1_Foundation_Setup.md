
# Phase 1 — Foundation Setup: Detailed Execution Guide

> **Phase:** 1 of 6
> **Duration:** 5 Days (Week 1)
> **Exit Gate:** `docker-compose up` → `/health/live` returns `200 OK`
> **Entry Gate:** `Architecture_Baseline_Approval.md` signed. WSL2 + Docker Desktop installed.

---

## Pre-Phase Checklist (Before Day 1)

Run on the **target Windows 11 Pro machine**. All items must be **PASS** before starting.

| # | Check | Command | Expected |
|---|---|---|---|
| P1 | WSL2 installed | `wsl --status` | `Default Version: 2` |
| P2 | Docker Desktop running | `docker info` | No error |
| P3 | Docker WSL2 backend | `docker info \| grep "WSL2"` | `wsl2` present |
| P4 | Git installed | `git --version` | `git version 2.x` |
| P5 | Python 3.10+ available | `python --version` | `Python 3.10+` |
| P6 | BitLocker status | `manage-bde -status C:` | `Protection On` (note: can be WARN for now, must pass by Phase 5 Go-Live) |

---

## Task INFRA-01: Initialize Git Repository

**Owner:** Engineering Lead | **Day:** 1 | **Duration:** 1 hour

### Steps

**Step 1.1 — Create root directory**
```powershell
# In PowerShell on Dev machine
mkdir "c:\Projects\secure-doc-ai"
cd "c:\Projects\secure-doc-ai"
```

**Step 1.2 — Initialize Git repo**
```powershell
git init
git branch -M main
```

**Step 1.3 — Create `.gitignore`**

Create file `secure-doc-ai/.gitignore`:
```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# Environment
.env
*.env

# Storage (never commit documents)
backend/storage/uploads/*
backend/storage/processed/*
backend/storage/signed/*
backend/storage/keys/*.pem
backend/storage/keys/*.key
backend/storage/keys/*.crt
!backend/storage/uploads/.gitkeep
!backend/storage/processed/.gitkeep
!backend/storage/signed/.gitkeep
!backend/storage/keys/.gitkeep

# Models (use Git LFS)
backend/models_bin/*.onnx
!backend/models_bin/.gitkeep

# SQLite
*.db
*.db-wal
*.db-shm

# Docker
.docker/

# OS
.DS_Store
Thumbs.db
```

**Step 1.4 — Create `.env.example`**

Create file `secure-doc-ai/.env.example`:
```ini
# Application
APP_ENV=development
LOG_LEVEL=INFO
API_KEY=CHANGE_ME_BEFORE_GO_LIVE

# Storage Paths (relative inside container)
UPLOAD_DIR=/app/storage/uploads
PROCESSED_DIR=/app/storage/processed
SIGNED_DIR=/app/storage/signed
KEYS_DIR=/app/storage/keys

# Database
DB_PATH=/app/storage/audit.db

# Performance
MAX_FILE_SIZE_MB=50
PROCESSING_TIMEOUT_SECONDS=30
```

**Step 1.5 — Create directory scaffold**
```powershell
$base = "c:\Projects\secure-doc-ai"
$dirs = @(
  "config\policies",
  "app\api\routes\v1",
  "app\core",
  "app\services\extraction",
  "app\services\detection",
  "app\services\redaction",
  "app\services\signing",
  "app\services\audit",
  "app\models",
  "app\db",
  "app\utils",
  "backend\storage\uploads",
  "backend\storage\processed",
  "backend\storage\signed",
  "backend\storage\keys",
  "backend\models_bin",
  "backend\scripts",
  "backend\tests\unit",
  "backend\tests\integration",
  "infrastructure\github\workflows",
  "docs\architecture",
  "docs\api",
  "docs\runbooks",
  "docs\risk",
  "frontend\src\components",
  "frontend\src\services"
)
foreach ($d in $dirs) {
  New-Item -ItemType Directory -Force -Path "$base\$d" | Out-Null
  # Create .gitkeep to preserve empty dirs
  New-Item -ItemType File -Force -Path "$base\$d\.gitkeep" | Out-Null
}
Write-Host "Scaffold complete."
```

**Step 1.6 — Create initial README**

Create file `secure-doc-ai/README.md`:
```markdown
# Secure Doc AI — Edge PII Detection System

On-premise, CPU-optimised PII detection, redaction, and audit system.
Zero data egress. Docker-based deployment.

## Quick Start
1. Copy `.env.example` → `.env` and fill in `API_KEY`
2. Run `docker-compose up -d`
3. Call `GET /health/live`

## Requirements
- Windows 11 Pro + WSL2 + Docker Desktop
- Intel i3 (2C/4T), 16GB RAM
```

**Step 1.7 — Initial commit**
```powershell
git add .
git commit -m "chore(INFRA-01): Initialize monorepo scaffold"
```

### Verification Gate — INFRA-01
```powershell
git log --oneline   # Should show: "chore(INFRA-01): Initialize monorepo scaffold"
git status          # Should show: "nothing to commit, working tree clean"
```
**PASS criteria:** Clean working tree. `.gitignore` excludes `.env`.

---

## Task INFRA-02: Configure WSL2 Resources

**Owner:** DevOps Engineer | **Day:** 1 | **Duration:** 30 min

### Steps

**Step 2.1 — Create `.wslconfig`**

Create file at `C:\Users\<YourUser>\.wslconfig`:
```ini
[wsl2]
memory=8GB
processors=2
swap=0
localhostForwarding=true
```

> **Why `swap=0`?** Prevents WSL2 from writing PII pages to a Windows swap file, which BitLocker does NOT protect in all configurations.

**Step 2.2 — Apply WSL2 config**
```powershell
wsl --shutdown
# Wait 10 seconds
docker info   # Restart Docker Desktop if Docker cannot connect
```

### Verification Gate — INFRA-02
```powershell
wsl -d Ubuntu -- free -h
```
**PASS criteria:** Total memory shown ≤ 8GB.

---

## Task INFRA-03: Write Hardened Dockerfile

**Owner:** DevOps / Engineering Lead | **Day:** 2 | **Duration:** 2 hours

### Steps

**Step 3.1 — Create `backend/Dockerfile`**
```dockerfile
# syntax=docker/dockerfile:1

# ── Stage 1: Build ───────────────────────────────────────────────────────────
FROM python:3.10-slim AS builder

WORKDIR /build

# Install build tools + libmagic
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.10-slim AS runtime

# Install runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (UID 1001)
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appgroup . .

# Create storage dirs with correct ownership
RUN mkdir -p /app/storage/uploads \
             /app/storage/processed \
             /app/storage/signed \
             /app/storage/keys \
    && chown -R appuser:appgroup /app/storage

# Switch to non-root
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**Step 3.2 — Create `backend/requirements.txt`**
```txt
# Web Framework
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.1
pydantic-settings==2.2.1
python-multipart==0.0.9

# Document Processing
pymupdf==1.24.2
python-magic==0.4.27

# OCR
onnxruntime==1.18.0
rapidocr-onnxruntime==1.3.22
pytesseract==0.3.10

# NER / ML
transformers==4.40.2
tokenizers==0.19.1

# Security
cryptography==42.0.7

# Database
sqlalchemy==2.0.29

# Observability
prometheus-client==0.20.0
python-json-logger==2.0.7

# Utilities
google-re2==1.1
watchdog==4.0.0
```

### Verification Gate — INFRA-03
```powershell
cd c:\Projects\secure-doc-ai\backend
docker build -t secure-doc-ai:test .
```
**PASS criteria:** Build completes with no errors. Image tagged `secure-doc-ai:test` exists.
```powershell
docker images secure-doc-ai  # Should list the image
docker run --rm secure-doc-ai:test id  # Should show uid=1001(appuser)
```

---

## Task INFRA-04: Create Hello World FastAPI App

**Owner:** Engineering Lead | **Day:** 2 | **Duration:** 2 hours

This creates the **minimal working API** — just enough to prove the container works. No business logic yet.

**Step 4.1 — Create `app/main.py`**
```python
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
```

**Step 4.2 — Create `config/settings.py`**
```python
"""
settings.py — Application configuration via environment variables.
Fails fast on missing API_KEY to prevent running with defaults.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    api_key: str  # Required. No default. Will raise ValidationError if missing.

    upload_dir: str = "/app/storage/uploads"
    processed_dir: str = "/app/storage/processed"
    signed_dir: str = "/app/storage/signed"
    keys_dir: str = "/app/storage/keys"
    db_path: str = "/app/storage/audit.db"

    max_file_size_mb: int = 50
    processing_timeout_seconds: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

### Verification Gate — INFRA-04
Build and run locally:
```powershell
cd c:\Projects\secure-doc-ai\backend
pip install fastapi uvicorn pydantic-settings
$env:API_KEY = "test-key-123"
uvicorn app.main:app --port 8000
```
In a second terminal:
```powershell
Invoke-WebRequest -Uri http://localhost:8000/health/live
```
**PASS criteria:** Response `{"status": "ok", "timestamp": "..."}` with HTTP 200.

---

## Task INFRA-05: Create `docker-compose.yml`

**Owner:** DevOps Engineer | **Day:** 3 | **Duration:** 2 hours

**Step 5.1 — Create `docker-compose.yml`** in `infrastructure/`:
```yaml
version: "3.9"

services:
  processor:
    image: secure-doc-ai:latest
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: pii_processor
    restart: unless-stopped
    network_mode: "host"          # Localhost only. No external exposure.
    user: "1001:1001"             # Non-root. Matches Dockerfile UID.
    read_only: true               # Read-only filesystem.
    tmpfs:
      - /tmp:size=256m,mode=1777  # RAM-only scratch. PII never hits disk.
    volumes:
      - uploads_vol:/app/storage/uploads
      - processed_vol:/app/storage/processed
      - signed_vol:/app/storage/signed
      - keys_vol:/app/storage/keys
      - audit_db_vol:/app/storage
    env_file:
      - .env
    environment:
      - APP_ENV=production
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"

volumes:
  uploads_vol:
    driver: local
    driver_opts:
      type: none
      device: ./backend/storage/uploads   # Host path mapping
      o: bind
  processed_vol:
    driver: local
    driver_opts:
      type: none
      device: ./backend/storage/processed
      o: bind
  signed_vol:
    driver: local
    driver_opts:
      type: none
      device: ./backend/storage/signed
      o: bind
  keys_vol:
    driver: local
    driver_opts:
      type: none
      device: ./backend/storage/keys
      o: bind
  audit_db_vol:
    driver: local
```

> **Volume Permission Note:** WSL2 bind-mounts may become owned by root. Run `icacls` or set WSL2 `umask` to ensure `1001:1001` ownership before first start.

**Step 5.2 — Create a `.env` copy from `.env.example`**
```powershell
Copy-Item .env.example .env
# Edit .env to set API_KEY to a non-default value
notepad .env
```

### Verification Gate — INFRA-05
```powershell
cd c:\Projects\secure-doc-ai
docker-compose -f infrastructure\docker-compose.yml up --build -d
Start-Sleep -Seconds 20
Invoke-WebRequest -Uri http://localhost:8000/health/live
```
**PASS criteria:** HTTP 200, `{"status": "ok", ...}`. Container appears in `docker ps` as `healthy`.

---

## Task SEC-01: Pre-flight Security Script

**Owner:** Security Engineer | **Day:** 4 | **Duration:** 2 hours

**Step 6.1 — Create `infrastructure/scripts/preflight.ps1`**
```powershell
<#
.SYNOPSIS
    Pre-flight security check for Secure Doc AI deployment.
    Must ALL PASS before going live.
#>

$pass = $true

# Check 1: BitLocker
Write-Host "CHECK 1: BitLocker status..."
$bitlocker = manage-bde -status C: 2>&1
if ($bitlocker -match "Protection On") {
    Write-Host "  [PASS] BitLocker Protection ON"
} else {
    Write-Host "  [WARN] BitLocker not enabled. Required before Go-Live."
    # Not hard-fail in Phase 1, becomes FAIL in Phase 5
}

# Check 2: WSL2 Memory Cap
Write-Host "CHECK 2: WSL2 .wslconfig..."
$wslcfg = "$env:USERPROFILE\.wslconfig"
if (Test-Path $wslcfg) {
    $content = Get-Content $wslcfg -Raw
    if ($content -match "memory=8GB") {
        Write-Host "  [PASS] .wslconfig memory cap found"
    } else {
        Write-Host "  [FAIL] .wslconfig does not cap memory at 8GB"
        $pass = $false
    }
} else {
    Write-Host "  [FAIL] .wslconfig not found at $wslcfg"
    $pass = $false
}

# Check 3: .env not in Git
Write-Host "CHECK 3: .env not tracked by Git..."
$tracked = git ls-files .env 2>&1
if ($tracked -eq "") {
    Write-Host "  [PASS] .env is NOT tracked by Git"
} else {
    Write-Host "  [FAIL] .env IS tracked by Git. Run: git rm --cached .env"
    $pass = $false
}

# Check 4: API_KEY not default
Write-Host "CHECK 4: API_KEY not default..."
if (Test-Path ".env") {
    $envContent = Get-Content ".env" -Raw
    if ($envContent -match "API_KEY=CHANGE_ME") {
        Write-Host "  [FAIL] API_KEY is still the default value"
        $pass = $false
    } else {
        Write-Host "  [PASS] API_KEY appears to be customised"
    }
} else {
    Write-Host "  [FAIL] .env file not found"
    $pass = $false
}

# Check 5: Container UID
Write-Host "CHECK 5: Container runs as non-root..."
$uid = docker exec pii_processor id -u 2>&1
if ($uid -eq "1001") {
    Write-Host "  [PASS] Container running as UID 1001"
} else {
    Write-Host "  [FAIL] Container UID is $uid (expected 1001)"
    $pass = $false
}

# Summary
Write-Host ""
if ($pass) {
    Write-Host "[ALL CHECKS PASSED] Safe to proceed." -ForegroundColor Green
} else {
    Write-Host "[CHECKS FAILED] Fix the above issues before continuing." -ForegroundColor Red
    exit 1
}
```

**Step 6.2 — Run preflight**
```powershell
.\infrastructure\scripts\preflight.ps1
```

### Verification Gate — SEC-01
**PASS criteria:** Script exits cleanly with `[ALL CHECKS PASSED]`.

---

## Task INFRA-02 (Git): Create CI Workflow Skeleton

**Owner:** DevOps | **Day:** 5 | **Duration:** 2 hours

**Create `infrastructure/github/workflows/backend-ci.yml`**:
```yaml
name: Backend CI

on:
  push:
    branches: [main, develop]
    paths: ["backend/**"]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          cd backend
          pip install ruff black pytest httpx
          pip install -r requirements.txt

      - name: Lint (ruff)
        run: ruff check backend/

      - name: Format check (black)
        run: black --check backend/

      - name: Run tests
        env:
          API_KEY: ci-test-key
        run: |
          cd backend
          pytest tests/ -v --tb=short

  docker-build:
    runs-on: ubuntu-latest
    needs: lint-and-test
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t secure-doc-ai:ci backend/
```

---

## Phase 1 Final Verification

Run all checks in sequence on the target machine:

```powershell
# 1. Container health
docker ps --filter name=pii_processor --format "{{.Status}}"
# Expected: Up X minutes (healthy)

# 2. API liveness
Invoke-WebRequest -Uri http://localhost:8000/health/live | Select-Object StatusCode, Content
# Expected: 200 {"status":"ok","timestamp":"...Z"}

# 3. API readiness
Invoke-WebRequest -Uri http://localhost:8000/health/ready | Select-Object StatusCode, Content
# Expected: 200 {"status":"ready",...}

# 4. Non-root check
docker exec pii_processor id
# Expected: uid=1001(appuser) gid=1001(appgroup)

# 5. tmpfs active
docker inspect pii_processor --format '{{json .HostConfig.Tmpfs}}'
# Expected: {"/tmp":"size=256m,mode=1777"}

# 6. Pre-flight script
.\infrastructure\scripts\preflight.ps1
# Expected: [ALL CHECKS PASSED]
```

---

## Phase 1 Exit Gate

| Gate | Check | Result |
|---|---|---|
| G1 | `docker-compose up` runs without error | ☐ |
| G2 | `/health/live` → `200 OK` | ☐ |
| G3 | `/health/ready` → `200 OK` | ☐ |
| G4 | Container UID is `1001` | ☐ |
| G5 | `tmpfs` is mounted | ☐ |
| G6 | `preflight.ps1` passes | ☐ |
| G7 | Git shows clean, `.env` not tracked | ☐ |

**All 7 gates must be ☑ before Phase 2 begins.**

---

## Phase 1 → Phase 2 Handoff

Once Phase 1 exit gate is confirmed:
1.  Create branch: `git checkout -b feature/PROC-01-file-watcher`
2.  Phase 2 begins with `core/watcher.py` implementation.
3.  The `pipeline.py` orchestrator skeleton is created before any service.
