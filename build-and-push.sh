#!/usr/bin/env bash
# Builds the server and panel images and pushes them unless --no-push is given.
# Usage: ./build-and-push.sh [tag] [--no-push]
set -euo pipefail

tag="${1:-latest}"
no_push="${2:-}"
registry="${REGISTRY:-docker.io/infish1997}"
platform="${PLATFORM:-linux/amd64}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

docker build --platform "$platform" -t "${registry}/mordhau-server:${tag}" "$script_dir/server"
docker build --platform "$platform" -t "${registry}/mordhau-panel:${tag}" "$script_dir/panel"

if [[ "$no_push" != "--no-push" ]]; then
  docker push "${registry}/mordhau-server:${tag}"
  docker push "${registry}/mordhau-panel:${tag}"
fi

echo "Images ready: ${registry}/mordhau-server:${tag} ${registry}/mordhau-panel:${tag}"
