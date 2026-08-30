from dataclasses import dataclass

from vss_worker.adapters import DetectedNote


@dataclass(frozen=True)
class EvaluationResult:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    mean_onset_error_ms: float | None
    mean_offset_error_ms: float | None


def evaluate_notes(
    reference: list[DetectedNote],
    prediction: list[DetectedNote],
    *,
    onset_tolerance_seconds: float = 0.05,
    offset_tolerance_seconds: float = 0.1,
) -> EvaluationResult:
    unmatched = set(range(len(prediction)))
    matches: list[tuple[DetectedNote, DetectedNote]] = []
    for expected in reference:
        candidates = [
            index
            for index in unmatched
            if prediction[index].pitch_midi == expected.pitch_midi
            and abs(prediction[index].start_seconds - expected.start_seconds)
            <= onset_tolerance_seconds
            and abs(prediction[index].end_seconds - expected.end_seconds)
            <= offset_tolerance_seconds
        ]
        if not candidates:
            continue
        best = min(
            candidates,
            key=lambda index: abs(prediction[index].start_seconds - expected.start_seconds),
        )
        unmatched.remove(best)
        matches.append((expected, prediction[best]))

    true_positives = len(matches)
    false_positives = len(prediction) - true_positives
    false_negatives = len(reference) - true_positives
    precision = true_positives / len(prediction) if prediction else 0.0
    recall = true_positives / len(reference) if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    onset_errors = [
        abs(actual.start_seconds - expected.start_seconds) * 1000 for expected, actual in matches
    ]
    offset_errors = [
        abs(actual.end_seconds - expected.end_seconds) * 1000 for expected, actual in matches
    ]
    return EvaluationResult(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        mean_onset_error_ms=sum(onset_errors) / len(onset_errors) if onset_errors else None,
        mean_offset_error_ms=sum(offset_errors) / len(offset_errors) if offset_errors else None,
    )
