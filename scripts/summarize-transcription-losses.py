import argparse
import json
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser(description="Summarize refinement and quantization diagnostics")
parser.add_argument("diagnostics_root", type=Path)
parser.add_argument("output", type=Path)
arguments = parser.parse_args()

actions: Counter[str] = Counter()
reasons: Counter[str] = Counter()
raw_notes = 0
refined_notes = 0
quantized_notes = 0
files = sorted(arguments.diagnostics_root.glob("*.json"))
for path in files:
    document = json.loads(path.read_text(encoding="utf-8"))
    raw_notes += len(document["raw_notes"])
    refined_notes += len(document["refined_notes"])
    quantized_notes += len(document["quantized_notes"])
    for decision in document["decisions"]:
        actions[decision["action"]] += 1
        reasons[decision["reason"]] += 1

summary = {
    "schema_version": "1.0",
    "clip_count": len(files),
    "note_counts": {
        "raw": raw_notes,
        "refined": refined_notes,
        "quantized": quantized_notes,
        "removed_or_merged_by_refinement": raw_notes - refined_notes,
        "removed_by_quantization_conflicts": refined_notes - quantized_notes,
    },
    "actions": dict(sorted(actions.items())),
    "reasons": dict(sorted(reasons.items())),
}
arguments.output.parent.mkdir(parents=True, exist_ok=True)
arguments.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
