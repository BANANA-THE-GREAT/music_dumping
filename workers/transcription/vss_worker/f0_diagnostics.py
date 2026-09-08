import bisect
import csv
import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

from vss_worker.adapters import DetectedNote
from vss_worker.benchmark import aggregate_evaluations, read_notes
from vss_worker.evaluation import TranscriptionEvaluation, evaluate_transcription


def read_reference_f0(path: Path) -> tuple[list[float], list[float]]:
    times = []
    frequencies = []
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.reader(source):
            times.append(float(row[0]))
            frequencies.append(float(row[1]))
    return times, frequencies


def read_f0_prediction(path: Path) -> dict[str, list[float]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "times_seconds": [float(value) for value in document["times_seconds"]],
        "f0_hz": [float(value) for value in document["f0_hz"]],
        "periodicity": [float(value) for value in document["periodicity"]],
    }


def _nearest(values: list[float], target: float) -> int:
    right = bisect.bisect_left(values, target)
    if right == 0:
        return 0
    if right == len(values):
        return len(values) - 1
    left = right - 1
    return left if target - values[left] <= values[right] - target else right


def _cents_error(actual_hz: float, expected_hz: float) -> float:
    return abs(1200 * math.log2(actual_hz / expected_hz))


def evaluate_f0_threshold(
    reference_times: list[float],
    reference_f0: list[float],
    prediction: dict[str, list[float]],
    threshold: float,
    pitch_tolerance_cents: float,
) -> dict[str, int]:
    counts = {
        "frames": 0,
        "reference_voiced": 0,
        "predicted_voiced": 0,
        "voiced_true_positive": 0,
        "pitch_true_positive": 0,
        "chroma_true_positive": 0,
    }
    for time_value, predicted_hz, periodicity in zip(
        prediction["times_seconds"],
        prediction["f0_hz"],
        prediction["periodicity"],
        strict=True,
    ):
        reference_hz = reference_f0[_nearest(reference_times, time_value)]
        expected_voiced = reference_hz > 0
        predicted_voiced = periodicity >= threshold
        counts["frames"] += 1
        counts["reference_voiced"] += expected_voiced
        counts["predicted_voiced"] += predicted_voiced
        counts["voiced_true_positive"] += expected_voiced and predicted_voiced
        if expected_voiced and predicted_voiced:
            error = _cents_error(predicted_hz, reference_hz)
            counts["pitch_true_positive"] += error <= pitch_tolerance_cents
            chroma_error = min(error % 1200, 1200 - (error % 1200))
            counts["chroma_true_positive"] += chroma_error <= pitch_tolerance_cents
    return counts


def estimate_global_delay(
    reference_times: list[float],
    reference_f0: list[float],
    prediction: dict[str, list[float]],
    *,
    maximum_delay_ms: float = 100,
    step_ms: float = 10,
    periodicity_threshold: float = 0.5,
) -> dict[str, float | int | None]:
    """Find one bounded delay; never stretches or locally warps the timeline."""
    if step_ms <= 0 or maximum_delay_ms < 0:
        raise ValueError("delay bounds must be non-negative and step must be positive")
    candidates = range(
        round(-maximum_delay_ms / step_ms), round(maximum_delay_ms / step_ms) + 1
    )
    best: tuple[float, float, int] | None = None
    for candidate in candidates:
        delay_ms = candidate * step_ms
        errors = []
        paired = 0
        for time_value, predicted_hz, periodicity in zip(
            prediction["times_seconds"],
            prediction["f0_hz"],
            prediction["periodicity"],
            strict=True,
        ):
            shifted_time = time_value + delay_ms / 1000
            if shifted_time < reference_times[0] or shifted_time > reference_times[-1]:
                continue
            reference_hz = reference_f0[_nearest(reference_times, shifted_time)]
            if (
                periodicity >= periodicity_threshold
                and predicted_hz > 0
                and reference_hz > 0
            ):
                errors.append(_cents_error(predicted_hz, reference_hz))
                paired += 1
        mean_error = sum(errors) / len(errors) if errors else math.inf
        score = (mean_error, abs(delay_ms), -paired)
        if best is None or score < (best[0], abs(best[1]), -best[2]):
            best = (mean_error, delay_ms, paired)
    if best is None or not math.isfinite(best[0]):
        return {"delay_ms": None, "mean_pitch_error_cents": None, "paired_voiced_frames": 0}
    return {
        "delay_ms": best[1],
        "mean_pitch_error_cents": best[0],
        "paired_voiced_frames": best[2],
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def summarize_f0_counts(counts: dict[str, int]) -> dict[str, float | int]:
    voiced_precision = _ratio(counts["voiced_true_positive"], counts["predicted_voiced"])
    voiced_recall = _ratio(counts["voiced_true_positive"], counts["reference_voiced"])
    voiced_f1 = (
        2 * voiced_precision * voiced_recall / (voiced_precision + voiced_recall)
        if voiced_precision + voiced_recall
        else 0.0
    )
    pitch_precision = _ratio(counts["pitch_true_positive"], counts["predicted_voiced"])
    pitch_recall = _ratio(counts["pitch_true_positive"], counts["reference_voiced"])
    pitch_f1 = (
        2 * pitch_precision * pitch_recall / (pitch_precision + pitch_recall)
        if pitch_precision + pitch_recall
        else 0.0
    )
    return {
        **counts,
        "voiced_precision": voiced_precision,
        "voiced_recall": voiced_recall,
        "voiced_f1": voiced_f1,
        "pitch_precision": pitch_precision,
        "pitch_recall": pitch_recall,
        "pitch_f1": pitch_f1,
        "raw_pitch_accuracy": _ratio(
            counts["pitch_true_positive"], counts["voiced_true_positive"]
        ),
        "raw_chroma_accuracy": _ratio(
            counts["chroma_true_positive"], counts["voiced_true_positive"]
        ),
    }


def _supported_runs(
    indices: list[int], maximum_gap_frames: int
) -> list[tuple[int, int]]:
    if not indices:
        return []
    runs = []
    start = previous = indices[0]
    for index in indices[1:]:
        if index - previous > maximum_gap_frames + 1:
            runs.append((start, previous))
            start = index
        previous = index
    runs.append((start, previous))
    return runs


def adjust_note_offsets(
    notes: list[DetectedNote],
    prediction: dict[str, list[float]],
    *,
    periodicity_threshold: float,
    pitch_tolerance_cents: float,
    maximum_gap_ms: float,
    maximum_contraction_ms: float,
    maximum_extension_ms: float,
    minimum_overlap_ms: float,
) -> list[DetectedNote]:
    times = prediction["times_seconds"]
    if len(times) < 2:
        return notes
    hop_seconds = times[1] - times[0]
    maximum_gap_frames = round(maximum_gap_ms / (hop_seconds * 1000))
    adjusted = []
    for note_index, note in enumerate(notes):
        next_onset = (
            notes[note_index + 1].start_seconds
            if note_index + 1 < len(notes)
            else math.inf
        )
        window_start = max(note.start_seconds, note.end_seconds - maximum_contraction_ms / 1000)
        window_end = min(next_onset, note.end_seconds + maximum_extension_ms / 1000)
        expected_hz = 440 * 2 ** ((note.pitch_midi - 69) / 12)
        supported = [
            index
            for index, (time_value, predicted_hz, periodicity) in enumerate(
                zip(
                    times,
                    prediction["f0_hz"],
                    prediction["periodicity"],
                    strict=True,
                )
            )
            if window_start <= time_value <= window_end
            and periodicity >= periodicity_threshold
            and _cents_error(predicted_hz, expected_hz) <= pitch_tolerance_cents
        ]
        runs = _supported_runs(supported, maximum_gap_frames)
        candidates = []
        for start_index, end_index in runs:
            run_start = times[start_index]
            run_end = times[end_index] + hop_seconds
            overlap = max(
                0.0, min(run_end, note.end_seconds) - max(run_start, note.start_seconds)
            )
            if overlap * 1000 >= minimum_overlap_ms and run_start < note.end_seconds:
                candidates.append((run_end, overlap))
        if not candidates:
            adjusted.append(note)
            continue
        run_end, _ = max(candidates, key=lambda item: (item[0], item[1]))
        new_end = min(max(run_end, note.start_seconds + hop_seconds), next_onset)
        adjusted.append(replace(note, end_seconds=new_end))
    return adjusted


def _evaluate_notes(
    reference: list[DetectedNote],
    notes: list[DetectedNote],
    tolerances: dict[str, float],
) -> TranscriptionEvaluation:
    return evaluate_transcription(
        reference,
        notes,
        pitch_tolerance_cents=tolerances["pitch_cents"],
        onset_tolerance_seconds=tolerances["onset_ms"] / 1000,
        offset_tolerance_seconds=tolerances["minimum_offset_ms"] / 1000,
        offset_tolerance_ratio=tolerances["offset_duration_ratio"],
    )


def _evaluate_adjusted_set(
    manifest_path: Path,
    clips: list[dict[str, Any]],
    reference_key: str,
    original_notes: dict[str, list[DetectedNote]],
    predictions: dict[str, dict[str, list[float]]],
    boundary: dict[str, float],
    tolerances: dict[str, float],
) -> dict[str, object]:
    original = []
    adjusted = []
    clip_results = []
    changed_notes = 0
    for clip in clips:
        reference = read_notes(manifest_path.parent / clip[reference_key])
        notes = original_notes[clip["id"]]
        revised = adjust_note_offsets(
            notes,
            predictions[clip["id"]],
            periodicity_threshold=boundary["periodicity_threshold"],
            pitch_tolerance_cents=boundary["pitch_tolerance_cents"],
            maximum_gap_ms=boundary["maximum_gap_ms"],
            maximum_contraction_ms=boundary["maximum_contraction_ms"],
            maximum_extension_ms=boundary["maximum_extension_ms"],
            minimum_overlap_ms=boundary["minimum_overlap_ms"],
        )
        changed_notes += sum(
            left.end_seconds != right.end_seconds
            for left, right in zip(notes, revised, strict=True)
        )
        original_result = _evaluate_notes(reference, notes, tolerances)
        adjusted_result = _evaluate_notes(reference, revised, tolerances)
        original.append(original_result)
        adjusted.append(adjusted_result)
        clip_results.append(
            {
                "id": clip["id"],
                "original": asdict(original_result),
                "adjusted": asdict(adjusted_result),
            }
        )
    return {
        "original": aggregate_evaluations(original),
        "adjusted": aggregate_evaluations(adjusted),
        "changed_notes": changed_notes,
        "clips": clip_results,
    }


def summarize_f0_diagnostics(
    manifest_path: Path,
    dataset_root: Path,
    f0_root: Path,
    note_root: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    split = config["split"]
    clips = [clip for clip in manifest["clips"] if clip["split"] == split]
    predictions = {
        clip["id"]: read_f0_prediction(f0_root / f"{clip['id']}.json") for clip in clips
    }
    threshold_results = {}
    for threshold in config["f0_evaluation"]["periodicity_thresholds"]:
        total: dict[str, int] = {}
        for clip in clips:
            reference_times, reference_f0 = read_reference_f0(
                dataset_root / "Annotations" / "F0" / f"{clip['id']}_f0.csv"
            )
            counts = evaluate_f0_threshold(
                reference_times,
                reference_f0,
                predictions[clip["id"]],
                threshold,
                config["f0_evaluation"]["pitch_tolerance_cents"],
            )
            for key, value in counts.items():
                total[key] = total.get(key, 0) + value
        threshold_results[str(threshold)] = summarize_f0_counts(total)
    selected_threshold = max(
        threshold_results,
        key=lambda value: (
            threshold_results[value]["pitch_f1"],
            threshold_results[value]["voiced_f1"],
        ),
    )

    tolerances = manifest["tolerances"]
    original_evaluations = []
    boundary_candidates: dict[str, dict[str, Any]] = {}
    references = {
        clip["id"]: read_notes(manifest_path.parent / clip["reference"]) for clip in clips
    }
    original_notes = {
        clip["id"]: read_notes(note_root / f"{clip['id']}.json") for clip in clips
    }

    for clip in clips:
        original_evaluations.append(
            _evaluate_notes(references[clip["id"]], original_notes[clip["id"]], tolerances)
        )
    original_metrics = aggregate_evaluations(original_evaluations)
    original_strict = cast(dict[str, float], original_metrics["onset_offset_pitch"])

    grid = config["boundary_grid"]
    for threshold in grid["periodicity_thresholds"]:
        for pitch_tolerance in grid["pitch_tolerances_cents"]:
            for maximum_gap_ms in grid["maximum_gap_ms"]:
                name = f"p{threshold:.2f}_c{pitch_tolerance}_g{maximum_gap_ms}"
                evaluations = []
                changed_notes = 0
                for clip in clips:
                    notes = original_notes[clip["id"]]
                    adjusted = adjust_note_offsets(
                        notes,
                        predictions[clip["id"]],
                        periodicity_threshold=threshold,
                        pitch_tolerance_cents=pitch_tolerance,
                        maximum_gap_ms=maximum_gap_ms,
                        maximum_contraction_ms=grid["maximum_contraction_ms"],
                        maximum_extension_ms=grid["maximum_extension_ms"],
                        minimum_overlap_ms=grid["minimum_overlap_ms"],
                    )
                    changed_notes += sum(
                        left.end_seconds != right.end_seconds
                        for left, right in zip(notes, adjusted, strict=True)
                    )
                    evaluations.append(
                        _evaluate_notes(references[clip["id"]], adjusted, tolerances)
                    )
                metrics = aggregate_evaluations(evaluations)
                strict = cast(dict[str, float], metrics["onset_offset_pitch"])
                boundary_candidates[name] = {
                    "parameters": {
                        "periodicity_threshold": threshold,
                        "pitch_tolerance_cents": pitch_tolerance,
                        "maximum_gap_ms": maximum_gap_ms,
                    },
                    "changed_notes": changed_notes,
                    "metrics": metrics,
                    "deltas_vs_original_game": {
                        key: strict[f"{key}_macro"] - original_strict[f"{key}_macro"]
                        for key in ("precision", "recall", "f1")
                    },
                }
    winner = max(
        boundary_candidates,
        key=lambda name: (
            boundary_candidates[name]["metrics"]["onset_offset_pitch"]["f1_macro"],
            boundary_candidates[name]["metrics"]["onset_offset_pitch"]["recall_macro"],
        ),
    )
    winner_delta = cast(
        dict[str, float], boundary_candidates[winner]["deltas_vs_original_game"]
    )
    passed = (
        winner_delta["f1"] >= config["selection"]["minimum_f1_improvement"]
        and winner_delta["precision"]
        >= -config["selection"]["maximum_precision_regression"]
    )
    winning_parameters = {
        **boundary_candidates[winner]["parameters"],
        "maximum_contraction_ms": grid["maximum_contraction_ms"],
        "maximum_extension_ms": grid["maximum_extension_ms"],
        "minimum_overlap_ms": grid["minimum_overlap_ms"],
    }
    alternate = _evaluate_adjusted_set(
        manifest_path,
        clips,
        "alternate_reference",
        original_notes,
        predictions,
        winning_parameters,
        tolerances,
    )
    return {
        "schema_version": "1.0",
        "split": split,
        "clip_count": len(clips),
        "f0_thresholds": threshold_results,
        "selected_f0_threshold": float(selected_threshold),
        "original_game_metrics": original_metrics,
        "boundary_candidates": boundary_candidates,
        "selection": {
            "winner": winner,
            "passed": passed,
            "policy": config["selection"],
        },
        "alternate_reference_check": alternate,
    }


def evaluate_fixed_f0_boundary(
    manifest_path: Path,
    f0_root: Path,
    note_root: Path,
    config: dict[str, Any],
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    split = config["split"]
    clips = [clip for clip in manifest["clips"] if clip["split"] == split]
    predictions = {
        clip["id"]: read_f0_prediction(f0_root / f"{clip['id']}.json") for clip in clips
    }
    original_notes = {
        clip["id"]: read_notes(note_root / f"{clip['id']}.json") for clip in clips
    }
    tolerances = manifest["tolerances"]
    boundary = config["selected_on_tuning"]["boundary_parameters"]
    primary = _evaluate_adjusted_set(
        manifest_path,
        clips,
        "reference",
        original_notes,
        predictions,
        boundary,
        tolerances,
    )
    alternate = _evaluate_adjusted_set(
        manifest_path,
        clips,
        "alternate_reference",
        original_notes,
        predictions,
        boundary,
        tolerances,
    )
    baseline_evaluations = []
    for clip in clips:
        reference = read_notes(manifest_path.parent / clip["reference"])
        baseline = read_notes(manifest_path.parent / clip["predictions"]["basic_pitch_raw"])
        baseline_evaluations.append(_evaluate_notes(reference, baseline, tolerances))
    baseline_metrics = aggregate_evaluations(baseline_evaluations)
    baseline_strict = cast(dict[str, float], baseline_metrics["onset_offset_pitch"])
    adjusted_metrics = cast(dict[str, Any], primary["adjusted"])
    adjusted_strict = cast(dict[str, float], adjusted_metrics["onset_offset_pitch"])
    deltas = {
        key: adjusted_strict[f"{key}_macro"] - baseline_strict[f"{key}_macro"]
        for key in ("precision", "recall", "f1")
    }
    gate = config["quality_gate"]
    checks = {
        "f1_improvement": deltas["f1"] >= gate["minimum_f1_improvement"],
        "recall_improvement": deltas["recall"] >= gate["minimum_recall_improvement"],
        "precision_regression": deltas["precision"] >= -gate["maximum_precision_regression"],
    }
    runtimes = {}
    if runtime_root is not None:
        for engine, variant in config["holdout_variants"].items():
            runtime = json.loads(
                (runtime_root / f"runtime-{variant}.json").read_text(encoding="utf-8")
            )
            clip_count = int(runtime.get("clip_count", len(runtime.get("clips", []))))
            failure_count = len(runtime.get("failures", []))
            failure_rate = failure_count / len(clips)
            runtimes[engine] = {
                "variant": variant,
                "clip_count": clip_count,
                "failure_count": failure_count,
                "failure_rate": failure_rate,
                "peak_rss_kib": runtime["peak_rss_kib"],
            }
            checks[f"{engine}_complete"] = clip_count == len(clips)
            checks[f"{engine}_failure_rate"] = (
                failure_rate <= gate["maximum_failure_rate"]
            )
    return {
        "schema_version": "1.0",
        "split": split,
        "clip_count": len(clips),
        "fixed_parameters": config["selected_on_tuning"],
        "baseline_metrics": baseline_metrics,
        "primary_reference": primary,
        "alternate_reference": alternate,
        "runtimes": runtimes,
        "deltas_vs_basic_pitch_raw": deltas,
        "quality_gate_checks": {**checks, "passed_all": all(checks.values())},
    }
