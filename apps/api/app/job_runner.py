import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from vss_worker.adapters import AudioNormalizer, MelodyTranscriber, VocalSeparator
from vss_worker.fake import build_fake_project

from app.database import SessionLocal
from app.models import JobRecord, ProjectRecord, UploadRecord
from app.schemas import JobStage, JobStatus, ScoreProject

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fake-worker")


def recover_interrupted_thread_jobs() -> int:
    from sqlalchemy import select

    recovered = 0
    with SessionLocal() as session:
        jobs = session.scalars(
            select(JobRecord).where(
                JobRecord.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING])
            )
        )
        for job in jobs:
            job.status = JobStatus.FAILED
            job.error_code = "WORKER_RESTARTED"
            job.error_message = "The local worker restarted before this job completed"
            job.retryable = True
            recovered += 1
        session.commit()
    return recovered


@lru_cache
def real_adapters() -> tuple[AudioNormalizer, VocalSeparator, MelodyTranscriber]:
    from vss_worker.basic_pitch_adapter import BasicPitchSubprocessTranscriber
    from vss_worker.demucs import DemucsSeparator
    from vss_worker.ffmpeg import FfmpegNormalizer

    return FfmpegNormalizer(), DemucsSeparator(), BasicPitchSubprocessTranscriber()


def dispatch_fake_job(job_id: str) -> None:
    executor.submit(run_fake_job, job_id)


def dispatch_job(job_id: str) -> None:
    from app.config import get_settings

    if get_settings().worker_backend == "celery":
        from vss_worker.celery_app import run_transcription_job

        run_transcription_job.delay(job_id)
    else:
        with SessionLocal() as session:
            job = session.get(JobRecord, job_id)
            transcriber = job.options.get("transcriber") if job is not None else None
        executor.submit(_runner_for(transcriber), job_id)


def run_selected_job(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        transcriber = job.options.get("transcriber") if job is not None else None
    _runner_for(transcriber)(job_id)


def _runner_for(transcriber: object) -> Callable[[str], None]:
    if transcriber == "basic_pitch":
        return run_real_job
    if transcriber == "game_f0":
        return run_unavailable_experimental_job
    return run_fake_job


def run_unavailable_experimental_job(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        if job is None or job.status == JobStatus.CANCELLED:
            return
    _fail(
        job_id,
        "EXPERIMENTAL_ENGINE_NOT_CONFIGURED",
        "The GAME + torchcrepe experimental engine is not configured in this worker",
    )


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
            _progress(job_id, stage, value)

        try:
            document = ScoreProject.model_validate(
                build_fake_project(
                    upload_id=upload.id,
                    file_name=upload.file_name,
                    object_key=upload.object_key,
                    progress=progress,
                )
            )
            _complete(job_id, document)
        except InterruptedError:
            return
        except Exception as error:  # worker boundary records stable failure state
            _fail(job_id, "FAKE_WORKER_FAILED", str(error))


def run_real_job(job_id: str) -> None:
    from vss_worker.cancellation import cancellation_scope
    from vss_worker.pipeline import build_real_project

    from app.config import get_settings

    settings = get_settings()
    normalizer, separator, transcriber = real_adapters()
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        if job is None or job.status == JobStatus.CANCELLED:
            return
        upload = session.get(UploadRecord, job.upload_id)
        if upload is None:
            _fail(job_id, "UPLOAD_MISSING", "The source upload no longer exists")
            return

        def progress(stage: str, value: float) -> None:
            _progress(job_id, stage, value)

        try:
            with cancellation_scope(lambda: _check_cancelled(job_id)):
                document = ScoreProject.model_validate(
                    build_real_project(
                        upload_id=upload.id,
                        file_name=upload.file_name,
                        object_key=upload.object_key,
                        source_path=settings.data_dir / upload.object_key,
                        work_dir=settings.data_dir / "work" / job_id,
                        normalizer=normalizer,
                        separator=separator,
                        transcriber=transcriber,
                        progress=progress,
                    )
                )
            _complete(job_id, document)
        except InterruptedError:
            return
        except Exception as error:
            _fail(job_id, "TRANSCRIPTION_FAILED", str(error))


def _fail(job_id: str, code: str, message: str) -> None:
    with SessionLocal() as session:
        session.execute(
            update(JobRecord)
            .where(
                JobRecord.id == job_id, JobRecord.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
            )
            .values(status=JobStatus.FAILED, error_code=code, error_message=message, retryable=True)
        )
        session.commit()


def _check_cancelled(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        if job is None or job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            raise InterruptedError("Task cancelled")


def _progress(job_id: str, stage: str, value: float) -> None:
    with SessionLocal() as session:
        result = cast(
            CursorResult[Any],
            session.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                )
                .values(status=JobStatus.RUNNING, stage=stage, progress=value)
            ),
        )
        if result.rowcount != 1:
            raise InterruptedError("Task cancelled")
        session.commit()


def _complete(job_id: str, document: ScoreProject) -> None:
    with SessionLocal() as session:
        result = cast(
            CursorResult[Any],
            session.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                )
                .values(
                    project_id=document.project_id,
                    status=JobStatus.COMPLETED,
                    stage=JobStage.COMPLETED,
                    progress=1,
                )
            )
        )
        if result.rowcount != 1:
            raise InterruptedError("Task cancelled")
        session.add(
            ProjectRecord(
                id=document.project_id,
                job_id=job_id,
                revision=document.revision,
                document=document.model_dump(mode="json"),
            )
        )
        session.commit()
