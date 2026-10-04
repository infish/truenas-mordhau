#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 docker.io/infish1997/mordhau-server:latest [linux/amd64] [--no-push]" >&2
  exit 2
fi

image="$1"
platform="${2:-linux/amd64}"
no_push="${3:-}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

docker build --platform "$platform" -t "$image" "$script_dir/image"

if [[ "$no_push" != "--no-push" ]]; then
  docker push "$image"
fi

echo "Image ready: $image"

