# Building the Alpine release image

The release builder creates a complete Alpine 3.24 and Plasma Mobile root filesystem for the SM-J701F `USERDATA` partition. It runs on a computer and does not contact the phone. The separate installer writes the resulting image only after its own device and data-loss checks.

Run `python3 tools/build-release.py` from the repository root. Docker, `gzip`, `blkid` and `e2fsck` are required. Add `--development` to include compilers, Git, Neovim and diagnostic tools. `--modules-dir PATH` adds locally built modules that match the installed kernel; the builder omits the Samsung firmware file copied from a phone. When the matching native-display modules and kernel-notes hash are present, the image enables the guarded native-display switch. Otherwise the desktop starts on the firmware framebuffer; Panfrost still provides GPU rendering. For a personal installation, `--wifi-firmware-dir PATH` supplies the three exact Broadcom files extracted from that handset, `--mfc-firmware-file FILE` supplies its video-decoder firmware, and `--umtprd-binary FILE` supplies an AArch64 uMTP-Responder executable for USB file transfer. These local additions mark the image non-redistributable in `release.json`: keep it in the ignored `build/` tree and do not upload it. A generic build has the USB MTP configuration but no responder executable, so MTP is unavailable until one is installed. The generic Alpine firmware package uses compressed files and a generic board profile, so Wi-Fi after a fresh generic installation is not yet guaranteed. A public release needs separate, licensed ways to supply the board firmware and MTP responder.

The builder verifies the pinned Alpine 3.24.0 minirootfs checksum and release signature, then resolves the requested AArch64 packages from Alpine 3.24 `main` and `community`. Package selection comes from `system/release/base-packages.txt`, `system/apps/core.txt`, and optionally `system/apps/optional-development.txt`. A pinned Alpine Docker image performs cross-architecture installation. The scripts in `system/release/` then add the phone's startup, OpenRC services, desktop settings, SD card mount and local account. Target package install scripts cannot run on the x86 build host; a one-time service rebuilds the machine-local caches before the first desktop login on the phone.

That first cache build can delay the initial desktop for several minutes on the phone's eMMC. Its progress and any errors are written to `/var/log/j701f-release-firstboot.log`; later boots skip it after success.

The outputs are in `build/release/`:

| File | Purpose |
| --- | --- |
| `userdata.ext4.gz` | Compressed ext4 payload for the recovery installer and FAT32 SD card |
| `userdata.ext4.gz.sha256` | Hash of that transport payload |
| `userdata.ext4.sha256` | Hash of the complete uncompressed partition image, for read-back |
| `release.json` | Device, partition length, UUID, base provenance, package requests and hashes |

The uncompressed image is exactly 23,314,432 sectors, the measured `USERDATA` size on this handset. Its ext4 UUID remains `4ce26b55-8a59-4fb7-aad4-919a5c2cefeb` and `/etc/j701f-system-version` remains `BURAK_ALPINE_0_1`; the existing BOOT handoff requires both. The builder checks the image size, UUID and filesystem with `e2fsck -fn`, and checks that the compressed file fits the FAT32 single-file limit. It leaves BOOT and RECOVERY untouched.

No saved Wi-Fi connection, SSH user key, SSH host key, password or phone-specific machine ID is copied into the release. The local `burak-alpine` account starts with an empty password and automatic graphical login; automatic screen locking is disabled until the owner sets a password. SSH permits public-key authentication for that account only; a key must be provisioned after installation. This image also follows the development phone's passwordless `sudo` policy, so physical access to the unlocked desktop grants administrator access. A fresh system may start offline until its owner configures Wi-Fi in Plasma. The release-specific Wi-Fi supervisor keeps NetworkManager running while offline so the first network can still be added from the graphical interface.

The build procedure is host-validated. A successful image build alone does not establish that a new installation boots or that TWRP/OrangeFox accepts a ZIP. Those claims require separate handset tests and are documented with the installer.
