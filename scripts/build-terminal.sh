#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
clang --target=aarch64-linux-gnu -fuse-ld=lld -Oz -Wall -Wextra -Werror -Wno-unused-function \
    -ffreestanding -fno-builtin -fno-stack-protector -fno-pie -nostdlib -static \
    -Wl,--build-id=none -Wl,-e,_start -Wl,-s \
    tools/ondevice-terminal.c -o "${TERMINAL_HELPER_OUTPUT:-ramdisk/bin/ondevice-terminal}"
