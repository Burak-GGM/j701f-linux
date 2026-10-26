#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
qemu=$(command -v qemu-aarch64 || command -v qemu-aarch64-static || true)
if [[ -z "$qemu" ]]; then
    echo 'SKIP: BusyBox execution checks; install qemu-user or qemu-user-static on Arch.'
    exit 0
fi
"$qemu" ramdisk/bin/busybox ash -n ramdisk/init
for script in ramdisk/bin/usb-debug ramdisk/bin/usb-shell ramdisk/bin/display-status ramdisk/bin/boot-manager; do
    "$qemu" ramdisk/bin/busybox ash -n "$script"
done
"$qemu" ramdisk/bin/busybox ash -c 'printf "AArch64 BusyBox shell executes successfully\n"'
applets=$("$qemu" ramdisk/bin/busybox --list)
while read -r name; do
    grep -qxF "$name" <<< "$applets" || { echo "Missing BusyBox applet: $name" >&2; exit 1; }
done < <(python3 -c 'import sys; sys.path.insert(0,"tools"); from recovery import APPLETS; print("\n".join(APPLETS))')
echo 'PASS: required applets and /init syntax. This is user-mode emulation, not a phone boot test.'
