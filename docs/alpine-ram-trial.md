# Alpine 3.24.0 RAM compatibility trial

The selected Alpine AArch64 minirootfs passed a bounded chroot trial on the actual phone on 2026-10-07. It ran under the existing `3.18.140-SIMPLE-KERNEL_V1.0` recovery kernel. No BOOT, SYSTEM, DATA or other storage partition was mounted, formatted or written. Recovery's PID 1 and display/USB services stayed in control. All temporary trial mounts and files were removed afterward.

## Reproduce

Close other USB serial terminals and boot the working Linux recovery, then run from the project:

```sh
python3 tools/alpine-ram-test.py
```

The script verifies cached downloads, or downloads missing files from Alpine's official HTTPS sites. `--prepare-only` verifies the archive without opening the phone. `--device /dev/ttyACM0` can select the serial port explicitly.

It uploads the compressed archive in 24 KiB chunks, checking each chunk and then the complete archive. The upload is about 4 MB and reports progress. Extraction happens in a separate 64 MiB tmpfs below a private `/tmp` directory; `/dev` gets a small RAM filesystem with only standard character nodes, and `/proc` is mounted read-only. No block device is exposed inside the trial `/dev`. The chroot test has a 30-second timeout. This is a controlled development test, not a security sandbox for arbitrary root programs.

Cleanup unmounts proc, dev and the root before deleting scratch files. If an unmount fails, it reports the retained RAM path and does not recursively remove a mounted root. A USB disconnect can leave RAM files or mounts pending inspection; restarting recovery clears them. The tool saves available failure output and the scratch path for diagnosis.

## Pinned input and verification

User-selected source: [alpine-minirootfs-3.24.0-aarch64.tar.gz](https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/aarch64/alpine-minirootfs-3.24.0-aarch64.tar.gz).

- Archive size: 4,043,766 bytes.
- SHA-256: `4b8cd66a6688b2a87276c39843ed89c3a06d9534fc6a5823c586aff2696c1f2a`.
- Matches the official adjacent `.sha256` file; pinned in the tool so the moving `latest-stable` alias cannot silently change the input.
- Detached `.asc` release signature verified against Alpine's HTTPS-published [release public key](https://alpinelinux.org/keys/ncopa.asc).
- Signing fingerprint: `0482 D840 22F5 2DF1 C4E7 CD43 293A CD09 07D9 495A` (Natanael Copa).
- 515 archive entries; 8,691,202 total unpacked regular-file bytes.

The key was obtained from Alpine's official site and its fingerprint is pinned. This verification does not claim an independent offline key-identity audit. Alpine documents its [checksum and signature verification procedure](https://docs.alpinelinux.org/user-handbook/0.1a/Installing/medium.html). The script also checks archive paths, symlink ancestors, hardlinks, entry types and RAM size limits before phone extraction, and confirms the expected release and AArch64 executable headers.

## Hardware results and limits

`build/phone-alpine-ram-test.txt` records:

- Alpine release `3.24.0`.
- Dynamic BusyBox `1.37.0` running through the included musl linker.
- APK `3.0.6-r0` starting and listing the installed package database.
- Shell arithmetic, process pipelines with awk, and RAM file creation/read/hash/removal passing.
- `ALPINE_BASIC_USERSPACE_PASS`, exit 0 and `ALPINE_RAM_CLEANUP_OK`.
- Final mount table containing only the original virtual/RAM filesystems.

APK printed warnings that cached repository indexes were absent. Listing installed packages still succeeded. This trial did not fetch repository indexes, install packages, test internet connectivity, configure Wi-Fi or exercise every syscall and application that a complete Alpine system may need.

This establishes that the base userspace can run on this kernel. It does not establish full Alpine boot. The minirootfs has `/sbin/init` linked to BusyBox, but its supplied `/etc/inittab` calls `/sbin/openrc`, which is absent, and starts gettys on `tty1`–`tty6`, while this phone has no usable virtual console. Starting that init unchanged is not our next boot image.

The next separate milestone is to configure and test a phone-specific init and loader handoff with the existing touchscreen terminal and USB console. Keep the root in RAM for that trial before any DATA preparation. A future DATA installation remains destructive to its Android data and internal-storage files and needs a concrete installation/restore plan.

`build/alpine-provenance.json` records source, hashes, signature fingerprint and archive inventory totals. All 44 Python tests passed, including archive checks for path/link escapes, device entries, duplicates and foreign architecture. The recovery artifact is unchanged by this RAM trial tool.
