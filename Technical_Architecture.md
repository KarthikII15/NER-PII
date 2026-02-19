
# Technical Architecture: Secure Edge PII Detection System

## 1. High-Level Architecture Diagram
The system follows a **Containerized Edge Micro-Service** pattern. It runs entirely on the local device host (Linux/Windows) within a Docker runtime environment.

*   **Host Logic:**
    *   **Input/Output Interface:** Local File System Watcher or Folder Mounts.
    *   **Container Runtime:** Docker Engine / Podman.
*   **The "Core" Container:**
    *   **API Gateway (Reverse Proxy):** Nginx/Traefik - Manages internal routing and TLS termination.
    *   **Orchestrator Service (Python/FastAPI):** Controls the pipeline logic.
    *   **ML Inference Service (Python/Triton):** Hosts the NER models (ONNX/TensorRT).
    *   **Tesseract/OCR Service:** Dedicated process for heavy extraction.
*   **Data Persistence Layer:**
    *   **Audit DB (SQLite):** Lightweight, zero-configuration SQL engine.
    *   **Ephemeral Storage (RAM Disk):** For temporary processing of unencrypted PII to ensure it vanishes on power loss.

---

## 2. Frontend Architecture Options
*Given the "Headless Edge" nature, the UI is an administrative utility, not the primary interface.*

*   **Option A: Local Web Dashboard (Recommended)**
    *   **Tech:** **React / Vue.js** (SPA) serving a static build from the Nginx container.
    *   **Usage:** Accessible via `http://localhost:8080` for configuration, log viewing, and health checks.
    *   **Reasoning:** Zero installation for the user; standard web tech allows for remote management if tunneled.
*   **Option B: Desktop Native App**
    *   **Tech:** **Electron / Tauri**.
    *   **Usage:** A standalone `.exe` or `.AppImage`.
    *   **Reasoning:** Higher resource overhead but better OS integration (tray icons, native notifications). *Not recommended for MVP.*
*   **Option C: CLI Only**
    *   **Tech:** Command Line Interface.
    *   **Usage:** Operators config via text files.
    *   **Reasoning:** Best for "Headless Servers" but poor UX for Branch Managers.

---

## 3. Backend Architecture Options
*   **Language:** **Python 3.10+**.
    *   *Why?* Unrivaled ecosystem for AI/ML (PyTorch, ONNX, Spacy) and PDF manipulation (PyMuPDF).
*   **Framework:** **FastAPI**.
    *   *Why?* Async performance (critical for I/O bound OCR tasks), auto-generated Swagger docs, type safety.
*   **Processing Model:** **Task Queue (Celery/RQ) with Redis**.
    *   *Why?* Decouples ingestion from processing. If 100 files are dropped at once, the API accepts them instantly, and the Workers process them sequentially to avoid OOM (Out of Memory) crashes on constrained Edge hardware.

---

## 4. Database Strategy
*   **Engine:** **SQLite (WAL Mode)**.
    *   *Why?* No separate server process to manage (vs PostgreSQL). Single file portability. robust enough for millions of rows if structured correctly.
*   **Schema Design:**
    *   `Events Table`: Immutable log of actions.
    *   `Policies Table`: JSON blobs of active rules.
*   **Audit integrity:**
    *   **Chained Hashing:** Each log entry typically contains the hash of the *previous* entry (Blockchain-lite style) to detect database tampering.

---

## 5. API Design Approach
*   **Style:** **RESTful API**.
*   **Endpoints:**
    *   `POST /ingest`: Upload file for processing.
    *   `GET /status/{id}`: Check pipeline status.
    *   `GET /audit`: Retrieve verification logs.
    *   `PUT /policy`: Update detection rules.
*   **Inter-Service Comm:** **gRPC** (Optional).
    *   *Why?* For the link between the Orchestrator and the ML Inference Engine, gRPC offers lower latency for passing tensor data compared to JSON.

---

## 6. Security Architecture
*   **Defense in Depth:**
    1.  **Least Privilege:** Docker containers run as non-root users.
    2.  **Volatile Memory:** PII extraction happens in RAM (tmpfs); swap is disabled for the container to prevent writing PII to disk.
    3.  **Code Signing:** The application updates are signed; the device rejects unsigned binaries.
    4.  **Local Encryption:** The signing certificate private key is encrypted at rest (AES-256) and unlocked only via environment variable/TPM interaction.

---

## 7. Scalability Plan
*   **Vertical Scaling (The Device):**
    *   The architecture detects available cores/GPU.
    *   **Worker Pool Size:** Dynamic. If running on a 64-core Server, span 20 OCR workers. If on a Raspberry Pi, spawn 1.
*   **Horizontal Scaling (The Fleet):**
    *   This is a "Shared Nothing" architecture. The device does not scale by clustering; you scale by **Deploying More Devices**.
    *   Management is handled by a central "Control Plane" that pushes config to thousands of autonomous nodes.

---

## 8. Performance Optimization Strategy
1.  **Model Quantization:** Convert PyTorch models to **ONNX Runtime (INT8)**. This reduces model size by 4x and increases speed by 3x on CPUs/NPUs.
2.  **Pipeline Batching:** Do not process one sentence at a time. Batch text chunks before sending to the NER model.
3.  **OCR Region of Interest (ROI):** If possible, use layout analysis to only OCR the "Form Fields" and skip the boilerplate text, saving 50% compute time.

---

## 9. DevOps & CI/CD Workflow
1.  **Source:** Git (GitHub/GitLab).
2.  **Build:** GitHub Actions builds multi-arch Docker images (AMD64 for Laptops, ARM64 for Jetson).
3.  **Test:** Automated Pytest suite (Unit tests) + Integration tests (Real PDF Redaction correctness).
4.  **Release:** Push to Container Registry (GHCR/DockerHub).
5.  **Update Strategy (OTA):**
    *   **Watchtower** pattern: The Edge device runs a small service that checks for new image tags, pulls them, and restarts the containers seamlessly.

---

## 10. Deployment Model
*   **Primary:** **On-Premise Edge (Containerized).**
    *   Delivered as a `docker-compose.yml` file.
*   **Hardware Compatibility:**
    *   **Tier 1 (High Perf):** NVIDIA Jetson Orin (GPU acceleration).
    *   **Tier 2 (Standard - User Device):** Intel Core i3 / i5 (CPU Only).
        *   *Constraint:* Requires ONNX Quantized models.
        *   *Capacity:* ~5-10 PPM.
    *   **Tier 3 (Low Power):** Raspberry Pi 5 (Slow, but functional for low volume).
