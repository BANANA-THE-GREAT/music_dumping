from app.schemas import (
    KeyPoint,
    MeterPoint,
    PipelineStep,
    RequantizeRequest,
    ScoreProject,
    TempoPoint,
)


def requantize(project: ScoreProject, request: RequantizeRequest) -> ScoreProject:
    milliseconds_per_beat = 60_000 / request.bpm

    for note in project.notes:
        raw_start = note.source_start_ms / milliseconds_per_beat
        raw_duration = (note.source_end_ms - note.source_start_ms) / milliseconds_per_beat
        note.quantized_start = round(raw_start / request.grid) * request.grid
        note.quantized_duration = max(
            request.grid, round(raw_duration / request.grid) * request.grid
        )

    project.analysis.tempo_map = [TempoPoint(time_ms=0, bpm=request.bpm)]
    project.analysis.meter_map = [
        MeterPoint(beat=0, numerator=request.numerator, denominator=request.denominator)
    ]
    project.analysis.key_map = [KeyPoint(beat=0, tonic=request.tonic, mode=request.mode)]
    project.pipeline.append(
        PipelineStep(
            stage="requantize",
            version="1",
            parameters={
                "bpm": request.bpm,
                "numerator": request.numerator,
                "denominator": request.denominator,
                "tonic": request.tonic,
                "mode": request.mode,
                "grid": request.grid,
            },
        )
    )
    return project
