#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
for tool in clang ld.lld; do
    command -v "$tool" >/dev/null || { echo 'Install: sudo pacman -S --needed clang lld linux-api-headers' >&2; exit 1; }
done
clang --target=aarch64-linux-gnu -fuse-ld=lld -Oz -Wall -Wextra -Werror \
    -ffreestanding -fno-builtin -fno-stack-protector -fno-pie -nostdlib -static \
    -Wl,--build-id=none -Wl,-e,_start -Wl,-s \
    tools/fb-heartbeat.c -o "${FB_HELPER_OUTPUT:-ramdisk/bin/fb-heartbeat}"
