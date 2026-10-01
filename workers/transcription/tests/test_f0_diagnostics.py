import json
from pathlib import Path

from vss_worker.adapters import DetectedNote
from vss_worker.f0_diagnostics import (
    adjust_note_offsets,
    estimate_global_delay,
    evaluate_f0_threshold,
    evaluate_fixed_f0_boundary,
    summarize_f0_counts,
)


def test_global_delay_is_bounded_without_time_warp() -> None:
    result = estimate_global_delay(
        [0, 0.01, 0.02, 0.03],
        [440, 440, 440, 0],
        {
            "times_seconds": [0, 0.01, 0.02, 0.03],
            "f0_hz": [440, 440, 440, 0],
            "periodicity": [0.9, 0.9, 0.9, 0.1],
        },
        maximum_delay_ms=30,
        step_ms=10,
    )
    assert result["delay_ms"] == 0
    assert result["paired_voiced_frames"] == 3


def test_f0_metrics_separate_voicing_and_pitch_accuracy() -> None:
    counts = evaluate_f0_threshold(
        [0, 0.01, 0.02],
        [440, 440, 0],
        {
            "times_seconds": [0, 0.01, 0.02],
            "f0_hz": [440, 880, 440],
            "periodicity": [0.9, 0.9, 0.9],
        },
        threshold=0.5,
        pitch_tolerance_cents=50,
    )
    metrics = summarize_f0_counts(counts)
    assert metrics["voiced_recall"] == 1
    assert metrics["voiced_precision"] == 2 / 3
    assert metrics["raw_pitch_accuracy"] == 0.5
    assert metrics["raw_chroma_accuracy"] == 1


def test_adjusts_only_note_offset_from_supported_f0_run() -> None:
    times = [index / 100 for index in range(101)]
    adjusted = adjust_note_offsets(
        [DetectedNote(0, 0.5, 69, 1)],
        {
            "times_seconds": times,
            "f0_hz": [440 for _ in times],
            "periodicity": [0.9 if time <= 0.6 else 0 for time in times],
        },
        periodicity_threshold=0.5,
        pitch_tolerance_cents=50,
        maximum_gap_ms=20,
        maximum_contraction_ms=400,
        maximum_extension_ms=400,
        minimum_overlap_ms=30,
    )
    assert adjusted[0].start_seconds == 0
    assert adjusted[0].pitch_midi == 69
    assert adjusted[0].end_seconds == 0.61


def test_fixed_holdout_checks_quality_and_runtime(tmp_path: Path) -> None:
    def write_notes(path: Path, end_seconds: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "notes": [
                        {
                            "start_seconds": 0,
                            "end_seconds": end_seconds,
                            "pitch_midi": 69,
                            "confidence": 1,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    reference = tmp_path / "reference.json"
    alternate = tmp_path / "alternate.json"
    baseline = tmp_path / "baseline.json"
    notes = tmp_path / "notes"
    f0 = tmp_path / "f0"
    runtime = tmp_path / "runtime"
    write_notes(reference, 0.5)
    write_notes(alternate, 0.5)
    write_notes(baseline, 0.2)
    write_notes(notes / "clip.json", 0.2)
    f0.mkdir()
    times = [index / 100 for index in range(61)]
    (f0 / "clip.json").write_text(
        json.dumps(
            {
                "times_seconds": times,
                "f0_hz": [440 for _ in times],
                "periodicity": [0.9 if value < 0.5 else 0 for value in times],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tolerances": {
                    "pitch_cents": 50,
                    "onset_ms": 50,
                    "minimum_offset_ms": 50,
                    "offset_duration_ratio": 0.2,
                },
                "clips": [
                    {
                        "id": "clip",
                        "split": "holdout",
                        "reference": str(reference),
                        "alternate_reference": str(alternate),
                        "predictions": {"basic_pitch_raw": str(baseline)},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runtime.mkdir()
    for variant in ("game-fixed", "f0-fixed"):
        (runtime / f"runtime-{variant}.json").write_text(
            json.dumps(
                {
                    "clip_count": 1,
                    "failures": [],
                    "peak_rss_kib": 10,
                }
            ),
            encoding="utf-8",
        )
    config = {
        "split": "holdout",
        "selected_on_tuning": {
            "boundary_parameters": {
                "periodicity_threshold": 0.4,
                "pitch_tolerance_cents": 100,
                "maximum_gap_ms": 20,
                "maximum_contraction_ms": 400,
                "maximum_extension_ms": 400,
                "minimum_overlap_ms": 30,
            }
        },
        "holdout_variants": {"game": "game-fixed", "f0": "f0-fixed"},
        "quality_gate": {
            "minimum_f1_improvement": 0.03,
            "minimum_recall_improvement": 0.05,
            "maximum_precision_regression": 0.02,
            "maximum_failure_rate": 0.02,
        },
    }

    result = evaluate_fixed_f0_boundary(manifest, f0, notes, config, runtime)

    assert result["quality_gate_checks"]["passed_all"] is True
    assert result["primary_reference"]["adjusted"]["onset_offset_pitch"]["f1_macro"] == 1
    assert result["runtimes"]["game"]["failure_count"] == 0
