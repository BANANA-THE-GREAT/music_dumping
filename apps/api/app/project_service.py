from app.schemas import (
    KeyPoint,
    MeterPoint,
    PipelineStep,
    QuantizationConflict,
    QuantizationSettings,
    RequantizeRequest,
    ScoreNote,
    ScoreProject,
    TempoPoint,
)
from app.tempo import beat_at_ms


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
