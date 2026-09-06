from vss_worker.adapters import DetectedNote as N
from vss_worker.melody import quantized_notes, refine_melody


def test_selects_confident_continuous_line_over_harmony() -> None:
    notes = [
        N(0, 0.5, 60, 0.9),
        N(0.5, 1, 62, 0.9),
        N(1, 1.5, 64, 0.9),
        N(0, 0.5, 79, 0.4),
        N(0.5, 1, 72, 0.4),
        N(1, 1.5, 81, 0.4),
    ]
    assert [n.pitch_midi for n in refine_melody(notes)] == [60, 62, 64]


def test_stitches_fragments_but_preserves_rearticulation_and_breaths() -> None:
    assert len(refine_melody([N(0, 0.3, 60, 0.8), N(0.34, 0.44, 60, 0.8)])) == 1
    assert len(refine_melody([N(0, 0.4, 60, 0.8), N(0.45, 0.85, 60, 0.8)])) == 2
    assert len(refine_melody([N(0, 0.1, 60, 0.8), N(0.5, 0.6, 60, 0.8)])) == 2


def test_raw_is_reversible_and_range_is_explicit() -> None:
    notes = [N(0, 1, 40, 0.8), N(0, 1, 72, 0.9)]
    assert refine_melody(notes, "raw") == notes
    assert [n.pitch_midi for n in refine_melody(notes)] == [72]
    assert refine_melody(notes, low=80) == []


def test_quantizes_endpoints_without_accumulating_duration_errors() -> None:
    notes = quantized_notes([N(0.07, 0.47, 60, 0.8), N(0.47, 0.9, 62, 0.8)], 120)
    assert (
        notes[0]["quantized_start"] + notes[0]["quantized_duration"] <= notes[1]["quantized_start"]
    )
