from app.schemas import (
    KeyPoint,
    MeterPoint,
    PipelineStep,
    RequantizeRequest,
    ScoreNote,
    ScoreProject,
    TempoPoint,
)


def requantize(project: ScoreProject, request: RequantizeRequest) -> ScoreProject:
    milliseconds_per_beat = 60_000 / request.bpm
    quantized: list[ScoreNote] = []
    for note in project.performance_notes or []:
        raw_start = note.source_start_ms / milliseconds_per_beat
        raw_duration = (note.source_end_ms - note.source_start_ms) / milliseconds_per_beat
        quantized.append(
            ScoreNote(
                id=note.id,
                source_start_ms=note.source_start_ms,
                source_end_ms=note.source_end_ms,
                source_note_ids=list(note.source_note_ids),
                pitch_midi=note.pitch_midi,
                confidence=note.confidence,
                quantized_start=round(raw_start / request.grid) * request.grid,
                quantized_duration=max(
                    request.grid, round(raw_duration / request.grid) * request.grid
                ),
                origin=note.origin,
            )
        )
    project.notes = quantized

    project.analysis.tempo_map = [TempoPoint(time_ms=0, bpm=request.bpm)]
    project.analysis.meter_map = [
        MeterPoint(beat=0, numerator=request.numerator, denominator=request.denominator)
    ]
    project.analysis.key_map = [KeyPoint(beat=0, tonic=request.tonic, mode=request.mode)]
    project.pipeline.append(
        PipelineStep(
            stage="requantize",
            version="2",
            parameters={
                "bpm": request.bpm,
                "numerator": request.numerator,
                "denominator": request.denominator,
                "tonic": request.tonic,
                "mode": request.mode,
                "grid": request.grid,
                "source": "performance_notes",
            },
        )
    )
    return project
