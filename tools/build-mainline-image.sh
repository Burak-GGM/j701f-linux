#!/bin/bash
# Written by Claude 2026-10-09. One command for the Alpine-handoff mainline image:
# DTB -> initramfs (helpers, handoff scripts, Wi-Fi firmware) -> FIT -> U-Boot
# loader -> Samsung container -> guard validation -> QEMU entry trace -> unit
# tests -> prepared BOOT update. Host only; nothing is written to the phone.
# Usage: tools/build-mainline-image.sh NAME kernel/dts/<board>.dts
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:?name}; DTS=${2:?dts}; EXTRA=${3:-}   # optional third argument: extra verifier flags, e.g. "--allow-audio --allow-sd"
KERNEL_PROFILE=${J701F_KERNEL_PROFILE:-panfrost}
case "$KERNEL_PROFILE" in panfrost|panfrost-7.2) ;; *) echo "Unsupported kernel profile: $KERNEL_PROFILE" >&2; exit 2;; esac
J=build/kernel/j701f-$N; H=build/kernel/handoff-$N; L=build/kernel/uboot-j701f-$N; SRC=build/kernel/j701f-wifi
mkdir -p "$J"; cp -r "$SRC/firmware" "$SRC/i2c-peek" "$SRC/reboot-recovery" "$J/"
# Claude 2026-10-10: J701F_RECOVERY_UI=path/to/recovery-ui (AArch64, static) builds the
# recovery variant (roadmap stage R): the UI, its scripts and the recovery mode of /init.
RECOVERY_ARGS=
if [ -n "${J701F_RECOVERY_UI:-}" ]; then
    [ -f "$J701F_RECOVERY_UI" ] || { echo "no such file: $J701F_RECOVERY_UI"; exit 1; }
    RECOVERY_ARGS="--extra recovery-main --helper $J701F_RECOVERY_UI --recovery-scripts recovery/scripts"
    # e2fsck and its libraries, copied from the phone's Alpine (see wiki: Graphical recovery)
    [ -d build/recovery-ui/e2fsck ] && RECOVERY_ARGS="$RECOVERY_ARGS --recovery-tools build/recovery-ui/e2fsck"
fi
q() { "$@" 2>&1 | tail -1 | cut -c1-76; [ "${PIPESTATUS[0]}" = 0 ] || exit 1; }
q python3 tools/build-j701f-dtb.py --kernel-profile "$KERNEL_PROFILE" --allow-emmc --allow-gpu --allow-wifi $EXTRA --source "$DTS" --output-dir "$J"
q python3 tools/build-mainline-initramfs.py --output-dir "$J" --helper "$J/i2c-peek" --helper "$J/reboot-recovery" \
    --extra alpine-handoff --extra alpine-usb-debug $RECOVERY_ARGS \
    --firmware "$J/firmware/brcmfmac43430-sdio.bin:brcm/brcmfmac43430-sdio.bin" \
    --firmware "$J/firmware/brcmfmac43430-sdio.clm_blob:brcm/brcmfmac43430-sdio.clm_blob" \
    --firmware "$J/firmware/brcmfmac43430-sdio.txt:brcm/brcmfmac43430-sdio.txt" \
    --firmware "$J/firmware/BCM43430A1.hcd:brcm/BCM43430A1.hcd" \
    --firmware "$J/firmware/BCM43430A1.hcd:brcm/BCM.hcd"
q python3 tools/build-mainline-fit.py --kernel-profile "$KERNEL_PROFILE" --kernel-compression gzip --diagnostic-dir "$J" --output-dir "$H"
q python3 tools/build-j701f-uboot.py --jobs 8 --embed-fit --fit-dir "$H" --artifact-dir "$L"
q python3 tools/package-embedded-mainline-diagnostic.py --fit-dir "$H" --loader-dir "$L"
q python3 tools/validate-embedded-ramboot-guards.py --fit-dir "$H" --loader-dir "$L"
python3 tools/trace-j701f-uboot.py --loader-dir "$L" --output-dir "build/kernel/diagnosis-$N" 2>&1 | grep -E "LINUX_ENTRY_BOUNDARY_REACHED" || { echo "QEMU trace did not reach Linux entry"; exit 1; }
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(OK|FAILED)"
q python3 tools/prepare-boot-update.py --handoff-dir "$H" --output-dir "build/kernel/boot-update-$N" --phone-dir "/home/burak-alpine/j701f/boot-update/$N"
grep -E "candidate_bytes" "build/kernel/boot-update-$N/manifest.json"
