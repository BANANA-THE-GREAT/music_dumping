#!/usr/bin/env bash
set -euo pipefail

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  printf 'Usage: %s\n' "$0"
  printf 'Install NVIDIA Container Toolkit, configure Docker, and restart Docker.\n'
  exit 0
fi

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

nvidia_smi=$(command -v nvidia-smi 2>/dev/null || true)
if [[ -z "$nvidia_smi" && -x /usr/lib/wsl/lib/nvidia-smi ]]; then
  nvidia_smi=/usr/lib/wsl/lib/nvidia-smi
fi
if [[ -z "$nvidia_smi" ]]; then
  printf 'nvidia-smi is unavailable; install or expose the host NVIDIA driver first.\n' >&2
  exit 1
fi
"$nvidia_smi" --query-gpu=name,driver_version --format=csv,noheader

if ! apt-cache show nvidia-container-toolkit >/dev/null 2>&1; then
  printf 'The nvidia-container-toolkit package is not configured in APT sources.\n' >&2
  printf 'Add the official NVIDIA Container Toolkit repository, then rerun this script.\n' >&2
  exit 1
fi

apt-get update
apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

printf '\nNVIDIA Container Toolkit configured. Verifying Docker runtime registration...\n'
docker info --format '{{json .Runtimes}}'
