import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.game_tuning import summarize_game_tuning  # noqa: E402

parser = argparse.ArgumentParser(description="Summarize a GAME tuning-only parameter sweep")
parser.add_argument("base_report", type=Path)
parser.add_argument("manifest", type=Path)
parser.add_argument("result_root", type=Path)
parser.add_argument("runtime_root", type=Path)
parser.add_argument("grid", type=Path)
parser.add_argument("output", type=Path)
arguments = parser.parse_args()

summary = summarize_game_tuning(
    json.loads(arguments.base_report.read_text(encoding="utf-8")),
    arguments.manifest,
    arguments.result_root,
    arguments.runtime_root,
    json.loads(arguments.grid.read_text(encoding="utf-8")),
)
arguments.output.parent.mkdir(parents=True, exist_ok=True)
arguments.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(summary["selection"]["winner"])
