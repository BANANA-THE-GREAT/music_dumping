from pathlib import Path
from typing import Any

from vss_worker.adapters import DetectedNote


class BasicPitchTranscriber:
    def transcribe(self, vocal_path: Path) -> list[DetectedNote]:
        try:
            from basic_pitch.inference import predict  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("Install the 'models' extra to use Basic Pitch") from error
        _model_output, _midi, events = predict(vocal_path)
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
