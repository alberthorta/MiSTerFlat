#!/bin/bash
# Installs MiSTerLily with the one-file installer, then runs the real tty2oled updater twice, in a
# Debian container laid out like a fresh MiSTer. Checks that the updater leaves our files alone and
# does not install its own daemon. Needs Docker and network (downloads the tty2oled pictures).
#
#   bash tests/mister/run_updater_test.sh
#
# Known container-only noise: the second run cannot execute rsyncy.py (no exec bit on ext4; on the
# MiSTer's exFAT every file is executable), so the rsync update step fails there.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$ROOT/tools/make_mister_installer.py" >/dev/null || exit 1
docker run --rm -v "$ROOT/dist:/dist:ro" -v "$ROOT/tests/mister/updater_after_install.sh:/t.sh:ro" \
  debian:bookworm-slim bash -c '
    apt-get update -qq >/dev/null && apt-get install -y -qq python3 procps wget ca-certificates p7zip rsync >/dev/null 2>&1
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/cacert.pem
    bash /t.sh'
