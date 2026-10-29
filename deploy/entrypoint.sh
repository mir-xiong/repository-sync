#!/usr/bin/env bash
set -euo pipefail

mkdir -p /data /mirrors

if [[ "$(id -u)" -eq 0 ]]; then
  chown -R app:app /data /mirrors
  exec runuser --user app -- "$@"
fi

exec "$@"
