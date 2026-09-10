from app.renderers import render_jianpu_svg, render_staff_svg
from app.schemas import (
    Analysis,
    KeyPoint,
    MeterPoint,
    ScoreNote,
    ScoreProject,
    SourceAudio,
    TempoPoint,
)


def project_for_rendering() -> ScoreProject:
    notes = [
        ScoreNote(
            id="note-c4",
            source_start_ms=0,
            source_end_ms=500,
            source_note_ids=["source-c4"],
            pitch_midi=60,
            confidence=0.9,
            quantized_start=0,
            quantized_duration=1,
            origin="model",
        ),
        ScoreNote(
            id="note-e4",
            source_start_ms=750,
            source_end_ms=1500,
            source_note_ids=["source-e4"],
            pitch_midi=64,
            confidence=0.9,
            quantized_start=1.5,
            quantized_duration=1.5,
            origin="model",
        ),
    ]
    return ScoreProject(
        project_id="render-test",
        score_name="Render Test",
        source=SourceAudio(file_name="render.wav", duration_ms=2000, audio_object_key=""),
        analysis=Analysis(
            tempo_map=[TempoPoint(time_ms=0, bpm=120)],
            meter_map=[MeterPoint(beat=0, numerator=4, denominator=4)],
            key_map=[KeyPoint(beat=0, tonic=0, mode="major")],
            confidence={},
        ),
        notes=notes,
        pipeline=[],
        revision=1,
    )


def test_staff_svg_preserves_note_and_source_mappings() -> None:
    content = render_staff_svg(project_for_rendering()).decode()
    assert content.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert 'data-note-id="note-c4"' in content
    assert 'data-source-note-ids="source-e4"' in content
    assert 'aria-label="五线谱"' in content


def test_jianpu_svg_uses_stable_layout_and_local_font_fallbacks() -> None:
    content = render_jianpu_svg(project_for_rendering()).decode()
    assert 'aria-label="简谱"' in content
    assert 'data-note-id="note-c4"' in content
    assert 'data-note-id="note-e4"' in content
    assert "fonts.googleapis.com" not in content
    assert "font-size:32px" in content
    assert 'class="jp-rest-range" data-rest-start="1" data-rest-end="1.5"' in content


def test_jianpu_svg_draws_duration_marks_and_cross_measure_continuations() -> None:
    project = project_for_rendering()
    project.notes.extend(
        [
            ScoreNote(
                id="note-short",
                source_start_ms=1600,
                source_end_ms=1700,
                source_note_ids=["source-short"],
                pitch_midi=67,
                confidence=0.9,
                quantized_start=3,
                quantized_duration=0.25,
                origin="model",
            ),
            ScoreNote(
                id="note-dotted",
                source_start_ms=1700,
                source_end_ms=2000,
                source_note_ids=["source-dotted"],
                pitch_midi=69,
                confidence=0.9,
                quantized_start=3.25,
                quantized_duration=0.75,
                origin="model",
            ),
            ScoreNote(
                id="note-cross-measure",
                source_start_ms=1900,
                source_end_ms=3000,
                source_note_ids=["source-cross-measure"],
                pitch_midi=72,
                confidence=0.9,
                quantized_start=3.5,
                quantized_duration=1.5,
                origin="model",
            ),
        ]
    )

    content = render_jianpu_svg(project).decode()
    assert content.count('class="jp-underline"') >= 3
    assert 'class="jp-rhythm-dot"' in content
    assert 'data-note-id="note-cross-measure"' in content
    assert 'data-continuation="true"' in content


def test_jianpu_svg_offsets_notes_with_the_same_start() -> None:
    project = project_for_rendering()
    project.notes.append(
        ScoreNote(
            id="note-g4",
            source_start_ms=0,
            source_end_ms=500,
            source_note_ids=["source-g4"],
            pitch_midi=67,
            confidence=0.9,
            quantized_start=0,
            quantized_duration=1,
            origin="model",
        )
    )

    content = render_jianpu_svg(project).decode()
    assert '<text x="80.00" y="160.00"' in content
    assert '<text x="102.00" y="160.00"' in content
