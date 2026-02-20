"""
watcher.py — File system watcher for automatic ingestion.
Detects new files in the uploads directory and triggers the processing pipeline.
"""
import logging
import os
import shutil
import time
import threading
from pathlib import Path
from uuid import uuid4

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver as Observer

logger = logging.getLogger(__name__)

# Files that are still being written — debounce for this many seconds
_WRITE_SETTLE_SECONDS = 1.5

# Extensions we accept at the watcher level (validator does deeper checks)
_ACCEPTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}


class _UploadHandler(FileSystemEventHandler):
    """Reacts to new files appearing in the uploads directory."""

    def __init__(self, processing_dir: Path, pipeline_callback):
        super().__init__()
        self.processing_dir = processing_dir
        self.pipeline_callback = pipeline_callback
    
    def on_created(self, event):
        self._process(event)
        
    def on_modified(self, event):
        self._process(event)
        
    def _process(self, event):
        if event.is_directory:
            return

        src = Path(event.src_path)

        # Ignore hidden / temp files
        if src.name.startswith(".") or src.name.startswith("~"):
            return

        # Quick extension filter
        if src.suffix.lower() not in _ACCEPTED_EXTENSIONS:
            return

        # Debounce: wait for the file copy to finish
        import threading
        threading.Thread(
            target=self._debounce_and_ingest,
            args=(src,),
            daemon=True,
        ).start()

    # ── private ──────────────────────────────────────────────────────────

    def _debounce_and_ingest(self, src: Path):
        """Wait for file size to stabilise, then move and process."""
        import time
        time.sleep(_WRITE_SETTLE_SECONDS)

        if not src.exists():
            return  # Possibly deleted before we got to it

        # Use UUID to prevent name collisions in processing dir
        from uuid import uuid4
        job_id = uuid4().hex
        dest = self.processing_dir / f"{job_id}{src.suffix.lower()}"

        try:
            self.processing_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(src), str(dest))
            logger.info(
                "Detected new file: %s → processing/%s", src.name, dest.name
            )
        except OSError:
            logger.exception("Failed to move %s to processing dir", src.name)
            return

        # Fire the pipeline
        try:
            self.pipeline_callback(job_id, dest, src.name)
        except Exception:
            logger.exception("Pipeline failed for job %s", job_id)


class FileWatcher:
    """Manages the Watchdog observer lifecycle."""

    def __init__(self, watch_dir: str, processing_dir: str, pipeline_callback):
        self.watch_dir = Path(watch_dir)
        self.processing_dir = Path(processing_dir)
        self.pipeline_callback = pipeline_callback
        self._observer: Observer | None = None

    def start(self):
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processing_dir.mkdir(parents=True, exist_ok=True)

        handler = _UploadHandler(self.processing_dir, self.pipeline_callback)
        
        # PollingObserver checks every 1s by default, which is fine
        self._observer = Observer(timeout=1.0)
        self._observer.schedule(handler, str(self.watch_dir), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info("FileWatcher started (Polling Mode) — monitoring %s", self.watch_dir)

        # Process any files that were already in the uploads dir
        self._process_existing_files(handler)

    def _process_existing_files(self, handler: _UploadHandler):
        """Handle files that were in the uploads directory before the watcher started."""
        existing = [
            f for f in self.watch_dir.iterdir()
            if f.is_file()
            and not f.name.startswith(".")
            and f.suffix.lower() in _ACCEPTED_EXTENSIONS
        ]
        if existing:
            logger.info(
                "Found %d pre-existing file(s) in uploads — processing now", len(existing)
            )
        for file_path in existing:
            import threading
            threading.Thread(
                target=handler._debounce_and_ingest,
                args=(file_path,),
                daemon=True,
            ).start()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            logger.info("FileWatcher stopped")
