import json
from pathlib import Path

from vss_worker.game_tuning import summarize_game_tuning


def _write_notes(path: Path, pitches: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    notes = [
        {
            "start_seconds": index,
            "end_seconds": index + 0.5,
            "pitch_midi": pitch,
            "confidence": 1,
        }
        for index, pitch in enumerate(pitches)
    ]
    path.write_text(json.dumps({"notes": notes}), encoding="utf-8")


def test_selects_highest_recall_candidate_after_constraints(tmp_path: Path) -> None:
    evaluation_root = tmp_path / "evaluation"
    result_root = tmp_path / "results"
    reference = tmp_path / "references" / "clip.json"
    _write_notes(reference, [60, 62])
    _write_notes(result_root / "conservative" / "clip.json", [60])
    _write_notes(result_root / "recall" / "clip.json", [60, 62])
    manifest = {
        "tolerances": {
            "pitch_cents": 50,
            "onset_ms": 50,
            "minimum_offset_ms": 50,
            "offset_duration_ratio": 0.2,
        },
        "clips": [
            {
                "id": "clip",
                "split": "tuning",
                "tags": [],
                "reference": str(reference),
            }
        ],
    }
    manifest_path = evaluation_root / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    for name in ("conservative", "recall"):
        (result_root / f"runtime-{name}.json").write_text(
            json.dumps(
                {
                    "parameters": {"presence_threshold": name},
                    "inference_seconds": 1,
                    "peak_rss_kib": 2,
                    "failures": [],
                }
            ),
            encoding="utf-8",
        )
    base_report = {
        "aggregate_by_split": {
            "tuning": {
                "basic_pitch_raw": {
                    "clip_count": 1,
                    "onset_pitch": {},
                    "onset_offset_pitch": {
                        "precision_macro": 0.5,
                        "recall_macro": 0.4,
                        "f1_macro": 0.44,
                    },
                    "errors": {},
                }
            }
        }
    }
    grid = {
        "split": "tuning",
        "selection": {
            "baseline_variant": "basic_pitch_raw",
            "minimum_f1_improvement": 0.03,
            "minimum_recall_improvement": 0.05,
            "maximum_precision_regression": 0.02,
            "maximum_failure_rate": 0.02,
        },
        "variants": [{"name": "conservative"}, {"name": "recall"}],
    }

    summary = summarize_game_tuning(
        base_report, manifest_path, result_root, result_root, grid
    )

    assert summary["selection"] == {
        "winner": "recall",
        "fallback_used": False,
        "passed_tuning_gate": True,
    }

    grid["selection"]["minimum_f1_improvement"] = 1
    fallback = summarize_game_tuning(
        base_report, manifest_path, result_root, result_root, grid
    )
    assert fallback["selection"] == {
        "winner": "recall",
        "fallback_used": True,
        "passed_tuning_gate": False,
    }
