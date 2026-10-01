import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.f0_diagnostics import summarize_f0_diagnostics  # noqa: E402

parser = argparse.ArgumentParser(description="Evaluate F0 and GAME boundary diagnostics")
parser.add_argument("manifest", type=Path)
parser.add_argument("dataset_root", type=Path)
parser.add_argument("f0_root", type=Path)
parser.add_argument("note_root", type=Path)
parser.add_argument("config", type=Path)
parser.add_argument("output", type=Path)
arguments = parser.parse_args()

summary = summarize_f0_diagnostics(
    arguments.manifest,
    arguments.dataset_root,
    arguments.f0_root,
    arguments.note_root,
    json.loads(arguments.config.read_text(encoding="utf-8")),
)
arguments.output.parent.mkdir(parents=True, exist_ok=True)
arguments.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(summary["selection"])
