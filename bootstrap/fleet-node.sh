#!/usr/bin/env bash
# Prepare a fleet GPU node for forge runs. Idempotent. Usage:
#   bootstrap/fleet-node.sh <profile>   # e.g. cuda-blackwell
set -euo pipefail
PROFILE="${1:?usage: fleet-node.sh <profile>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
mountpoint -q /mnt/models || { echo "FATAL: /mnt/models NFS not mounted"; exit 4; }

(cd "$REPO/envs/$PROFILE" && uv sync)

# flash-attn needs the profile's torch present first; compile on the node.
(cd "$REPO/envs/$PROFILE" && uv pip install flash-attn --no-build-isolation) \
  || echo "WARN: flash-attn build failed — training falls back to SDPA/xformers"

# llama.cpp for GGUF export (pin a tag; update deliberately, not on every run)
if [ ! -d /opt/llama.cpp ]; then
  sudo git clone --depth 1 https://github.com/ggml-org/llama.cpp /opt/llama.cpp
  (cd /opt/llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build -j "$(nproc)")
fi
echo "OK: $PROFILE ready on $(hostname)"
