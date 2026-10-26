#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
package=tools/downloads/busybox-static-1.36.1-r31.apk
if [[ ! -f "$package" ]]; then
    command -v curl >/dev/null || { echo 'Install curl: sudo pacman -S --needed curl' >&2; exit 1; }
    mkdir -p tools/downloads
    trap 'rm -f -- "$package.part"' EXIT
    curl --fail --location --proto '=https' --tlsv1.2 --max-time 120 \
        https://dl-cdn.alpinelinux.org/alpine/v3.20/main/aarch64/busybox-static-1.36.1-r31.apk \
        -o "$package.part"
    # Python validates the pinned digest before installing the payload.
    mv -- "$package.part" "$package"
fi
exec python3 tools/recovery.py install-busybox
