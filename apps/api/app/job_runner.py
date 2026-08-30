import time
from concurrent.futures import ThreadPoolExecutor

from vss_worker.fake import build_fake_project

from app.database import SessionLocal
from app.models import JobRecord, ProjectRecord, UploadRecord
from app.schemas import JobStage, JobStatus, ScoreProject

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fake-worker")


def dispatch_fake_job(job_id: str) -> None:
    executor.submit(run_fake_job, job_id)


def dispatch_job(job_id: str) -> None:
    from app.config import get_settings

    if get_settings().worker_backend == "celery":
        from vss_worker.celery_app import run_transcription_job

        run_transcription_job.delay(job_id)
    else:
        dispatch_fake_job(job_id)


def run_fake_job(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        if job is None or job.status == JobStatus.CANCELLED:
            return
        upload = session.get(UploadRecord, job.upload_id)
        if upload is None:
            _fail(job_id, "UPLOAD_MISSING", "The source upload no longer exists")
            return

        def progress(stage: str, value: float) -> None:
            time.sleep(0.02)
            with SessionLocal() as progress_session:
                current = progress_session.get(JobRecord, job_id)
                if current is None or current.status == JobStatus.CANCELLED:
                    raise InterruptedError
                current.status = JobStatus.RUNNING
                current.stage = stage
                current.progress = value
                progress_session.commit()

        try:
            document = ScoreProject.model_validate(
                build_fake_project(
                    upload_id=upload.id,
                    file_name=upload.file_name,
                    object_key=upload.object_key,
                    progress=progress,
                )
            )
            project = ProjectRecord(
                id=document.project_id,
                job_id=job_id,
                revision=document.revision,
                document=document.model_dump(mode="json"),
            )
            session.add(project)
            job.project_id = project.id
            job.status = JobStatus.COMPLETED
            job.stage = JobStage.COMPLETED
            job.progress = 1
            session.commit()
        except InterruptedError:
            return
        except Exception as error:  # worker boundary records stable failure state
            _fail(job_id, "FAKE_WORKER_FAILED", str(error))


def _fail(job_id: str, code: str, message: str) -> None:
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message
        job.retryable = True
        session.commit()
