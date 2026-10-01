import statistics
import time
from pathlib import Path
from uuid import uuid4

from vss_worker.adapters import (
    AudioNormalizer,
    DetectedNote,
    EvidenceTranscriber,
    MelodyTranscriber,
    Progress,
    VocalSeparator,
)
from vss_worker.melody import quantized_notes, refine_melody


def _transcription_diagnostics(vocal_path: Path, notes: list[DetectedNote]) -> dict[str, object]:
    try:
        import soundfile as sf  # type: ignore[import-not-found]

        samples, sample_rate = sf.read(vocal_path, always_2d=False, dtype="float32")
        if getattr(samples, "ndim", 1) > 1:
            samples = samples.mean(axis=1)
        frame_size = max(1, int(sample_rate * 0.02))
        energies = [
            float((frame * frame).mean() ** 0.5)
            for frame in (
                samples[start : start + frame_size] for start in range(0, len(samples), frame_size)
            )
            if len(frame)
        ]
        peak = max(energies, default=0.0)
        threshold = max(0.003, peak * 0.08)
        first_loud = next(
            (index for index, energy in enumerate(energies) if energy >= threshold), len(energies)
        )
        leading_silence_ms = round(first_loud * 20)
        low_energy_notes = (
            [
                note
                for note in notes
                if note.start_seconds < len(samples) / sample_rate
                and energies[min(len(energies) - 1, max(0, int(note.start_seconds * 50)))]
                < threshold
            ]
            if energies
            else []
        )
        leading_notes = [note for note in notes if note.start_seconds * 1000 < leading_silence_ms]
        return {
            "input_duration_ms": round(len(samples) / sample_rate * 1000),
            "leading_silence_ms": leading_silence_ms,
            "low_energy_threshold": round(threshold, 6),
            "notes_in_leading_silence": len(leading_notes),
            "low_energy_note_count": len(low_energy_notes),
        }
    except Exception:
        return {
            "input_duration_ms": round(max((note.end_seconds for note in notes), default=0) * 1000),
            "leading_silence_ms": 0,
            "low_energy_threshold": 0,
            "notes_in_leading_silence": 0,
            "low_energy_note_count": 0,
        }


def _runtime_device(adapter: object) -> str:
    device = getattr(adapter, "device", None)
    return device if isinstance(device, str) else "worker-default"


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


def estimate_meter(notes: list[DetectedNote]) -> tuple[int, int, float]:
    ordered = sorted(notes, key=lambda note: note.start_seconds)
    if len(ordered) < 6:
        return 4, 4, 0.2
    best: tuple[float, int] = (0.0, 4)
    for period in (2, 3, 4, 6):
        phase_scores = []
        for phase in range(period):
            accented = [
                note.confidence for index, note in enumerate(ordered) if index % period == phase
            ]
            unaccented = [
                note.confidence for index, note in enumerate(ordered) if index % period != phase
            ]
            contrast = statistics.fmean(accented) - statistics.fmean(unaccented)
            phase_scores.append(contrast)
        score = max(phase_scores)
        if score > best[0]:
            best = score, period
    contrast, numerator = best
    if contrast < 0.08:
        return 4, 4, 0.25
    denominator = 8 if numerator == 6 else 4
    confidence = min(0.9, 0.35 + contrast)
    return numerator, denominator, round(confidence, 3)


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
    evidence_transcriber: EvidenceTranscriber | None = None,
    progress: Progress,
) -> dict[str, object]:
    pipeline_steps: list[dict[str, object]] = []
    progress("preprocessing", 0.1)
    started = time.perf_counter()
    normalized = normalizer.normalize(source_path, work_dir / "normalized.wav")
    pipeline_steps.append(
        {
            "stage": "normalize",
            "version": "1",
            "parameters": {
                "implementation": type(normalizer).__name__,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "device": "cpu",
            },
        }
    )
    progress("separating", 0.3)
    started = time.perf_counter()
    vocal = separator.separate(normalized, work_dir / "stems")
    pipeline_steps.append(
        {
            "stage": "separate_vocals",
            "version": "1",
            "parameters": {
                "implementation": type(separator).__name__,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "device": _runtime_device(separator),
            },
        }
    )
    progress("transcribing", 0.65)
    started = time.perf_counter()
    transcription_evidence = None
    active_transcriber: object = transcriber
    if evidence_transcriber is None:
        detected = sorted(transcriber.transcribe(vocal), key=lambda note: note.start_seconds)
    else:
        active_transcriber = evidence_transcriber
        result = evidence_transcriber.transcribe(vocal, work_dir / "evidence")
        detected = sorted(result.notes, key=lambda note: note.start_seconds)
        transcription_evidence = result.transcription_evidence
    engine_name = type(active_transcriber).__name__
    pipeline_steps.append(
        {
            "stage": "transcribe_notes",
            "version": "1",
            "parameters": {
                "implementation": engine_name,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "device": _runtime_device(active_transcriber),
                "detected_notes": len(detected),
            },
        }
    )
    progress("tracking_beats", 0.76)
    started = time.perf_counter()
    melody = refine_melody(detected)
    bpm = _estimate_bpm(melody)
    tonic, mode = _estimate_key(melody)
    numerator, denominator, meter_confidence = estimate_meter(melody)
    pipeline_steps.append(
        {
            "stage": "analyze_music",
            "version": "1",
            "parameters": {
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "tempo_method": "median_onset_interval",
                "key_method": "krumhansl_schmuckler",
                "meter_method": "accent_cycle",
                "device": "cpu",
            },
        }
    )
    progress("postprocessing", 0.86)
    notes = quantized_notes(melody, bpm)
    performance_source = quantized_notes(melody, bpm, monophonic=False)
    performance_notes = [
        {
            key: value
            for key, value in note.items()
            if key not in {"quantized_start", "quantized_duration"}
        }
        for note in performance_source
    ]
    pipeline_steps.append(
        {
            "stage": "melody_refinement",
            "version": "1",
            "parameters": {
                "method": "confidence_continuity_viterbi",
                "mode": "balanced",
                "input_notes": len(detected),
                "output_notes": len(notes),
            },
        }
    )
    progress("rendering", 0.96)
    project_id = str(uuid4())
    duration_ms = round(max((note.end_seconds for note in detected), default=0) * 1000)
    base_name = file_name.rsplit(".", 1)[0] or file_name
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "project_group_id": upload_id,
        "project_name": base_name,
        "score_name": f"{base_name} · {engine_name}",
        "engine": engine_name,
        "source": {
            "file_name": file_name,
            "duration_ms": duration_ms,
            "audio_object_key": object_key,
            "vocal_object_key": f"work/{work_dir.name}/{vocal.relative_to(work_dir).as_posix()}",
        },
        "transcription_input": {
            "variant": "vocal_stem",
            "object_key": f"work/{work_dir.name}/{vocal.relative_to(work_dir).as_posix()}",
            "separator": type(separator).__name__,
        },
        "transcription_diagnostics": _transcription_diagnostics(vocal, detected),
        "analysis": {
            "tempo_map": [{"time_ms": 0, "bpm": bpm}],
            "meter_map": [{"beat": 0, "numerator": numerator, "denominator": denominator}],
            "key_map": [{"beat": 0, "tonic": tonic, "mode": mode}],
            "confidence": {"tempo": 0.65, "meter": meter_confidence, "key": 0.6},
        },
        "notes": notes,
        "performance_notes": performance_notes,
        "raw_notes": quantized_notes(detected, bpm, monophonic=False),
        "transcription_evidence": transcription_evidence,
        "pipeline": [
            {
                "stage": "audio_to_melody",
                "version": "1.0.0",
                "parameters": {"upload_id": upload_id},
            },
            *pipeline_steps,
        ],
        "revision": 1,
    }
