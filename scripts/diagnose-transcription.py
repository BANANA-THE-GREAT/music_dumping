import argparse
import json
import sys
from pathlib import Path
from typing import Any

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.adapters import DetectedNote  # noqa: E402
from vss_worker.melody import (  # noqa: E402
    QuantizationConfig,
    RefinementConfig,
    diagnostics_document,
)


def read_notes(path: Path) -> list[DetectedNote]:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return [DetectedNote(**note) for note in document["notes"]]


parser = argparse.ArgumentParser(description="Export raw, refined, and quantized diagnostics")
parser.add_argument("input", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--bpm", type=float, default=120)
parser.add_argument("--mode", choices=("raw", "conservative", "balanced"), default="balanced")
parser.add_argument("--low-pitch", type=int, default=48)
parser.add_argument("--high-pitch", type=int, default=84)
parser.add_argument("--minimum-duration-ms", type=float, default=60)
parser.add_argument("--minimum-confidence", type=float, default=0.2)
parser.add_argument("--disable-pitch-range", action="store_true")
parser.add_argument("--disable-continuity", action="store_true")
parser.add_argument("--disable-stitching", action="store_true")
parser.add_argument("--disable-quantization", action="store_true")
parser.add_argument("--keep-quantization-conflicts", action="store_true")
parser.add_argument("--grid", type=float, default=0.25)
arguments = parser.parse_args()

refinement = RefinementConfig(
    mode=arguments.mode,
    low_pitch=arguments.low_pitch,
    high_pitch=arguments.high_pitch,
    minimum_duration_seconds=arguments.minimum_duration_ms / 1000,
    minimum_confidence=arguments.minimum_confidence,
    apply_pitch_range=not arguments.disable_pitch_range,
    apply_continuity=not arguments.disable_continuity,
    stitch_short_fragments=not arguments.disable_stitching,
)
quantization = QuantizationConfig(
    grid=arguments.grid,
    monophonic=not arguments.disable_quantization,
    resolve_start_conflicts=not arguments.keep_quantization_conflicts,
)
document = diagnostics_document(
    read_notes(arguments.input), arguments.bpm, refinement, quantization
)
if arguments.disable_quantization:
    document["quantized_notes"] = []
arguments.output.parent.mkdir(parents=True, exist_ok=True)
arguments.output.write_text(json.dumps(document, indent=2), encoding="utf-8")
