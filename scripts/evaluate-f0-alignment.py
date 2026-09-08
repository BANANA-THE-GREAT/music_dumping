#!/usr/bin/env python3
"""Estimate a bounded global delay between reference and predicted F0 tracks."""

import argparse
import json
from pathlib import Path

from vss_worker.f0_diagnostics import (
    estimate_global_delay,
    read_f0_prediction,
    read_reference_f0,
)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("reference", type=Path, help="reference F0 CSV: time_seconds,f0_hz")
parser.add_argument("prediction", type=Path, help="prediction JSON with F0 arrays")
parser.add_argument("--maximum-delay-ms", type=float, default=100)
parser.add_argument("--step-ms", type=float, default=10)
parser.add_argument("--periodicity-threshold", type=float, default=0.5)
parser.add_argument("--report", type=Path)
arguments = parser.parse_args()

reference = read_reference_f0(arguments.reference)
prediction = read_f0_prediction(arguments.prediction)
report = estimate_global_delay(
    *reference,
    prediction,
    maximum_delay_ms=arguments.maximum_delay_ms,
    step_ms=arguments.step_ms,
    periodicity_threshold=arguments.periodicity_threshold,
)
if arguments.report:
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
