import json
from pathlib import Path

from vss_worker.benchmark import evaluate_manifest


def test_manifest_evaluation_is_reproducible() -> None:
    root = Path(__file__).resolve().parents[3]
    report = evaluate_manifest(root / "evaluation" / "manifest.json")
    aggregate = report["aggregate"]["basic_pitch_raw_fixture"]
    assert aggregate["clip_count"] == 1
    assert aggregate["onset_pitch"]["f1_macro"] == 0.75
    assert report["dataset_status"] == "synthetic_scaffold_only"


def test_reads_quantized_beats_as_evaluated_seconds(tmp_path: Path) -> None:
    from vss_worker.benchmark import read_notes

    path = tmp_path / "quantized.json"
    path.write_text(
        json.dumps(
            {
                "bpm": 120,
                "notes": [
                    {
                        "quantized_start": 2,
                        "quantized_duration": 1,
                        "source_start_ms": 9000,
                        "source_end_ms": 9500,
                        "pitch_midi": 60,
                        "confidence": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    note = read_notes(path)[0]
    assert note.start_seconds == 1
    assert note.end_seconds == 1.5
