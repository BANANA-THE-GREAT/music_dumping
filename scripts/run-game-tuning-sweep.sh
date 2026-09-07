#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
audio_root="$root/data/evaluation/vocadito/Audio"
model_root="$root/data/models/game/GAME-1.0-medium"
result_root="$root/data/evaluation/vocadito-results"
report_root="$root/evaluation/reports"
image=vocal-score-studio-game-eval:1.0.0

common=(
  --rm
  --user "$(id -u):$(id -g)"
  -e HOME=/tmp
  -v "$root:/workspace:ro"
  -v "$audio_root:/audio:ro"
  -v "$model_root:/models:ro"
  -v "$result_root:/results"
)

run_variant() {
  local variant=$1
  local presence=$2
  local boundary=$3
  local steps=$4
  local count=0
  if [[ -d "$result_root/$variant" ]]; then
    count=$(find "$result_root/$variant" -maxdepth 1 -type f -name 'vocadito_*.json' | wc -l)
  fi
  if [[ -f "$result_root/runtime-$variant.json" && "$count" -eq 25 ]]; then
    printf 'Reusing complete tuning result for %s\n' "$variant"
    return
  fi
  printf 'Running %s (presence=%s boundary=%s steps=%s)\n' \
    "$variant" "$presence" "$boundary" "$steps"
  docker run "${common[@]}" "$image" \
    /audio /results /models/model.pt \
    --variant "$variant" \
    --manifest /workspace/evaluation/vocadito-manifest.json \
    --split tuning \
    --batch-size 4 \
    --presence-threshold "$presence" \
    --boundary-threshold "$boundary" \
    --d3pm-steps "$steps" \
    --language-id 0
}

run_variant game_medium_p010_b010_s8 0.10 0.10 8
run_variant game_medium_p010_b020_s8 0.10 0.20 8
run_variant game_medium_p015_b010_s8 0.15 0.10 8
run_variant game_medium_p015_b020_s8 0.15 0.20 8
run_variant game_medium_p020_b010_s8 0.20 0.10 8
run_variant game_medium_p020_b020_s8 0.20 0.20 8
run_variant game_medium_p015_b010_s16 0.15 0.10 16

docker run --rm --user "$(id -u):$(id -g)" \
  --entrypoint python \
  -v "$root:/workspace:ro" \
  -v "$result_root:/results:ro" \
  -v "$report_root:/reports" \
  vocal-score-studio-worker:latest \
  /workspace/scripts/summarize-game-tuning.py \
  /workspace/evaluation/reports/vocadito-candidates.json \
  /workspace/evaluation/vocadito-manifest.json \
  /results /results \
  /workspace/evaluation/game-tuning-grid.json \
  /reports/vocadito-game-tuning.json
