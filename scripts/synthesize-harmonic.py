#!/usr/bin/env python3
"""Render a deterministic harmonic WAV from a torchcrepe F0 JSONL track."""

import argparse
import json
from pathlib import Path

from vss_worker.harmonic_synth import read_f0_jsonl, synthesize_harmonic, write_wav


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("input", type=Path, help="F0 JSONL with time_seconds, f0_hz, periodicity")
parser.add_argument("output", type=Path, help="output mono PCM16 WAV")
parser.add_argument("--report", type=Path, help="optional JSON report path")
parser.add_argument("--sample-rate", type=int, default=16_000)
parser.add_argument("--periodicity-threshold", type=float, default=0.5)
parser.add_argument("--harmonics", type=int, default=8)
parser.add_argument("--amplitude", type=float, default=0.35)
arguments = parser.parse_args()

frames = read_f0_jsonl(arguments.input)
pcm, report = synthesize_harmonic(
    frames,
    sample_rate=arguments.sample_rate,
    periodicity_threshold=arguments.periodicity_threshold,
    harmonics=arguments.harmonics,
    amplitude=arguments.amplitude,
)
write_wav(arguments.output, pcm, arguments.sample_rate)
if arguments.report:
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
