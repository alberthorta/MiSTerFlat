#!/bin/bash
# Copy MiSTerManager to a MiSTer over SSH and install it there.
#   ./deploy.sh [host]     (default: $MISTER_HOST or root@mister)
set -eu
HOST="${1:-${MISTER_HOST:-root@mister}}"
DIR="$(cd "$(dirname "$0")" && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp -R "$DIR/mistermanager" "$STAGE/"
cp "$DIR/mister/S60mistermanager" "$DIR/mister/install.sh" "$DIR/mister/uninstall.sh" "$STAGE/"
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} +

ssh "$HOST" 'rm -rf /tmp/mistermanager-install && mkdir -p /tmp/mistermanager-install'
scp -q -r "$STAGE"/* "$HOST:/tmp/mistermanager-install/"
ssh "$HOST" 'bash /tmp/mistermanager-install/install.sh && rm -rf /tmp/mistermanager-install'
