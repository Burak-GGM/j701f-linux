#!/usr/bin/env bash
# Default: offline plan. Explicit --execute enables only BOOT/USERDATA writes.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONPATH="$PWD/tools${PYTHONPATH:+:$PYTHONPATH}"
exec python3 tools/flash-system.py "$@"
