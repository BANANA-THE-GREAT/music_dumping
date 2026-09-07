#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
audio_root="$root/data/evaluation/vocadito/Audio"
result_root="$root/data/evaluation/vocadito-results"
game_model="$root/data/models/game/GAME-1.0-medium"
manifest="$root/evaluation/vocadito-manifest.json"

count_results() {
  local variant=$1
  find "$result_root/$variant" -maxdepth 1 -type f -name 'vocadito_*.json' 2>/dev/null \
    | wc -l
}

bash "$root/scripts/prepare-candidate-build-context.sh"
docker build -f "$root/infra/experiments/torchcrepe/Dockerfile" \
  -t vocal-score-studio-torchcrepe-eval:0.0.24 "$root"

if [[ "$(count_results game_medium_p015_b010_s8)" -ne 25 ]]; then
  printf 'GAME tuning result is incomplete; running the tuning sweep first.\n'
  bash "$root/scripts/run-game-tuning-sweep.sh"
fi

if [[ "$(count_results torchcrepe_full)" -ne 25 ]]; then
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$root:/workspace:ro" \
    -v "$audio_root:/audio:ro" \
    -v "$result_root:/results" \
    vocal-score-studio-torchcrepe-eval:0.0.24 \
    /audio /results /workspace/evaluation/vocadito-manifest.json \
    --split tuning --variant torchcrepe_full --batch-size 512
fi

"$root/.venv/bin/python" "$root/scripts/summarize-f0-diagnostics.py" \
  "$manifest" "$root/data/evaluation/vocadito" \
  "$result_root/torchcrepe_full" \
  "$result_root/game_medium_p015_b010_s8" \
  "$root/evaluation/f0-diagnostic-config.json" \
  "$root/evaluation/reports/vocadito-f0-diagnostics.json"

"$root/.venv/bin/python" - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("evaluation/reports/vocadito-f0-diagnostics.json").read_text())
if not report["selection"]["passed"]:
    raise SystemExit("F0 boundary rule failed tuning; holdout remains untouched")
PY

if [[ "$(count_results game_medium_p015_b010_s8_holdout)" -ne 15 ]]; then
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$root:/workspace:ro" \
    -v "$audio_root:/audio:ro" \
    -v "$result_root:/results" \
    -v "$game_model:/models:ro" \
    vocal-score-studio-game-eval:1.0.0 \
    /audio /results /models/model.pt \
    --variant game_medium_p015_b010_s8_holdout \
    --manifest /workspace/evaluation/vocadito-manifest.json \
    --split holdout --batch-size 4 \
    --presence-threshold 0.15 --boundary-threshold 0.10 \
    --d3pm-steps 8 --language-id 0
fi

if [[ "$(count_results torchcrepe_full_holdout)" -ne 15 ]]; then
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$root:/workspace:ro" \
    -v "$audio_root:/audio:ro" \
    -v "$result_root:/results" \
    vocal-score-studio-torchcrepe-eval:0.0.24 \
    /audio /results /workspace/evaluation/vocadito-manifest.json \
    --split holdout --variant torchcrepe_full_holdout --batch-size 512
fi

"$root/.venv/bin/python" "$root/scripts/evaluate-fixed-f0-boundary.py" \
  "$manifest" \
  "$result_root/torchcrepe_full_holdout" \
  "$result_root/game_medium_p015_b010_s8_holdout" \
  "$result_root" \
  "$root/evaluation/f0-holdout-config.json" \
  "$root/evaluation/reports/vocadito-f0-holdout.json"
