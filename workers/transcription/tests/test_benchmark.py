from pathlib import Path

from vss_worker.benchmark import evaluate_manifest


def test_manifest_evaluation_is_reproducible() -> None:
    root = Path(__file__).resolve().parents[3]
    report = evaluate_manifest(root / "evaluation" / "manifest.json")
    aggregate = report["aggregate"]["basic_pitch_raw_fixture"]
    assert aggregate["clip_count"] == 1
    assert aggregate["onset_pitch"]["f1_macro"] == 0.75
    assert report["dataset_status"] == "synthetic_scaffold_only"
