#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${SOCIAL_PUBLISHER_IMAGE:-localhost/thought-leadership-social:latest}"
DATA_DIR="${SOCIAL_PUBLISHER_DATA_DIR:-$(dirname "${SCRIPT_DIR}")/content-workspace/social-exports}"

exec podman run --rm \
  --env-file "${HOME}/.config/social-publisher/social-publisher.env" \
  -e BUFFER_API_KEY="${BUFFER_API_KEY}" \
  -e BSKY_APP_PASSWORD="${BSKY_APP_PASSWORD}" \
  -e MASTODON_ACCESS_TOKEN="${MASTODON_ACCESS_TOKEN}" \
  -e SOCIAL_SCHEDULE_CSV=/data/social-schedule.csv \
  -e SOCIAL_STATE_FILE=/data/social-publisher-state.json \
  -v "${DATA_DIR}:/data:Z" \
  "${IMAGE_NAME}" "$@"
