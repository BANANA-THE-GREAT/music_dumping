import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.adapters import DetectedNote  # noqa: E402
from vss_worker.evaluation import evaluate_transcription  # noqa: E402


def read_notes(path: Path) -> list[DetectedNote]:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    notes = document["notes"]
    if notes and "source_start_ms" in notes[0]:
        return [
            DetectedNote(
                start_seconds=note["source_start_ms"] / 1000,
                end_seconds=note["source_end_ms"] / 1000,
                pitch_midi=note["pitch_midi"],
                confidence=note["confidence"],
            )
            for note in notes
        ]
    return [DetectedNote(**note) for note in notes]


parser = argparse.ArgumentParser(description="Evaluate note-level melody transcription")
parser.add_argument("reference", type=Path)
parser.add_argument("prediction", type=Path)
parser.add_argument("--onset-ms", type=float, default=50)
parser.add_argument("--offset-ms", type=float, default=50)
parser.add_argument("--offset-ratio", type=float, default=0.2)
parser.add_argument("--pitch-cents", type=float, default=50)
arguments = parser.parse_args()
result = evaluate_transcription(
    read_notes(arguments.reference),
    read_notes(arguments.prediction),
    pitch_tolerance_cents=arguments.pitch_cents,
    onset_tolerance_seconds=arguments.onset_ms / 1000,
    offset_tolerance_seconds=arguments.offset_ms / 1000,
    offset_tolerance_ratio=arguments.offset_ratio,
)
print(json.dumps(asdict(result), indent=2))
