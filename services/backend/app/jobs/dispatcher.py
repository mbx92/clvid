from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.domain.models import Job, OutboxEvent, utcnow

from .celery_app import celery_app

log = logging.getLogger("clipper.dispatcher")


def dispatch_once(limit: int = 30) -> int:
    sent = 0
    with session_scope() as db:
        events = db.scalars(select(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))
                            .order_by(OutboxEvent.created_at).limit(limit).with_for_update(skip_locked=True)).all()
        for event in events:
            job = db.get(Job, event.job_id)
            if not job or job.status != "queued":
                event.dispatched_at = utcnow()
                continue
            event.attempt += 1
            try:
                queue = "light" if job.kind in ("analyze", "delete_assets") else "heavy"
                celery_app.send_task("clipper.run_job", args=[job.id], task_id=job.id, queue=queue, retry=False)
            except Exception:
                # Commit attempt count without discarding the durable event.
                log.warning("Broker unavailable; pending outbox event retained (job=%s)", job.id)
                break
            event.dispatched_at = utcnow()
            sent += 1
    return sent


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            dispatch_once()
        except Exception:
            log.error("Dispatcher database unavailable; retrying")
        time.sleep(get_settings().dispatch_interval_seconds)


if __name__ == "__main__":
    main()
