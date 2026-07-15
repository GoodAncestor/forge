#!/usr/bin/env bash
# Stand up forge on a TEMPORARY off-fleet node (cloud rental / loaner).
# No NFS, no lease. Syncs inputs from the NAS via jumpbox over Tailscale.
# Usage: bootstrap/ephemeral-node.sh <profile> <jumpbox-ssh> <remote-model-path> [remote-data-path]
set -euo pipefail
PROFILE="${1:?profile}" JUMP="${2:?user@jumpbox}" MODELS="${3:?remote model path}"
DATA="${4:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
(cd "$REPO/envs/$PROFILE" && uv sync)

sudo mkdir -p /mnt/models /mnt/models/datasets && sudo chown "$(id -u)" /mnt/models
rsync -a --partial --info=progress2 "$JUMP:$MODELS" /mnt/models/
[ -n "$DATA" ] && rsync -a --partial --info=progress2 "$JUMP:$DATA" /mnt/models/datasets/

cat <<'EOF'
Node ready. Run jobs with --off-fleet. BEFORE the node evaporates, push results:
  rsync -a runs/ "$JUMP:/mnt/HDD/models/forge-runs/$(hostname)/"
EOF
