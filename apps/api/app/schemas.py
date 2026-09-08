from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    separator: Literal["fake", "demucs"] = "fake"
    transcriber: Literal["fake", "basic_pitch", "game_f0"] = "fake"
    detect_meter: bool = True
    detect_key: bool = True
    auto_start: bool = True


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
    source_note_ids: list[str] = Field(default_factory=list)
    pitch_midi: int = Field(ge=0, le=127)
    confidence: float = Field(ge=0, le=1)
    quantized_start: float = Field(ge=0)
    quantized_duration: float = Field(gt=0)
    origin: Literal["model", "user"]


class PitchBendPoint(BaseModel):
    offset_ms: int = Field(ge=0)
    cents: float = Field(ge=-200, le=200)


class PerformanceNote(BaseModel):
    id: str
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(ge=0)
    source_note_ids: list[str] = Field(default_factory=list)
    pitch_midi: int = Field(ge=0, le=127)
    confidence: float = Field(ge=0, le=1)
    origin: Literal["model", "user"]
    pitch_bends: list[PitchBendPoint] = Field(default_factory=list)


class QuantizationConflict(BaseModel):
    beat: float = Field(ge=0)
    note_ids: list[str] = Field(min_length=2)


class QuantizationSettings(BaseModel):
    enabled: bool = True
    grid: float = Field(default=0.25, gt=0)
    strength: float = Field(default=1, ge=0, le=1)
    offset_ms: int = 0
    conflicts: list[QuantizationConflict] = Field(default_factory=list)


class PipelineStep(BaseModel):
    stage: str
    version: str
    parameters: dict[str, object] = Field(default_factory=dict)


class ModelProvenance(BaseModel):
    name: str = Field(min_length=1)
    implementation: str = Field(min_length=1)
    code_revision: str = Field(min_length=1)
    model_revision: str | None = None
    weight_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parameters: dict[str, object] = Field(default_factory=dict)
    device: str | None = None


class F0TrackArtifact(BaseModel):
    object_key: str = Field(min_length=1)
    format: Literal["jsonl"] = "jsonl"
    frame_period_ms: float = Field(gt=0)
    frame_count: int = Field(ge=0)
    voiced_frame_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    provenance: ModelProvenance

    @model_validator(mode="after")
    def validate_voiced_frame_count(self) -> "F0TrackArtifact":
        if self.voiced_frame_count > self.frame_count:
            raise ValueError("voiced_frame_count cannot exceed frame_count")
        return self


class BoundarySuggestion(BaseModel):
    id: str
    source_note_id: str
    kind: Literal["adjust_end"] = "adjust_end"
    original_end_ms: int = Field(ge=0)
    proposed_end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    reason: Literal["f0_voicing_extension", "f0_voicing_contraction"]
    review_status: Literal["pending", "accepted", "rejected"] = "pending"
    reviewed_revision: int | None = Field(default=None, ge=1)
    accepted_from_origin: Literal["model", "user"] | None = None
    accepted_from_quantized_duration: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_changed_boundary(self) -> "BoundarySuggestion":
        if self.proposed_end_ms == self.original_end_ms:
            raise ValueError("proposed_end_ms must differ from original_end_ms")
        return self


class TranscriptionEvidence(BaseModel):
    note_model: ModelProvenance
    f0_track: F0TrackArtifact | None = None
    boundary_suggestions: list[BoundarySuggestion] = Field(default_factory=list)


class ScoreProject(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    source: SourceAudio
    analysis: Analysis
    notes: list[ScoreNote]
    performance_notes: list[PerformanceNote] | None = None
    quantization: QuantizationSettings = Field(default_factory=QuantizationSettings)
    raw_notes: list[ScoreNote] | None = None
    transcription_evidence: TranscriptionEvidence | None = None
    pipeline: list[PipelineStep]
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def populate_legacy_performance_notes(self) -> "ScoreProject":
        if self.performance_notes is None:
            self.performance_notes = [
                PerformanceNote(
                    id=note.id,
                    source_start_ms=note.source_start_ms,
                    source_end_ms=note.source_end_ms,
                    source_note_ids=list(note.source_note_ids),
                    pitch_midi=note.pitch_midi,
                    confidence=note.confidence,
                    origin=note.origin,
                )
                for note in self.notes
            ]
        return self


class ProjectSummary(BaseModel):
    project_id: str
    file_name: str
    duration_ms: int
    note_count: int
    revision: int
    updated_at: datetime


class ProjectPatch(BaseModel):
    expected_revision: int = Field(ge=1)
    notes: list[ScoreNote] | None = None


class BoundarySuggestionReviewRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    action: Literal["accept", "reject", "reset"]


class MelodyRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    mode: Literal["raw", "conservative", "balanced"] = "balanced"
    low_pitch: int = Field(default=48, ge=0, le=127)
    high_pitch: int = Field(default=84, ge=0, le=127)


class RequantizeRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    bpm: float = Field(ge=20, le=300)
    numerator: int = Field(ge=1, le=16)
    denominator: Literal[2, 4, 8, 16]
    tonic: int = Field(ge=0, le=11)
    mode: Literal["major", "minor"]
    enabled: bool = True
    grid: float = 0.25
    strength: float = Field(default=1, ge=0, le=1)
    offset_ms: int = Field(default=0, ge=-10_000, le=10_000)
    tempo_map: list[TempoPoint] | None = None

    @model_validator(mode="after")
    def normalize_tempo_points(self) -> "RequantizeRequest":
        if self.tempo_map is None:
            self.tempo_map = [TempoPoint(time_ms=0, bpm=self.bpm)]
        else:
            from app.tempo import normalize_tempo_map

            self.tempo_map = normalize_tempo_map(self.tempo_map)
        return self

    @field_validator("grid")
    @classmethod
    def validate_grid(cls, value: float) -> float:
        choices = (0.125, 1 / 6, 0.25, 1 / 3, 0.5, 1.0)
        closest = min(choices, key=lambda choice: abs(choice - value))
        if abs(closest - value) > 1e-6:
            raise ValueError("grid must be a supported straight or triplet value")
        return closest


class ErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool = False
