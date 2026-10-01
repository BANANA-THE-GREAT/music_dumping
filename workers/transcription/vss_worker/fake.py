from collections.abc import Callable
from uuid import uuid4

ProgressCallback = Callable[[str, float], None]


def build_fake_project(
    *, upload_id: str, file_name: str, object_key: str, progress: ProgressCallback
) -> dict[str, object]:
    stages = [
        ("preprocessing", 0.12),
        ("separating", 0.30),
        ("tracking_beats", 0.48),
        ("transcribing", 0.68),
        ("postprocessing", 0.86),
        ("rendering", 0.96),
    ]
    for stage, value in stages:
        progress(stage, value)

    project_id = str(uuid4())
    pitches = [60, 60, 67, 67, 69, 69, 67, 65, 64, 62, 60]
    notes = [
        {
            "id": str(uuid4()),
            "source_start_ms": index * 500,
            "source_end_ms": index * 500 + (900 if index in {6, 10} else 440),
            "pitch_midi": pitch,
            "confidence": 0.9,
            "quantized_start": float(index),
            "quantized_duration": 2.0 if index in {6, 10} else 1.0,
            "origin": "model",
        }
        for index, pitch in enumerate(pitches)
    ]
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "source": {
            "file_name": file_name,
            "duration_ms": 6000,
            "audio_object_key": object_key,
            "vocal_object_key": None,
        },
        "analysis": {
            "tempo_map": [{"time_ms": 0, "bpm": 120}],
            "meter_map": [{"beat": 0, "numerator": 4, "denominator": 4}],
            "key_map": [{"beat": 0, "tonic": 0, "mode": "major"}],
            "confidence": {"tempo": 0.95, "meter": 0.9, "key": 0.92},
        },
        "notes": notes,
        "performance_notes": [
            {
                key: value
                for key, value in note.items()
                if key not in {"quantized_start", "quantized_duration"}
            }
            for note in notes
        ],
        "pipeline": [
            {
                "stage": "fake_transcription",
                "version": "1.0.0",
                "parameters": {"upload_id": upload_id},
            }
        ],
        "revision": 1,
    }
