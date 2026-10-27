# Device test plan: release ZIP from OrangeFox, and the way back to rec8

Written by Claude 2026-10-27 at Codex's request. Nothing in this plan has been run; it is
carried out only after Codex's USERDATA reinstall test has finished and the `phone` lock is free.

## Which recovery

| Image | Source | Size | SHA-256 | Verdict |
| --- | --- | --- | --- | --- |
| OrangeFox R11.1 beta (2021-07-30) | `OrangeFox-j7velte-beta@R11.1.zip` from the official API (`api.orangefox.download`, release `6103cb9ddfa9fd3c4edb5762`, mirror `dl.orangefox.download`) | 32194576 | `5bbcb385a5b007a037713b169e69255534fbfb3527fa9ced63c61fe08b1eb68e` | **Use.** ZIP MD5 `ec7ddb2c…` and `recovery.img` MD5 `ddab4a15…` match the API. Byte-identical to `original/OrangeFox-recovery.img` and the hash pinned in `tools/recovery.py`: this is the recovery that ran on this phone at the start of the project |
| OrangeFox R11.0_1 stable (2020-11-04) | official API, release `5fa2585c18a4f5027b916617` | 32165904 | `c4256d131a7859a6e90db03b6079fa5510edd1e4a3c615686d890870919daf5f` | Spare. MD5s match the API; never run on this phone |
| TWRP "For J7 Nxt" (2018) | `tools/TWRP RECOVERY For J7 Nxt.tar`, origin unknown | 21198864 | `69d18ff3aafc3874df87b4821b535479bf3011634d5c37613238d8d34ca89026` | **Do not use.** twrp.me has no j7velte build (only j7elte, j7xelte and Qualcomm J7s); no provenance |

The downloads are in `build/third-party/recoveries/` (not tracked). OrangeFox does not publish
SHA-256 values; the MD5 values above come from its API.

Both OrangeFox images fit RECOVERY (`mmcblk0p11`, 77824 sectors = 39845888 bytes). Headers:
Android boot image v0, page 2048, kernel 18270584 bytes, a Samsung DT table of 358400 bytes,
command line `buildvariant=eng`, `SEANDROIDENFORCE` trailer. Their fstab mounts `/data` from
`by-name/USERDATA` (`length=-20480`), binds `/sdcard` onto `/data/media/0`, and mounts the SD
card at `/sdcard1`.

## Risks found in the image

- **OrangeFox can patch BOOT.** Settings → "Disable DM-Verity" / "Disable Forced Encryption"
  (`fox_reboot_dm_verity_check`, `fox_reboot_forced_encryption_check`) patch the boot image with
  `magiskboot` on reboot. Their defaults cannot be read from the image. Both must be **off**, and
  BOOT is hashed before and after.
- OrangeFox mounts USERDATA at start and keeps logs and a `Fox` folder on `/sdcard`, that is in
  `/data/media/0` of whatever is in USERDATA. Harmless before the install (it is erased), but it
  writes into the newly installed system if the phone goes back into OrangeFox afterwards.
- The ZIP needs **Volume Up pressed on the phone**: the owner must be at the phone for step 6.
- Its own copy of the previous RECOVERY slot is kept by `tools/install-recovery.sh` in
  `~/j701f/recovery-install/` — on USERDATA, which the test erases. The host copy (step 2) is
  the one that survives.

## Steps

All phone steps under `tools/coord.sh lock phone claude …`. Values written down in each step go
into `build/kernel/recovery-zip-test/`.

1. **Before.** From the running Alpine: SHA-256 of all of BOOT (`mmcblk0p10`) and RECOVERY
   (`mmcblk0p11`). Expected: BOOT as in `build/kernel/boot-slot.json`, RECOVERY
   `fe96fd9b…` (`build/kernel/recovery-slot.json`, rec8).
2. **Keep rec8 whole on the computer.** Copy the full 38 MiB RECOVERY slot to
   `build/backups/recovery-slot-rec8.img` and check it against `fe96fd9b…`.
3. **Install OrangeFox R11.1.** Copy the image to
   `build/kernel/boot-update-orangefox-r11.1/boot-mainline.img` and run
   `tools/install-recovery.sh orangefox-r11.1` (partition name and size guards, read-back, writes
   the previous slot back on mismatch). Correct `contents` in `recovery-slot.json` by hand: the
   script calls every image a "graphical recovery".
4. **Stage the release on the SD card.** `j701f-release/` (the four release files) and the ZIP
   beside it in the SD card's root, plus `rec8.img` (`build/kernel/boot-update-rec8/boot-mainline.img`,
   SHA-256 `d439dfae…`) for the way back. FAT32: every file below 4 GiB.
5. **Into OrangeFox** with `~/j701f/boot-swap/reboot-recovery.sh --execute`. In OrangeFox:
   Settings → check that DM-Verity and Forced Encryption patching are off; MTP off.
6. **Flash the ZIP** from `/sdcard1`. Expected: all checks pass, warning, **Volume Up by the owner**,
   write, full read-back, UUID, `DONE`. `install.status` on the SD card says `PASS`.
7. **Back to rec8, still in OrangeFox:** Install → Install Image → `rec8.img` → Recovery.
   (A recovery may write its own slot: it runs from RAM.)
8. **Reboot to system.** The new Alpine from the release must start. Then, as in step 1: BOOT
   must be unchanged; the first 15878160 bytes of RECOVERY must hash to `d439dfae…`.

## If something goes wrong

| Situation | Way back |
| --- | --- |
| OrangeFox install (step 3) fails its read-back | The script writes the previous slot back by itself |
| The ZIP refuses or is cancelled | Nothing was written; reboot to system |
| The ZIP fails while writing | USERDATA incomplete, BOOT and RECOVERY unchanged: run it again, or reinstall with Codex's host installer |
| Step 7 not possible | From any running Alpine with SSH: `tools/install-recovery.sh rec8`, or write `build/backups/recovery-slot-rec8.img` for an exact copy. The fresh release has a new SSH host key: `build/phone-ssh-known-hosts` must be updated first |
| No Linux and no recovery start | Download Mode (owner, buttons) and Odin with a recovery-only tar of `rec8.img`. `scripts/flash.sh` only accepts the stage-1 image; that tar has to be made and checked first |
| BOOT hash changed after step 8 | OrangeFox patched it: write the cam5 BOOT image back through rec8 (`tools/run-recovery-update.sh cam5`) |
