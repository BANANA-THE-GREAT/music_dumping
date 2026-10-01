import argparse
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from vss_worker.vocadito import prepare_vocadito  # noqa: E402

parser = argparse.ArgumentParser(description="Prepare Vocadito for singer-disjoint evaluation")
parser.add_argument("dataset_root", type=Path)
parser.add_argument(
    "--output-root", type=Path, default=root / "data" / "evaluation" / "vocadito-prepared"
)
parser.add_argument(
    "--manifest", type=Path, default=root / "evaluation" / "vocadito-manifest.json"
)
parser.add_argument(
    "--prediction-root", type=Path, default=root / "data" / "evaluation" / "vocadito-results"
)
arguments = parser.parse_args()
manifest = prepare_vocadito(
    arguments.dataset_root,
    arguments.output_root,
    arguments.manifest,
    prediction_root=arguments.prediction_root,
)
counts = {
    split: sum(clip["split"] == split for clip in manifest["clips"])
    for split in ("tuning", "holdout")
}
print(f"Prepared {len(manifest['clips'])} clips: {counts}")
