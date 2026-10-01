#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
pytorch_index_url=${VSS_PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}
pytorch_package=${VSS_PYTORCH_PACKAGE:-torch==2.14.0+cpu}
pytorch_expect_cuda=${VSS_PYTORCH_EXPECT_CUDA:-0}
output_image=${VSS_WORKER_IMAGE:-vocal-score-studio-worker:latest}

VSS_DEPENDENCIES_ONLY=1 "$root/scripts/build-api-image.sh"
api_dependency_image=$(docker image inspect vocal-score-studio-api-deps:local --format '{{.Id}}')
dependency_hash=$(
  {
    printf '%s\n%s\n%s\n%s\n' \
      "$api_dependency_image" \
      "$pytorch_index_url" \
      "$pytorch_package" \
      "$pytorch_expect_cuda"
    sha256sum "$root/requirements/worker.lock" | cut -d' ' -f1
    sha256sum "$root/infra/docker/Dockerfile.worker-deps" | cut -d' ' -f1
  } | sha256sum | cut -c1-12
)
dependency_image="vocal-score-studio-worker-deps:$dependency_hash"

if ! docker image inspect "$dependency_image" >/dev/null 2>&1; then
  printf 'Building Worker dependency image %s (network may be required).\n' "$dependency_image"
  docker build \
    -f "$root/infra/docker/Dockerfile.worker-deps" \
    --build-arg "API_DEPENDENCY_IMAGE=vocal-score-studio-api-deps:local" \
    --build-arg "PYTORCH_INDEX_URL=$pytorch_index_url" \
    --build-arg "PYTORCH_PACKAGE=$pytorch_package" \
    --build-arg "PYTORCH_EXPECT_CUDA=$pytorch_expect_cuda" \
    -t "$dependency_image" \
    "$root"
else
  printf 'Reusing Worker dependency image %s.\n' "$dependency_image"
fi

docker tag "$dependency_image" vocal-score-studio-worker-deps:local
if [[ ${VSS_DEPENDENCIES_ONLY:-0} == 1 ]]; then
  exit 0
fi

docker build \
  -f "$root/infra/docker/Dockerfile.worker" \
  --build-arg "WORKER_DEPENDENCY_IMAGE=$dependency_image" \
  -t "$output_image" \
  "$root"
