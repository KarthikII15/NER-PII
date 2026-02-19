
# Project Plan: Secure Edge PII Detection System

> **Document Type:** Program Management Plan
> **Version:** 1.0 | **Date:** 2026-02-19
> **Status:** APPROVED FOR EXECUTION

---

## 1. Project Overview

### 1.1 Objective
Deliver a production-grade, on-premise PII detection and redaction system. The system must process PDF/Image documents on a CPU-only edge device (Intel i3, 16GB RAM, Windows 11 Pro), redact detected PII, digitally sign the output, and maintain a tamper-evident audit log — with zero data leaving the device.

### 1.2 Scope

**In-Scope:**
*   Local folder-watcher ingestion pipeline.
*   OCR (RapidOCR ONNX) + NER (DistilBERT INT8) + Redaction (PyMuPDF).
*   Digital signing of output PDFs (X.509 self-signed cert).
*   SQLite-based audit trail (WAL mode, DbWriterThread).
*   React dashboard (queue depth, latency, health status).
*   Docker Compose deployment on Windows 11 Pro / WSL2.
*   CI/CD via GitHub Actions.

**Out-of-Scope:**
*   Cloud sync or any external data egress.
*   Multi-tenancy or multi-device deployment.
*   GPU acceleration (CUDA/OpenCL).
*   Handwriting recognition.
*   PDF/A archival standard compliance.
*   Active Directory / LDAP integration.

### 1.3 Success Criteria
1.  Processing latency: **< 10 seconds per A4 page** at p95.
2.  PII detection accuracy: **> 90% F1-score** on the golden test set.
3.  System uptime on target hardware: **> 99%** during business hours.
4.  Zero PII written to persistent disk at any point during processing.
5.  All audit entries contain SHA-256 hashes, UTC timestamps, and entity counts.

### 1.4 Assumptions
1.  Target deployment machine runs **Windows 11 Pro** with WSL2 and Docker Desktop installed.
2.  Initial build requires internet access to pull `python:3.10-slim` and install dependencies. Post-build is airgap-capable.
3.  A single engineer (or small team) will own Backend and DevOps workstreams.
4.  Host **BitLocker** encryption is enabled before system goes live.
5.  Input documents are primarily English-language.

### 1.5 Constraints
1.  **Hardware:** Intel i3-1115G4 — max 2 CPU workers. No GPU memory pool.
2.  **Budget:** Zero CAPEX beyond existing hardware. OSS-only tooling.
3.  **Timeline:** 5-week delivery to Alpha. 7-week to Production Go-Live.

---

## 2. Governance Model

### 2.1 Stakeholders
| Stakeholder | Role | Interest |
| :--- | :--- | :--- |
| Product Owner | Defines acceptance criteria | Business outcomes |
| Engineering Lead | Technical delivery authority | Architecture integrity |
| Security Officer | Approves security posture | Compliance & risk |
| QA Lead | Owns test sign-off | Quality gate authority |

### 2.2 RACI Matrix
| Activity | Product Owner | Eng Lead | Security | QA |
| :--- | :---: | :---: | :---: | :---: |
| Architecture decisions | C | **R/A** | C | I |
| Security hardening | I | C | **R/A** | C |
| Sprint planning | C | **R/A** | I | C |
| Go-Live approval | **A** | R | C | R |
| Test sign-off | I | I | C | **R/A** |

> R=Responsible, A=Accountable, C=Consulted, I=Informed

### 2.3 Decision-Making Framework
*   **Architectural changes:** Requires Engineering Lead + Security Officer sign-off.
*   **Scope changes:** Requires Product Owner approval. Logged as a Change Request.
*   **Go-Live gate:** Requires all four stakeholders to confirm their gate criteria are met.

### 2.4 Escalation Path
`Developer → Engineering Lead (24h) → Product Owner (48h) → CTO Review`

---

## 3. Phase Breakdown

### Phase 1 — Foundation Setup (Week 1)
*   **Objective:** Establish a working, hardened infrastructure baseline.
*   **Deliverables:** Git repo, `Dockerfile`, `docker-compose.yml`, `.wslconfig`, Hello World FastAPI response.
*   **Entry Criteria:** Architecture Baseline Approved (`Architecture_Baseline_Approval.md`).
*   **Exit Criteria:** `docker-compose up` produces a running container; `/health/live` returns `200 OK`.
*   **Key Milestone:** "Hello World Container" (INFRA-04 complete).
*   **Dependencies:** Windows 11 Pro with WSL2 and Docker Desktop installed on target machine.

### Phase 2 — Core Development (Week 2–3)
*   **Objective:** Build the end-to-end processing pipeline.
*   **Deliverables:** File Watcher, `Validator` (5 checks), `OCRProcessor`, `PIIDetector` (INT8), `Redactor`, `AuditLogger` (WAL + UTC).
*   **Entry Criteria:** Phase 1 exit criteria met.
*   **Exit Criteria:** A test PDF placed in `/input` produces a redacted, signed PDF in `/output` with a corresponding DB record. Processing latency < 15s/page under test conditions.
*   **Key Milestone:** "First Redacted Document."
*   **Dependencies:** `tesseract-ocr-eng` bundled in Docker image; DistilBERT INT8 model baked in.

### Phase 3 — Integration & Hardening (Week 3)
*   **Objective:** Connect all components; apply security hardening.
*   **Deliverables:** Nginx TLS termination, API Key auth, `tmpfs` mount, BitLocker pre-flight script, non-root containers (UID 1001), Dead Letter Queue (DLQ), Startup Reconciliation script.
*   **Entry Criteria:** Phase 2 exit criteria met.
*   **Exit Criteria:** Security checklist items SEC-01 through SEC-03 all pass. Container runs as UID 1001. Processing with invalid API key returns `401`.
*   **Key Milestone:** "Security Gate Passed."
*   **Dependencies:** Self-signed X.509 cert generated; `google-re2` or timeout-wrapped `re` confirmed.

### Phase 4 — Testing & Stabilization (Week 4)
*   **Objective:** Validate system quality, reliability, and resilience.
*   **Deliverables:** Unit test suite (>80% coverage), Golden Test Set (5 PDFs), Locust load test, 12-hour soak test with `mprof`, fuzz test (QA-05).
*   **Entry Criteria:** Phase 3 exit criteria met.
*   **Exit Criteria:** All tests pass. Heap growth < 50MB over 12h soak. Fuzz test does not crash the system. p95 latency < 10s on the baseline PDF.
*   **Key Milestone:** "QA Sign-Off."
*   **Dependencies:** Golden test set available (QA-02). Locust installed.

### Phase 5 — Deployment & Go-Live (Week 5)
*   **Objective:** Deploy to production hardware and execute the Go-Live checklist.
*   **Deliverables:** All Go-Live checklist items checked off. Runbook delivered. OpenAPI spec published.
*   **Entry Criteria:** Phase 4 exit criteria met. QA Lead sign-off received.
*   **Exit Criteria:** All 9 Go-Live checklist items confirmed. System processes 100 files/hour for 1 hour without incident.
*   **Key Milestone:** **"Production Go-Live."**
*   **Dependencies:** BitLocker enabled on host. `.wslconfig` deployed. Airgap image saved.

### Phase 6 — Post-Launch Optimization (Week 6–7)
*   **Objective:** Monitor, stabilise, and improve based on production behaviour.
*   **Deliverables:** Prometheus dashboard configured, weekly `mprof` report, inode monitoring cron job, OCR accuracy refinement list.
*   **Entry Criteria:** Phase 5 exit criteria met. System live for > 5 business days.
*   **Exit Criteria:** Failure rate < 1%/day sustained for 5 days. No `CRITICAL` log events. Latency p95 < 10s confirmed in production.

---

## 4. Workstream Breakdown

| Workstream | Owner | Phases Active | Key Tasks |
| :--- | :--- | :--- | :--- |
| **Backend** | Eng Lead | 2–4 | Watcher, Validator, Processor, Logger, DLQ |
| **AI / ML** | Eng Lead | 2–3 | OCR (RapidOCR), NER (DistilBERT INT8), Quantization |
| **Frontend** | Frontend Dev | 3–4 | React Dashboard, `/stats` polling |
| **Data Engineering** | Backend Eng | 2–3 | SQLite schema, WAL mode, DbWriterThread, pruning cron |
| **DevOps** | DevOps Eng | 1–5 | Docker, WSL2, CI/CD (GitHub Actions), Watchtower, rollback |
| **Security** | Security Eng | 1–3 | X.509 cert, BitLocker check, non-root, tmpfs, log sanitisation |
| **QA** | QA Lead | 4 | Unit tests, Golden Set, Load test, Soak test, Fuzz test |
| **Documentation** | Eng Lead | 4–5 | OpenAPI spec, Runbook (5 scenarios), Chain of Custody doc |

---

## 5. Timeline Strategy

### 5.1 Critical Path
`INFRA-01 → INFRA-03/04 → PROC-01 → PROC-02 → PROC-03 → PROC-04 → PROC-05 → AUDIT-01/02 → QA-01 → QA-04 → DOC-02 → Go-Live`

### 5.2 Parallel Tracks
*   **Track A (Core):** Backend processing pipeline (PROC series).
*   **Track B (Infra):** Docker hardening, CI/CD setup (INFRA, OPS series) — runs parallel to Track A after Week 1.
*   **Track C (UI):** React dashboard (UI series) — starts Week 3, independent of Track A.

### 5.3 Duration per Phase
| Phase | Duration | Calendar Weeks |
| :--- | :--- | :--- |
| 1 — Foundation | 5 days | Week 1 |
| 2 — Core Development | 10 days | Week 2–3 |
| 3 — Integration & Hardening | 5 days | Week 3 |
| 4 — Testing | 5 days | Week 4 |
| 5 — Go-Live | 3 days | Week 5 |
| 6 — Optimisation | 10 days | Week 6–7 |

### 5.4 Resource Allocation
| Role | Phases | Allocation |
| :--- | :--- | :--- |
| Engineering Lead | 1–6 | 80% |
| DevOps Engineer | 1–5 | 50% |
| QA Lead | 4–6 | 60% |
| Security Engineer | 1–3 | 30% |
| Frontend Developer | 3–4 | 40% |

---

## 6. Risk Management Plan

### 6.1 Top Risks
| Risk | Probability | Impact | Mitigation | Contingency |
| :--- | :---: | :---: | :--- | :--- |
| CPU saturation on i3 | High | High | INT8 quantization, 2-worker limit | Fall back to Regex-Only "Lite" mode |
| WSL2 memory runaway | Medium | High | `.wslconfig` cap at 8GB | `wsl --shutdown` + `docker-compose restart` |
| Model accuracy < 90% F1 | Medium | High | Golden test set validation in Phase 4 | Augment with Regex post-processor |
| SQLite lock (concurrent writes) | Low | High | WAL mode + DbWriterThread | Pre-empted by architecture; no contingency needed |
| Encrypted PDF crash | Medium | Medium | Validator guard (PROC-02) | DLQ routes to `Error/Encrypted` |

### 6.2 Contingency Planning
*   **If latency > 15s/page:** Disable spaCy/DistilBERT; switch to Regex-only detection for MVP delivery. Re-enable ML in Phase 6.
*   **If WSL2 corrupts Docker state:** Run `docker system prune -a` + `wsl --unregister Ubuntu` + reinstall. Airgap image enables same-day restore.

---

## 7. Communication Plan

### 7.1 Cadence
| Meeting | Frequency | Attendees | Purpose |
| :--- | :--- | :--- | :--- |
| Sprint Standup | Daily (async) | Engineering team | Blocker identification |
| Sprint Review | Weekly (Friday) | All stakeholders | Demo working software |
| Risk Review | Weekly | Eng Lead + Security | Update risk register |
| Go-Live Briefing | Once (end of Phase 4) | All stakeholders | Final approval |

### 7.2 Reporting Structure
*   **Progress:** Updated `task.md` checked into Git. Visible to all.
*   **Risks:** Updated Risk Matrix in `Risk_Assessment.md` weekly.

### 7.3 Documentation Version Control
*   All documents stored in Git repo under `/docs/`.
*   Version format: `YYYY-MM-DD_v{major}.{minor}` in document header.
*   Breaking changes to API or architecture require a new major version and stakeholder sign-off.

---

## 8. Go-Live Readiness Checklist

### 8.1 Technical
*   [ ] `/health/live` returns `200 OK`.
*   [ ] `/health/ready` returns `200 OK` (model loaded, DB connected).
*   [ ] End-to-end test: clean PDF in `/output` for a known PII document.
*   [ ] p95 processing latency < 10s verified via Locust.

### 8.2 Security
*   [ ] Host BitLocker verified enabled (`manage-bde -status`).
*   [ ] API key is non-default, stored in `.env` (not in Git).
*   [ ] `tmpfs` mount confirmed (`docker inspect processor | grep tmpfs`).
*   [ ] Container runs as UID 1001 (`docker exec processor id`).
*   [ ] Container clock synced with host UTC.

### 8.3 Operational
*   [ ] `.wslconfig` deployed; WSL2 RAM capped at 8GB.
*   [ ] Runbook (`Runbook.md`) reviewed and accessible offline.
*   [ ] Log rotation confirmed (max 10MB, keep 5 files).
*   [ ] Daily inode pruning cron job active.

### 8.4 Rollback
*   [ ] Docker image saved: `pii-processor-v1.0.tar.gz` on external drive.
*   [ ] `rollback.sh` script tested (retags and restarts previous image).
*   [ ] DB backup (`audit.db`) taken before go-live.
