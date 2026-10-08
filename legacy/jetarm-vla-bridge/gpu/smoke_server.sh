#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_NAME="${ENV_NAME:-jetarm-vla}"
PORT="${PORT:-8008}"

cd "$PROJECT_ROOT"
: "${CONDA_SH:?Set CONDA_SH to the conda profile.d/conda.sh path}"
source "$CONDA_SH"
conda activate "$ENV_NAME"
python -m compileall -q gpu jetarm_vla_common

uvicorn gpu.server:app --host 127.0.0.1 --port "$PORT" > /tmp/jetarm_vla_uvicorn.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
sleep 3

python - <<'PY'
import os

import requests

port = os.environ.get("PORT", "8008")
base_url = "http://127.0.0.1:{}".format(port)
print(requests.get(base_url + "/health", timeout=3).json())
payload = {
    "language_instruction": "pick the red block",
    "observation.images.rgb_front": "",
    "observation.images.depth_front_vis": "",
    "observation.state": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0, 0, 0, 0, 0, 0, 1],
}
print(requests.post(base_url + "/select_action", json=payload, timeout=3).json())
PY

cat /tmp/jetarm_vla_uvicorn.log
