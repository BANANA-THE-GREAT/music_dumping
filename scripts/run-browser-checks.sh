#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
image=${PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.55.0-noble}
score_url=${SCORE_URL:-http://127.0.0.1:8888}

docker run --rm --network host \
  -v "${project_dir}:/workspace" \
  -w /workspace \
  -e "SCORE_URL=${score_url}" \
  "${image}" node scripts/check-score-editor.mjs

docker run --rm --network host \
  -v "${project_dir}:/workspace" \
  -w /workspace \
  -e "SCORE_URL=${score_url}" \
  "${image}" node scripts/check-transcription-ui.mjs
