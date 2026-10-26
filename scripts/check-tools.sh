#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
failed=0
for tool in python3 make bash clang ld.lld; do
    if command -v "$tool" >/dev/null; then printf 'OK: %s\n' "$tool";
    else printf 'MISSING: %s\n' "$tool"; failed=1; fi
done
if command -v python3 >/dev/null; then
    python3 -c 'import gzip, lzma, tarfile, hashlib, zlib; import sys; assert sys.version_info >= (3, 10)' || failed=1
fi
for tool in curl qemu-aarch64 qemu-aarch64-static adb readelf cpio; do
    if command -v "$tool" >/dev/null; then printf 'Available: %s\n' "$tool"; fi
done
[[ -x tools/odin4 ]] && echo 'Available: tools/odin4 (not invoked during build)'
if (( failed )); then
    echo 'Arch build tools: sudo pacman -S --needed python make bash curl clang lld linux-api-headers' >&2
    exit 1
fi
