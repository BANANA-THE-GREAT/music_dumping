import math
import time
from collections.abc import Iterator
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal, get_session
from app.exporters import project_to_midi, project_to_musicxml
from app.job_runner import dispatch_job
from app.models import JobRecord, ProjectRecord, UploadRecord
from app.project_service import (
    boundary_quantized_duration,
    requantize,
    synchronize_score_edits,
)
from app.repository import create_job, create_upload, job_response
from app.schemas import (
    AudioAlignmentRequest,
    BoundaryBatchReviewRequest,
    BoundarySuggestionReviewRequest,
    JobCreate,
    JobResponse,
    JobStage,
    JobStatus,
    MelodyRequest,
    PipelineStep,
    ProjectBulkDeleteRequest,
    ProjectCatalogSummary,
    ProjectPatch,
    ProjectRenameRequest,
    ProjectSummary,
    RequantizeRequest,
    ScoreProject,
    UploadResponse,
)
from app.storage import UploadTooLargeError, remove_project_files, resolve_data_path, save_upload

router = APIRouter(prefix="/v1")
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _hydrate_project_metadata(
    record: ProjectRecord, session: Session
) -> tuple[ScoreProject, UploadRecord | None, bool]:
    project = ScoreProject.model_validate(record.document)
    job = session.get(JobRecord, record.job_id)
    upload = session.get(UploadRecord, job.upload_id) if job else None
    if upload is None:
        return project, None, False
    changed = False
    audio_name = upload.file_name.rsplit(".", 1)[0] or upload.file_name
    if not project.project_group_id:
        project.project_group_id = upload.id
        changed = True
    if not project.project_name or project.project_name == "未命名项目":
        project.project_name = upload.project_name or audio_name
        changed = True
    if not project.score_name or project.score_name == "未命名谱面":
        records = session.scalars(
            select(ProjectRecord)
            .join(JobRecord, ProjectRecord.job_id == JobRecord.id)
            .where(JobRecord.upload_id == upload.id)
            .order_by(ProjectRecord.created_at, ProjectRecord.id)
        ).all()
        project.score_name = f"{audio_name}-{records.index(record) + 1}"
        changed = True
    if changed:
        record.document = project.model_dump(mode="json")
    return project, upload, changed


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
    record = session.scalar(select(JobRecord).where(JobRecord.id == job_id).with_for_update())
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Job is already terminal")
    record.status = JobStatus.CANCELLED
    record.stage = JobStage.CANCELLED
    session.commit()
    return job_response(record)


@router.post(
    "/jobs/{job_id}/retry", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED
)
def retry_job(job_id: str, session: SessionDep) -> JobResponse:
    previous = session.get(JobRecord, job_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if previous.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried")
    options = {**previous.options, "auto_start": True}
    request = JobCreate(upload_id=previous.upload_id, options=options)
    response = create_job(session, request)
    if request.options.auto_start:
        dispatch_job(response.id)
    return response


@router.get("/projects/{project_id}", response_model=ScoreProject)
def get_project(project_id: str, session: SessionDep) -> ScoreProject:
    record = session.get(ProjectRecord, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project, _, changed = _hydrate_project_metadata(record, session)
    if changed:
        session.commit()
    return project


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


@router.get("/project-catalog", response_model=list[ProjectCatalogSummary])
def list_project_catalog(session: SessionDep) -> list[ProjectCatalogSummary]:
    records = session.scalars(
        select(ProjectRecord).order_by(ProjectRecord.updated_at.desc()).limit(200)
    )
    summaries: list[ProjectCatalogSummary] = []
    represented_uploads: set[str] = set()
    metadata_changed = False
    for record in records:
        project, upload, changed = _hydrate_project_metadata(record, session)
        metadata_changed = metadata_changed or changed
        if upload:
            represented_uploads.add(upload.id)
        summaries.append(
            ProjectCatalogSummary(
                project_id=project.project_id,
                project_group_id=project.project_group_id or (upload.id if upload else ""),
                upload_id=upload.id if upload else "",
                project_name=upload.project_name
                if upload and upload.project_name
                else (project.project_name or "未命名项目"),
                score_name=project.score_name or "未命名谱面",
                engine=project.engine or "unknown",
                file_name=project.source.file_name,
                duration_ms=project.source.duration_ms,
                note_count=len(project.notes),
                revision=record.revision,
                updated_at=record.updated_at,
            )
        )
    if metadata_changed:
        session.commit()
    uploads = session.scalars(
        select(UploadRecord).order_by(UploadRecord.created_at.desc()).limit(200)
    )
    for upload in uploads:
        if upload.id in represented_uploads:
            continue
        summaries.append(
            ProjectCatalogSummary(
                project_group_id=upload.id,
                upload_id=upload.id,
                project_name=upload.project_name or upload.file_name.rsplit(".", 1)[0],
                file_name=upload.file_name,
                updated_at=upload.created_at,
            )
        )
    summaries.sort(key=lambda item: item.updated_at, reverse=True)
    return summaries


def _project_document(project_id: str, session: Session) -> ScoreProject:
    record = session.get(ProjectRecord, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project, _, changed = _hydrate_project_metadata(record, session)
    if changed:
        session.commit()
    return project


@router.patch("/projects/{project_id}/name", response_model=ScoreProject)
def rename_project(
    project_id: str, request: ProjectRenameRequest, session: SessionDep
) -> ScoreProject:
    record, project = _editable_project(project_id, request.expected_revision, session)
    project.score_name = request.name
    return _save_project(record, project, session)


@router.patch("/uploads/{upload_id}/name", response_model=UploadResponse)
def rename_audio_project(
    upload_id: str, request: ProjectRenameRequest, session: SessionDep
) -> UploadResponse:
    upload = session.get(UploadRecord, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    upload.project_name = request.name
    session.commit()
    session.refresh(upload)
    return UploadResponse.model_validate(upload, from_attributes=True)


@router.get("/projects/{project_id}/exports/midi")
def export_project_midi(
    project_id: str,
    session: SessionDep,
    version: Literal["score", "performance"] = "score",
) -> Response:
    content = project_to_midi(_project_document(project_id, session), version)
    suffix = ".performance" if version == "performance" else ""
    return Response(
        content=content,
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{project_id}{suffix}.mid"'},
    )


@router.get("/projects/{project_id}/exports/musicxml")
def export_project_musicxml(project_id: str, session: SessionDep) -> Response:
    content = project_to_musicxml(_project_document(project_id, session))
    return Response(
        content=content,
        media_type="application/vnd.recordare.musicxml+xml",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.musicxml"'},
    )


@router.get("/projects/{project_id}/audio")
def stream_project_audio(
    project_id: str,
    session: SessionDep,
    settings: SettingsDep,
    variant: Literal["source", "vocals"] = "source",
) -> FileResponse:
    record = session.get(ProjectRecord, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project = ScoreProject.model_validate(record.document)
    object_key = (
        project.source.audio_object_key if variant == "source" else project.source.vocal_object_key
    )
    if not object_key:
        raise HTTPException(status_code=404, detail="Separated vocals are not available")
    path = resolve_data_path(settings, object_key)
    if variant == "vocals" and not path.is_file():
        # Older documents incorrectly used the project ID rather than the worker job ID.
        path = resolve_data_path(
            settings, f"work/{record.job_id}/stems/htdemucs/normalized/vocals.wav"
        )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Project audio not found")
    job = session.get(JobRecord, record.job_id)
    upload = session.get(UploadRecord, job.upload_id) if job else None
    return FileResponse(
        path,
        media_type="audio/wav"
        if variant == "vocals"
        else upload.content_type
        if upload
        else "application/octet-stream",
        filename="vocals.wav" if variant == "vocals" else project.source.file_name,
    )


@router.get("/projects/{project_id}/evidence/f0")
def stream_project_f0(project_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    project = _project_document(project_id, session)
    artifact = (
        project.transcription_evidence.f0_track
        if project.transcription_evidence is not None
        else None
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="F0 evidence is not available")
    path = resolve_data_path(settings, artifact.object_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="F0 evidence file not found")
    return FileResponse(path, media_type="application/x-ndjson", filename="f0.jsonl")


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
        synchronize_score_edits(project, request.notes, record.revision + 1)
    return _save_project(record, project, session)


@router.post("/projects/{project_id}/boundary-suggestions/batch", response_model=ScoreProject)
def review_boundary_batch(
    project_id: str,
    request: BoundaryBatchReviewRequest,
    session: SessionDep,
) -> ScoreProject:
    # Register the static /batch path before /{suggestion_id}; FastAPI matches in order.
    return _review_boundary_batch(project_id, request, session)


@router.post(
    "/projects/{project_id}/boundary-suggestions/{suggestion_id}",
    response_model=ScoreProject,
)
def review_boundary_suggestion(
    project_id: str,
    suggestion_id: str,
    request: BoundarySuggestionReviewRequest,
    session: SessionDep,
) -> ScoreProject:
    from app.schemas import PipelineStep

    record, project = _editable_project(project_id, request.expected_revision, session)
    evidence = project.transcription_evidence
    if evidence is None:
        raise HTTPException(status_code=404, detail={"code": "SUGGESTION_NOT_FOUND"})
    suggestion = next(
        (item for item in evidence.boundary_suggestions if item.id == suggestion_id), None
    )
    if suggestion is None:
        raise HTTPException(status_code=404, detail={"code": "SUGGESTION_NOT_FOUND"})
    if suggestion.review_status == "superseded":
        raise HTTPException(status_code=409, detail={"code": "SUGGESTION_SUPERSEDED"})
    if request.action != "reset" and suggestion.review_status != "pending":
        raise HTTPException(status_code=409, detail={"code": "SUGGESTION_ALREADY_REVIEWED"})
    if request.action == "reset" and suggestion.review_status == "pending":
        raise HTTPException(status_code=409, detail={"code": "SUGGESTION_NOT_REVIEWED"})

    target = next(
        (note for note in project.notes if suggestion.source_note_id in note.source_note_ids),
        None,
    )
    performance_target = next(
        (
            note
            for note in project.performance_notes or []
            if suggestion.source_note_id in note.source_note_ids
        ),
        None,
    )
    changes_note = request.action == "accept" or (
        request.action == "reset" and suggestion.review_status == "accepted"
    )
    if changes_note:
        if target is None or performance_target is None:
            raise HTTPException(status_code=409, detail={"code": "SUGGESTION_TARGET_MISSING"})
        expected_end = (
            suggestion.original_end_ms if request.action == "accept" else suggestion.proposed_end_ms
        )
        if target.source_end_ms != expected_end:
            raise HTTPException(status_code=409, detail={"code": "SUGGESTION_TARGET_CHANGED"})
        if performance_target.source_end_ms != expected_end:
            raise HTTPException(status_code=409, detail={"code": "SUGGESTION_TARGET_CHANGED"})
        if request.action == "reset":
            expected_duration = boundary_quantized_duration(
                project, target, suggestion.proposed_end_ms
            )
            if not math.isclose(target.quantized_duration, expected_duration):
                raise HTTPException(status_code=409, detail={"code": "SUGGESTION_TARGET_CHANGED"})

    next_revision = record.revision + 1
    if request.action == "accept":
        assert target is not None
        assert performance_target is not None
        suggestion.accepted_from_origin = target.origin
        suggestion.accepted_from_quantized_duration = target.quantized_duration
        target.source_end_ms = suggestion.proposed_end_ms
        target.quantized_duration = boundary_quantized_duration(
            project, target, target.source_end_ms
        )
        target.origin = "user"
        performance_target.source_end_ms = suggestion.proposed_end_ms
        performance_target.origin = "user"
        suggestion.review_status = "accepted"
        suggestion.superseded_reason = None
        suggestion.reviewed_revision = next_revision
    elif request.action == "reject":
        suggestion.review_status = "rejected"
        suggestion.superseded_reason = None
        suggestion.reviewed_revision = next_revision
    else:
        if changes_note:
            assert target is not None
            assert performance_target is not None
            target.source_end_ms = suggestion.original_end_ms
            target.quantized_duration = (
                suggestion.accepted_from_quantized_duration
                if suggestion.accepted_from_quantized_duration is not None
                else boundary_quantized_duration(project, target, target.source_end_ms)
            )
            target.origin = suggestion.accepted_from_origin or "model"
            performance_target.source_end_ms = suggestion.original_end_ms
            performance_target.origin = suggestion.accepted_from_origin or "model"
        suggestion.review_status = "pending"
        suggestion.superseded_reason = None
        suggestion.reviewed_revision = None
        suggestion.accepted_from_origin = None
        suggestion.accepted_from_quantized_duration = None
    project.pipeline.append(
        PipelineStep(
            stage="boundary_suggestion_review",
            version="1",
            parameters={"suggestion_id": suggestion.id, "action": request.action},
        )
    )
    return _save_project(record, project, session)


def _review_boundary_batch(
    project_id: str,
    request: BoundaryBatchReviewRequest,
    session: SessionDep,
) -> ScoreProject:
    record, project = _editable_project(project_id, request.expected_revision, session)
    evidence = project.transcription_evidence
    if evidence is None:
        raise HTTPException(status_code=404, detail={"code": "SUGGESTION_NOT_FOUND"})
    pending = [
        item
        for item in evidence.boundary_suggestions
        if item.review_status == "pending" and item.confidence >= request.threshold
    ]
    if request.action == "preview":
        return project
    if request.action == "reset":
        batch_id = evidence.last_boundary_batch_id
        if not batch_id:
            raise HTTPException(status_code=409, detail={"code": "NO_BOUNDARY_BATCH"})
        restored = 0
        for suggestion in evidence.boundary_suggestions:
            if suggestion.review_batch_id != batch_id or suggestion.review_status != "accepted":
                continue
            target = next(
                (
                    note
                    for note in project.notes
                    if suggestion.source_note_id in note.source_note_ids
                ),
                None,
            )
            performance_target = next(
                (
                    note
                    for note in project.performance_notes or []
                    if suggestion.source_note_id in note.source_note_ids
                ),
                None,
            )
            if (
                target is None
                or performance_target is None
                or target.source_end_ms != suggestion.proposed_end_ms
            ):
                continue
            target.source_end_ms = suggestion.original_end_ms
            target.quantized_duration = suggestion.accepted_from_quantized_duration or (
                boundary_quantized_duration(project, target, target.source_end_ms)
            )
            target.origin = suggestion.accepted_from_origin or "model"
            performance_target.source_end_ms = suggestion.original_end_ms
            performance_target.origin = suggestion.accepted_from_origin or "model"
            suggestion.review_status = "pending"
            suggestion.superseded_reason = None
            suggestion.reviewed_revision = None
            suggestion.review_batch_id = None
            suggestion.accepted_from_origin = None
            suggestion.accepted_from_quantized_duration = None
            restored += 1
        evidence.last_boundary_batch_id = None
        project.pipeline.append(
            PipelineStep(
                stage="boundary_suggestion_batch_reset",
                version="1",
                parameters={"restored": restored, "batch_id": batch_id},
            )
        )
        return _save_project(record, project, session)

    batch_id = str(uuid4())
    changed = 0
    for suggestion in pending:
        target = next(
            (note for note in project.notes if suggestion.source_note_id in note.source_note_ids),
            None,
        )
        performance_target = next(
            (
                note
                for note in project.performance_notes or []
                if suggestion.source_note_id in note.source_note_ids
            ),
            None,
        )
        if (
            target is None
            or performance_target is None
            or target.source_end_ms != suggestion.original_end_ms
        ):
            continue
        suggestion.accepted_from_origin = target.origin
        suggestion.accepted_from_quantized_duration = target.quantized_duration
        target.source_end_ms = suggestion.proposed_end_ms
        target.quantized_duration = boundary_quantized_duration(
            project, target, target.source_end_ms
        )
        target.origin = "user"
        performance_target.source_end_ms = suggestion.proposed_end_ms
        performance_target.origin = "user"
        suggestion.review_status = "accepted"
        suggestion.superseded_reason = None
        suggestion.review_batch_id = batch_id
        suggestion.reviewed_revision = record.revision + 1
        changed += 1
    evidence.last_boundary_batch_id = batch_id if changed else None
    project.pipeline.append(
        PipelineStep(
            stage="boundary_suggestion_batch_accept",
            version="1",
            parameters={"threshold": request.threshold, "accepted": changed, "batch_id": batch_id},
        )
    )
    return _save_project(record, project, session)


@router.patch("/projects/{project_id}/alignment", response_model=ScoreProject)
def update_audio_alignment(
    project_id: str, request: AudioAlignmentRequest, session: SessionDep
) -> ScoreProject:
    record, project = _editable_project(project_id, request.expected_revision, session)
    project.audio_alignment.offset_ms = request.offset_ms
    project.audio_alignment.source = request.source
    project.audio_alignment.status = request.status
    project.pipeline.append(
        PipelineStep(
            stage="audio_alignment",
            version="1",
            parameters={"offset_ms": request.offset_ms, "source": request.source},
        )
    )
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
    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING}:
        raise HTTPException(status_code=409, detail={"code": "PROJECT_JOB_RUNNING"})
    upload = session.get(UploadRecord, job.upload_id)
    object_key = upload.object_key if upload else None
    session.delete(project)
    # There are no ORM relationships to order these dependent DELETE statements.
    session.flush()
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


@router.post("/projects/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_projects(
    request: ProjectBulkDeleteRequest, session: SessionDep, settings: SettingsDep
) -> dict[str, int]:
    records = [session.get(ProjectRecord, project_id) for project_id in set(request.project_ids)]
    missing = sum(record is None for record in records)
    existing = [record for record in records if record is not None]
    running = [
        record.id
        for record in existing
        if (job := session.get(JobRecord, record.job_id)) is not None
        and job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING}
    ]
    if running:
        raise HTTPException(
            status_code=409, detail={"code": "PROJECT_JOB_RUNNING", "project_ids": running}
        )

    upload_ids = {
        job.upload_id
        for record in existing
        if (job := session.get(JobRecord, record.job_id)) is not None
    }
    object_keys: dict[str, str] = {}
    cleanup_jobs: list[tuple[str, str]] = []
    for record in existing:
        job = session.get(JobRecord, record.job_id)
        upload = session.get(UploadRecord, job.upload_id) if job else None
        if job is not None:
            if upload is not None:
                object_keys[upload.id] = upload.object_key
                cleanup_jobs.append((upload.object_key, job.id))
            session.delete(record)
            session.flush()
            session.delete(job)
        if upload is not None:
            object_keys[upload.id] = upload.object_key
    session.flush()
    removed_uploads = 0
    for upload_id in upload_ids:
        if (
            session.scalar(select(JobRecord.id).where(JobRecord.upload_id == upload_id).limit(1))
            is not None
        ):
            continue
        upload = session.get(UploadRecord, upload_id)
        if upload is not None:
            object_keys.setdefault(upload_id, upload.object_key)
            session.delete(upload)
            removed_uploads += 1
    session.commit()
    for object_key, job_id in cleanup_jobs:
        if object_key:
            remove_project_files(settings, object_key, job_id)
    return {
        "deleted_projects": len(existing),
        "deleted_uploads": removed_uploads,
        "missing": missing,
    }


@router.post("/projects/{project_id}/melody", response_model=ScoreProject)
def refine_project_melody(
    project_id: str, request: MelodyRequest, session: SessionDep
) -> ScoreProject:
    from vss_worker.adapters import DetectedNote
    from vss_worker.melody import quantized_notes, refine_melody

    from app.schemas import PerformanceNote, PipelineStep, ScoreNote

    if request.low_pitch > request.high_pitch:
        raise HTTPException(status_code=422, detail="Invalid vocal pitch range")
    record, project = _editable_project(project_id, request.expected_revision, session)
    if project.raw_notes is None:
        project.raw_notes = [n.model_copy(deep=True) for n in project.notes]
    if request.mode == "raw":
        project.notes = [n.model_copy(deep=True) for n in project.raw_notes]
        performance_source = project.raw_notes
    else:
        detected = [
            DetectedNote(
                n.source_start_ms / 1000,
                n.source_end_ms / 1000,
                n.pitch_midi,
                n.confidence,
                n.source_note_ids[0] if n.source_note_ids else n.id,
            )
            for n in project.raw_notes
        ]
        refined = refine_melody(detected, request.mode, request.low_pitch, request.high_pitch)
        bpm = project.analysis.tempo_map[0].bpm
        project.notes = [ScoreNote.model_validate(n) for n in quantized_notes(refined, bpm)]
        performance_source = [
            ScoreNote.model_validate(n) for n in quantized_notes(refined, bpm, monophonic=False)
        ]
    project.performance_notes = [
        PerformanceNote(
            id=note.id,
            source_start_ms=note.source_start_ms,
            source_end_ms=note.source_end_ms,
            source_note_ids=list(note.source_note_ids),
            pitch_midi=note.pitch_midi,
            confidence=note.confidence,
            origin=note.origin,
        )
        for note in performance_source
    ]
    project.pipeline.append(
        PipelineStep(
            stage="melody_refinement",
            version="1",
            parameters={
                "method": "confidence_continuity_viterbi",
                **request.model_dump(exclude={"expected_revision"}),
                "input_notes": len(project.raw_notes),
                "output_notes": len(project.notes),
            },
        )
    )
    return _save_project(record, project, session)


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unused_upload(upload_id: str, session: SessionDep) -> Response:
    upload = session.get(UploadRecord, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    session.delete(upload)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
