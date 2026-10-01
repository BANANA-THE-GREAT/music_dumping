from typing import Literal

from app.schemas import (
    KeyPoint,
    MeterPoint,
    PerformanceNote,
    PipelineStep,
    QuantizationConflict,
    QuantizationSettings,
    RequantizeRequest,
    ScoreNote,
    ScoreProject,
    TempoPoint,
)
from app.tempo import beat_at_ms, ms_at_beat

SupersededReason = Literal[
    "manual_timing_edit", "target_deleted", "target_structure_changed"
]


def _source_owners(notes: list[ScoreNote]) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for note in notes:
        for source_id in note.source_note_ids:
            owners.setdefault(source_id, set()).add(note.id)
    return owners


def synchronize_score_edits(
    project: ScoreProject, updated_notes: list[ScoreNote], next_revision: int
) -> ScoreProject:
    """Apply readable score edits to the canonical performance-note layer."""
    old_notes = {note.id: note for note in project.notes}
    old_performance = {note.id: note for note in project.performance_notes or []}
    old_owners = _source_owners(project.notes)
    new_owners = _source_owners(updated_notes)
    superseded_reasons: dict[str, SupersededReason] = {}

    for source_id in old_owners.keys() | new_owners.keys():
        previous_owners = old_owners.get(source_id, set())
        current_owners = new_owners.get(source_id, set())
        if previous_owners and not current_owners:
            superseded_reasons[source_id] = "target_deleted"
        elif previous_owners != current_owners:
            superseded_reasons[source_id] = "target_structure_changed"

    synchronized_notes: list[ScoreNote] = []
    synchronized_performance: list[PerformanceNote] = []
    pitch_edits = 0
    timing_edits = 0
    created = 0

    for updated in updated_notes:
        previous = old_notes.get(updated.id)
        performance = old_performance.get(updated.id)
        if previous is not None and set(previous.source_note_ids) != set(
            updated.source_note_ids
        ):
            for source_id in set(previous.source_note_ids) | set(updated.source_note_ids):
                superseded_reasons[source_id] = "target_structure_changed"
        timing_changed = previous is None or not (
            abs(previous.quantized_start - updated.quantized_start) < 1e-9
            and abs(previous.quantized_duration - updated.quantized_duration) < 1e-9
        )
        pitch_changed = previous is None or previous.pitch_midi != updated.pitch_midi

        if timing_changed:
            start_ms = ms_at_beat(updated.quantized_start, project.analysis.tempo_map)
            end_ms = max(
                start_ms + 1,
                ms_at_beat(
                    updated.quantized_start + updated.quantized_duration,
                    project.analysis.tempo_map,
                ),
            )
            timing_edits += 1
            for source_id in updated.source_note_ids:
                superseded_reasons.setdefault(source_id, "manual_timing_edit")
        elif performance is not None:
            start_ms = performance.source_start_ms
            end_ms = performance.source_end_ms
        else:
            start_ms = updated.source_start_ms
            end_ms = updated.source_end_ms

        if pitch_changed:
            pitch_edits += 1
        if previous is None:
            created += 1

        synchronized = updated.model_copy(
            update={
                "source_start_ms": start_ms,
                "source_end_ms": end_ms,
                "origin": "user"
                if previous is None or timing_changed or pitch_changed
                else updated.origin,
            }
        )
        synchronized_notes.append(synchronized)
        synchronized_performance.append(
            PerformanceNote(
                id=updated.id,
                source_start_ms=start_ms,
                source_end_ms=end_ms,
                source_note_ids=list(updated.source_note_ids),
                pitch_midi=updated.pitch_midi,
                confidence=updated.confidence,
                origin=synchronized.origin,
                pitch_bends=list(performance.pitch_bends) if performance is not None else [],
            )
        )

    superseded = 0
    evidence = project.transcription_evidence
    if evidence is not None:
        for suggestion in evidence.boundary_suggestions:
            reason = superseded_reasons.get(suggestion.source_note_id)
            if reason is None or suggestion.review_status == "superseded":
                continue
            suggestion.review_status = "superseded"
            suggestion.superseded_reason = reason
            suggestion.reviewed_revision = next_revision
            superseded += 1
        batch_id = evidence.last_boundary_batch_id
        if batch_id and not any(
            suggestion.review_batch_id == batch_id
            and suggestion.review_status == "accepted"
            for suggestion in evidence.boundary_suggestions
        ):
            evidence.last_boundary_batch_id = None

    deleted = len(set(old_notes) - {note.id for note in updated_notes})
    project.notes = synchronized_notes
    project.performance_notes = synchronized_performance
    project.pipeline.append(
        PipelineStep(
            stage="synchronize_score_edits",
            version="1",
            parameters={
                "pitch_edits": pitch_edits,
                "timing_edits": timing_edits,
                "created_notes": created,
                "deleted_notes": deleted,
                "superseded_suggestions": superseded,
            },
        )
    )
    return project


def boundary_quantized_duration(
    project: ScoreProject, note: ScoreNote, proposed_end_ms: int
) -> float:
    """Map a reviewed performance end to one readable score duration."""
    end_beats = beat_at_ms(proposed_end_ms, project.analysis.tempo_map)
    settings = project.quantization
    if not settings.enabled:
        return max(0.01, end_beats - note.quantized_start)

    offset_beats = beat_at_ms(max(0, settings.offset_ms), project.analysis.tempo_map)
    snapped_end = (
        round((end_beats - offset_beats) / settings.grid) * settings.grid
        + offset_beats
    )
    # A boundary review must never create an unreadably short score value.
    return max(settings.grid, snapped_end - note.quantized_start)


def requantize(project: ScoreProject, request: RequantizeRequest) -> ScoreProject:
    tempo_map = request.tempo_map or [TempoPoint(time_ms=0, bpm=request.bpm)]
    offset_beats = beat_at_ms(max(0, request.offset_ms), tempo_map)
    quantized: list[ScoreNote] = []
    for performance_note in project.performance_notes or []:
        raw_start = beat_at_ms(performance_note.source_start_ms, tempo_map)
        raw_end = beat_at_ms(performance_note.source_end_ms, tempo_map)
        if request.enabled:
            snapped_start = (
                round((raw_start - offset_beats) / request.grid) * request.grid
                + offset_beats
            )
            snapped_end = (
                round((raw_end - offset_beats) / request.grid) * request.grid
                + offset_beats
            )
            start = raw_start + (snapped_start - raw_start) * request.strength
            end = raw_end + (snapped_end - raw_end) * request.strength
            minimum_duration = (
                request.grid * request.strength if request.strength > 0 else 0.01
            )
        else:
            start, end = raw_start, raw_end
            minimum_duration = 0.01
        quantized.append(
            ScoreNote(
                id=performance_note.id,
                source_start_ms=performance_note.source_start_ms,
                source_end_ms=performance_note.source_end_ms,
                source_note_ids=list(performance_note.source_note_ids),
                pitch_midi=performance_note.pitch_midi,
                confidence=performance_note.confidence,
                quantized_start=max(0, start),
                quantized_duration=max(minimum_duration, end - start),
                origin=performance_note.origin,
            )
        )
    project.notes = quantized
    by_start: dict[float, list[str]] = {}
    for score_note in quantized:
        by_start.setdefault(round(score_note.quantized_start, 6), []).append(score_note.id)
    project.quantization = QuantizationSettings(
        enabled=request.enabled,
        grid=request.grid,
        strength=request.strength,
        offset_ms=request.offset_ms,
        conflicts=[
            QuantizationConflict(beat=beat, note_ids=note_ids)
            for beat, note_ids in sorted(by_start.items())
            if len(note_ids) > 1
        ],
    )

    project.analysis.tempo_map = list(tempo_map)
    project.analysis.meter_map = [
        MeterPoint(beat=0, numerator=request.numerator, denominator=request.denominator)
    ]
    project.analysis.key_map = [KeyPoint(beat=0, tonic=request.tonic, mode=request.mode)]
    project.pipeline.append(
        PipelineStep(
            stage="requantize",
            version="3",
            parameters={
                "bpm": request.bpm,
                "numerator": request.numerator,
                "denominator": request.denominator,
                "tonic": request.tonic,
                "mode": request.mode,
                "grid": request.grid,
                "enabled": request.enabled,
                "strength": request.strength,
                "offset_ms": request.offset_ms,
                "conflicts": len(project.quantization.conflicts),
                "source": "performance_notes",
                "tempo_map": [point.model_dump() for point in tempo_map],
            },
        )
    )
    return project
