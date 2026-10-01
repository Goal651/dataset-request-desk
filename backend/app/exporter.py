"""Background export worker (stretch item: background work).

Each assignment gets one ExportJob row. A worker thread claims `pending` jobs,
simulates an export (2-5s sleep, 20% random failure) and records the outcome.

Retry design:
- `attempt` counts started attempts; a failed attempt puts the job back to
  `pending` with the error recorded, up to MAX_ATTEMPTS. A job that exhausts
  its attempts stays `failed` and is no longer picked up.
- Completing a job is a guarded UPDATE (status must still be `running`), so a
  worker that died mid-attempt leaves the job pending/failed, never "done":
  work is idempotent and safe to retry after a crash.
- This process runs a single worker thread; with multiple workers you would
  claim with SELECT ... FOR UPDATE SKIP LOCKED (noted in NOTES.md).
"""

from __future__ import annotations

import logging
import random
import threading
import time

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ExportJob

logger = logging.getLogger("drd.exporter")

MAX_ATTEMPTS = 4
FAIL_PROBABILITY = 0.2
SLEEP_RANGE = (2.0, 5.0)


def run_export_attempt(session, job: ExportJob) -> bool:
    """Claim, simulate, and record one attempt. Returns True when done."""
    job.status = "running"
    job.attempt += 1
    job.error = None
    session.commit()

    time.sleep(random.uniform(*SLEEP_RANGE))
    failed = random.random() < FAIL_PROBABILITY

    # Re-read and guard: only the worker that set it 'running' may finish it.
    current = session.get(ExportJob, job.id)
    if current is None or current.status != "running" or current.attempt != job.attempt:
        return False
    if failed:
        if current.attempt >= MAX_ATTEMPTS:
            current.status = "failed"
            current.error = f"export failed after {current.attempt} attempts"
        else:
            current.status = "pending"  # retry
            current.error = "transient export error; will retry"
        session.commit()
        return False
    current.status = "done"
    current.error = None
    session.commit()
    return True


def process_job(job_id: int) -> bool:
    """Process one job by id in its own session/transaction. True when done."""
    session = SessionLocal()
    try:
        job = session.get(ExportJob, job_id)
        if job is None or job.status != "pending":
            return False
        return run_export_attempt(session, job)
    finally:
        session.close()


class ExportWorker:
    """Polls for pending export jobs and processes them serially in a thread."""

    def __init__(self, poll_interval: float = 1.0, retry_delay: float = 3.0) -> None:
        self.poll_interval = poll_interval
        self.retry_delay = retry_delay
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="export-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        logger.info("export worker started")
        while not self._stop.is_set():
            job_id = self._next_job_id()
            if job_id is None:
                self._stop.wait(self.poll_interval)
                continue
            done = process_job(job_id)
            if not done:
                self._stop.wait(self.retry_delay)  # back off before the retry

    def _next_job_id(self) -> int | None:
        session = SessionLocal()
        try:
            return session.execute(
                select(ExportJob.id)
                .where(ExportJob.status == "pending")
                .order_by(ExportJob.id)
                .limit(1)
            ).scalar_one_or_none()
        finally:
            session.close()


worker = ExportWorker()
