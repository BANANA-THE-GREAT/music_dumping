from pathlib import Path

import pytest
from vss_worker.demucs import DemucsSeparator
from vss_worker.ffmpeg import FfmpegNormalizer


def test_ffmpeg_normalization_command_and_output(tmp_path: Path) -> None:
    source = tmp_path / "song.mp3"
    destination = tmp_path / "work" / "normalized.wav"
    source.write_bytes(b"audio")

    def runner(arguments: list[str]) -> None:
        assert arguments[-1] == str(destination)
        assert arguments[arguments.index("-ar") + 1] == "44100"
        destination.write_bytes(b"wave")

    result = FfmpegNormalizer(runner=runner).normalize(source, destination)
    assert result == destination
    assert result.read_bytes() == b"wave"


def test_ffmpeg_requires_output_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="normalized audio"):
        FfmpegNormalizer(runner=lambda _arguments: None).normalize(
            tmp_path / "missing.mp3", tmp_path / "normalized.wav"
        )


def test_demucs_command_and_vocal_location(tmp_path: Path) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"wave")
    output = tmp_path / "stems"

    def runner(arguments: list[str]) -> None:
        assert "--two-stems" in arguments
        assert arguments[arguments.index("--device") + 1] == "cpu"
        vocal = output / "htdemucs" / "song" / "vocals.wav"
        vocal.parent.mkdir(parents=True)
        vocal.write_bytes(b"vocals")

    result = DemucsSeparator(runner=runner, device="cpu").separate(source, output)
    assert result.name == "vocals.wav"
    assert result.read_bytes() == b"vocals"
