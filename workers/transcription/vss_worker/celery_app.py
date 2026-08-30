from app.config import get_settings
from app.job_runner import run_fake_job
from celery import Celery  # type: ignore[import-untyped]

settings = get_settings()
celery_app = Celery(
    "vocal_score_transcription",
    broker=settings.broker_url,
    backend=settings.result_backend,
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)


@celery_app.task(name="transcription.run", bind=True, max_retries=2)  # type: ignore[untyped-decorator]
def run_transcription_job(self: object, job_id: str) -> None:
    run_fake_job(job_id)
