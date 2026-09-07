import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.f0_diagnostics import evaluate_fixed_f0_boundary  # noqa: E402

parser = argparse.ArgumentParser(description="Evaluate fixed GAME plus F0 boundaries")
parser.add_argument("manifest", type=Path)
parser.add_argument("f0_root", type=Path)
parser.add_argument("note_root", type=Path)
parser.add_argument("runtime_root", type=Path)
parser.add_argument("config", type=Path)
parser.add_argument("output", type=Path)
arguments = parser.parse_args()

result = evaluate_fixed_f0_boundary(
    arguments.manifest,
    arguments.f0_root,
    arguments.note_root,
    json.loads(arguments.config.read_text(encoding="utf-8")),
    arguments.runtime_root,
)
arguments.output.parent.mkdir(parents=True, exist_ok=True)
arguments.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(result["quality_gate_checks"])
