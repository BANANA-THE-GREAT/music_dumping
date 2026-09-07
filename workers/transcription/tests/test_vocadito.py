import csv
import json
import wave
from pathlib import Path

from vss_worker.vocadito import hz_to_midi, prepare_vocadito, read_note_annotation


def write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000)


def test_converts_hz_annotations_to_continuous_midi(tmp_path: Path) -> None:
    annotation = tmp_path / "notes.csv"
    annotation.write_text("0.1,440,0.5\n", encoding="utf-8")
    notes = read_note_annotation(annotation, "clip-a1")
    assert hz_to_midi(440) == 69
    assert notes[0].pitch_midi == 69
    assert notes[0].pitch_cents == 6900
    assert notes[0].end_seconds == 0.6


def test_prepares_singer_disjoint_manifest(tmp_path: Path) -> None:
    dataset = tmp_path / "vocadito"
    notes_dir = dataset / "Annotations" / "Notes"
    notes_dir.mkdir(parents=True)
    with (dataset / "vocadito_metadata.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("track_id", "singer_id", "average_pitch", "language"))
        for track_id in range(1, 41):
            singer = "S1" if track_id in {1, 3, 8} else f"S{track_id + 30}"
            writer.writerow((track_id, singer, 60, "test"))
            write_wav(dataset / "Audio" / f"vocadito_{track_id}.wav")
            for annotator in ("A1", "A2"):
                (notes_dir / f"vocadito_{track_id}_notes{annotator}.csv").write_text(
                    "0,440,0.5\n", encoding="utf-8"
                )
    output = tmp_path / "prepared"
    manifest_path = tmp_path / "evaluation" / "manifest.json"
    manifest = prepare_vocadito(dataset, output, manifest_path)
    assert len(manifest["clips"]) == 40
    assert manifest["dataset"]["doi"] == "10.5281/zenodo.5578807"
    assert manifest["dataset"]["authors"][0] == "Rachel Bittner"
    assert {clip["split"] for clip in manifest["clips"] if "singer:S1" in clip["tags"]} == {
        "holdout"
    }
    agreement = json.loads((output / "annotation-agreement.json").read_text())
    assert agreement["clips"][0]["metrics"]["onset_offset_pitch"]["f1"] == 1
    assert agreement["clips"][0]["uncertain_regions"] == []
