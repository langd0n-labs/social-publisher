#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
IMAGE_NAME="${SOCIAL_PUBLISHER_IMAGE:-localhost/social-publisher:latest}"
DATA_DIR="${SOCIAL_PUBLISHER_DATA_DIR:-${PROJECT_ROOT}/content-workspace/social-exports}"
BWS_TOKEN_FILE="${BWS_TOKEN_FILE:-${HOME}/.config/bws-tokens/social-publisher.token}"
BWS_BIN="${BWS_BIN:-${HOME}/.local/bin/bws}"

if ! podman image exists "${IMAGE_NAME}"; then
  podman build -t "${IMAGE_NAME}" -f "${SCRIPT_DIR}/Containerfile" "${SCRIPT_DIR}"
fi

if [[ -z "${BWS_PROJECT_ID:-}" ]]; then
  echo "Set BWS_PROJECT_ID to your Bitwarden Secrets Manager project id" >&2
  exit 1
fi

if [[ ! -r "${BWS_TOKEN_FILE}" ]]; then
  echo "Missing Bitwarden Secrets Manager access token: ${BWS_TOKEN_FILE}" >&2
  exit 1
fi

export BWS_ACCESS_TOKEN="$(<"${BWS_TOKEN_FILE}")"
export SOCIAL_PUBLISHER_IMAGE="${IMAGE_NAME}"
export SOCIAL_PUBLISHER_DATA_DIR="${DATA_DIR}"
exec "${BWS_BIN}" run --shell /bin/bash -o none --project-id "${BWS_PROJECT_ID}" -- \
  "${SCRIPT_DIR}/run-social-publisher-container.sh" "$@"
