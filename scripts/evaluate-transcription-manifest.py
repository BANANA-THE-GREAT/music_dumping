import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.benchmark import evaluate_manifest  # noqa: E402

parser = argparse.ArgumentParser(description="Evaluate all transcription variants in a manifest")
parser.add_argument("manifest", type=Path)
parser.add_argument("--output", type=Path)
arguments = parser.parse_args()
report = json.dumps(evaluate_manifest(arguments.manifest), indent=2)
if arguments.output:
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(report + "\n", encoding="utf-8")
else:
    print(report)
