#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
audio_root="$root/data/evaluation/vocadito/Audio"
result_root="$root/data/evaluation/vocadito-results"
model_root="$root/data/models/game"
image=vocal-score-studio-worker:latest

common=(
  --rm
  --gpus all
  --user "$(id -u):$(id -g)"
  -e HOME=/tmp
  -e CUDA_VISIBLE_DEVICES=0
  -v "$root:/workspace:ro"
  -v "$audio_root:/audio:ro"
  -v "$result_root:/results"
)

docker run "${common[@]}" -v "$model_root:/models:ro" "$image" \
  python /workspace/scripts/experiments/run-game-benchmark.py \
  /audio /results /models/GAME-1.0-medium/model.pt \
  --variant game_medium_p015_b010_s8_gpu_holdout \
  --manifest /workspace/evaluation/vocadito-manifest.json \
  --split holdout --batch-size 4 --presence-threshold 0.15 \
  --boundary-threshold 0.10 --d3pm-steps 8 --language-id 0 --device cuda

docker run "${common[@]}" "$image" \
  python /workspace/scripts/experiments/run-torchcrepe-benchmark.py \
  /audio /results /workspace/evaluation/vocadito-manifest.json \
  --split holdout --variant torchcrepe_full_gpu_holdout \
  --batch-size 512 --device cuda

"$root/.venv/bin/python" "$root/scripts/compare-gpu-holdout.py" \
  "$root/evaluation/vocadito-manifest.json" \
  "$result_root/game_medium_p015_b010_s8_holdout" \
  "$result_root/game_medium_p015_b010_s8_gpu_holdout" \
  "$result_root/torchcrepe_full_holdout" \
  "$result_root/torchcrepe_full_gpu_holdout" \
  "$root/data/evaluation/vocadito/Annotations/F0" \
  "$root/evaluation/reports/gpu-holdout-comparison.json"
