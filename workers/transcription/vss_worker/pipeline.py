import statistics
from pathlib import Path
from uuid import uuid4

from vss_worker.adapters import (
    AudioNormalizer,
    DetectedNote,
    MelodyTranscriber,
    Progress,
    VocalSeparator,
)


def _estimate_bpm(notes: list[DetectedNote]) -> float:
    onsets = sorted({note.start_seconds for note in notes})
    intervals = [
        right - left for left, right in zip(onsets, onsets[1:], strict=False) if right - left > 0.1
    ]
    if not intervals:
        return 120.0
    bpm = 60 / statistics.median(intervals)
    while bpm < 70:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return round(bpm, 2)


def _estimate_key(notes: list[DetectedNote]) -> tuple[int, str]:
    if not notes:
        return 0, "major"
    weights = [0.0] * 12
    for note in notes:
        weights[note.pitch_midi % 12] += (note.end_seconds - note.start_seconds) * note.confidence
    major = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
    minor = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
    candidates = [
        (
            sum(weights[(pitch + tonic) % 12] * value for pitch, value in enumerate(profile)),
            tonic,
            mode,
        )
        for mode, profile in (("major", major), ("minor", minor))
        for tonic in range(12)
    ]
    _, tonic, mode = max(candidates)
    return tonic, mode


def build_real_project(
    *,
    upload_id: str,
    file_name: str,
    object_key: str,
    source_path: Path,
    work_dir: Path,
    normalizer: AudioNormalizer,
    separator: VocalSeparator,
    transcriber: MelodyTranscriber,
    progress: Progress,
) -> dict[str, object]:
    progress("preprocessing", 0.1)
    normalized = normalizer.normalize(source_path, work_dir / "normalized.wav")
    progress("separating", 0.3)
    vocal = separator.separate(normalized, work_dir / "stems")
    progress("transcribing", 0.65)
    detected = sorted(transcriber.transcribe(vocal), key=lambda note: note.start_seconds)
    progress("tracking_beats", 0.76)
    bpm = _estimate_bpm(detected)
    tonic, mode = _estimate_key(detected)
    seconds_per_beat = 60 / bpm
    progress("postprocessing", 0.86)
    notes = []
    for note in detected:
        start = round(note.start_seconds / seconds_per_beat * 4) / 4
        duration = max(
            0.25,
            round((note.end_seconds - note.start_seconds) / seconds_per_beat * 4) / 4,
        )
        notes.append(
            {
                "id": str(uuid4()),
                "source_start_ms": round(note.start_seconds * 1000),
                "source_end_ms": round(note.end_seconds * 1000),
                "pitch_midi": note.pitch_midi,
                "confidence": note.confidence,
                "quantized_start": start,
                "quantized_duration": duration,
                "origin": "model",
            }
        )
    progress("rendering", 0.96)
    project_id = str(uuid4())
    duration_ms = round(max((note.end_seconds for note in detected), default=0) * 1000)
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "source": {
            "file_name": file_name,
            "duration_ms": duration_ms,
            "audio_object_key": object_key,
            "vocal_object_key": f"work/{project_id}/stems/htdemucs/normalized/vocals.wav",
        },
        "analysis": {
            "tempo_map": [{"time_ms": 0, "bpm": bpm}],
            "meter_map": [{"beat": 0, "numerator": 4, "denominator": 4}],
            "key_map": [{"beat": 0, "tonic": tonic, "mode": mode}],
            "confidence": {"tempo": 0.65, "meter": 0.3, "key": 0.6},
        },
        "notes": notes,
        "pipeline": [
            {
                "stage": "audio_to_melody",
                "version": "1.0.0",
                "parameters": {
                    "upload_id": upload_id,
                    "normalizer": type(normalizer).__name__,
                    "separator": type(separator).__name__,
                    "transcriber": type(transcriber).__name__,
                },
            }
        ],
        "revision": 1,
    }
