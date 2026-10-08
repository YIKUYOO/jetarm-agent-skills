#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_NAME="${ENV_NAME:-jetarm-vla}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8008}"
VLA_MODE="${VLA_MODE:-mock}"
VLA_POLICY_PATH="${VLA_POLICY_PATH:-$PROJECT_ROOT/outputs/smolvla_rgbd_smoke/checkpoints/000100/pretrained_model}"
VLA_DEVICE="${VLA_DEVICE:-cuda}"
HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"

export HF_ENDPOINT
export VLA_DEVICE
export VLA_MODE
export VLA_POLICY_PATH

: "${CONDA_SH:?Set CONDA_SH to the conda profile.d/conda.sh path}"
source "$CONDA_SH"
conda activate "$ENV_NAME"
cd "$PROJECT_ROOT"
uvicorn gpu.server:app --host "$HOST" --port "$PORT"
