#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
clang -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined \
    tests/fb_heartbeat_test.c -o build/test-fb-heartbeat
ASAN_OPTIONS=detect_leaks=0 ./build/test-fb-heartbeat build/display-preview.ppm
clang -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined \
    tests/fb_runtime_test.c -o build/test-fb-runtime
ASAN_OPTIONS=detect_leaks=0 ./build/test-fb-runtime
qemu=$(command -v qemu-aarch64 || command -v qemu-aarch64-static || true)
if [[ -n "$qemu" ]]; then
    # Only /dev/null: never open a host framebuffer in tests.
    result=0
    "$qemu" ramdisk/bin/fb-heartbeat /dev/null > build/display-helper-test.log 2>&1 || result=$?
    [[ "$result" == 1 ]] && grep -q 'Framebuffer query failed' build/display-helper-test.log
    echo 'PASS: static AArch64 display helper executes and rejects a non-framebuffer device'
fi
