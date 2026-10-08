#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_NAME="${ENV_NAME:-jetarm-vla}"

cd "$PROJECT_ROOT"
: "${CONDA_SH:?Set CONDA_SH to the conda profile.d/conda.sh path}"
source "$CONDA_SH"
if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -y -n "$ENV_NAME" python=3.12
fi
conda activate "$ENV_NAME"
PYTHON_MINOR="$(python -c 'import sys; print(sys.version_info.minor)')"
if [ "$PYTHON_MINOR" -lt 12 ]; then
  conda deactivate
  conda install -y -n "$ENV_NAME" python=3.12
  conda activate "$ENV_NAME"
fi
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn pillow numpy requests pydantic

LEROBOT_DIR="$PROJECT_ROOT/third_party/lerobot"

if [ -d "$LEROBOT_DIR" ] && ! git -C "$LEROBOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  mv "$LEROBOT_DIR" "$LEROBOT_DIR.incomplete.$(date +%Y%m%d%H%M%S)"
fi

if [ ! -d "$LEROBOT_DIR" ]; then
  mkdir -p "$PROJECT_ROOT/third_party"
  for attempt in 1 2 3; do
    if git -c http.version=HTTP/1.1 clone --depth 1 https://github.com/huggingface/lerobot.git "$LEROBOT_DIR"; then
      break
    fi
    rm -rf "$LEROBOT_DIR"
    if [ "$attempt" = "3" ]; then
      echo "failed to clone LeRobot after 3 attempts" >&2
      exit 1
    fi
    sleep 5
  done
fi

cd "$LEROBOT_DIR"
python -m pip install -e ".[smolvla,dataset]"

python - <<'PY'
import importlib.util

for name in ["torch", "lerobot", "lerobot.datasets", "lerobot.policies.smolvla"]:
    if importlib.util.find_spec(name) is None:
        raise SystemExit(f"missing required module after install: {name}")

import torch

print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
PY
