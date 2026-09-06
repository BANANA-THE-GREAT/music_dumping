from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DetectedNote:
    start_seconds: float
    end_seconds: float
    pitch_midi: int
    confidence: float
    source_id: str | None = None
    pitch_cents: float | None = None


@dataclass(frozen=True)
class BeatGrid:
    beats_seconds: list[float]
    downbeats_seconds: list[float]
    bpm: float


Progress = Callable[[str, float], None]


class AudioNormalizer(Protocol):
    def normalize(self, source: Path, destination: Path) -> Path: ...


class VocalSeparator(Protocol):
    def separate(self, source: Path, output_dir: Path) -> Path: ...


class MelodyTranscriber(Protocol):
    def transcribe(self, vocal_path: Path) -> list[DetectedNote]: ...


class BeatTracker(Protocol):
    def track(self, source: Path) -> BeatGrid: ...
