#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export VSS_PYTORCH_INDEX_URL=${VSS_PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}
export VSS_PYTORCH_PACKAGE=${VSS_PYTORCH_PACKAGE:-torch==2.8.0+cu128}
export VSS_PYTORCH_EXPECT_CUDA=1

exec "$root/scripts/build-quality-worker.sh"
