#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
sources="$root/infra/experiments/sources"
model="$root/data/models/game/GAME-1.0-medium/model.pt"

bash "$root/scripts/prepare-candidate-build-context.sh"

verify_sha256() {
  local expected=$1
  local path=$2
  local actual
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  if [[ "$actual" != "$expected" ]]; then
    printf 'SHA-256 mismatch for %s\nexpected: %s\nactual:   %s\n' \
      "$path" "$expected" "$actual" >&2
    exit 1
  fi
}

if [[ ! -f "$model" ]]; then
  printf 'Missing GAME medium weight: %s\n' "$model" >&2
  printf 'Download GAME-1.0-medium and place model.pt at that path.\n' >&2
  exit 1
fi

verify_sha256 \
  41188c7b0f9f4baf0a7b9ad0621c20f643d8c90751b92221493f49e8aeef47d4 \
  "$sources/game-e66c31251605e334b1bf0f565252d4987a9065c0.tar.gz"
verify_sha256 \
  4c4651da5c071f81d7825ed58edc32b42f74e794152ff45d9b08432e882e8f91 \
  "$sources/torchcrepe-19e2ec3d494c0797a5ff2a11408ec5838fba6681.tar.gz"
verify_sha256 \
  e9904159fb0646e1a352b9d2bc74615547cfa3e32d45c7464d440ac142846d93 \
  "$model"

if ! docker image inspect vocal-score-studio-worker-basic:latest >/dev/null 2>&1; then
  if docker image inspect vocal-score-studio-worker:latest >/dev/null 2>&1 \
    && docker run --rm --entrypoint sh vocal-score-studio-worker:latest \
      -c 'test ! -d /opt/game'; then
    docker tag vocal-score-studio-worker:latest vocal-score-studio-worker-basic:latest
  else
    docker build \
      -f "$root/infra/docker/Dockerfile.worker" \
      -t vocal-score-studio-worker-basic:latest \
      "$root"
  fi
fi
DOCKER_BUILDKIT=0 docker build \
  -f "$root/infra/docker/Dockerfile.worker-quality" \
  -t vocal-score-studio-worker:latest \
  "$root"
