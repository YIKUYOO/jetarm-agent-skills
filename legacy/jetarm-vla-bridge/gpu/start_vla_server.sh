#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SESSION="${SESSION:-jetarm_vla_server_v2}"
PORT="${PORT:-8008}"
CHECKPOINT_ROOT="${CHECKPOINT_ROOT:-$PROJECT_ROOT/outputs/smolvla_rgbd_v2/checkpoints}"
VLA_POLICY_PATH="${VLA_POLICY_PATH:-}"
REPLACE="${REPLACE:-false}"

if [ -z "$VLA_POLICY_PATH" ]; then
  VLA_POLICY_PATH="$(find "$CHECKPOINT_ROOT" -mindepth 2 -maxdepth 2 -type d -name pretrained_model | sort | tail -n 1)"
fi
if [ -z "$VLA_POLICY_PATH" ] || [ ! -f "$VLA_POLICY_PATH/model.safetensors" ]; then
  echo "could not find a valid VLA_POLICY_PATH under $CHECKPOINT_ROOT" >&2
  exit 2
fi

cd "$PROJECT_ROOT"
mkdir -p logs
if tmux has-session -t "$SESSION" 2>/dev/null; then
  if [ "$REPLACE" = "true" ]; then
    tmux kill-session -t "$SESSION"
  else
    echo "tmux session already exists: $SESSION" >&2
    exit 2
  fi
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
log_path="logs/${SESSION}_${timestamp}.log"
ln -sfn "$(basename "$log_path")" "logs/${SESSION}_latest.log"
tmux new-session -d -s "$SESSION" -c "$PROJECT_ROOT" \
  "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0} VLA_MODE=smolvla VLA_POLICY_PATH='$VLA_POLICY_PATH' PORT='$PORT' bash gpu/run_server.sh > '$log_path' 2>&1"
echo "started $SESSION port=$PORT policy=$VLA_POLICY_PATH log=$log_path"
