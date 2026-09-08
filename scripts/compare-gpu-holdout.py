import argparse
import json
import math
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.benchmark import aggregate_evaluations, read_notes  # noqa: E402
from vss_worker.evaluation import evaluate_transcription  # noqa: E402
from vss_worker.f0_diagnostics import (  # noqa: E402
    evaluate_f0_threshold,
    read_f0_prediction,
    read_reference_f0,
    summarize_f0_counts,
)

MAX_GAME_F1_REGRESSION = 0.03
MAX_VOICING_DISAGREEMENT_RATE = 0.01
MAX_F0_PITCH_F1_REGRESSION = 0.005
DIRECT_PITCH_MAE_TARGET_CENTS = 5.0
F0_REFERENCE_PITCH_TOLERANCE_CENTS = 50.0
PERIODICITY_THRESHOLD = 0.4


def evaluate_game(
    manifest: dict[str, object],
    manifest_path: Path,
    predictions: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    tolerances = manifest["tolerances"]
    assert isinstance(tolerances, dict)
    evaluations = []
    clips = {}
    for clip in manifest["clips"]:
        assert isinstance(clip, dict)
        if clip["split"] != "holdout":
            continue
        clip_id = str(clip["id"])
        result = evaluate_transcription(
            read_notes(manifest_path.parent / str(clip["reference"])),
            read_notes(predictions / f"{clip_id}.json"),
            pitch_tolerance_cents=float(tolerances["pitch_cents"]),
            onset_tolerance_seconds=float(tolerances["onset_ms"]) / 1000,
            offset_tolerance_seconds=float(tolerances["minimum_offset_ms"]) / 1000,
            offset_tolerance_ratio=float(tolerances["offset_duration_ratio"]),
        )
        evaluations.append(result)
        clips[clip_id] = asdict(result)
    return aggregate_evaluations(evaluations), clips


def compare_f0(
    manifest: dict[str, object], cpu_predictions: Path, gpu_predictions: Path
) -> dict[str, object]:
    total_frames = 0
    frame_count_mismatches = 0
    voicing_disagreements = 0
    pitch_errors_cents = []
    signed_pitch_errors_cents = []
    clips = {}
    for clip in manifest["clips"]:
        assert isinstance(clip, dict)
        if clip["split"] != "holdout":
            continue
        clip_id = str(clip["id"])
        cpu = json.loads((cpu_predictions / f"{clip_id}.json").read_text())
        gpu = json.loads((gpu_predictions / f"{clip_id}.json").read_text())
        cpu_f0 = cpu["f0_hz"]
        gpu_f0 = gpu["f0_hz"]
        cpu_periodicity = cpu["periodicity"]
        gpu_periodicity = gpu["periodicity"]
        if len(cpu_f0) != len(gpu_f0):
            frame_count_mismatches += 1
        frame_count = min(len(cpu_f0), len(gpu_f0))
        clip_disagreements = 0
        clip_pitch_errors = []
        for index in range(frame_count):
            cpu_voiced = cpu_periodicity[index] >= PERIODICITY_THRESHOLD
            gpu_voiced = gpu_periodicity[index] >= PERIODICITY_THRESHOLD
            if cpu_voiced != gpu_voiced:
                clip_disagreements += 1
            if cpu_voiced and gpu_voiced and cpu_f0[index] > 0 and gpu_f0[index] > 0:
                error = abs(1200 * math.log2(gpu_f0[index] / cpu_f0[index]))
                if math.isfinite(error):
                    clip_pitch_errors.append(error)
                    signed_pitch_errors_cents.append(
                        1200 * math.log2(gpu_f0[index] / cpu_f0[index])
                    )
        total_frames += frame_count
        voicing_disagreements += clip_disagreements
        pitch_errors_cents.extend(clip_pitch_errors)
        clips[clip_id] = {
            "frame_count_cpu": len(cpu_f0),
            "frame_count_gpu": len(gpu_f0),
            "voicing_disagreements": clip_disagreements,
            "pitch_mae_cents": (
                sum(clip_pitch_errors) / len(clip_pitch_errors)
                if clip_pitch_errors
                else None
            ),
        }
    return {
        "total_frames": total_frames,
        "frame_count_mismatches": frame_count_mismatches,
        "voicing_disagreements": voicing_disagreements,
        "voicing_disagreement_rate": (
            voicing_disagreements / total_frames if total_frames else 0.0
        ),
        "pitch_mae_cents": (
            sum(pitch_errors_cents) / len(pitch_errors_cents)
            if pitch_errors_cents
            else None
        ),
        "pitch_median_absolute_error_cents": (
            statistics.median(pitch_errors_cents) if pitch_errors_cents else None
        ),
        "pitch_p95_absolute_error_cents": (
            percentile(pitch_errors_cents, 0.95) if pitch_errors_cents else None
        ),
        "pitch_max_absolute_error_cents": (
            max(pitch_errors_cents) if pitch_errors_cents else None
        ),
        "pitch_mean_signed_error_cents": (
            statistics.fmean(signed_pitch_errors_cents)
            if signed_pitch_errors_cents
            else None
        ),
        "pitch_within_50_cents_rate": (
            sum(error <= 50 for error in pitch_errors_cents) / len(pitch_errors_cents)
            if pitch_errors_cents
            else None
        ),
        "clips": clips,
    }


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def evaluate_f0_against_reference(
    manifest: dict[str, object],
    reference_root: Path,
    predictions: Path,
) -> dict[str, float | int]:
    total: dict[str, int] = {}
    for clip in manifest["clips"]:
        assert isinstance(clip, dict)
        if clip["split"] != "holdout":
            continue
        clip_id = str(clip["id"])
        reference_times, reference_f0 = read_reference_f0(
            reference_root / f"{clip_id}_f0.csv"
        )
        counts = evaluate_f0_threshold(
            reference_times,
            reference_f0,
            read_f0_prediction(predictions / f"{clip_id}.json"),
            PERIODICITY_THRESHOLD,
            F0_REFERENCE_PITCH_TOLERANCE_CENTS,
        )
        for key, value in counts.items():
            total[key] = total.get(key, 0) + value
    return summarize_f0_counts(total)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare CPU and GPU holdout outputs")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("cpu_game", type=Path)
    parser.add_argument("gpu_game", type=Path)
    parser.add_argument("cpu_f0", type=Path)
    parser.add_argument("gpu_f0", type=Path)
    parser.add_argument("reference_f0_root", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()

    manifest = json.loads(arguments.manifest.read_text())
    cpu_game, cpu_clips = evaluate_game(manifest, arguments.manifest, arguments.cpu_game)
    gpu_game, gpu_clips = evaluate_game(manifest, arguments.manifest, arguments.gpu_game)
    f0 = compare_f0(manifest, arguments.cpu_f0, arguments.gpu_f0)
    cpu_f0_reference = evaluate_f0_against_reference(
        manifest, arguments.reference_f0_root, arguments.cpu_f0
    )
    gpu_f0_reference = evaluate_f0_against_reference(
        manifest, arguments.reference_f0_root, arguments.gpu_f0
    )
    f0_reference_deltas = {
        key: float(gpu_f0_reference[key]) - float(cpu_f0_reference[key])
        for key in ("voiced_f1", "pitch_f1", "raw_pitch_accuracy")
    }
    cpu_onset = cpu_game["onset_pitch"]
    gpu_onset = gpu_game["onset_pitch"]
    cpu_strict = cpu_game["onset_offset_pitch"]
    gpu_strict = gpu_game["onset_offset_pitch"]
    assert isinstance(cpu_onset, dict) and isinstance(gpu_onset, dict)
    assert isinstance(cpu_strict, dict) and isinstance(gpu_strict, dict)
    deltas = {
        "onset_pitch_f1": float(gpu_onset["f1_macro"]) - float(cpu_onset["f1_macro"]),
        "onset_offset_pitch_f1": float(gpu_strict["f1_macro"])
        - float(cpu_strict["f1_macro"]),
    }
    checks = {
        "game_onset_pitch_f1": deltas["onset_pitch_f1"] >= -MAX_GAME_F1_REGRESSION,
        "game_onset_offset_pitch_f1": (
            deltas["onset_offset_pitch_f1"] >= -MAX_GAME_F1_REGRESSION
        ),
        "f0_frame_counts": f0["frame_count_mismatches"] == 0,
        "f0_voicing": (
            float(f0["voicing_disagreement_rate"]) <= MAX_VOICING_DISAGREEMENT_RATE
        ),
        "f0_reference_pitch_f1": (
            f0_reference_deltas["pitch_f1"] >= -MAX_F0_PITCH_F1_REGRESSION
        ),
        "f0_reference_raw_pitch_accuracy": (
            f0_reference_deltas["raw_pitch_accuracy"]
            >= -MAX_F0_PITCH_F1_REGRESSION
        ),
    }
    report = {
        "schema_version": "1.1",
        "date": "2026-09-08",
        "split": "holdout",
        "thresholds": {
            "maximum_game_f1_regression": MAX_GAME_F1_REGRESSION,
            "maximum_voicing_disagreement_rate": MAX_VOICING_DISAGREEMENT_RATE,
            "maximum_f0_reference_metric_regression": MAX_F0_PITCH_F1_REGRESSION,
            "f0_reference_pitch_tolerance_cents": F0_REFERENCE_PITCH_TOLERANCE_CENTS,
            "direct_pitch_mae_target_cents": DIRECT_PITCH_MAE_TARGET_CENTS,
        },
        "cpu_game": cpu_game,
        "gpu_game": gpu_game,
        "game_deltas": deltas,
        "f0_comparison": f0,
        "f0_reference": {
            "cpu": cpu_f0_reference,
            "gpu": gpu_f0_reference,
            "deltas": f0_reference_deltas,
        },
        "diagnostics": {
            "direct_pitch_mae_target_met": (
                f0["pitch_mae_cents"] is not None
                and float(f0["pitch_mae_cents"])
                <= DIRECT_PITCH_MAE_TARGET_CENTS
            ),
            "direct_pitch_comparison_is_quality_gate": False,
            "rationale": (
                "CPU output is not ground truth; CUDA numerical differences can alter "
                "torchcrepe's locally weighted pitch estimate without changing its "
                "accuracy against the Vocadito reference F0."
            ),
        },
        "clips": {"cpu_game": cpu_clips, "gpu_game": gpu_clips},
        "checks": checks,
        "passed": all(checks.values()),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "checks": checks}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
