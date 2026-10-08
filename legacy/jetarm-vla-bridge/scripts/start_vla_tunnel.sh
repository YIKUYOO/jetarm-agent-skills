#!/usr/bin/env bash
set -euo pipefail

GPU_USER="${GPU_USER:?Set GPU_USER}"
GPU_HOST="${GPU_HOST:?Set GPU_HOST}"
GPU_SSH_PORT="${GPU_SSH_PORT:-22}"
LOCAL_HOST="${LOCAL_HOST:-127.0.0.1}"
LOCAL_PORT="${LOCAL_PORT:-18008}"
REMOTE_HOST="${REMOTE_HOST:-127.0.0.1}"
REMOTE_PORT="${REMOTE_PORT:-8008}"
KEY_PATH="${KEY_PATH:?Set KEY_PATH to your existing SSH private-key file}"

if [ ! -r "$KEY_PATH" ]; then
  echo "missing SSH key: $KEY_PATH" >&2
  echo "generate it on Jetson and add the public key to the GPU user's authorized_keys first" >&2
  exit 2
fi

if pgrep -f "ssh .*${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT}.*${GPU_USER}@${GPU_HOST}" >/dev/null 2>&1; then
  echo "JetArm VLA tunnel already appears to be running on ${LOCAL_HOST}:${LOCAL_PORT}"
else
  ssh \
    -fnN \
    -i "$KEY_PATH" \
    -p "$GPU_SSH_PORT" \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=yes \
    -L "${LOCAL_HOST}:${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT}" \
    "${GPU_USER}@${GPU_HOST}"
  echo "started JetArm VLA tunnel ${LOCAL_HOST}:${LOCAL_PORT} -> ${GPU_USER}@${GPU_HOST}:${REMOTE_HOST}:${REMOTE_PORT}"
fi

python3 - <<PY
import json
import urllib.request

url = "http://${LOCAL_HOST}:${LOCAL_PORT}/health"
with urllib.request.urlopen(url, timeout=20) as response:
    body = response.read().decode("utf-8", "replace")
print(body)
payload = json.loads(body)
if payload.get("mode") not in {"smolvla-checkpoint", "hold-current-pose"}:
    raise SystemExit("unexpected VLA health mode: {}".format(payload.get("mode")))
PY
