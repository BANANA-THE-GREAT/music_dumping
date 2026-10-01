import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from vss_worker.benchmark import aggregate_evaluations, read_notes
from vss_worker.evaluation import TranscriptionEvaluation, evaluate_transcription


def _evaluate_variant(
    manifest_path: Path,
    result_root: Path,
    variant: str,
    split: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    tolerances = manifest["tolerances"]
    evaluations: list[TranscriptionEvaluation] = []
    clips = []
    for clip in manifest["clips"]:
        if clip["split"] != split:
            continue
        reference = read_notes(manifest_path.parent / clip["reference"])
        prediction = read_notes(result_root / variant / f"{clip['id']}.json")
        result = evaluate_transcription(
            reference,
            prediction,
            pitch_tolerance_cents=tolerances["pitch_cents"],
            onset_tolerance_seconds=tolerances["onset_ms"] / 1000,
            offset_tolerance_seconds=tolerances["minimum_offset_ms"] / 1000,
            offset_tolerance_ratio=tolerances["offset_duration_ratio"],
        )
        evaluations.append(result)
        clips.append({"id": clip["id"], "tags": clip["tags"], "result": asdict(result)})
    return aggregate_evaluations(evaluations), clips


def summarize_game_tuning(
    base_report: dict[str, Any],
    manifest_path: Path,
    result_root: Path,
    runtime_root: Path,
    grid: dict[str, Any],
) -> dict[str, Any]:
    split = grid["split"]
    baseline_variant = grid["selection"]["baseline_variant"]
    baseline = base_report["aggregate_by_split"][split][baseline_variant]
    baseline_metric = baseline["onset_offset_pitch"]
    expected_clips = sum(
        clip["split"] == split
        for clip in json.loads(manifest_path.read_text(encoding="utf-8"))["clips"]
    )
    candidates = {}
    for definition in grid["variants"]:
        variant = definition["name"]
        metrics, clips = _evaluate_variant(manifest_path, result_root, variant, split)
        runtime = json.loads(
            (runtime_root / f"runtime-{variant}.json").read_text(encoding="utf-8")
        )
        metric = cast(dict[str, float], metrics["onset_offset_pitch"])
        deltas = {
            "precision": metric["precision_macro"] - baseline_metric["precision_macro"],
            "recall": metric["recall_macro"] - baseline_metric["recall_macro"],
            "f1": metric["f1_macro"] - baseline_metric["f1_macro"],
        }
        failure_count = len(runtime.get("failures", []))
        checks = {
            "complete": metrics["clip_count"] == expected_clips,
            "f1_improvement": (
                deltas["f1"] >= grid["selection"]["minimum_f1_improvement"]
            ),
            "recall_improvement": (
                deltas["recall"] >= grid["selection"]["minimum_recall_improvement"]
            ),
            "precision_regression": (
                deltas["precision"]
                >= -grid["selection"]["maximum_precision_regression"]
            ),
            "failure_rate": (
                failure_count / expected_clips
                <= grid["selection"]["maximum_failure_rate"]
            ),
        }
        candidates[variant] = {
            "parameters": runtime["parameters"],
            "metrics": metrics,
            "deltas_vs_baseline": deltas,
            "checks": {**checks, "passed_all": all(checks.values())},
            "runtime": {
                "inference_seconds": runtime["inference_seconds"],
                "peak_rss_kib": runtime["peak_rss_kib"],
                "failure_count": failure_count,
            },
            "clips": clips,
        }

    eligible = [
        name
        for name, candidate in candidates.items()
        if candidate["checks"]["complete"]
        and candidate["checks"]["precision_regression"]
        and candidate["checks"]["failure_rate"]
        and candidate["checks"]["f1_improvement"]
    ]
    fallback_used = not eligible
    if fallback_used:
        eligible = [
            name
            for name, candidate in candidates.items()
            if candidate["checks"]["complete"]
            and candidate["checks"]["precision_regression"]
            and candidate["checks"]["failure_rate"]
        ]
    winner = max(
        eligible,
        key=lambda name: (
            candidates[name]["metrics"]["onset_offset_pitch"]["recall_macro"],
            candidates[name]["metrics"]["onset_offset_pitch"]["f1_macro"],
        ),
    )
    return {
        "schema_version": "1.0",
        "split": split,
        "baseline_variant": baseline_variant,
        "baseline_metrics": baseline,
        "selection_policy": grid["selection"],
        "candidates": candidates,
        "selection": {
            "winner": winner,
            "fallback_used": fallback_used,
            "passed_tuning_gate": candidates[winner]["checks"]["passed_all"],
        },
    }
