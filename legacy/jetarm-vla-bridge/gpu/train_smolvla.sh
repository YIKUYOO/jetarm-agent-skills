#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_NAME="${ENV_NAME:-jetarm-vla}"
DATASET_REPO_ID="${DATASET_REPO_ID:-}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/outputs/smolvla_rgbd_smoke}"
STEPS="${STEPS:-100}"
BATCH_SIZE="${BATCH_SIZE:-1}"
POLICY_REPO_ID="${POLICY_REPO_ID:-your-account/jetarm_smolvla_rgbd_smoke}"
HF_LEROBOT_HOME="${HF_LEROBOT_HOME:-$PROJECT_ROOT/datasets/lerobot}"
HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"

if [ -z "$DATASET_REPO_ID" ]; then
  echo "DATASET_REPO_ID is required, e.g. export DATASET_REPO_ID=your-account/jetarm_rgbd_pick_place" >&2
  exit 2
fi

export HF_ENDPOINT
export HF_LEROBOT_HOME
: "${CONDA_SH:?Set CONDA_SH to the conda profile.d/conda.sh path}"
source "$CONDA_SH"
conda activate "$ENV_NAME"
cd "$PROJECT_ROOT/third_party/lerobot"

lerobot-train \
  --policy.type=smolvla \
  --policy.repo_id="$POLICY_REPO_ID" \
  --policy.load_vlm_weights=true \
  --policy.push_to_hub=false \
  --dataset.repo_id="$DATASET_REPO_ID" \
  --dataset.video_backend=pyav \
  --batch_size="$BATCH_SIZE" \
  --steps="$STEPS" \
  --output_dir="$OUTPUT_DIR" \
  --job_name=jetarm_smolvla_rgbd \
  --policy.device=cuda \
  --wandb.enable=false
