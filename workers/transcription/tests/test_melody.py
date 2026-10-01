from vss_worker.adapters import DetectedNote as N
from vss_worker.melody import (
    QuantizationConfig,
    RefinementConfig,
    diagnostics_document,
    quantize_with_diagnostics,
    quantized_notes,
    refine_melody,
    refine_melody_with_diagnostics,
)


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


def test_refinement_diagnostics_explain_each_filter() -> None:
    result = refine_melody_with_diagnostics(
        [
            N(0, 0.03, 60, 0.9, "short"),
            N(0, 0.5, 90, 0.9, "range"),
            N(0, 0.5, 64, 0.1, "quiet"),
            N(0, 0.5, 67, 0.9, "kept"),
        ],
        RefinementConfig(apply_continuity=False),
    )
    assert [note.source_id for note in result.notes] == ["kept"]
    assert {(decision.source_ids[0], decision.reason) for decision in result.decisions} == {
        ("short", "shorter_than_minimum_duration"),
        ("range", "outside_pitch_range"),
        ("quiet", "below_minimum_confidence"),
        ("kept", "continuity_disabled"),
    }


def test_quantization_conflicts_can_be_kept_for_ablation() -> None:
    notes = [N(0.01, 0.2, 60, 0.7, "left"), N(0.02, 0.3, 64, 0.9, "right")]
    resolved = quantize_with_diagnostics(notes, 120)
    assert [note["source_note_ids"] for note in resolved.notes] == [["right"]]
    assert resolved.decisions[0].source_ids == ("left",)
    retained = quantize_with_diagnostics(
        notes, 120, QuantizationConfig(resolve_start_conflicts=False)
    )
    assert len(retained.notes) == 2


def test_diagnostics_document_keeps_all_pipeline_stages() -> None:
    document = diagnostics_document([N(0, 0.5, 60, 0.9)], 120)
    assert len(document["raw_notes"]) == 1
    assert len(document["refined_notes"]) == 1
    assert len(document["quantized_notes"]) == 1
    assert document["quantized_notes"][0]["source_note_ids"] == ["raw-000000"]
