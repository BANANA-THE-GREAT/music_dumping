from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ReadinessResponse(HealthResponse):
    checks: dict[str, Literal["ok", "unavailable"]]


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class JobStage(StrEnum):
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    SEPARATING = "separating"
    TRACKING_BEATS = "tracking_beats"
    TRANSCRIBING = "transcribing"
    POSTPROCESSING = "postprocessing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class UploadResponse(BaseModel):
    id: str
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class JobOptions(BaseModel):
    separator: str = "fake"
    transcriber: str = "fake"
    detect_meter: bool = True
    detect_key: bool = True


class JobCreate(BaseModel):
    upload_id: str
    options: JobOptions = Field(default_factory=JobOptions)


class JobResponse(BaseModel):
    id: str
    upload_id: str
    status: JobStatus
    stage: JobStage
    progress: float = Field(ge=0, le=1)
    project_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    created_at: datetime
    updated_at: datetime


class TempoPoint(BaseModel):
    time_ms: int = Field(ge=0)
    bpm: float = Field(gt=0)


class MeterPoint(BaseModel):
    beat: float = Field(ge=0)
    numerator: int = Field(gt=0)
    denominator: int = Field(gt=0)


class KeyPoint(BaseModel):
    beat: float = Field(ge=0)
    tonic: int = Field(ge=0, le=11)
    mode: Literal["major", "minor"]


class Analysis(BaseModel):
    tempo_map: list[TempoPoint]
    meter_map: list[MeterPoint]
    key_map: list[KeyPoint]
    confidence: dict[str, float]


class SourceAudio(BaseModel):
    file_name: str
    duration_ms: int = Field(ge=0)
    audio_object_key: str
    vocal_object_key: str | None = None


class ScoreNote(BaseModel):
    id: str
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(ge=0)
    pitch_midi: int = Field(ge=0, le=127)
    confidence: float = Field(ge=0, le=1)
    quantized_start: float = Field(ge=0)
    quantized_duration: float = Field(gt=0)
    origin: Literal["model", "user"]


class PipelineStep(BaseModel):
    stage: str
    version: str
    parameters: dict[str, object] = Field(default_factory=dict)


class ScoreProject(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    source: SourceAudio
    analysis: Analysis
    notes: list[ScoreNote]
    pipeline: list[PipelineStep]
    revision: int = Field(ge=1)


class ErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool = False
