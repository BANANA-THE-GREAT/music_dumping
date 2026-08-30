from collections.abc import Callable
from pathlib import Path
from typing import Any

from vss_worker.basic_pitch_adapter import BasicPitchTranscriber


def test_basic_pitch_model_is_loaded_once_and_reused(tmp_path: Path) -> None:
    loads = 0
    models: list[object] = []

    def factory(_path: Path) -> object:
        nonlocal loads
        loads += 1
        return object()

    def predict(_path: Path, model: object) -> tuple[object, object, list[tuple[Any, ...]]]:
        models.append(model)
        return {}, object(), [(0.0, 0.5, 60, 0.9)]

    class TestTranscriber(BasicPitchTranscriber):
        def _dependencies(
            self,
        ) -> tuple[
            Callable[[Path, object], tuple[object, object, list[tuple[Any, ...]]]],
            Callable[[Path], object],
            Path,
        ]:
            return predict, factory, tmp_path / "model"

    transcriber = TestTranscriber()
    first = transcriber.transcribe(tmp_path / "first.wav")
    second = transcriber.transcribe(tmp_path / "second.wav")
    assert loads == 1
    assert models[0] is models[1]
    assert first == second
    assert first[0].pitch_midi == 60
