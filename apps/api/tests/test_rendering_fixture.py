import json
from pathlib import Path
from xml.etree.ElementTree import fromstring

from app.exporters import project_to_midi, project_to_musicxml
from app.renderers import render_jianpu_svg, render_staff_svg
from app.schemas import ScoreProject


def _fixture() -> ScoreProject:
    path = Path(__file__).parents[3] / "evaluation" / "fixtures" / "rendering-score-project.json"
    return ScoreProject.model_validate(json.loads(path.read_text()))


def test_rendering_fixture_covers_complex_score_features() -> None:
    project = _fixture()
    durations = {round(note.quantized_duration, 8) for note in project.notes}
    starts = [round(note.quantized_start, 8) for note in project.notes]
    assert {0.16666667, 0.25, 0.33333333, 0.5, 1.0, 1.5, 2.0} <= durations
    assert len(starts) != len(set(starts))
    assert any(
        int(note.quantized_start // 4)
        != int((note.quantized_start + note.quantized_duration - 1e-9) // 4)
        for note in project.notes
    )
    assert min(note.pitch_midi for note in project.notes) <= 48
    assert max(note.pitch_midi for note in project.notes) >= 72


def test_rendering_fixture_generates_all_semantic_sources() -> None:
    project = _fixture()
    midi = project_to_midi(project)
    musicxml = project_to_musicxml(project)
    staff_svg = render_staff_svg(project)
    jianpu_svg = render_jianpu_svg(project)

    assert midi.startswith(b"MThd")
    root = fromstring(musicxml.split(b"\n", 1)[1])
    assert len(root.findall(".//time-modification")) >= 5
    assert root.findall(".//chord")
    assert root.findall(".//notations/tied")
    assert b'data-note-id="cross-measure"' in staff_svg
    assert b'data-note-id="cross-measure"' in jianpu_svg
    assert b'data-continuation="true"' in jianpu_svg
    assert b'class="jp-rest-range"' in jianpu_svg
