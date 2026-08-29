from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import JobRecord, UploadRecord
from app.schemas import JobCreate, JobResponse, JobStage, JobStatus, UploadResponse


def create_upload(
    session: Session,
    *,
    file_name: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    object_key: str,
) -> UploadResponse:
    record = UploadRecord(
        id=object_key.split("/")[1],
        file_name=file_name,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        object_key=object_key,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return UploadResponse.model_validate(record, from_attributes=True)


def create_job(session: Session, request: JobCreate) -> JobResponse:
    record = JobRecord(
        id=str(uuid4()),
        upload_id=request.upload_id,
        status=JobStatus.QUEUED,
        stage=JobStage.QUEUED,
        progress=0,
        options=request.options.model_dump(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return job_response(record)


def job_response(record: JobRecord) -> JobResponse:
    return JobResponse.model_validate(record, from_attributes=True)
