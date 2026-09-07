#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

game_root="$root/data/models/game"
some_root="$root/data/models/some"
audio_root="$root/data/evaluation/vocadito/Audio"
result_root="$root/data/evaluation/vocadito-results"

printf '%s  %s\n' \
  3d3e1ac0a83234b2a163a3d43043455d15670765eaa25ef6285c399da1ccc576 \
  "$game_root/GAME-1.0-small.zip" | sha256sum -c -
printf '%s  %s\n' \
  8c5b3e531e2905b935e664e2f533921cd637243770fab5282413bdb5051ca60c \
  "$game_root/GAME-1.0-medium.zip" | sha256sum -c -
printf '%s  %s\n' \
  bc91b1afc3ae350bd70d36ec418c471baa65c94fbeeaa09d6e178cbcfca886ec \
  "$some_root/0119_continuous128_5spk.zip" | sha256sum -c -

unzip -q -n "$game_root/GAME-1.0-small.zip" -d "$game_root"
unzip -q -n "$game_root/GAME-1.0-medium.zip" -d "$game_root"
unzip -q -n "$some_root/0119_continuous128_5spk.zip" -d "$some_root"
bash scripts/prepare-candidate-build-context.sh

docker build -f infra/docker/Dockerfile.worker \
  -t vocal-score-studio-worker:latest .
docker build -f infra/experiments/game/Dockerfile \
  -t vocal-score-studio-game-eval:1.0.0 .
docker build -f infra/experiments/some/Dockerfile \
  -t vocal-score-studio-some-eval:1.0.0 .

mkdir -p "$result_root"
common_mounts=(
  --rm
  --user "$(id -u):$(id -g)"
  -e HOME=/tmp
  -v "$root:/workspace:ro"
  -v "$audio_root:/audio:ro"
  -v "$result_root:/results"
)
docker run "${common_mounts[@]}" -v "$game_root:/models:ro" \
  vocal-score-studio-game-eval:1.0.0 \
  /audio /results /models/GAME-1.0-small/model.pt \
  --variant game_1_0_small --batch-size 4
docker run "${common_mounts[@]}" -v "$game_root:/models:ro" \
  vocal-score-studio-game-eval:1.0.0 \
  /audio /results /models/GAME-1.0-medium/model.pt \
  --variant game_1_0_medium --batch-size 4
docker run "${common_mounts[@]}" -v "$some_root:/models:ro" \
  vocal-score-studio-some-eval:1.0.0 \
  /audio /results \
  /models/0119_continuous256_5spk/model_ckpt_steps_100000_simplified.ckpt

.venv/bin/python scripts/prepare-vocadito.py data/evaluation/vocadito
.venv/bin/python scripts/evaluate-transcription-manifest.py \
  evaluation/vocadito-manifest.json \
  --output evaluation/reports/vocadito-candidates.json
.venv/bin/python scripts/summarize-candidate-benchmark.py \
  evaluation/reports/vocadito-candidates.json \
  data/evaluation/vocadito-results \
  evaluation/reports/vocadito-candidate-summary.json
