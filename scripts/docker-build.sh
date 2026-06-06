#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-klm-tools}"
IMAGE_TAG="${IMAGE_TAG:-local}"
OUTPUT_TAR="${OUTPUT_TAR:-}"

docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .

if [[ -n "${OUTPUT_TAR}" ]]; then
  mkdir -p "$(dirname "${OUTPUT_TAR}")"
  docker save "${IMAGE_NAME}:${IMAGE_TAG}" -o "${OUTPUT_TAR}"
fi
