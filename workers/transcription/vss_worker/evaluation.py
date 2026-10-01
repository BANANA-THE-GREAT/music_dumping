from dataclasses import dataclass
from statistics import fmean

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


@dataclass(frozen=True)
class ErrorBreakdown:
    missed_notes: int
    extra_notes: int
    octave_errors: int
    possible_splits: int
    possible_merges: int
    weak_note_misses: int


@dataclass(frozen=True)
class TranscriptionEvaluation:
    onset_pitch: EvaluationResult
    onset_offset_pitch: EvaluationResult
    errors: ErrorBreakdown


def _pitch_cents(note: DetectedNote) -> float:
    return note.pitch_cents if note.pitch_cents is not None else note.pitch_midi * 100.0


def _match_notes(
    reference: list[DetectedNote],
    prediction: list[DetectedNote],
    *,
    pitch_tolerance_cents: float,
    onset_tolerance_seconds: float,
    offset_tolerance_seconds: float,
    offset_tolerance_ratio: float,
    require_offset: bool,
) -> tuple[EvaluationResult, set[int], set[int]]:
    unmatched_predictions = set(range(len(prediction)))
    unmatched_references = set(range(len(reference)))
    matches: list[tuple[DetectedNote, DetectedNote]] = []
    for reference_index, expected in enumerate(reference):
        offset_tolerance = max(
            offset_tolerance_seconds,
            (expected.end_seconds - expected.start_seconds) * offset_tolerance_ratio,
        )
        candidates = [
            index
            for index in unmatched_predictions
            if abs(_pitch_cents(prediction[index]) - _pitch_cents(expected))
            <= pitch_tolerance_cents
            and abs(prediction[index].start_seconds - expected.start_seconds)
            <= onset_tolerance_seconds
            and (
                not require_offset
                or abs(prediction[index].end_seconds - expected.end_seconds) <= offset_tolerance
            )
        ]
        if not candidates:
            continue
        best = min(
            candidates,
            key=lambda index: (
                abs(prediction[index].start_seconds - expected.start_seconds),
                abs(prediction[index].end_seconds - expected.end_seconds),
                abs(_pitch_cents(prediction[index]) - _pitch_cents(expected)),
            ),
        )
        unmatched_predictions.remove(best)
        unmatched_references.remove(reference_index)
        matches.append((expected, prediction[best]))

    true_positives = len(matches)
    precision = true_positives / len(prediction) if prediction else 0.0
    recall = true_positives / len(reference) if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    onset_errors = [
        abs(actual.start_seconds - expected.start_seconds) * 1000
        for expected, actual in matches
    ]
    offset_errors = [
        abs(actual.end_seconds - expected.end_seconds) * 1000 for expected, actual in matches
    ]
    return (
        EvaluationResult(
            true_positives=true_positives,
            false_positives=len(prediction) - true_positives,
            false_negatives=len(reference) - true_positives,
            precision=precision,
            recall=recall,
            f1=f1,
            mean_onset_error_ms=fmean(onset_errors) if onset_errors else None,
            mean_offset_error_ms=fmean(offset_errors) if offset_errors else None,
        ),
        unmatched_references,
        unmatched_predictions,
    )


def evaluate_notes(
    reference: list[DetectedNote],
    prediction: list[DetectedNote],
    *,
    onset_tolerance_seconds: float = 0.05,
    offset_tolerance_seconds: float = 0.1,
) -> EvaluationResult:
    result, _, _ = _match_notes(
        reference,
        prediction,
        pitch_tolerance_cents=0,
        onset_tolerance_seconds=onset_tolerance_seconds,
        offset_tolerance_seconds=offset_tolerance_seconds,
        offset_tolerance_ratio=0,
        require_offset=True,
    )
    return result


def evaluate_transcription(
    reference: list[DetectedNote],
    prediction: list[DetectedNote],
    *,
    pitch_tolerance_cents: float = 50,
    onset_tolerance_seconds: float = 0.05,
    offset_tolerance_seconds: float = 0.05,
    offset_tolerance_ratio: float = 0.2,
    weak_confidence_threshold: float = 0.5,
) -> TranscriptionEvaluation:
    onset_pitch, _, _ = _match_notes(
        reference,
        prediction,
        pitch_tolerance_cents=pitch_tolerance_cents,
        onset_tolerance_seconds=onset_tolerance_seconds,
        offset_tolerance_seconds=offset_tolerance_seconds,
        offset_tolerance_ratio=offset_tolerance_ratio,
        require_offset=False,
    )
    onset_offset_pitch, missed, extra = _match_notes(
        reference,
        prediction,
        pitch_tolerance_cents=pitch_tolerance_cents,
        onset_tolerance_seconds=onset_tolerance_seconds,
        offset_tolerance_seconds=offset_tolerance_seconds,
        offset_tolerance_ratio=offset_tolerance_ratio,
        require_offset=True,
    )
    octave_errors = sum(
        1
        for reference_index in missed
        if any(
            abs(
                prediction[prediction_index].start_seconds
                - reference[reference_index].start_seconds
            )
            <= onset_tolerance_seconds
            and abs(
                abs(
                    _pitch_cents(prediction[prediction_index])
                    - _pitch_cents(reference[reference_index])
                )
                - 1200
            )
            <= pitch_tolerance_cents
            for prediction_index in extra
        )
    )
    possible_splits = sum(
        1
        for expected in reference
        if sum(
            actual.pitch_midi == expected.pitch_midi
            and actual.start_seconds < expected.end_seconds
            and actual.end_seconds > expected.start_seconds
            for actual in prediction
        )
        > 1
    )
    possible_merges = sum(
        1
        for actual in prediction
        if sum(
            expected.pitch_midi == actual.pitch_midi
            and expected.start_seconds < actual.end_seconds
            and expected.end_seconds > actual.start_seconds
            for expected in reference
        )
        > 1
    )
    return TranscriptionEvaluation(
        onset_pitch=onset_pitch,
        onset_offset_pitch=onset_offset_pitch,
        errors=ErrorBreakdown(
            missed_notes=len(missed),
            extra_notes=len(extra),
            octave_errors=octave_errors,
            possible_splits=possible_splits,
            possible_merges=possible_merges,
            weak_note_misses=sum(
                reference[index].confidence < weak_confidence_threshold for index in missed
            ),
        ),
    )
