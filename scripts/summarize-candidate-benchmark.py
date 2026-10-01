import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.candidate_report import summarize_candidates  # noqa: E402

parser = argparse.ArgumentParser(description="Summarize candidate transcription benchmarks")
parser.add_argument("report", type=Path)
parser.add_argument("runtime_root", type=Path)
parser.add_argument("output", type=Path)
arguments = parser.parse_args()

report = json.loads(arguments.report.read_text(encoding="utf-8"))
variants = ("game_1_0_small", "game_1_0_medium", "some_continuous256_5spk")
runtimes = {
    variant: json.loads(
        (arguments.runtime_root / f"runtime-{variant}.json").read_text(encoding="utf-8")
    )
    for variant in variants
}
summary = summarize_candidates(report, runtimes)
arguments.output.parent.mkdir(parents=True, exist_ok=True)
arguments.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
