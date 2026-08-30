from pathlib import Path

from vss_worker.adapters import DetectedNote
from vss_worker.pipeline import build_real_project, estimate_meter


class FakeNormalizer:
    def normalize(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True)
        destination.write_bytes(source.read_bytes())
        return destination


class FakeSeparator:
    def separate(self, source: Path, output_dir: Path) -> Path:
        vocal = output_dir / "vocals.wav"
        vocal.parent.mkdir(parents=True)
        vocal.write_bytes(source.read_bytes())
        return vocal


class FakeTranscriber:
    def transcribe(self, vocal_path: Path) -> list[DetectedNote]:
        assert vocal_path.exists()
        return [
            DetectedNote(0, 0.45, 60, 0.9),
            DetectedNote(0.5, 0.95, 64, 0.8),
            DetectedNote(1, 1.9, 67, 0.95),
        ]


def test_real_pipeline_composes_adapters_and_quantizes(tmp_path: Path) -> None:
    source = tmp_path / "source.mp3"
    source.write_bytes(b"audio")
    stages: list[str] = []
    document = build_real_project(
        upload_id="upload-1",
        file_name="song.mp3",
        object_key="uploads/upload-1/source.mp3",
        source_path=source,
        work_dir=tmp_path / "work",
        normalizer=FakeNormalizer(),
        separator=FakeSeparator(),
        transcriber=FakeTranscriber(),
        progress=lambda stage, _value: stages.append(stage),
    )
    assert document["analysis"]["tempo_map"][0]["bpm"] == 120
    assert [note["pitch_midi"] for note in document["notes"]] == [60, 64, 67]
    assert document["notes"][2]["quantized_duration"] == 1.75
    assert stages == [
        "preprocessing",
        "separating",
        "transcribing",
        "tracking_beats",
        "postprocessing",
        "rendering",
    ]


def test_meter_estimator_detects_three_four_accent_cycle() -> None:
    notes = [
        DetectedNote(
            index * 0.5, index * 0.5 + 0.4, 60 + index % 5, 0.95 if index % 3 == 0 else 0.3
        )
        for index in range(12)
    ]
    assert estimate_meter(notes)[:2] == (3, 4)


def test_meter_estimator_detects_six_eight_and_falls_back_when_unclear() -> None:
    six_eight = [
        DetectedNote(index * 0.25, index * 0.25 + 0.2, 60, 0.95 if index % 6 == 0 else 0.25)
        for index in range(18)
    ]
    assert estimate_meter(six_eight)[:2] == (6, 8)
    uniform = [DetectedNote(index * 0.5, index * 0.5 + 0.4, 60, 0.8) for index in range(8)]
    assert estimate_meter(uniform)[:2] == (4, 4)
