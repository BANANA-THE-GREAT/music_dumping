import pytest
from vss_worker.adapters import DetectedNote
from vss_worker.evaluation import evaluate_notes


def test_note_metrics_use_one_to_one_pitch_and_timing_matches() -> None:
    reference = [
        DetectedNote(0, 0.5, 60, 1),
        DetectedNote(0.5, 1, 62, 1),
        DetectedNote(1, 1.5, 64, 1),
    ]
    prediction = [
        DetectedNote(0.02, 0.52, 60, 0.9),
        DetectedNote(0.49, 1.04, 62, 0.8),
        DetectedNote(1, 1.5, 65, 0.9),
        DetectedNote(2, 2.5, 67, 0.7),
    ]
    result = evaluate_notes(reference, prediction)
    assert result.true_positives == 2
    assert result.false_positives == 2
    assert result.false_negatives == 1
    assert result.precision == 0.5
    assert result.recall == 2 / 3
    assert result.f1 == pytest.approx(4 / 7)
    assert result.mean_onset_error_ms == pytest.approx(15)


def test_empty_prediction_has_zero_metrics() -> None:
    result = evaluate_notes([DetectedNote(0, 1, 60, 1)], [])
    assert result.precision == result.recall == result.f1 == 0
    assert result.mean_onset_error_ms is None
