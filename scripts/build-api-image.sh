#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
dependency_hash=$(
  {
    sha256sum "$root/requirements/api.lock" | cut -d' ' -f1
    sha256sum "$root/infra/docker/Dockerfile.api-deps" | cut -d' ' -f1
  } \
  | sha256sum \
  | cut -c1-12
)
dependency_image="vocal-score-studio-api-deps:$dependency_hash"
output_image=${VSS_API_IMAGE:-vocal-score-studio-api:latest}

if ! docker image inspect "$dependency_image" >/dev/null 2>&1; then
  printf 'Building API dependency image %s (network may be required).\n' "$dependency_image"
  docker build \
    -f "$root/infra/docker/Dockerfile.api-deps" \
    -t "$dependency_image" \
    "$root"
else
  printf 'Reusing API dependency image %s.\n' "$dependency_image"
fi

docker tag "$dependency_image" vocal-score-studio-api-deps:local
if [[ ${VSS_DEPENDENCIES_ONLY:-0} == 1 ]]; then
  exit 0
fi

docker build \
  -f "$root/infra/docker/Dockerfile.api" \
  --build-arg "API_DEPENDENCY_IMAGE=$dependency_image" \
  -t "$output_image" \
  "$root"
