#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
clang -O1 -g -Wall -Wextra -Werror -Wno-unused-function -fsanitize=address,undefined \
    tests/terminal_test.c -o build/test-terminal
ASAN_OPTIONS=detect_leaks=0 ./build/test-terminal build/terminal-preview.ppm
qemu=$(command -v qemu-aarch64 || command -v qemu-aarch64-static || true)
if [[ -n "$qemu" ]]; then
    "$qemu" "${TERMINAL_HELPER_OUTPUT:-ramdisk/bin/ondevice-terminal}" --pty-test > build/terminal-pty-test.log 2>&1
    grep -q 'PTY-THREE-SESSIONS-OK' build/terminal-pty-test.log
    echo 'PASS: static AArch64 terminal runs three independent shells on real PTYs'
fi
