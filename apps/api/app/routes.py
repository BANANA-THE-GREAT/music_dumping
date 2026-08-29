import time
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal, get_session
from app.job_runner import dispatch_fake_job
from app.models import JobRecord, ProjectRecord, UploadRecord
from app.repository import create_job, create_upload, job_response
from app.schemas import JobCreate, JobResponse, JobStage, JobStatus, ScoreProject, UploadResponse
from app.storage import UploadTooLargeError, save_upload

router = APIRouter(prefix="/v1")
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    session: SessionDep, settings: SettingsDep, file: Annotated[UploadFile, File()]
) -> UploadResponse:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in settings.allowed_audio_types:
        raise HTTPException(status_code=415, detail="Unsupported audio content type")
    try:
        object_key, size, sha256 = await save_upload(file, settings)
    except UploadTooLargeError as error:
        raise HTTPException(status_code=413, detail="Audio file is too large") from error
    if size == 0:
        raise HTTPException(status_code=400, detail="Audio file is empty")
    return create_upload(
        session,
        file_name=file.filename or "audio",
        content_type=content_type,
        size_bytes=size,
        sha256=sha256,
        object_key=object_key,
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(request: JobCreate, session: SessionDep) -> JobResponse:
    if session.get(UploadRecord, request.upload_id) is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    response = create_job(session, request)
    if request.options.auto_start:
        dispatch_fake_job(response.id)
    return response


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: SessionDep) -> JobResponse:
    record = session.get(JobRecord, job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_response(record)


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, session: SessionDep) -> StreamingResponse:
    if session.get(JobRecord, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    def stream() -> Iterator[str]:
        last_payload = ""
        while True:
            with SessionLocal() as event_session:
                record = event_session.get(JobRecord, job_id)
                if record is None:
                    return
                payload = job_response(record).model_dump_json()
                if payload != last_payload:
                    yield f"event: progress\ndata: {payload}\n\n"
                    last_payload = payload
                if record.status in {
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                }:
                    return
            time.sleep(0.1)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, session: SessionDep) -> JobResponse:
    record = session.get(JobRecord, job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Job is already terminal")
    record.status = JobStatus.CANCELLED
    record.stage = JobStage.CANCELLED
    session.commit()
    return job_response(record)


@router.get("/projects/{project_id}", response_model=ScoreProject)
def get_project(project_id: str, session: SessionDep) -> ScoreProject:
    record = session.get(ProjectRecord, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ScoreProject.model_validate(record.document)


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unused_upload(upload_id: str, session: SessionDep) -> Response:
    upload = session.get(UploadRecord, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    session.delete(upload)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
