import json
import sys
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from vss_worker.adapters import DetectedNote
from vss_worker.command import run_command


class BasicPitchSubprocessTranscriber:
    device = "cpu"

    def transcribe(self, vocal_path: Path) -> list[DetectedNote]:
        output = vocal_path.parent / "note-events.json"
        run_command([sys.executable, "-m", "vss_worker.predict_cli", str(vocal_path), str(output)])
        return [DetectedNote(**note) for note in json.loads(output.read_text(encoding="utf-8"))]


class BasicPitchTranscriber:
    device = "cpu"

    def __init__(self) -> None:
        self._model: object | None = None
        self._model_lock = Lock()

    def _dependencies(
        self,
    ) -> tuple[
        Callable[[Path, object], tuple[object, object, list[tuple[Any, ...]]]],
        Callable[[Path], object],
        Path,
    ]:
        try:
            from basic_pitch import ICASSP_2022_MODEL_PATH  # type: ignore[import-not-found]
            from basic_pitch.inference import Model, predict  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("Install the 'models' extra to use Basic Pitch") from error
        return predict, Model, Path(ICASSP_2022_MODEL_PATH)

    def _loaded_model(self, factory: Callable[[Path], object], model_path: Path) -> object:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = factory(model_path)
        return self._model

    def transcribe(self, vocal_path: Path) -> list[DetectedNote]:
        predict, factory, model_path = self._dependencies()
        model = self._loaded_model(factory, model_path)
        _model_output, _midi, events = predict(vocal_path, model)
        return [self._convert(event) for event in events]

    @staticmethod
    def _convert(event: tuple[Any, ...]) -> DetectedNote:
        start, end, pitch, amplitude = event[:4]
        return DetectedNote(
            start_seconds=float(start),
            end_seconds=float(end),
            pitch_midi=int(pitch),
            confidence=float(amplitude),
        )
