#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
sources="$root/infra/experiments/sources"
game_commit=e66c31251605e334b1bf0f565252d4987a9065c0
some_commit=dcfd40f9bfaa7c9649aae01a2795af73946ec5e7
torchcrepe_commit=19e2ec3d494c0797a5ff2a11408ec5838fba6681

mkdir -p "$sources"
cp /etc/ssl/certs/ca-certificates.crt "$sources/ca-certificates.crt"

archive_repo() {
  local name=$1
  local url=$2
  local commit=$3
  local checkout
  if [[ -f "$sources/$name-$commit.tar.gz" ]]; then
    return
  fi
  checkout=$(mktemp -d "/tmp/vss-$name-source.XXXXXX")
  git clone --filter=blob:none "$url" "$checkout"
  git -C "$checkout" checkout "$commit"
  test "$(git -C "$checkout" rev-parse HEAD)" = "$commit"
  git -C "$checkout" archive \
    --format=tar.gz \
    --prefix="$name-$commit/" \
    -o "$sources/$name-$commit.tar.gz" \
    HEAD
}

archive_repo game https://github.com/openvpi/GAME.git "$game_commit"
archive_repo some https://github.com/openvpi/SOME.git "$some_commit"
archive_repo torchcrepe https://github.com/maxrmorrison/torchcrepe.git "$torchcrepe_commit"

printf 'Prepared candidate build context in %s\n' "$sources"
