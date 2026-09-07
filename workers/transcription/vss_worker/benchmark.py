import json
from dataclasses import asdict, fields
from pathlib import Path
from statistics import fmean
from typing import Any

from vss_worker.adapters import DetectedNote
from vss_worker.evaluation import TranscriptionEvaluation, evaluate_transcription


def read_notes(path: Path) -> list[DetectedNote]:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    notes = document["notes"]
    bpm = document.get("bpm")

    def timing(note: dict[str, Any]) -> tuple[float, float]:
        if bpm is not None and "quantized_start" in note:
            seconds_per_beat = 60 / float(bpm)
            start = float(note["quantized_start"]) * seconds_per_beat
            end = start + float(note["quantized_duration"]) * seconds_per_beat
            return start, end
        return (
            float(note.get("start_seconds", note.get("source_start_ms", 0) / 1000)),
            float(note.get("end_seconds", note.get("source_end_ms", 0) / 1000)),
        )

    return [
        DetectedNote(
            start_seconds=timing(note)[0],
            end_seconds=timing(note)[1],
            pitch_midi=note["pitch_midi"],
            confidence=note.get("confidence", 1.0),
            source_id=note.get("source_id"),
            pitch_cents=note.get("pitch_cents"),
        )
        for note in notes
    ]


def _mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return fmean(present) if present else None


def _aggregate(evaluations: list[TranscriptionEvaluation]) -> dict[str, object]:
    if not evaluations:
        return {"clip_count": 0}

    def metrics(name: str) -> dict[str, object]:
        results = [getattr(evaluation, name) for evaluation in evaluations]
        return {
            "precision_macro": fmean(result.precision for result in results),
            "recall_macro": fmean(result.recall for result in results),
            "f1_macro": fmean(result.f1 for result in results),
            "mean_onset_error_ms": _mean([result.mean_onset_error_ms for result in results]),
            "mean_offset_error_ms": _mean([result.mean_offset_error_ms for result in results]),
        }

    return {
        "clip_count": len(evaluations),
        "onset_pitch": metrics("onset_pitch"),
        "onset_offset_pitch": metrics("onset_offset_pitch"),
        "errors": {
            field: sum(getattr(evaluation.errors, field) for evaluation in evaluations)
            for field in (item.name for item in fields(evaluations[0].errors))
        },
    }


def evaluate_manifest(path: Path) -> dict[str, object]:
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    tolerances = manifest["tolerances"]
    reports: dict[str, list[TranscriptionEvaluation]] = {}
    reports_by_split: dict[str, dict[str, list[TranscriptionEvaluation]]] = {}
    clips: list[dict[str, object]] = []
    for clip in manifest["clips"]:
        reference = read_notes(path.parent / clip["reference"])
        clip_results: dict[str, object] = {}
        for variant, relative_path in clip["predictions"].items():
            result = evaluate_transcription(
                reference,
                read_notes(path.parent / relative_path),
                pitch_tolerance_cents=tolerances["pitch_cents"],
                onset_tolerance_seconds=tolerances["onset_ms"] / 1000,
                offset_tolerance_seconds=tolerances["minimum_offset_ms"] / 1000,
                offset_tolerance_ratio=tolerances["offset_duration_ratio"],
            )
            reports.setdefault(variant, []).append(result)
            reports_by_split.setdefault(clip["split"], {}).setdefault(variant, []).append(
                result
            )
            clip_results[variant] = asdict(result)
        clips.append(
            {
                "id": clip["id"],
                "split": clip["split"],
                "tags": clip["tags"],
                "results": clip_results,
            }
        )
    return {
        "schema_version": "1.0",
        "manifest": str(path),
        "dataset_status": manifest["dataset_status"],
        "tolerances": tolerances,
        "quality_gate": manifest["quality_gate"],
        "clips": clips,
        "aggregate": {variant: _aggregate(values) for variant, values in reports.items()},
        "aggregate_by_split": {
            split: {variant: _aggregate(values) for variant, values in variants.items()}
            for split, variants in sorted(reports_by_split.items())
        },
    }
