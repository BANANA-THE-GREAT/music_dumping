import json
from pathlib import Path
from xml.etree.ElementTree import fromstring

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
    assert "1 = C · 4/4 · ♩ = 120 · 简谱版" in content
    assert 'data-note-start="0" data-note-end="1"' in content
    assert 'data-segment-start="0" data-segment-end="1" data-measure="1"' in content
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
    root = fromstring(content)
    positions = {
        group.get("data-note-id"): float(group.get("data-layout-x", "0"))
        for group in root.iter("{http://www.w3.org/2000/svg}g")
        if group.get("data-note-id")
    }
    assert positions["note-g4"] - positions["note-c4"] >= 44


def test_complex_jianpu_fixture_maintains_minimum_event_spacing() -> None:
    fixture = Path(__file__).parents[3] / "evaluation/fixtures/rendering-score-project.json"
    project = ScoreProject.model_validate(json.loads(fixture.read_text()))
    root = fromstring(render_jianpu_svg(project))
    events_by_measure: dict[str, list[float]] = {}
    for measure in root.findall(".//{http://www.w3.org/2000/svg}g[@data-measure]"):
        positions = [
            float(group.get("data-layout-x", "0"))
            for group in measure.findall(".//{http://www.w3.org/2000/svg}g[@data-layout-x]")
        ]
        events_by_measure[measure.get("data-measure", "")] = sorted(set(positions))
    for positions in events_by_measure.values():
        assert all(
            right - left >= 28 for left, right in zip(positions, positions[1:], strict=False)
        )
