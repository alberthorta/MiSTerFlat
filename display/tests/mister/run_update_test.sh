#!/bin/bash
# misterlily_update.sh against the real GitHub repository and picture server, in a container laid
# out like a fresh MiSTer (Docker + network).   bash tests/mister/run_update_test.sh
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$ROOT/tools/make_mister_installer.py" >/dev/null || exit 1
docker run --rm -v "$ROOT/dist:/dist:ro" -v "$ROOT/tests/mister/update_from_github.sh:/t.sh:ro" \
  debian:bookworm-slim bash -c '
    apt-get update -qq >/dev/null && apt-get install -y -qq python3 procps curl ca-certificates p7zip >/dev/null 2>&1
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/cacert.pem
    bash /t.sh'
