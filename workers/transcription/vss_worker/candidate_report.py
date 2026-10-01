import statistics
from typing import Any


def _runtime_summary(runtime: dict[str, Any], expected_clips: int) -> dict[str, Any]:
    failures = runtime.get("failures", [])
    if "clips" in runtime:
        elapsed = [float(clip["elapsed_seconds"]) for clip in runtime["clips"]]
        inference_seconds = sum(elapsed)
        median_clip_seconds = statistics.median(elapsed) if elapsed else None
        clip_count = len(elapsed)
    else:
        inference_seconds = float(runtime["inference_seconds"])
        clip_count = int(runtime["clip_count"])
        median_clip_seconds = None
    return {
        "upstream_commit": runtime["upstream_commit"],
        "model_sha256": runtime["model_sha256"],
        "device": runtime["device"],
        "seed": runtime["seed"],
        "model_load_seconds": runtime["model_load_seconds"],
        "inference_seconds": inference_seconds,
        "seconds_per_clip": inference_seconds / clip_count if clip_count else None,
        "median_clip_seconds": median_clip_seconds,
        "peak_rss_kib": runtime["peak_rss_kib"],
        "clip_count": clip_count,
        "failure_count": len(failures),
        "failure_rate": len(failures) / expected_clips,
    }


def summarize_candidates(
    report: dict[str, Any], runtimes: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    split = "holdout"
    baseline_variant = "basic_pitch_raw"
    aggregate = report["aggregate_by_split"][split]
    baseline = aggregate[baseline_variant]["onset_offset_pitch"]
    gate = report["quality_gate"]
    expected_clips = len(report["clips"])
    candidates = {}
    for variant, runtime in runtimes.items():
        metric = aggregate[variant]
        onset = metric["onset_pitch"]
        onset_offset = metric["onset_offset_pitch"]
        resources = _runtime_summary(runtime, expected_clips)
        deltas = {
            "onset_f1": onset["f1_macro"] - aggregate[baseline_variant]["onset_pitch"]["f1_macro"],
            "onset_offset_precision": onset_offset["precision_macro"] - baseline["precision_macro"],
            "onset_offset_recall": onset_offset["recall_macro"] - baseline["recall_macro"],
            "onset_offset_f1": onset_offset["f1_macro"] - baseline["f1_macro"],
        }
        checks = {
            "onset_offset_f1_improvement": (
                deltas["onset_offset_f1"] >= gate["candidate_onset_offset_f1_improvement"]
            ),
            "recall_improvement": (
                deltas["onset_offset_recall"] >= gate["candidate_recall_improvement"]
            ),
            "precision_regression": (
                deltas["onset_offset_precision"] >= -gate["maximum_precision_regression"]
            ),
            "failure_rate": resources["failure_rate"] <= gate["maximum_failure_rate"],
        }
        candidates[variant] = {
            "metrics": {
                "onset_f1": onset["f1_macro"],
                "onset_offset_precision": onset_offset["precision_macro"],
                "onset_offset_recall": onset_offset["recall_macro"],
                "onset_offset_f1": onset_offset["f1_macro"],
            },
            "deltas_vs_basic_pitch_raw": deltas,
            "resources": resources,
            "quality_gate_checks": {**checks, "passed_all": all(checks.values())},
        }
    best = max(candidates, key=lambda name: candidates[name]["metrics"]["onset_offset_f1"])
    return {
        "schema_version": "1.0",
        "split": split,
        "baseline_variant": baseline_variant,
        "quality_gate": gate,
        "baseline_metrics": aggregate[baseline_variant],
        "candidates": candidates,
        "recommendation": {
            "default_engine": "basic_pitch",
            "best_experimental_candidate": best,
            "reason": "No candidate passed every preregistered quality gate check.",
        },
    }
