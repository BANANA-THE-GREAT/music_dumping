import time
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal, get_session
from app.exporters import project_to_midi, project_to_musicxml
from app.job_runner import dispatch_job
from app.models import JobRecord, ProjectRecord, UploadRecord
from app.project_service import requantize
from app.repository import create_job, create_upload, job_response
from app.schemas import (
    JobCreate,
    JobResponse,
    JobStage,
    JobStatus,
    ProjectPatch,
    ProjectSummary,
    RequantizeRequest,
    ScoreProject,
    UploadResponse,
)
from app.storage import UploadTooLargeError, remove_project_files, save_upload

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
        dispatch_job(response.id)
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


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(session: SessionDep) -> list[ProjectSummary]:
    records = session.scalars(
        select(ProjectRecord).order_by(ProjectRecord.updated_at.desc()).limit(50)
    )
    summaries = []
    for record in records:
        project = ScoreProject.model_validate(record.document)
        summaries.append(
            ProjectSummary(
                project_id=project.project_id,
                file_name=project.source.file_name,
                duration_ms=project.source.duration_ms,
                note_count=len(project.notes),
                revision=record.revision,
                updated_at=record.updated_at,
            )
        )
    return summaries


def _project_document(project_id: str, session: Session) -> ScoreProject:
    record = session.get(ProjectRecord, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ScoreProject.model_validate(record.document)


@router.get("/projects/{project_id}/exports/midi")
def export_project_midi(project_id: str, session: SessionDep) -> Response:
    content = project_to_midi(_project_document(project_id, session))
    return Response(
        content=content,
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.mid"'},
    )


@router.get("/projects/{project_id}/exports/musicxml")
def export_project_musicxml(project_id: str, session: SessionDep) -> Response:
    content = project_to_musicxml(_project_document(project_id, session))
    return Response(
        content=content,
        media_type="application/vnd.recordare.musicxml+xml",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.musicxml"'},
    )


def _editable_project(
    project_id: str, expected_revision: int, session: Session
) -> tuple[ProjectRecord, ScoreProject]:
    record = session.get(ProjectRecord, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if record.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "current_revision": record.revision,
            },
        )
    return record, ScoreProject.model_validate(record.document)


def _save_project(record: ProjectRecord, project: ScoreProject, session: Session) -> ScoreProject:
    record.revision += 1
    project.revision = record.revision
    record.document = project.model_dump(mode="json")
    session.commit()
    return project


@router.patch("/projects/{project_id}", response_model=ScoreProject)
def update_project(project_id: str, request: ProjectPatch, session: SessionDep) -> ScoreProject:
    record, project = _editable_project(project_id, request.expected_revision, session)
    if request.notes is not None:
        project.notes = request.notes
    return _save_project(record, project, session)


@router.post("/projects/{project_id}/requantize", response_model=ScoreProject)
def requantize_project(
    project_id: str, request: RequantizeRequest, session: SessionDep
) -> ScoreProject:
    record, project = _editable_project(project_id, request.expected_revision, session)
    return _save_project(record, requantize(project, request), session)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, session: SessionDep, settings: SettingsDep) -> Response:
    project = session.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job = session.get(JobRecord, project.job_id)
    if job is None:
        session.delete(project)
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    upload = session.get(UploadRecord, job.upload_id)
    object_key = upload.object_key if upload else None
    session.delete(project)
    session.delete(job)
    session.flush()
    other_job = session.scalar(
        select(JobRecord.id).where(JobRecord.upload_id == job.upload_id).limit(1)
    )
    if upload is not None and other_job is None:
        session.delete(upload)
    session.commit()
    if object_key is not None and other_job is None:
        remove_project_files(settings, object_key, job.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unused_upload(upload_id: str, session: SessionDep) -> Response:
    upload = session.get(UploadRecord, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    session.delete(upload)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
