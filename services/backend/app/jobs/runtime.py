from __future__ import annotations

import socket
import threading
import time
from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.domain.models import Job, JobAttempt, Project, utcnow
from app.media.process import Cancelled, MediaError


class JobContext:
    def __init__(self, job_id: str, attempt: int, attempt_id: str):
        self.job_id, self.attempt, self.attempt_id = job_id, attempt, attempt_id
        self.settings = get_settings()
        with session_scope() as db:
            queued = db.get(Job, job_id)
            snapshot = (queued.limits_json or {}) if queued else {}
        self.settings = self.settings.model_copy(update={key: snapshot[key] for key in
                    ("max_video_seconds", "max_upload_bytes") if key in snapshot})
        self.stop_event, self.cancel_event = threading.Event(), threading.Event()
        self.started = time.monotonic()
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name=f"heartbeat-{job_id}")

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _heartbeat_loop(self):
        while not self.stop_event.wait(max(1, self.settings.heartbeat_seconds)):
            try:
                with session_scope() as db:
                    initial = db.get(Job, self.job_id)
                    project = db.scalar(select(Project).where(Project.id == initial.project_id).with_for_update()) if initial else None
                    job = db.scalar(select(Job).where(Job.id == self.job_id).with_for_update().execution_options(populate_existing=True))
                    if (not job or job.attempt != self.attempt or job.status not in ("running", "cancel_requested") or
                            job.status == "cancel_requested" or not project or
                            project.lifecycle_state != "active" and job.kind != "delete_assets"):
                        self.cancel_event.set()
                    if job and job.attempt == self.attempt and job.status in ("running", "cancel_requested"):
                        job.lease_expires_at = utcnow() + timedelta(seconds=self.settings.job_lease_seconds)
            except Exception:
                # Stop local work on DB loss. A stale worker cannot publish later.
                self.cancel_event.set()

    def cancelled(self) -> bool:
        if time.monotonic() - self.started > self.settings.job_timeout_seconds:
            raise MediaError("job_timeout", "Pekerjaan melewati batas waktu yang dikonfigurasi.")
        return self.cancel_event.is_set()

    def check(self, db=None):
        if self.cancelled():
            raise Cancelled()
        if db is not None:
            initial = db.get(Job, self.job_id)
            project = db.scalar(select(Project).where(Project.id == initial.project_id).with_for_update()) if initial else None
            job = db.scalar(select(Job).where(Job.id == self.job_id).with_for_update().execution_options(populate_existing=True))
            if (not job or job.attempt != self.attempt or job.status != "running" or
                    not project or project.lifecycle_state != "active" and job.kind != "delete_assets"):
                raise Cancelled()
            return job, project

    def progress(self, value: float | None):
        self.check()
        with session_scope() as db:
            job, _ = self.check(db)
            job.progress = value
            job.lease_expires_at = utcnow() + timedelta(seconds=self.settings.job_lease_seconds)

    def stage(self, name: str):
        with session_scope() as db:
            job, project = self.check(db)
            job.stage, job.progress = name, None
            states = {"import_url": "importing", "validate": "validating", "prepare_preview": "validating", "transcribe": "transcribing", "analyze": "analyzing"}
            if name in states:
                project.status = states[name]
                project.error_message = None


def claim(job_id: str) -> tuple[int, str] | None:
    with session_scope() as db:
        initial = db.get(Job, job_id)
        if not initial:
            return None
        project = db.scalar(select(Project).where(Project.id == initial.project_id).with_for_update())
        if not project:
            return None
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
        if not job or job.status != "queued":
            return None
        if not project or project.lifecycle_state != "active" and job.kind != "delete_assets":
            job.status, job.finished_at = "cancelled", utcnow()
            return None
        job.status, job.progress, job.started_at = "running", None, utcnow()
        job.attempt += 1
        job.lease_expires_at = utcnow() + timedelta(seconds=get_settings().job_lease_seconds)
        attempt = JobAttempt(job_id=job.id, attempt=job.attempt, worker_id=socket.gethostname(), started_at=utcnow())
        db.add(attempt)
        db.flush()
        return job.attempt, attempt.id
